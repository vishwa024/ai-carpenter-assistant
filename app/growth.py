"""Follow-Up & Business Growth Engine for AI Master Carpenter Assistant.

Manages:
- Automated follow-up rule evaluation (2-hour, 24-hour, 48-hour nurture nudges)
- Post-installation satisfaction check and Google/WhatsApp review requests
- Workshop business growth analytics:
  * Conversion rate (Won vs Lost vs Pipeline)
  * Revenue generated and estimated pipeline value
  * Top Ahmedabad localities and furniture demand breakdown
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from app.database import db
from app.crm import crm

logger = logging.getLogger("carpenter.growth")


class GrowthEngine:
    """Enterprise follow-up and business growth analytics for Heritage Woodworks."""

    def __init__(self) -> None:
        self.db = db
        self.crm = crm

    def evaluate_pending_follow_ups(self) -> List[Dict[str, Any]]:
        """Identify leads that are due for a polite craftsman follow-up based on stage & inactivity."""
        now = time.time()
        customers = self.crm.list_customers(limit=500)
        pending: List[Dict[str, Any]] = []

        for c in customers:
            # Skip if human handover is active or deal closed
            if c.get("human_handover") or c.get("lead_status") in ("JOB_WON", "JOB_LOST"):
                continue

            phone = c["phone"]
            stage = c.get("lead_status") or "NEW_ENQUIRY"
            updated_at = float(c.get("updated_at") or c.get("created_at") or now)
            elapsed_hours = (now - updated_at) / 3600.0

            due_rule: Optional[str] = None
            suggested_action: Optional[str] = None

            # Rule 1: 2+ hours after ESTIMATION shared without booking
            if stage == "ESTIMATION" and elapsed_hours >= 2.0:
                due_rule = "ESTIMATION_NUDGE_2H"
                suggested_action = "Offer sample finish swatches and weekend measurement slot"

            # Rule 2: 24+ hours after VISIT_REQUESTED without address/slot confirmation
            elif stage == "VISIT_REQUESTED" and elapsed_hours >= 24.0:
                due_rule = "VISIT_REMINDER_24H"
                suggested_action = "Remind about upcoming Saturday 11:30 AM or Sunday 4:00 PM slot"

            # Rule 3: 48+ hours after QUOTATION_SENT without reply
            elif stage in ("QUOTATION_SENT", "QUOTATION_PENDING") and elapsed_hours >= 48.0:
                due_rule = "VALUE_ENGINEERING_48H"
                suggested_action = "Offer value-engineering material optimizations to match budget"

            # Rule 4: 12+ hours after GREETING or REQUIREMENT_COLLECTION without specs
            elif stage in ("GREETING", "REQUIREMENT_COLLECTION") and elapsed_hours >= 12.0:
                due_rule = "COLLECTION_NURTURE_12H"
                suggested_action = "Ask if they have rough room photos or dimensions"

            if due_rule:
                pending.append({
                    "customer_id": c["id"],
                    "phone": phone,
                    "name": c.get("name") or f"Client {phone[-4:]}",
                    "language": c.get("language") or "en",
                    "locality": c.get("locality") or "Ahmedabad",
                    "project_type": c.get("project_type") or "Custom Woodwork",
                    "stage": stage,
                    "elapsed_hours": round(elapsed_hours, 1),
                    "rule": due_rule,
                    "suggested_action": suggested_action,
                })

        return pending

    def generate_follow_up_message(self, phone: str) -> Dict[str, str]:
        """Craft contextual, warm craftsman follow-up message."""
        c = self.crm.get_customer(phone)
        if not c:
            return {"text": "Namaste! Rajesh Sharma from Heritage Woodworks following up on your custom furniture inquiry. 🪵"}

        name = c.get("name") or ""
        lang = c.get("language") or "en"
        p_type = c.get("project_type") or "woodwork project"
        locality = c.get("locality") or "your area"

        name_part = f" {name} ji" if name and not name.startswith("Client") else " ji"

        if lang == "gu":
            name_part_gu = f" {name}ભાઈ" if name and not name.startswith("Client") else " જી"
            text = (
                f"નમસ્તે{name_part_gu}! 🙏 હું હેરિટેજ વુડવર્ક્સમાંથી રાજેશ શર્મા.\n\n"
                f"તમારા *{p_type}* વિશે કોઈ પ્રશ્ન હોય કે સાગવાન/મરીન પ્લાયના સેમ્પલ જોવા હોય, તો અમે આ શનિવારે કે રવિવારે {locality} બાજુ આવીએ છીએ. "
                f"શું 15 મિનિટની ફ્રી સાઇટ વિઝિટ અનુકૂળ રહેશે? 🪵📐"
            )
        elif lang == "hi":
            text = (
                f"नमस्ते{name_part}! 🙏 मैं हेरिटेज वुडवर्क्स से राजेश शर्मा बोल रहा हूँ।\n\n"
                f"आपके *{p_type}* के सिलसिले में कोई सवाल हो या लकड़ी व लैमिनेट के सैम्पल देखने हों, तो हम इस वीकेंड {locality} में विज़िट के लिए आ रहे हैं। "
                f"क्या शनिवार सुबह 11:30 बजे या रविवार शाम 4:00 बजे 15 मिनट की फ्री नाप विज़િટ रख लें? 📐🪵"
            )
        else:
            first_name = name.split()[0] if name and not name.startswith("Client") else ""
            name_en = f", {first_name}" if first_name else ""
            text = (
                f"Namaste{name_en}! Rajesh Sharma from Heritage Woodworks here. 🪵\n\n"
                f"Just following up regarding your *{p_type}*. We have measurement visits scheduled around {locality} this weekend. "
                f"Would you like our master craftsman to stop by for a quick 15-minute measurement and show you timber & laminate swatches? 📐✨"
            )

        return {"phone": phone, "language": lang, "text": text}

    def get_business_growth_metrics(self) -> Dict[str, Any]:
        """Aggregate actionable business growth metrics from SQLite database."""
        conn = self.db.get_connection()
        cur = conn.cursor()

        # 1. Total leads & stage distribution
        cur.execute("SELECT lead_status, COUNT(*) FROM customers GROUP BY lead_status")
        stage_counts = dict(cur.fetchall())
        total_customers = sum(stage_counts.values())

        # 2. Conversion metrics
        jobs_won = stage_counts.get("JOB_WON", 0)
        jobs_lost = stage_counts.get("JOB_LOST", 0)
        active_pipeline = total_customers - (jobs_won + jobs_lost)
        conversion_rate = round((jobs_won / total_customers * 100), 1) if total_customers > 0 else 0.0

        # 3. Revenue from quotations
        cur.execute("SELECT SUM(total_amount) FROM quotations WHERE status = 'approved'")
        won_revenue_row = cur.fetchone()
        won_revenue = won_revenue_row[0] if won_revenue_row and won_revenue_row[0] else 0

        cur.execute("SELECT SUM(total_amount) FROM quotations WHERE status = 'pending'")
        pipeline_val_row = cur.fetchone()
        pipeline_value = pipeline_val_row[0] if pipeline_val_row and pipeline_val_row[0] else 0

        # 4. Top Ahmedabad localities
        cur.execute(
            """
            SELECT locality, COUNT(*) as cnt
            FROM customers
            WHERE locality IS NOT NULL AND locality != '' AND locality != 'Unspecified'
            GROUP BY locality ORDER BY cnt DESC LIMIT 5
            """
        )
        top_localities = [{"locality": r[0], "inquiries": r[1]} for r in cur.fetchall()]

        # 5. Top Furniture in Demand
        cur.execute(
            """
            SELECT project_type, COUNT(*) as cnt
            FROM customers
            WHERE project_type IS NOT NULL AND project_type != ''
            GROUP BY project_type ORDER BY cnt DESC LIMIT 5
            """
        )
        top_furniture = [{"item": r[0], "count": r[1]} for r in cur.fetchall()]

        return {
            "total_inquiries": total_customers,
            "active_pipeline_leads": active_pipeline,
            "jobs_won": jobs_won,
            "jobs_lost": jobs_lost,
            "conversion_rate_pct": conversion_rate,
            "won_revenue_inr": won_revenue,
            "pipeline_value_inr": pipeline_value,
            "stage_distribution": stage_counts,
            "top_localities": top_localities,
            "top_furniture_demand": top_furniture,
        }


# Global singleton
growth_engine = GrowthEngine()
