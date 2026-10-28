"""Carpenter AI Agent Brain.

Integrates with Google Gemini API to power a warm, polite, highly skilled
master carpenter persona handling WhatsApp inquiries, clarifying project specs,
and scheduling measurement appointments.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from app.config import config

logger = logging.getLogger("carpenter.agent")

# Master Carpenter System Prompt
MASTER_CARPENTER_SYSTEM_PROMPT = """You are Rajesh Sharma, a warm, polite, and deeply experienced Master Carpenter ("Ustad Ji") running 'Heritage Woodworks & Joinery' - a premier custom furniture and architectural woodwork studio.

Your Craft & Expertise:
- 25+ years of hands-on woodworking craftsmanship with solid teak (CP/Burma Sagwan), Indian rosewood (Sheesham), and IS 710 BWP Marine Plywood.
- Workshop fabrication ensures dust-free and noise-free installation at client homes.

Your Natural WhatsApp Sales & Bargaining Workflow:
1. GREETING & DISCOVERY:
   - When customer says hello or mentions what they want to make, warmly acknowledge their idea.
   - Ask for rough size / wall dimensions (e.g. 10x8 ft, 6-seater) and preferred material (Teak/Sheesham vs Marine Ply with Laminate/Acrylic/PU).
2. TRANSPARENT BUDGET & TIMELINE IN DAYS:
   - When size/project is known, provide an approximate price range guide:
     • Modular Kitchens: ₹1,40,000 – ₹2,20,000 (approx. ₹1,500 – ₹2,200/sq.ft in BWP Marine Ply with German soft-close fittings).
     • Fitted Wardrobes: ₹95,000 – ₹1,50,000 (approx. ₹1,200 – ₹1,800/sq.ft depending on laminate/PU finish).
     • Solid Wood Dining Tables: ₹38,000 – ₹55,000 (6-seater) or ₹55,000 – ₹78,000 (8-seater) in Solid Teak/Sheesham.
     • Custom Beds: ₹45,000 – ₹70,000 (King Size hydraulic storage with cushioned headboard).
     • Wooden Doors & Chaukhats: ₹28,000 – ₹45,000 in seasoned CP Teak.
   - State the completion timeline clearly: 12–18 working days workshop fabrication + 2–3 days fast on-site installation.
   - Explain that exact price is decided after finalizing specific hardware & finish choices.
3. EXPERT BARGAINING & VALUE NEGOTIATION (CRITICAL):
   - When a customer says their budget is low (e.g. "my budget is 15000", "only have 20k", "too expensive", "can you reduce?"):
     • Acknowledge their budget with deep respect and warmth. Never dismiss them.
     • Explain why premium custom woodworking has real material costs (marine ply sheets, hardware, PU polish cost ₹15k–₹25k in raw materials alone).
     • Propose practical value-engineering compromises:
       - For Beds: Offer a Queen Platform bed with pull-out drawers in commercial hardwood ply around ₹22,000 – ₹25,000 instead of ₹50k hydraulic King bed.
       - For Kitchens: Offer BWP ply for wet sink areas + commercial ply for dry overheads (₹90k–₹1.1L).
       - For Wardrobes: Offer hinged doors instead of sliding tracks (saves ₹15k–₹20k).
       - For Dining: Offer a solid wood bench combination or 4-seater.
     • Negotiate a realistic middle-ground offer and suggest a measurement visit to see physical wood/finish swatches.
4. OFFER MEASUREMENT VISIT:
   - Guide customer to schedule a free 15-minute on-site laser measurement visit (offering Saturday 11:30 AM or Sunday 4:00 PM).
5. CONFIRMATION:
   - When customer confirms slot or address, confirm the booking with full details.
6. POST-CONFIRMATION COURTESY:
   - If customer replies "ok", "thank you", or "see you" after confirmation, warmly thank them and close politely. NEVER re-prompt for time booking once confirmed!

