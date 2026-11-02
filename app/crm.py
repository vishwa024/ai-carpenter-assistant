"""CRM Layer for AI Master Carpenter Assistant.

Manages customer records, Ahmedabad locality tracking, lead attribution,
search, filtering, sorting, duplicate prevention, and CSV export.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.database import db

logger = logging.getLogger("carpenter.crm")

# Standardized Ahmedabad Localities
AHMEDABAD_LOCALITIES = [
    "Bopal", "South Bopal", "Satellite", "Vastrapur", "Thaltej",
    "Bodakdev", "Prahlad Nagar", "Navrangpura", "Nehrunagar", "Gota", "Chandkheda",
    "Ranip", "Ghatlodia", "Naranpura", "Sabarmati", "Motera",
    "Memnagar", "Ambawadi", "Ellisbridge", "Vejalpur", "Jodhpur",
    "Shilaj", "Shela", "Science City", "Nikol", "Naroda", "Odhav",
    "Narol", "Vatva", "Maninagar", "Paldi", "Adajan", "Vesu", "Varachha"
]

# Standard Lead Sources
LEAD_SOURCES = [
    "WhatsApp", "Instagram", "Facebook", "Referral", "Existing customer", "Website", "Other"
]

# Standard Lead Pipeline Stages (matching 14-stage conversation engine)
LEAD_STAGES = [
    "NEW_ENQUIRY", "GREETING", "REQUIREMENT_COLLECTION", "PROJECT_DISCOVERY",
    "BUDGET_DISCUSSION", "ESTIMATION", "VISIT_REQUESTED", "VISIT_CONFIRMED",
    "QUOTATION_PENDING", "QUOTATION_SENT", "NEGOTIATION", "FOLLOW_UP",
    "JOB_WON", "JOB_LOST", "HUMAN_HANDOVER"
]


def sanitize_phone(phone: str) -> str:
    """Normalize phone number to digits only (E.164 without leading plus)."""
    clean = re.sub(r"[^\d]", "", str(phone or ""))
    # If starting with 00, trim
    if clean.startswith("00"):
        clean = clean[2:]
    return clean


def detect_ahmedabad_locality(text: str) -> Optional[str]:
    """Detect prominent Ahmedabad locality from text."""
    if not text:
        return None
    text_lower = text.lower()
    for loc in AHMEDABAD_LOCALITIES:
        if loc.lower() in text_lower:
            return loc
    # Check Gujarati/Hindi variants
    geo_map = {
        "બોપલ": "Bopal", "નહેરુનગર": "Nehrunagar", "સેટેલાઇટ": "Satellite",
        "વસ્ત્રાપુર": "Vastrapur", "થલતેજ": "Thaltej", "બોડકદેવ": "Bodakdev",
        "ગોટા": "Gota", "ચાંદખેડા": "Chandkheda", "રાણીપ": "Ranip",
        "બોપલ": "Bopal", "नेहरूनगर": "Nehrunagar", "सैटेलाइट": "Satellite",
        "वस्त्रापुर": "Vastrapur", "थालतेज": "Thaltej", "बोडकदेव": "Bodakdev",
        "गोता": "Gota", "चांदखेड़ा": "Chandkheda", "रानीप": "Ranip",
        "अहमदाबाद": "Ahmedabad Central", "અમદાવાદ": "Ahmedabad Central"
    }
    for kw, loc_name in geo_map.items():
        if kw in text_lower:
            return loc_name
    return None


class CRMManager:
    """Enterprise-grade CRM for Single Workshop Operations."""

    def __init__(self) -> None:
        self.db = db

    def get_or_create_customer(
        self,
        phone: str,
        name: Optional[str] = None,
        language: str = "en",
        lead_source: str = "WhatsApp",
    ) -> Dict[str, Any]:
        """Get existing customer or create a new one with duplicate prevention."""
        clean_phone = sanitize_phone(phone)
        if not clean_phone:
            raise ValueError("Phone number is required")

        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone = ?", (clean_phone,))
        row = cur.fetchone()

        now = time.time()
        invalid_names = {
            "others", "other", "customer", "client", "user", "admin", "contact",
            "unknown", "test", "demo", "none", "null", "false", "true", "undefined"
        }
        valid_name = (name or "").strip()
        if valid_name.lower() in invalid_names or valid_name.lower().startswith("client"):
            valid_name = None

        if row:
            customer = dict(row)
            # Update name if previously empty and newly provided
            updates = []
            params = []
            if valid_name and (not customer.get("name") or customer.get("name").startswith("Client")):
                updates.append("name = ?")
                params.append(valid_name)
            if language and customer.get("language") != language:
                updates.append("language = ?")
                params.append(language)

            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(clean_phone)
                with conn:
                    conn.execute(
                        f"UPDATE customers SET {', '.join(updates)} WHERE phone = ?",
                        tuple(params),
                    )
                cur.execute("SELECT * FROM customers WHERE phone = ?", (clean_phone,))
                customer = dict(cur.fetchone())
            return customer

        # Create new customer record
        display_name = valid_name or f"Client {clean_phone[-4:]}"
        source = lead_source if lead_source in LEAD_SOURCES else "WhatsApp"
        with conn:
            conn.execute(
                """
                INSERT INTO customers (
                    phone, name, language, lead_source, lead_status,
                    human_handover, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (clean_phone, display_name, language, source, "NEW_ENQUIRY", 0, now, now),
            )
        cur.execute("SELECT * FROM customers WHERE phone = ?", (clean_phone,))
        return dict(cur.fetchone())

    def update_customer(self, phone: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
        """Update customer fields safely."""
        clean_phone = sanitize_phone(phone)
        allowed_fields = {
            "name", "language", "locality", "lead_source", "lead_status",
            "budget", "human_handover", "project_type", "dimensions",
            "preferred_materials", "consultation_mode", "follow_up_date", "notes"
        }

        updates = []
        params = []
        for key, val in kwargs.items():
            if key in allowed_fields:
                updates.append(f"{key} = ?")
                if key == "preferred_materials" and isinstance(val, (list, set)):
                    val = json.dumps(list(val))
                params.append(val)

        if not updates:
            return self.get_customer(clean_phone)

        updates.append("updated_at = ?")
        params.append(time.time())
        params.append(clean_phone)

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                f"UPDATE customers SET {', '.join(updates)} WHERE phone = ?",
                tuple(params),
            )
        return self.get_customer(clean_phone)

    def get_customer(self, phone: str) -> Optional[Dict[str, Any]]:
        """Fetch customer by phone."""
        clean_phone = sanitize_phone(phone)
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM customers WHERE phone = ?", (clean_phone,))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("preferred_materials"):
            try:
                res["preferred_materials"] = json.loads(res["preferred_materials"])
            except Exception:
                res["preferred_materials"] = []
        return res

    def list_customers(
        self,
        query: Optional[str] = None,
        locality: Optional[str] = None,
        lead_status: Optional[str] = None,
        lead_source: Optional[str] = None,
        sort_by: str = "updated_at",
        ascending: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Search, filter, and sort customers."""
        conn = self.db.get_connection()
        cur = conn.cursor()

        sql = "SELECT * FROM customers WHERE 1=1"
        params: List[Any] = []

        if query:
            q_clean = f"%{query.strip()}%"
            sql += " AND (name LIKE ? OR phone LIKE ? OR project_type LIKE ? OR notes LIKE ?)"
            params.extend([q_clean, q_clean, q_clean, q_clean])

        if locality:
            sql += " AND locality = ?"
            params.append(locality)

        if lead_status:
            sql += " AND lead_status = ?"
            params.append(lead_status)

        if lead_source:
            sql += " AND lead_source = ?"
            params.append(lead_source)

        allowed_sort = {"created_at", "updated_at", "name", "budget", "lead_status", "locality"}
        sort_col = sort_by if sort_by in allowed_sort else "updated_at"
        order = "ASC" if ascending else "DESC"

        sql += f" ORDER BY {sort_col} {order} LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        result = []
        for r in rows:
            c = dict(r)
            if c.get("preferred_materials"):
                try:
                    c["preferred_materials"] = json.loads(c["preferred_materials"])
                except Exception:
                    c["preferred_materials"] = []
            result.append(c)
        return result

    def get_conversation_history(self, phone: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch conversation turns for a customer."""
        clean_phone = sanitize_phone(phone)
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT role, text, media_json, stage, source, latency_ms, timestamp
            FROM conversations
            WHERE phone = ?
            ORDER BY timestamp ASC
            LIMIT ?
            """,
            (clean_phone, limit),
        )
        history = []
        for row in cur.fetchall():
            turn = dict(row)
            if turn.get("media_json"):
                try:
                    turn["media"] = json.loads(turn["media_json"])
                except Exception:
                    pass
            history.append(turn)
        return history

    def append_message(
        self,
        phone: str,
        role: str,
        text: str,
        media_info: Optional[Dict[str, Any]] = None,
        stage: Optional[str] = None,
        source: Optional[str] = None,
        latency_ms: int = 0,
        message_id: Optional[str] = None,
    ) -> None:
        """Append message turn to database."""
        clean_phone = sanitize_phone(phone)
        conn = self.db.get_connection()
        now = time.time()
        media_str = json.dumps(media_info) if media_info else None
        with conn:
            conn.execute(
                """
                INSERT INTO conversations (
                    phone, message_id, role, text, media_json, stage, source, latency_ms, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (clean_phone, message_id, role, text, media_str, stage, source, latency_ms, now),
            )
            conn.execute(
                "UPDATE customers SET updated_at = ? WHERE phone = ?",
                (now, clean_phone),
            )

    def set_human_handover(self, phone: str, enabled: bool) -> bool:
        """Enable or disable human handover mode."""
        clean_phone = sanitize_phone(phone)
        conn = self.db.get_connection()
        with conn:
            conn.execute(
                "UPDATE customers SET human_handover = ?, updated_at = ? WHERE phone = ?",
                (1 if enabled else 0, time.time(), clean_phone),
            )
        return True

    def toggle_human_handover(self, phone: str, enabled: bool) -> bool:
        """Alias for set_human_handover."""
        return self.set_human_handover(phone, enabled)

    def export_csv(self) -> str:
        """Export customer database as formatted CSV."""
        customers = self.list_customers(limit=10000)
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "Customer ID",
            "Name",
            "WhatsApp Number",
            "Language",
            "Ahmedabad Locality",
            "Lead Source",
            "Pipeline Stage",
            "Project Type",
            "Dimensions",
            "Budget (INR)",
            "Follow-up Date",
            "Human Handover",
            "Created Date",
            "Last Active",
            "Notes"
        ])

        for c in customers:
            created_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(c["created_at"]))
            updated_dt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(c["updated_at"]))
            writer.writerow([
                c["id"],
                c["name"] or "",
                f"+{c['phone']}",
                c["language"],
                c["locality"] or "Unspecified",
                c["lead_source"] or "WhatsApp",
                c["lead_status"] or "NEW_ENQUIRY",
                c["project_type"] or "",
                c["dimensions"] or "",
                c["budget"] or "",
                c["follow_up_date"] or "",
                "YES" if c.get("human_handover") else "NO",
                created_dt,
                updated_dt,
                c["notes"] or ""
            ])

        return output.getvalue()


# Global CRM Manager singleton
crm = CRMManager()
