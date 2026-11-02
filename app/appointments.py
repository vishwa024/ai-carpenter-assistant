"""Appointment & Site Visit Scheduling Engine for AI Master Carpenter Assistant.

Manages:
- Smart 2-slot scheduling (Saturday 11:30 AM / Sunday 4:00 PM)
- Multilingual invitation and confirmation messages (en, gu, hi)
- Full address and locality capture with validation
- Conflict checking and double-booking prevention
- SQLite database persistence in appointments table
"""
from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.database import db
from app.crm import sanitize_phone, detect_ahmedabad_locality

logger = logging.getLogger("carpenter.appointments")

# Standard workshop measurement slots
DEFAULT_SATURDAY_SLOT = "Saturday at 11:30 AM"
DEFAULT_SUNDAY_SLOT = "Sunday at 4:00 PM"


def get_smart_visit_slots(lang: str = "en") -> Dict[str, str]:
    """Return upcoming weekend measurement slots localized."""
    now = datetime.datetime.now()
    # Calculate days until Saturday (weekday 5) and Sunday (weekday 6)
    days_to_sat = (5 - now.weekday()) % 7
    if days_to_sat == 0 and now.hour >= 12:
        days_to_sat = 7
    days_to_sun = (6 - now.weekday()) % 7
    if days_to_sun == 0 and now.hour >= 16:
        days_to_sun = 7

    sat_date = now + datetime.timedelta(days=days_to_sat)
    sun_date = now + datetime.timedelta(days=days_to_sun)

    if lang == "gu":
        slot_a = f"આ શનિવારે સવારે 11:30 વાગ્યે ({sat_date.strftime('%d %b')})"
        slot_b = f"આ રવિવારે સાંજે 4:00 વાગ્યે ({sun_date.strftime('%d %b')})"
        prompt = f"સાઇટ પર ચોક્કસ માપ લેવા માટે, શું અમે *{slot_a}* કે *{slot_b}* 15 મિનિટની ફ્રી માપણી વિઝિટ રાખી શકીએ? 📐🪵"
    elif lang == "hi":
        slot_a = f"इस शनिवार सुबह 11:30 बजे ({sat_date.strftime('%d %b')})"
        slot_b = f"इस रविवार शाम 4:00 बजे ({sun_date.strftime('%d %b')})"
        prompt = f"दीवार का सही नाप लेने के लिए क्या हम *{slot_a}* या *{slot_b}* 15 मिनट की फ्री नाप विज़िट रख लें? 📐🪵"
    else:
        slot_a = f"this Saturday at 11:30 AM ({sat_date.strftime('%d %b')})"
        slot_b = f"this Sunday at 4:00 PM ({sun_date.strftime('%d %b')})"
        prompt = f"To verify exact site measurements, shall we book a free 15-minute measurement visit *{slot_a}* or *{slot_b}*? 📐🪵"

    return {
        "slot_a": slot_a,
        "slot_b": slot_b,
        "prompt": prompt,
    }


class AppointmentEngine:
    """Manages carpenter site visit bookings, schedule validation, and persistence."""

    def __init__(self) -> None:
        self.db = db

    def check_availability(self, slot_time: str) -> bool:
        """Check if a measurement slot has reached maximum concurrent capacity (max 2 visits per slot)."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM appointments WHERE slot_time = ? AND status = 'confirmed'",
            (slot_time,),
        )
        count = cur.fetchone()[0]
        return count < 2

    def create_or_request_visit(
        self,
        phone: str,
        slot_time: str,
        address: Optional[str] = None,
        project_scope: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record or update a requested site visit in the database."""
        clean_phone = sanitize_phone(phone)
        locality = detect_ahmedabad_locality(address or "")
        now = time.time()
        conn = self.db.get_connection()

        # Check existing appointment
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM appointments WHERE phone = ? AND status IN ('requested', 'confirmed')",
            (clean_phone,),
        )
        row = cur.fetchone()

        status = "confirmed" if address and len(address.strip()) >= 8 else "requested"

        with conn:
            if row:
                apt_id = row[0]
                conn.execute(
                    """
                    UPDATE appointments
                    SET slot_time = ?, address = COALESCE(?, address), locality = COALESCE(?, locality),
                        project_scope = COALESCE(?, project_scope), notes = COALESCE(?, notes),
                        status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (slot_time, address, locality, project_scope, notes, status, now, apt_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO appointments (
                        phone, status, slot_time, address, locality,
                        project_scope, notes, approved_by_carpenter, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (clean_phone, status, slot_time, address, locality, project_scope, notes, now, now),
                )
                apt_id = cur.lastrowid

        return self.get_appointment_by_id(apt_id) or {}

    def confirm_visit(
        self,
        phone: str,
        address: str,
        slot_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Confirm a visit once customer provides their physical address."""
        clean_phone = sanitize_phone(phone)
        locality = detect_ahmedabad_locality(address)
        now = time.time()
        conn = self.db.get_connection()

        with conn:
            if slot_time:
                conn.execute(
                    """
                    UPDATE appointments
                    SET status = 'confirmed', address = ?, locality = ?, slot_time = ?, updated_at = ?
                    WHERE phone = ? AND status IN ('requested', 'confirmed')
                    """,
                    (address, locality, slot_time, now, clean_phone),
                )
            else:
                conn.execute(
                    """
                    UPDATE appointments
                    SET status = 'confirmed', address = ?, locality = ?, updated_at = ?
                    WHERE phone = ? AND status IN ('requested', 'confirmed')
                    """,
                    (address, locality, now, clean_phone),
                )

        return self.get_appointment_for_customer(clean_phone) or {}

    def get_appointment_by_id(self, appointment_id: int) -> Optional[Dict[str, Any]]:
        """Fetch appointment record by primary ID."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_appointment_for_customer(self, phone: str) -> Optional[Dict[str, Any]]:
        """Fetch active appointment for customer phone."""
        clean_phone = sanitize_phone(phone)
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT * FROM appointments
            WHERE phone = ?
            ORDER BY updated_at DESC LIMIT 1
            """,
            (clean_phone,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_appointments(
        self,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List workshop appointments, optionally filtered by status."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT * FROM appointments WHERE status = ? ORDER BY slot_time ASC LIMIT ?",
                (status, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM appointments ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]

    def reschedule_visit(self, phone: str, new_slot: str) -> bool:
        """Reschedule existing appointment to a new slot."""
        clean_phone = sanitize_phone(phone)
        now = time.time()
        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                """
                UPDATE appointments
                SET slot_time = ?, status = 'rescheduled', updated_at = ?
                WHERE phone = ? AND status IN ('requested', 'confirmed', 'rescheduled')
                """,
                (new_slot, now, clean_phone),
            )
            return cur.rowcount > 0

    def cancel_visit(self, phone: str, reason: str = "") -> bool:
        """Cancel a visit and log cancellation reason."""
        clean_phone = sanitize_phone(phone)
        now = time.time()
        conn = self.db.get_connection()
        with conn:
            cur = conn.execute(
                """
                UPDATE appointments
                SET status = 'cancelled', notes = COALESCE(notes || ' | Cancelled: ' || ?, ?), updated_at = ?
                WHERE phone = ? AND status IN ('requested', 'confirmed', 'rescheduled')
                """,
                (reason, f"Cancelled: {reason}", now, clean_phone),
            )
            return cur.rowcount > 0


# Global singleton
appointment_engine = AppointmentEngine()