Formatting: Concise for mobile WhatsApp, *bold* highlights, bullet points (•), and tasteful craft emojis (🪵, 🪚, 📐, ✨).
"""


def get_price_and_timeline_estimate(project_type: Optional[str], dimensions: Optional[str]) -> Tuple[str, str]:
    """Return realistic price estimate range and completion timeline in days."""
    p_type = (project_type or "").lower()
    dim = (dimensions or "").lower()

    if "kitchen" in p_type:
        price = "₹1,40,000 – ₹2,20,000 (approx. ₹1,500 – ₹2,200/sq.ft in IS 710 BWP Marine Ply with soft-close German fittings)"
        timeline = "14 to 18 working days (precision machine crafting in workshop) + 2 to 3 days on-site assembly"
    elif "wardrobe" in p_type or "cupboard" in p_type or "closet" in p_type:
        price = "₹95,000 – ₹1,50,000 (approx. ₹1,200 – ₹1,800/sq.ft depending on 1mm laminate vs PU polish & internal organizers)"
        timeline = "12 to 15 working days workshop fabrication + 2 days on-site installation"
    elif "dining" in p_type or "table" in p_type:
        if "8" in dim or "8-seater" in dim:
            price = "₹55,000 – ₹78,000 (Solid Teak/Sheesham 8-seater with 8 cushioned chairs)"
        else:
            price = "₹38,000 – ₹55,000 (Solid Teak/Sheesham 6-seater with 6 cushioned chairs)"
        timeline = "15 to 20 working days for timber seasoning, mortise & tenon joinery, and 4-coat PU polish"
    elif "door" in p_type:
        price = "₹28,000 – ₹45,000 in seasoned CP/Burma Teak with matching chaukhat frame"
        timeline = "10 to 14 working days"
    elif "bed" in p_type:
        price = "₹45,000 – ₹70,000 (King Size with hydraulic storage & cushioned headboard)"
        timeline = "12 to 15 working days"
    else:
        price = "₹1,200 – ₹2,000 per sq. ft. depending on solid wood vs marine ply + PU/laminate finish"
        timeline = "12 to 18 working days"

    return price, timeline


def generate_bargaining_response(session: CustomerSession, budget: Optional[int], user_text: str) -> str:
    """Generate master craftsman negotiation, value-engineering compromise, and counter-offer."""
    p_type = (session.project_type or "woodwork").lower()
    b_val = budget or session.customer_budget

    # 1. Custom Bed Bargaining
    if "bed" in p_type:
        if b_val and b_val < 20000:
            return (
                f"I completely understand and respect your budget of *₹{b_val:,}*, Ji! 🙏\n\n"
                f"Let me be completely transparent with you as a craftsman: A full King Size hydraulic bed in IS 710 waterproof marine ply with heavy-duty hydraulic pumps alone costs around ₹22,000+ in raw timber and hardware.\n\n"
                f"However, we can definitely work together on smart value options:\n\n"
                f"• *Sturdy Queen Platform Bed*: We can craft a sleek Queen platform bed in seasoned commercial hardwood ply with a 1mm matte laminate finish around *₹22,000 – ₹25,000* (giving you lifelong durability without failing like cheap market particle boards).\n"
                f"• *Manual Drawer Storage*: We can use smooth bottom pull-out drawers instead of expensive hydraulic pump kits.\n"
                f"• *Artisan Counter-Offer*: If you can stretch slightly to around *₹22,000*, I can personally craft a solid, lifelong Queen bed with drawer storage for you!\n\n"
                f"Would you like to explore this *₹22,000* design, or shall we arrange a visit to discuss what best fits your space? 🪵✨"
            )
        elif b_val and b_val <= 35000:
            return (
                f"Thank you for sharing your budget of *₹{b_val:,}*! 🪵\n\n"
                f"While our King Size hydraulic bed with cushioned headboard is ₹45k–₹70k, we can handcraft a beautiful *Queen Platform Bed with 2 bottom storage drawers* in premium commercial hardwood ply for *₹26,000 – ₹32,000*, right in your range!\n\n"
                f"Would you like our team to bring timber and laminate swatches to show you how sturdy this build is? 📐"
            )

    # 2. Modular Kitchen Bargaining
    if "kitchen" in p_type:
        if b_val and b_val < 100000:
            return (
                f"I hear you, Ji! Working within *₹{b_val:,}* is something we can help optimize smartly.\n\n"
                f"For modular kitchens, using boiling water-proof (IS 710) ply is essential near sinks so wood never rots or swells. To bring the cost down closer to your budget:\n\n"
                f"• *Value Material Mix*: We can use BWP marine ply for wet base units and durable commercial ply with 0.8mm laminate for dry overhead cabinets, bringing the cost down to *₹90,000 – ₹1,10,000*.\n"
                f"• *Layout Optimization*: Mixing open floating shelves with core modular base cabinets.\n\n"
                f"If you can meet us around *₹90,000 – ₹95,000*, we can deliver a dependable, moisture-proof kitchen with soft-close German fittings. Shall we visit your site to suggest a budget-optimized layout? 📐✨"
            )

    # 3. Custom Wardrobe Bargaining
    if "wardrobe" in p_type:
        if b_val and b_val < 60000:
            return (
                f"I appreciate you sharing your budget of *₹{b_val:,}*! 🪵\n\n"
                f"Sliding door track mechanisms alone cost ₹15k–₹20k. To give you the best durability for your budget:\n\n"
                f"• *Hinged Shutters*: Classic hinged doors with soft-close German hinges save you ₹18,000 instantly.\n"
                f"• *Smart Partitioning*: Streamlined internal drawers with commercial hardwood ply, bringing the total to *₹55,000 – ₹65,000*.\n\n"
                f"Shall we measure your wall space during our free visit to calculate an exact quote with zero wood wastage? 🪚"
            )

    # 4. Dining Table Bargaining
    if "dining" in p_type or "table" in p_type:
        if b_val and b_val < 25000:
            return (
                f"I understand your budget of *₹{b_val:,}*! 🙏\n\n"
                f"Solid seasoned Teak or Sheesham is dense timber that lasts generations. For around *₹24,000 – ₹28,000*, we can craft a solid Sheesham 4-seater table, or a 6-seater table paired with a wooden dining bench on one side (which looks modern and saves the cost of 2 individual chairs)!\n\n"
                f"Would you be open to a 4-seater or a bench combination around *₹24,000*? 🪵✨"
            )

    # 5. General Discount or Bargaining Request
    budget_mention = f" of *₹{b_val:,}*" if b_val else ""
    return (
        f"I completely understand your budget{budget_mention}, Ji! 🙏\n\n"
        f"As a workshop-direct atelier, our prices are already 25–30% lower than branded showroom stores because we don't have showroom rental overheads.\n\n"
        f"However, if you can stretch slightly or finalize during our on-site measurement visit, I am happy to offer an *artisan courtesy discount of 5% to 8%*, or *upgrade all your fittings to German soft-close (Hettich) for free*! 🪵✨\n\n"
        f"Shall we book a quick 15-minute measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM* to explore the best options for your space? 📐"
    )


@dataclass
class CustomerSession:
    """Multi-turn customer session context."""

    phone_number: str
    customer_name: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: List[Dict[str, str]] = field(default_factory=list)  # [{"role": "user"|"model", "text": "..."}]
    project_type: Optional[str] = None
    dimensions: Optional[str] = None
    preferred_materials: List[str] = field(default_factory=list)
    customer_budget: Optional[int] = None
    negotiation_stage: str = "none"  # "none", "bargaining", "compromise_offered", "accepted"
    appointment_status: str = "none"  # "none", "requested", "confirmed"
    appointment_slot: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SessionStore:
    """Thread-safe multi-turn session repository."""

    def __init__(self) -> None:
        self._sessions: Dict[str, CustomerSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, phone_number: str, customer_name: Optional[str] = None) -> CustomerSession:
        with self._lock:
            clean_phone = phone_number.strip().lstrip("+")
            if clean_phone not in self._sessions:
                self._sessions[clean_phone] = CustomerSession(
                    phone_number=clean_phone,
                    customer_name=customer_name or f"Client {clean_phone[-4:]}",
                )
            session = self._sessions[clean_phone]
            if customer_name and session.customer_name != customer_name:
                session.customer_name = customer_name
            return session

    def get(self, phone_number: str) -> Optional[CustomerSession]:
        with self._lock:
            clean_phone = phone_number.strip().lstrip("+")
            return self._sessions.get(clean_phone)

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            # Sort by last updated descending
            sorted_sessions = sorted(
                self._sessions.values(), key=lambda s: s.updated_at, reverse=True
            )
            return [s.to_dict() for s in sorted_sessions]

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


class CarpenterAgent:
    """Carpenter AI Agent Brain with Google Gemini integration and domain fallback."""

    def __init__(self, session_store: Optional[SessionStore] = None) -> None:
        self.sessions = session_store or SessionStore()
        self._client: Any = None
        self._init_gemini_client()

    def _init_gemini_client(self) -> None:
        """Initialize Google GenAI client if credentials are configured."""
        if config.is_gemini_configured:
            try:
                from google import genai

                self._client = genai.Client(api_key=config.GEMINI_API_KEY)
                logger.info(f"Initialized Google GenAI SDK with model: {config.GEMINI_MODEL}")
            except Exception as e:
                logger.warning(f"Failed to initialize google-genai client: {e}. Falling back to domain engine.")
                self._client = None
        else:
            logger.info("GEMINI_API_KEY not configured. Running with domain-specific Master Carpenter engine.")
            self._client = None

    def _extract_project_metadata(self, session: CustomerSession, user_text: str) -> None:
        """Extract project specifications and scheduling intent from conversation text."""
        text_lower = user_text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))

        # Project type detection
        if any(w in text_lower for w in ["wardrobe", "cupboard", "closet", "almirah"]):
            session.project_type = "Custom Wardrobe"
        elif any(w in text_lower for w in ["kitchen", "modular kitchen", "cabinets"]):
            session.project_type = "Modular Kitchen"
        elif any(w in text_lower for w in ["dining", "table", "chair"]):
            session.project_type = "Solid Wood Dining Table"
        elif any(w in text_lower for w in ["door", "entrance door", "chaukhat", "carving door"]):
            session.project_type = "Wooden Door & Frame"
        elif any(w in text_lower for w in ["bed", "storage bed", "hydraulic"]):
            session.project_type = "Custom Storage Bed"
        elif any(w in text_lower for w in ["tv unit", "console", "media unit"]):
            session.project_type = "TV Entertainment Unit"
        elif any(w in text_lower for w in ["mandir", "pooja", "temple"]):
            session.project_type = "Pooja Mandir"

        # Dimensions detection (e.g. 10x8, 10x8 ft, 6 seater, 7x3)
        dim_match = re.search(r"(\d+(\.\d+)?\s*(x|\*|by)\s*\d+(\.\d+)?\s*(ft|feet|inch|in|m|meter)?)", text_lower)
        if dim_match:
            session.dimensions = dim_match.group(0).strip()
        elif "6 seater" in text_lower or "6-seater" in text_lower:
            session.dimensions = "6-Seater (approx 6ft x 3ft)"
        elif "8 seater" in text_lower or "8-seater" in text_lower:
            session.dimensions = "8-Seater (approx 8ft x 3.5ft)"

        # Materials detection
        materials_map = {
            "teak": "First-Grade Teak (Sagwan)",
            "sagwan": "First-Grade Teak (Sagwan)",
            "sheesham": "Solid Indian Rosewood (Sheesham)",
            "rosewood": "Solid Indian Rosewood (Sheesham)",
            "ply": "IS 710 Marine Plywood (BWP)",
            "plywood": "IS 710 Marine Plywood (BWP)",
            "laminate": "1mm Anti-Scratch Laminate",
            "veneer": "Natural Wood Veneer",
            "pu": "Polyurethane (PU) Polish",
            "acrylic": "High-Gloss Acrylic Finish",
            "ash": "Solid White Ash",
            "oak": "White Oak",
        }
        for kw, mat_name in materials_map.items():
            if kw in text_lower and mat_name not in session.preferred_materials:
                session.preferred_materials.append(mat_name)

        # Appointment / Scheduling intent detection (including typos like 'sechudel', 'schedul')
        scheduling_keywords = {
            "visit", "measurement", "measurements", "appointment", "book", "booking",
            "schedule", "sechudel", "schedul", "skedule", "meeting", "meet", "come", "slot", "slots"
        }
        affirmative_words = {
            "yes", "yeah", "yep", "sure", "ok", "okay", "yup", "done", "please", "pls",
            "confirm", "go ahead", "why not", "sounds good", "perfect"
        }

        # Budget detection (e.g. "my budget is 15000 Rs", "15k", "budget 20000", "can do in 18k", "max 25000")
        budget_patterns = [
            r"(?:budget\s*(?:is|of|around)?|have|max|for|in|only)\s*[:=]?\s*(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{3})+|\d+)\s*(k|thousand|l|lakh|rs\.?|inr|rupees)?",
            r"\b(\d{1,3})\s*k\s*(?:rs\.?|inr|rupees|budget)?\b",
            r"(?:rs\.?|inr|₹)\s*(\d{1,3}(?:,\d{3})+|\d+)",
            r"(\d{4,7})\s*(?:rs|inr|rupees)",
        ]
        for pat in budget_patterns:
            bm = re.search(pat, text_lower)
            if bm:
                raw_n = bm.group(1).replace(",", "")
                mult = bm.group(2) if len(bm.groups()) >= 2 and bm.group(2) else ""
                try:
                    b_num = int(raw_n)
                    if "k" in mult:
                        b_num *= 1000
                    elif "l" in mult or "lakh" in mult:
                        b_num *= 100000
                    if 1000 <= b_num <= 10000000:
                        session.customer_budget = b_num
                        session.negotiation_stage = "bargaining"
                        break
                except ValueError:
                    pass

        # Check if previous agent turn offered a measurement visit
        prev_agent_offered_visit = False
        for turn in reversed(session.history[:-1]):
            if turn.get("role") == "model":
                prev_text = turn.get("text", "").lower()
                if any(k in prev_text for k in ["visit", "schedule", "measurement", "slot", "workshop"]):
                    prev_agent_offered_visit = True
                break

        has_scheduling_word = bool(words.intersection(scheduling_keywords)) or any(
            k in text_lower for k in ["site visit", "laser measurement", "come over", "come to"]
        )
        is_affirming_visit = prev_agent_offered_visit and bool(words.intersection(affirmative_words))

        if has_scheduling_word or is_affirming_visit:
            if session.appointment_status == "none":
                session.appointment_status = "requested"

        # Check specific day / time slots
        days_and_slots = [
            "saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday",
            "weekend", "tomorrow", "morning", "evening", "afternoon", "11:30", "11 am", "4 pm", "10 am"
        ]
        for slot_kw in days_and_slots:
            if slot_kw in text_lower:
                session.appointment_status = "confirmed"
                session.appointment_slot = slot_kw.capitalize() + " Slot"
                break

        # Address / Location detection
        address_markers = ["flat", "apt", "apartment", "tower", "road", "street", "sector", "phase", "block", "society", "colony", "layout", "nagar", "house"]
        if any(marker in text_lower for marker in address_markers) or (len(user_text.split()) > 3 and any(c.isdigit() for c in user_text) and not dim_match):
            session.appointment_status = "confirmed"
            if not session.appointment_slot:
                session.appointment_slot = "This Weekend"

    def _generate_fallback_response(self, session: CustomerSession, user_text: str) -> str:
        """Intelligent offline Master Carpenter response generator with multi-turn state."""
        text_lower = user_text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))
        name = session.customer_name or "Ji"

        # Check previous turn context
        prev_agent_msg = ""
        for turn in reversed(session.history[:-1]):
            if turn.get("role") == "model":
                prev_agent_msg = turn.get("text", "").lower()
                break

        scheduling_keywords = {
            "visit", "measurement", "measurements", "appointment", "book", "booking",
            "schedule", "sechudel", "schedul", "skedule", "meeting", "meet", "slot", "slots"
        }
        affirmative_words = {
            "yes", "yeah", "yep", "sure", "ok", "okay", "yup", "done", "please", "pls", "confirm", "go ahead"
        }
        courtesy_words = {
            "ok", "okay", "thank", "thanks", "thx", "great", "perfect", "good", "bye", "see", "alright", "done"
        }

        user_is_scheduling = bool(words.intersection(scheduling_keywords)) or any(
            k in text_lower for k in ["site visit", "come over", "come to", "laser measurement"]
        )
        user_is_affirming = bool(words.intersection(affirmative_words)) and (
            "visit" in prev_agent_msg or "schedule" in prev_agent_msg or "measurement" in prev_agent_msg or session.appointment_status == "requested"
        )
        has_time_slot = any(w in words for w in ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "weekend", "tomorrow", "morning", "evening"]) or any(t in text_lower for t in ["11:30", "11 am", "4 pm", "10 am"])
        address_markers = ["flat", "apt", "apartment", "tower", "road", "street", "sector", "phase", "block", "society", "colony", "layout", "nagar"]
        has_address = any(marker in text_lower for marker in address_markers)

        # 1. Post-Booking Confirmation Courtesy (Customer says "ok", "thank you", "great" after booking confirmed)
        if session.appointment_status == "confirmed" and (words.intersection(courtesy_words) or "thank you" in text_lower or "thanks" in text_lower):
            slot_str = session.appointment_slot or "your scheduled appointment"
            return (
                f"You're very welcome! 🙏 Everything is set for your laser measurement visit on *{slot_str}*.\n\n"
                f"Feel free to share any photo references or design ideas here anytime before we arrive. Looking forward to meeting you! 🪵✨"
            )

        # 2. Booking confirmed when customer provides a specific day/time slot or address
        if (has_time_slot or has_address) and session.appointment_status in ("requested", "confirmed"):
            session.appointment_status = "confirmed"
            slot_name = session.appointment_slot or "your selected time"
            project_name = session.project_type or "custom woodwork"
            return (
                f"Booking confirmed! 📅✨\n\n"
                f"• *Appointment*: *{slot_name}*\n"
                f"• *Project Scope*: *{project_name}*\n"
                f"• *What we bring*: Laser measurement tape & physical wood samples (Teak, Sheesham, Marine Ply, PU swatches).\n\n"
                f"Our master carpenter team will call you 30 minutes before arrival. Looking forward to meeting you! 🙏🪵"
            )

        # 3. Customer agreed to schedule a visit ("yes", "sure", "schedule meeting", "sechudel meeting")
        if (user_is_scheduling or user_is_affirming) and session.appointment_status != "confirmed":
            session.appointment_status = "requested"
            project_context = f"for your *{session.project_type}*" if session.project_type else ""
            return (
                f"Wonderful! 📐 I will gladly visit your site {project_context} with our laser tools and wood samples.\n\n"
                f"We currently have slots open this:\n"
                f"• *Saturday at 11:30 AM*\n"
                f"• *Sunday at 4:00 PM*\n\n"
                f"Which slot suits you best? Also, please share your *apartment address or landmark* so we can lock it in! 🪚✨"
            )

        # 4. Greetings & Initial Inquiry (Only if user is simply saying hello without project details)
        greetings = {"hi", "hello", "hey", "namaste", "start", "greetings"}
        is_only_greeting = bool(words.intersection(greetings)) and (
            len(words) <= 3 or (not session.project_type and not session.dimensions and not session.preferred_materials)
        )
        if is_only_greeting and len(session.history) <= 2:
            return (
                f"Namaste! 🙏 I am *Rajesh Sharma*, Master Carpenter at *Heritage Woodworks*.\n\n"
                f"We handcraft bespoke wardrobes, modular kitchens, solid Teak/Sheesham dining tables, and entrance doors:\n\n"
                f"• *Fitted Wardrobes* (Hinged / Sliding)\n"
                f"• *Modular Kitchens* (IS 710 BWP Marine Ply)\n"
                f"• *Solid Wood Dining Sets* (Teak / Sheesham)\n"
                f"• *Main Doors & Chaukhats*\n\n"
                f"What piece are you planning to make for your home? 🪵✨"
            )

        # 5. Customer states a Budget or requests Bargaining / Discount / Negotiation
        has_budget_mention = bool(
            session.customer_budget
            or any(w in words for w in ["budget", "discount", "expensive", "costly", "cheaper", "reduce", "less", "concession", "afford"])
            or any(k in text_lower for k in ["too high", "too much", "best price", "can you do", "my budget", "within", "max"])
        )
        if has_budget_mention:
            return generate_bargaining_response(session, session.customer_budget, user_text)

        # 6. Customer provided Dimensions & Requirements -> Approximate Budget, Timeline in Days, then Slot Booking
        is_dimension_input = bool(
            ("x" in text_lower or "*" in text_lower or "by" in text_lower)
            or any(w in text_lower for w in ["ft", "feet", "inch", "seater", "king", "queen"])
            or (session.dimensions and not has_budget_mention)
        )
        if is_dimension_input and (session.dimensions or any(c.isdigit() for c in user_text)):
            dim_str = session.dimensions or "your specified scale"
            p_name = session.project_type or "Custom Furniture"
            price_est, timeline_est = get_price_and_timeline_estimate(session.project_type, session.dimensions)

            return (
                f"Got your specifications for *{p_name}* ({dim_str})! 📏\n\n"
                f"• *Approximate Budget Guide*: {price_est}\n"
                f"• *Completion Timeline*: *{timeline_est}*\n"
                f"• *Craftsmanship*: Premium seasoned timber / IS 710 marine ply with soft-close German fittings.\n\n"
                f"The final price is decided based on your choice of finish (Laminate vs Acrylic vs PU) and hardware.\n\n"
                f"To verify exact site measurements and give you an itemized quotation with 3D design, shall we book a free 15-minute measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM*? 📐🪵"
            )

        # 7. Customer mentioned what they want to make (without dimensions yet) -> Budget range, Timeline, Ask for Size
        if session.project_type:
            p_name = session.project_type
            price_est, timeline_est = get_price_and_timeline_estimate(p_name, None)
            return (
                f"We would love to handcraft your *{p_name}*! 🪵\n\n"
                f"• *Approximate Budget Range*: {price_est}\n"
                f"• *Estimated Timeline*: *{timeline_est}*\n\n"
                f"To help us estimate the exact price:\n"
                f"1. What are your approximate room / wall dimensions or seating size? 📐\n"
                f"2. Do you have a preferred finish in mind (Solid Teak, Sheesham, or Marine Ply with Laminate/PU)?\n\n"
                f"Or if you prefer, our team can visit with laser measuring tape and wood samples to measure on-site! 🪚"
            )

        # 7. Material inquiry
        if any(w in text_lower for w in ["teak", "sheesham", "ply", "laminate", "material", "wood", "difference"]):
            return (
                f"Excellent question! Choosing the right timber is 80% of fine woodworking:\n\n"
                f"• *Teak (Sagwan)*: High natural oil content, 100% termite proof, ideal for lifetime pieces and doors.\n"
                f"• *Sheesham*: Hard, dense, with striking dual-tone grain. Perfect for dining sets & sturdy beds.\n"
                f"• *IS 710 BWP Marine Ply*: Waterproof, best for kitchens & wardrobes, paired with *1mm Matte/PU finish*.\n\n"
                f"Do you have a specific finish in mind, like warm natural grains or modern matte solid colors? 🪵"
            )

        # 8. General project advice
        return (
            f"Thank you for reaching out to Heritage Woodworks! 🪵\n\n"
            f"We use seasoned timber and IS 710 waterproof marine ply with soft-close German fittings. "
            f"Every piece is crafted with precision mortise & tenon joinery in 12–18 working days.\n\n"
            f"What piece are you looking to create for your home, and what are the approximate room dimensions? 📐"
        )

    def process_message(
        self,
        sender_phone: str,
        message_text: str,
        customer_name: Optional[str] = None,
        media_info: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Process incoming customer message and return master carpenter response.

        Args:
            sender_phone: Phone number of the sender.
            message_text: Text message body.
            customer_name: Optional WhatsApp profile name.
            media_info: Optional media attachment details.

        Returns:
            Dict containing response_text, session_id, and metadata.
        """
        start_time = time.time()
        session = self.sessions.get_or_create(sender_phone, customer_name)
        session.updated_at = time.time()

        # Append incoming message to history
        user_turn = {
            "role": "user",
            "text": message_text,
            "timestamp": time.time(),
        }
        if media_info:
            user_turn["media"] = media_info
        session.history.append(user_turn)

        # Extract metadata
        self._extract_project_metadata(session, message_text)

        response_text = ""
        source = "domain_engine"

        # Try Google Gemini if configured
        if self._client:
            try:
                from google.genai import types

                # Prepare conversation history for Gemini
                contents: List[types.Content] = []
                # Keep last 10 turns to stay concise and relevant
                recent_history = session.history[-10:]
                for item in recent_history:
                    role = "user" if item["role"] == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=item["text"])],
                        )
                    )

                response = self._client.models.generate_content(
                    model=config.GEMINI_MODEL,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=MASTER_CARPENTER_SYSTEM_PROMPT,
                        temperature=0.6,
                        max_output_tokens=600,
                    ),
                )
                if response and response.text:
                    response_text = response.text.strip()
                    source = f"gemini:{config.GEMINI_MODEL}"
            except Exception as e:
                logger.error(f"Gemini API invocation error: {e}. Falling back to domain engine.")
                response_text = self._generate_fallback_response(session, message_text)
                source = "domain_engine_fallback"
        else:
            response_text = self._generate_fallback_response(session, message_text)

        # Store model response in session
        session.history.append(
            {
                "role": "model",
                "text": response_text,
                "timestamp": time.time(),
                "source": source,
            }
        )

        latency_ms = int((time.time() - start_time) * 1000)

        result = {
            "recipient_id": session.phone_number,
            "response_text": response_text,
            "source": source,
            "latency_ms": latency_ms,
            "session": session.to_dict(),
        }

        logger.info(
            f"[AGENT RESPONSE] To: {session.phone_number} | Source: {source} | Latency: {latency_ms}ms"
        )
        return result


# Global singleton agent
carpenter_agent = CarpenterAgent()
