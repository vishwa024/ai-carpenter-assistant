"""Pricing and Estimation Engine for AI Master Carpenter Assistant.

Independent of the LLM. Implements:
- Editable material & hardware catalogue pricing
- Unit conversions & sq.ft calculations with wastage
- Transparent reproducible formula:
  Material + Hardware + Labour + Finishing + Transport + Installation + Taxes + Approved Margin = Estimated Price
- Three quotation tiers: Preliminary Estimate -> Detailed Quotation -> Final Approved Quotation
- Negotiation logic with value-engineering alternatives
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from app.database import db

logger = logging.getLogger("carpenter.pricing")

# Default Baseline Rates (Per Sq. Ft / Unit) - Verified Ahmedabad Workshop Benchmarks
TAX_RATE_GST = 0.18        # 18% GST standard on modular woodwork fabrication
WASTAGE_FACTOR = 0.10      # 10% standard workshop cutting & grain matching wastage
APPROVED_MARGIN = 0.15     # 15% standard workshop profit margin


def parse_dimension_details(dim_str: Optional[str], text_lower: str = "") -> Dict[str, Any]:
    """Extract width, height, length, square footage and seating details with unit conversions."""
    combined = f"{dim_str or ''} {text_lower}".lower().replace("×", "x").replace("X", "x")

    # 1. Check Seater (Sofas / Dining)
    seater_match = re.search(r"\b(\d+)\s*[-]?\s*(?:seater|seat|સીટર|सीटर|chair|chairs)\b", combined)
    if seater_match:
        sc = int(seater_match.group(1))
        return {
            "type": "seater",
            "seater_count": sc,
            "dimensions_label": f"{sc}-Seater",
            "sqft": sc * 12.0,  # ~12 sq.ft allowance per seating unit
        }

    # 2. Check Bed Scale
    if any(k in combined for k in ["king size", "king bed", "કિંગ સાઈઝ", "किंग साइज"]):
        return {
            "type": "bed",
            "scale": "King Size",
            "width_ft": 6.0,
            "length_ft": 6.5,
            "sqft": 39.0,
            "dimensions_label": "King Size (approx 6.5ft x 6ft)",
        }
    if any(k in combined for k in ["queen size", "queen bed", "ક્વીન સાઈઝ", "क्वीन साइज"]):
        return {
            "type": "bed",
            "scale": "Queen Size",
            "width_ft": 5.0,
            "length_ft": 6.5,
            "sqft": 32.5,
            "dimensions_label": "Queen Size (approx 6.5ft x 5ft)",
        }

    # 3. Check 2D Dimensions (e.g. 10x8, 10x8 ft, 10*20, 120x96 inch, 3x2.5 m)
    dim_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:x|\*|by|બાય|बाय)\s*(\d+(?:\.\d+)?)\s*(ft|feet|inch|in|m|meter|ફૂટ|ફીટ|फुट|फीट)?",
        combined,
    )
    if dim_match:
        val1 = float(dim_match.group(1))
        val2 = float(dim_match.group(2))
        unit = (dim_match.group(3) or "ft").strip().lower()

        # Convert to feet
        if unit in ("inch", "in"):
            val1 = round(val1 / 12.0, 2)
            val2 = round(val2 / 12.0, 2)
        elif unit in ("m", "meter"):
            val1 = round(val1 * 3.28084, 2)
            val2 = round(val2 * 3.28084, 2)

        sqft = round(val1 * val2, 1)
        dim_label = f"{val1}x{val2} ft"
        return {
            "type": "area",
            "width_ft": val1,
            "height_ft": val2,
            "sqft": sqft,
            "dimensions_label": dim_label,
        }

    # 4. Check Single Area (e.g. 100 sqft, 100 sq.ft, 100 ચોરસ ફૂટ)
    sqft_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:sqft|sq\.ft|square feet|ચોરસ ફૂટ|स्क्वायर फीट)", combined)
    if sqft_match:
        sqft = float(sqft_match.group(1))
        return {
            "type": "area",
            "sqft": sqft,
            "dimensions_label": f"{int(sqft)} sq.ft.",
        }

    # Default fallback
    return {
        "type": "unknown",
        "sqft": 100.0,
        "dimensions_label": "Standard Scale (approx 100 sq.ft.)",
    }


class PricingEngine:
    """Deterministic, Transparent Pricing Engine."""

    def __init__(self) -> None:
        self.db = db

    def get_catalogue_rate(self, item_id: str, default_rate: float) -> float:
        """Fetch live verified rate from database catalogue."""
        try:
            conn = self.db.get_connection()
            cur = conn.cursor()
            cur.execute("SELECT rate FROM catalogue WHERE item_id = ?", (item_id,))
            row = cur.fetchone()
            if row:
                return float(row[0])
        except Exception as e:
            logger.warning(f"Failed to fetch rate for {item_id}: {e}")
        return default_rate

    def calculate_turnkey_breakdown(
        self,
        project_type: str,
        dim_info: Dict[str, Any],
        finish_type: str = "laminate",  # 'laminate', 'pu', 'acrylic', 'melamine'
    ) -> Dict[str, Any]:
        """Calculate fully itemized, reproducible price breakdown.

        Formula: Material + Hardware + Labour + Finishing + Transport + Installation + Taxes + Approved Margin = Estimated Price.
        """
        sqft = float(dim_info.get("sqft") or 100.0)
        p_lower = (project_type or "").lower()

        # 1. Base Board / Timber Material Cost
        if any(k in p_lower for k in ["dining", "table", "sofa", "temple", "mandir", "chair"]):
            # Solid Teak / Sheesham construction
            timber_cuft = max(3.0, round(sqft * 0.15, 2))
            timber_rate = self.get_catalogue_rate("mat_cp_teak", 3800.0)
            material_raw = timber_cuft * timber_rate
        else:
            # 18mm IS 710 BWP Marine Plywood Carcass
            ply_rate = self.get_catalogue_rate("mat_bwp_marine_18", 115.0)
            material_raw = sqft * ply_rate

        material_with_wastage = round(material_raw * (1.0 + WASTAGE_FACTOR), 2)

        # 2. Hardware Cost
        if "kitchen" in p_lower:
            # Tandem drawers + soft-close hinges + gas lifts
            hinge_rate = self.get_catalogue_rate("hard_hettich_hinges", 340.0)
            tandem_rate = self.get_catalogue_rate("hard_tandem_box", 2150.0)
            hardware_cost = round((sqft / 20.0) * hinge_rate + 3.0 * tandem_rate, 2)
        elif "wardrobe" in p_lower:
            hinge_rate = self.get_catalogue_rate("hard_hettich_hinges", 340.0)
            hardware_cost = round((sqft / 15.0) * hinge_rate + 2500.0, 2)  # internal drawers & locksets
        elif "bed" in p_lower and "hydraulic" in p_lower:
            hyd_rate = self.get_catalogue_rate("hard_bed_hydraulic", 4800.0)
            hardware_cost = hyd_rate + 1200.0
        else:
            hardware_cost = round(max(1500.0, sqft * 35.0), 2)

        # 3. Joinery & Fabrication Labour Cost
        labour_rate = self.get_catalogue_rate("srv_carpentry_labour", 480.0)
        labour_cost = round(sqft * labour_rate, 2)

        # 4. Finishing Cost
        if finish_type in ("pu", "pu_polish", "polish"):
            finish_rate = self.get_catalogue_rate("fin_pu_polish_4coat", 280.0)
            finish_name = "Italian 4-Coat Polyurethane (PU) Polish"
        elif finish_type == "acrylic":
            finish_rate = self.get_catalogue_rate("fin_acrylic_gloss", 120.0)
            finish_name = "High-Gloss Seamless Acrylic"
        elif finish_type == "melamine":
            finish_rate = self.get_catalogue_rate("fin_natural_melamine", 110.0)
            finish_name = "Natural Melamine Polish"
        else:
            finish_rate = self.get_catalogue_rate("fin_laminate_1mm", 55.0)
            finish_name = "1mm Anti-Scratch Decorative Laminate"

        finishing_cost = round(sqft * finish_rate, 2)

        # 5. Local Transport & Packaging Cost
        transport_cost = self.get_catalogue_rate("srv_local_transport", 1800.0)

        # 6. On-Site Installation & Leveling Cost
        install_rate = self.get_catalogue_rate("srv_site_fitting", 160.0)
        installation_cost = round(sqft * install_rate, 2)

        # Subtotal of Direct Costs
        direct_cost = round(
            material_with_wastage + hardware_cost + labour_cost + finishing_cost + transport_cost + installation_cost,
            2,
        )

        # 7. Workshop Approved Margin
        margin_amount = round(direct_cost * APPROVED_MARGIN, 2)

        # 8. Taxes (GST)
        tax_amount = round((direct_cost + margin_amount) * TAX_RATE_GST, 2)

        # Total Estimated Turnkey Price
        total_estimate = direct_cost + margin_amount + tax_amount
        # Round to nearest 500 for clean Indian commercial quotations
        rounded_total = int(math.ceil(total_estimate / 500.0) * 500)
        rate_per_sqft = int(round(rounded_total / max(1.0, sqft)))

        return {
            "project_type": project_type,
            "dimensions": dim_info.get("dimensions_label"),
            "sqft": sqft,
            "finish_name": finish_name,
            "formula_breakdown": {
                "material_cost": material_with_wastage,
                "hardware_cost": hardware_cost,
                "labour_cost": labour_cost,
                "finishing_cost": finishing_cost,
                "transport_cost": transport_cost,
                "installation_cost": installation_cost,
                "direct_cost": direct_cost,
                "approved_margin": margin_amount,
                "taxes_gst_18pct": tax_amount,
                "total_exact": total_estimate,
            },
            "total_turnkey": rounded_total,
            "rate_per_sqft": rate_per_sqft,
            "timeline": "12 to 16 working days workshop fabrication + 2 days on-site installation",
        }

    def generate_three_level_quote(
        self,
        phone: str,
        project_type: str,
        dim_info: Dict[str, Any],
        level: str = "preliminary",  # 'preliminary', 'detailed', 'final_approved'
        finish_type: str = "laminate",
        admin_approved_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate one of three quotation tiers and persist to database."""
        breakdown_lam = self.calculate_turnkey_breakdown(project_type, dim_info, "laminate")
        breakdown_pu = self.calculate_turnkey_breakdown(project_type, dim_info, "pu")

        sqft = float(dim_info.get("sqft") or 100.0)
        quotation_id = f"HW-{int(time.time())}-{phone[-4:]}"

        total_lam = breakdown_lam["total_turnkey"]
        total_pu = breakdown_pu["total_turnkey"]

        is_final_approved = (level == "final_approved" and bool(admin_approved_by))
        status = "approved" if is_final_approved else ("sent" if level == "detailed" else "preliminary")

        # Persist quotation to database
        try:
            conn = self.db.get_connection()
            with conn:
                conn.execute(
                    """
                    INSERT INTO quotations (
                        quotation_id, phone, level, project_type, dimensions, sqft,
                        breakdown_json, total_amount, status, approved_by, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        quotation_id,
                        phone,
                        level,
                        project_type,
                        dim_info.get("dimensions_label"),
                        sqft,
                        json.dumps({
                            "laminate_option": breakdown_lam,
                            "pu_polish_option": breakdown_pu,
                        }),
                        total_lam,
                        status,
                        admin_approved_by,
                        time.time(),
                        time.time(),
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to record quotation {quotation_id}: {e}")

        return {
            "quotation_id": quotation_id,
            "level": level,
            "is_final_approved": is_final_approved,
            "project_type": project_type,
            "sqft": sqft,
            "dimensions": dim_info.get("dimensions_label"),
            "laminate_option": breakdown_lam,
            "pu_polish_option": breakdown_pu,
            "total_lam": total_lam,
            "rate_lam": breakdown_lam["rate_per_sqft"],
            "total_pu": total_pu,
            "rate_pu": breakdown_pu["rate_per_sqft"],
            "timeline": breakdown_lam["timeline"],
        }

    def generate_value_engineering_alternative(
        self,
        project_type: str,
        dim_info: Dict[str, Any],
        customer_budget: int,
        lang: str = "en",
    ) -> Dict[str, Any]:
        """Produce cheaper design alternatives when customer budget is below standard estimate.

        Explains material tradeoffs without compromising structural IS 710 joinery integrity.
        """
        sqft = float(dim_info.get("sqft") or 100.0)
        p_lower = (project_type or "").lower()

        if any(k in p_lower for k in ["bed", "palang", "પલંગ", "पलंग"]):
            # Suggest Platform/Drawer bed instead of heavy Hydraulic Lift
            alt_name = "Solid Platform Bed with Underbed Storage Drawers"
            alt_price = 22000
            savings = 13000
            reason_en = "By substituting the expensive gas-spring hydraulic mechanism with handcrafted smooth-glide bottom storage drawers, we achieve the same storage capacity while saving ₹13,000 on imported hardware."
            reason_hi = "हाइड्रोलिक लिफ्ट के बदले स्मूद-ग्लाइड स्टोरेज दराज (ड्रॉअर) बनाकर हम ₹13,000 बचा सकते हैं, जिससे पूरी मजबूती के साथ बेड ₹22,000 में तैयार हो जाएगा।"
            reason_gu = "હાઈડ્રોલિક લિફ્ટ મિકેનિઝમની જગ્યાએ હેન્ડક્રાફ્ટેડ સ્ટોરેજ ડ્રોઅર્સ (દરાજ) બનાવીને આપણે ₹13,000 ની બચત કરી શકીએ છીએ અને ₹22,000 માં પલંગ તૈયાર થઈ જશે."
        elif any(k in p_lower for k in ["wardrobe", "cupboard", "almirah", "કબાટ", "अलमारी"]):
            alt_name = "1mm Anti-Scratch Matte Laminate with Hinged Shutters"
            alt_price = int(sqft * 1250)
            savings = int(sqft * 450)
            reason_en = "By opting for 1mm durable anti-scratch laminate with hinged doors instead of 4-coat Italian PU sliding systems, you save around ₹450/sq.ft with zero compromise on internal waterproof marine ply."
            reason_hi = "4-कोट इटैलियन PU स्लाइडिंग के बजाय 1mm एंटी-स्क्रैच लैमिनेट और हिंज्ड दरवाजों से लगभग ₹450 प्रति स्क्वायर फीट की बचत होगी, और अंदर 100% वाटरप्रूफ मरीन प्लाई ही रहेगी।"
            reason_gu = "PU સ્લાઇડિંગની જગ્યાએ 1mm એન્ટી-સ્ક્રેચ લેમિનેટ અને હિન્જ્ડ શટર પસંદ કરવાથી પ્રતિ ચોરસ ફૂટ આશરે ₹450 ની બચત થશે, અંદર 18mm વોટરપ્રૂફ મરીન પ્લાયની ગુણવત્તા યથાવત રહેશે."
        else:
            alt_name = "Commercial MR Ply Core with 1mm Laminate"
            alt_price = int(sqft * 1150)
            savings = int(sqft * 350)
            reason_en = "We can optimize the internal shelf structure to bring down the fabrication cost while keeping the external facade looking 100% premium."
            reason_hi = "हम अंदरूनी शेल्फ डिज़ाइन को वैल्यू-इंजीनियर करके फिनिशिंग को पूरी तरह प्रीमियम रखते हुए बजट में तैयार कर सकते हैं।"
            reason_gu = "અમે આંતરિક શેલ્ફ પ્લાનિંગ સરળ કરીને ડિઝાઇનને સંપૂર્ણ પ્રીમિયમ લૂક સાથે તમારા બજેટમાં લાવી શકીએ છીએ."

        return {
            "alternative_name": alt_name,
            "alternative_price": alt_price,
            "savings_amount": savings,
            "reason": reason_gu if lang == "gu" else (reason_hi if lang == "hi" else reason_en),
        }

    def save_quotation(
        self,
        phone: str,
        project_type: str,
        dimensions: Optional[str],
        level: str,
        breakdown: Dict[str, Any],
        total_amount: int,
        status: str = "pending",
        quotation_id: Optional[str] = None,
    ) -> str:
        """Persist a quotation into SQLite database."""
        clean_phone = re.sub(r"[^\d]", "", str(phone or ""))
        if clean_phone.startswith("00"):
            clean_phone = clean_phone[2:]

        qid = quotation_id or f"QUO-{int(time.time() * 1000)}"
        sqft = float(breakdown.get("sqft") or breakdown.get("dim_info", {}).get("sqft") or 0.0)
        breakdown_str = json.dumps(breakdown)
        now = time.time()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO quotations (
                    quotation_id, phone, level, project_type, dimensions, sqft,
                    breakdown_json, total_amount, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (qid, clean_phone, level, project_type, dimensions, sqft, breakdown_str, total_amount, status, now, now),
            )
        logger.info(f"Saved quotation {qid} for {clean_phone} at level {level} (Total: ₹{total_amount:,})")
        return qid

    def approve_quotation(self, quotation_id: str, approved_by: str = "admin") -> bool:
        """Human Master Carpenter approval for quotations / exceptional discounts."""
        conn = self.db.get_connection()
        now = time.time()
        with conn:
            cur = conn.execute(
                """
                UPDATE quotations
                SET status = 'approved', approved_by = ?, updated_at = ?
                WHERE quotation_id = ?
                """,
                (approved_by, now, quotation_id),
            )
            success = cur.rowcount > 0
        if success:
            logger.info(f"Quotation {quotation_id} approved by {approved_by}")
        return success

    def get_quotation(self, quotation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific quotation by ID."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM quotations WHERE quotation_id = ?", (quotation_id,))
        row = cur.fetchone()
        if not row:
            return None
        res = dict(row)
        if res.get("breakdown_json"):
            try:
                res["breakdown"] = json.loads(res["breakdown_json"])
            except Exception:
                res["breakdown"] = {}
        return res

    def get_quotations_for_customer(self, phone: str) -> List[Dict[str, Any]]:
        """List all quotations for a specific customer."""
        clean_phone = re.sub(r"[^\d]", "", str(phone or ""))
        conn = self.db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM quotations WHERE phone = ? ORDER BY created_at DESC", (clean_phone,))
        out = []
        for row in cur.fetchall():
            res = dict(row)
            if res.get("breakdown_json"):
                try:
                    res["breakdown"] = json.loads(res["breakdown_json"])
                except Exception:
                    res["breakdown"] = {}
            out.append(res)
        return out

    def get_all_quotations(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all workshop quotations, optionally filtered by status."""
        conn = self.db.get_connection()
        cur = conn.cursor()
        if status:
            cur.execute("SELECT * FROM quotations WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            cur.execute("SELECT * FROM quotations ORDER BY created_at DESC")
        out = []
        for row in cur.fetchall():
            res = dict(row)
            if res.get("breakdown_json"):
                try:
                    res["breakdown"] = json.loads(res["breakdown_json"])
                except Exception:
                    res["breakdown"] = {}
            out.append(res)
        return out


# Global Pricing Engine singleton
pricing_engine = PricingEngine()
