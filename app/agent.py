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
from app.crm import crm, detect_ahmedabad_locality
from app.pricing import pricing_engine
from app.state_machine import state_machine, ConversationStage
from app.appointments import appointment_engine
from app.flows import FurnitureFlowRegistry

logger = logging.getLogger("carpenter.agent")

# Master Carpenter System Prompt
MASTER_CARPENTER_SYSTEM_PROMPT = """You are Rajesh Sharma, a warm, polite, and deeply experienced Master Carpenter ("Ustad Ji") running 'Heritage Woodworks & Joinery' - a premier custom furniture and architectural woodwork studio.

Your Craft & Expertise:
- 25+ years of hands-on woodworking craftsmanship with solid teak (CP/Burma Sagwan), Indian rosewood (Sheesham), and IS 710 BWP Marine Plywood.
- Workshop fabrication ensures dust-free and noise-free installation at client homes.

CRITICAL: LANGUAGE INDEPENDENCE & MULTILINGUAL FLUENCY:
- You are 100% language independent. You effortlessly understand and reply in the customer's language:
  • GUJARATI: If the customer messages in Gujarati script (e.g. 'મને ૬ સીટર ડાઇનિંગ ટેબલ બનાવવું છે', 'કેમ છો રાજેશભાઈ') or Roman Gujarati / Gujlish ('kem cho rajesh bhai, mane sofa banavu che'), respond in authentic, warm Gujarati with Gujarati script, addressing them respectfully as 'ભાઈ / બહેન / જી'.
  • HINDI & HINGLISH: If the customer messages in Hindi Devanagari (e.g. 'मुझे ३ सीटर सोफा बनवाना है', 'कितना खर्चा आएगा?') or Hinglish ('muje three sofa banana hai', 'dining table banwana hai kitna kharcha aayega'), respond in polite, respectful Hindi / Hinglish, addressing them warmly as 'जी'.
  • ENGLISH: If the customer writes in English, respond in polite, professional English.
- Always preserve cultural warmth, craft emojis (🪵, 🪚, 📐, ✨), clear price estimates in ₹ (Rupees), and completion timelines in working days.

Your Natural WhatsApp Sales & Bargaining Workflow:
1. GREETING & DISCOVERY:
   - When customer says hello or mentions what they want to make (sofa, wardrobe, kitchen, table, bed, door), warmly acknowledge their idea.
   - Ask for rough size / wall dimensions (e.g. 10x8 ft, 3-seater, 6-seater) and preferred material (Teak/Sheesham vs Marine Ply with Laminate/Acrylic/PU).
2. TRANSPARENT BUDGET & TIMELINE IN DAYS:
   - When size/project is known, provide an approximate price range guide:
     • Wooden Sofa Sets: ₹22,000 – ₹35,000 (3-seater solid Teak/Sheesham with 40D cushions) or ₹45,000 – ₹75,000 (L-Shape sectional).
     • Modular Kitchens: ₹1,40,000 – ₹2,20,000 (approx. ₹1,500 – ₹2,200/sq.ft in BWP Marine Ply with German soft-close fittings).
     • Fitted Wardrobes: ₹95,000 – ₹1,50,000 (approx. ₹1,200 – ₹1,800/sq.ft depending on laminate/PU finish).
     • Solid Wood Dining Tables: ₹38,000 – ₹55,000 (6-seater) or ₹55,000 – ₹78,000 (8-seater) in Solid Teak/Sheesham.
     • Custom Beds: ₹45,000 – ₹70,000 (King Size hydraulic storage with cushioned headboard).
     • Wooden Doors & Chaukhats: ₹28,000 – ₹45,000 in seasoned CP Teak.
   - State the completion timeline clearly: 12–18 working days workshop fabrication + 2–3 days fast on-site installation.
   - Explain that exact price is decided after finalizing specific hardware & finish choices.
3. EXPERT BARGAINING & VALUE NEGOTIATION:
   - When a customer says their budget is low (e.g. "my budget is 15000", "too expensive", "kam karo", "bhav osho karo"):
     • Acknowledge their budget with deep respect. Never dismiss them.
     • Explain material realities (plywood, fittings, teak timber raw cost).
     • Propose practical value-engineering compromises (commercial ply mix, hinged vs sliding, platform bed vs hydraulic).
     • Negotiate a realistic middle-ground offer and suggest a free laser measurement visit.
4. OFFER MEASUREMENT VISIT & CHAT ESTIMATION:
   - Offer a free 15-minute on-site laser measurement visit (Saturday 11:30 AM or Sunday 4:00 PM).
   - Also let the customer know that if they are busy or don't have time for a visit, they can confirm right in chat by sharing room photos and rough measurements!
5. CHAT CONFIRMATION (WHEN CUSTOMER DOESN'T HAVE TIME OR CANNOT VISIT):
   - If customer says they don't have time, are busy, cannot meet in person, or prefer chat:
     • Reassure them that we can finalize everything right in chat without an in-person visit!
     • Ask for 4 essentials:
       1. 📸 Clear room / wall photos or a video showing the space (checking skirting, electrical points, ceiling height).
       2. 📏 Rough tape measurements (length × width or height in feet/inches).
       3. 🖼️ Reference photo/Pinterest idea of the design they want made.
       4. 🪵 Preferred material (Solid Teak/Sheesham vs Marine Ply with Laminate/PU polish).
     • Promise to review their photos and send a firm itemized quote and 3D drawing directly in the chat!
6. CONFIRMATION:
   - When customer confirms slot/address OR shares their room photos for chat confirmation, confirm the booking with full details.
7. POST-CONFIRMATION COURTESY:
   - If customer replies "ok", "thank you", "dhanyawad", or "aabhar" after confirmation, warmly thank them and close politely. NEVER re-prompt for time booking once confirmed!

Formatting: Concise for mobile WhatsApp, *bold* highlights, bullet points (•), and tasteful craft emojis (🪵, 🪚, 📐, ✨).
"""


def detect_language(text: str) -> str:
    """Detect customer language: 'gu' (Gujarati), 'hi' (Hindi/Hinglish), or 'en' (English)."""
    text_lower = text.lower()

    # 1. Unicode script detection
    for ch in text:
        # Gujarati Unicode block: U+0A80 to U+0AFF
        if "\u0a80" <= ch <= "\u0aff":
            return "gu"
        # Devanagari (Hindi) Unicode block: U+0900 to U+097F
        if "\u0900" <= ch <= "\u097f":
            return "hi"

    words = set(re.findall(r"\b\w+\b", text_lower))

    # 2. Multi-word phrases in Roman Gujarati
    gu_phrases = [
        "kem cho", "kemcho", "banaavu chhe", "banavu che", "bnavu che",
        "banavvi che", "banavvu che", "bnavvi che", "sofa banavu", "table banavu",
        "kabaat banavu", "ghare aavo", "ketla rupya", "ketlo kharch", "tamare tya",
        "sofa joiye", "mane joiye", "mane banavu"
    ]
    if any(p in text_lower for p in gu_phrases):
        return "gu"

    # Single distinct words in Roman Gujarati
    gu_words = {
        "kemcho", "banaavu", "banavu", "bnavu", "banavvi", "banavvu", "bnavvi", "joiye", "joyiye",
        "chhe", "lakdu", "lakda", "kabaat", "aavjo", "sisam", "mane",
        "aabhar", "shaniwar", "raviwar"
    }
    if words.intersection(gu_words):
        return "gu"

    # 3. Multi-word phrases in Roman Hindi / Hinglish
    hi_phrases = [
        "banana hai", "banwana hai", "banani hai", "bana do", "karna hai",
        "kitna kharcha", "kya price", "kya rate", "aa jao", "aao",
        "sofa banana", "bed banana", "table banana", "thik hai", "theek hai",
        "kitna padega", "bata do"
    ]
    if any(p in text_lower for p in hi_phrases):
        return "hi"

    # Single distinct words in Roman Hindi / Hinglish
    hi_words = {
        "muje", "mujhe", "khidkhi", "khidki", "chahiye", "chahie", "kharcha",
        "bataiye", "batao", "khatiya", "almari", "bhaiya", "shukriya",
        "dhanyawad", "shanivar", "ravivar", "chalega", "namaste", "namaskar"
    }
    if words.intersection(hi_words):
        return "hi"

    return "en"


def get_price_and_timeline_estimate(
    project_type: Optional[str],
    dimensions: Optional[str],
    lang: str = "en",
) -> Tuple[str, str]:
    """Return realistic price estimate range and completion timeline in days, localized."""
    p_type = (project_type or "").lower()
    dim = (dimensions or "").lower()

    if "sofa" in p_type or "couch" in p_type or "સોફા" in p_type or "सोफा" in p_type:
        if "l-shape" in dim or "corner" in dim or "l shape" in dim:
            if lang == "gu":
                price = "₹45,000 – ₹75,000 (L-Shape સેક્શનલ સોફા, સાગવાન/શીશમ ફ્રેમ અને 40D હાઈ-ડેન્સિટી ફોમ સાથે)"
                timeline = "12 થી 15 કામકાજના દિવસો વર્કશોપ બનાવટ + પોલિશ"
            elif lang == "hi":
                price = "₹45,000 – ₹75,000 (L-Shape सेक्शनल सोफा, सागवान/शीशम फ्रेम और 40D हाई-डेंसिटी फोम सहित)"
                timeline = "12 से 15 कार्य दिवस वर्कशॉप निर्माण + पॉलिश"
            else:
                price = "₹45,000 – ₹75,000 (L-Shape sectional in Teak/Sheesham frame with 40D high-resilience foam & stain-resistant fabric)"
                timeline = "12 to 15 working days workshop fabrication + polish"
        elif "3" in dim or "three" in dim or "3-seater" in dim or "૩" in dim or "३" in dim:
            if lang == "gu":
                price = "₹22,000 – ₹35,000 (સોલિડ સાગવાન/શીશમ ૩-સીટર સોફા ફ્રેમ + 40D પ્રીમિયમ ગાદી)"
                timeline = "10 થી 14 કામકાજના દિવસો"
            elif lang == "hi":
                price = "₹22,000 – ₹35,000 (सॉलिड सागवान/शीशम ३-सीटर सोफा फ्रेम + 40D प्रीमियम कुशन)"
                timeline = "10 से 14 कार्य दिवस"
            else:
                price = "₹22,000 – ₹35,000 (Solid Teak/Sheesham 3-seater wooden frame with 40D high-density cushions)"
                timeline = "10 to 14 working days"
        else:
            if lang == "gu":
                price = "₹35,000 – ₹55,000 (૫-સીટર ૩+૧+૧ સોલિડ વુડન સોફા સેટ)"
                timeline = "12 થી 16 કામકાજના દિવસો"
            elif lang == "hi":
                price = "₹35,000 – ₹55,000 (५-सीटर ३+१+१ सॉलिड वुडन सोफा सेट)"
                timeline = "12 से 16 कार्य दिवस"
            else:
                price = "₹35,000 – ₹55,000 (5-seater 3+1+1 wooden sofa set in solid Teak/Sheesham)"
                timeline = "12 to 16 working days"
    elif "kitchen" in p_type or "રસોઈ" in p_type or "रसोई" in p_type:
        if lang == "gu":
            price = "₹1,40,000 – ₹2,20,000 (આશરે ₹1,500 – ₹2,200/ચોરસ ફૂટ IS 710 BWP મરીન પ્લાય અને જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ સાથે)"
            timeline = "14 થી 18 કામકાજના દિવસો (વર્કશોપમાં મશીન ક્રાફ્ટિંગ) + 2 થી 3 દિવસ સાઇટ પર ફિટિંગ"
        elif lang == "hi":
            price = "₹1,40,000 – ₹2,20,000 (लगभग ₹1,500 – ₹2,200/स्क्वायर फीट IS 710 BWP मरीन प्लाई और जर्मन सॉफ्ट-क्लोज़ फिटिंग्स सहित)"
            timeline = "14 से 18 कार्य दिवस (वर्कशॉप में प्रिसिजन क्राफ्टिंग) + 2 से 3 दिन साइट पर असेंबली"
        else:
            price = "₹1,40,000 – ₹2,20,000 (approx. ₹1,500 – ₹2,200/sq.ft in IS 710 BWP Marine Ply with soft-close German fittings)"
            timeline = "14 to 18 working days (precision machine crafting in workshop) + 2 to 3 days on-site assembly"
    elif "wardrobe" in p_type or "cupboard" in p_type or "closet" in p_type or "કબાટ" in p_type or "अलमारी" in p_type:
        if lang == "gu":
            price = "₹95,000 – ₹1,50,000 (આશરે ₹1,200 – ₹1,800/ચોરસ ફૂટ 1mm લેમિનેટ અથવા PU પોલિશ મુજબ)"
            timeline = "12 થી 15 કામકાજના દિવસો વર્કશોપ ફેબ્રિકેશન + 2 દિવસ સાઇટ ફિટિંગ"
        elif lang == "hi":
            price = "₹95,000 – ₹1,50,000 (लगभग ₹1,200 – ₹1,800/स्क्वायर फीट 1mm लैमिनेट अथवा PU पॉलिश के अनुसार)"
            timeline = "12 से 15 कार्य दिवस वर्कशॉप निर्माण + 2 दिन साइट इंस्टॉलेशन"
        else:
            price = "₹95,000 – ₹1,50,000 (approx. ₹1,200 – ₹1,800/sq.ft depending on 1mm laminate vs PU polish & internal organizers)"
            timeline = "12 to 15 working days workshop fabrication + 2 days on-site installation"
    elif "dining" in p_type or "table" in p_type or "ટેબલ" in p_type or "मेज" in p_type:
        if "8" in dim or "8-seater" in dim or "૮" in dim or "८" in dim:
            if lang == "gu":
                price = "₹55,000 – ₹78,000 (ઓરિજિનલ સાગવાન/શીશમ ૮-સીટર ટેબલ ૮ કુશન ખુરશીઓ સાથે)"
            elif lang == "hi":
                price = "₹55,000 – ₹78,000 (सॉलिड सागवान/शीशम ८-सीटर टेबल ८ कुशन कुर्सियों के साथ)"
            else:
                price = "₹55,000 – ₹78,000 (Solid Teak/Sheesham 8-seater with 8 cushioned chairs)"
        else:
            if lang == "gu":
                price = "₹38,000 – ₹55,000 (ઓરિજિનલ સાગવાન/શીશમ ૬-સીટર ટેબલ ૬ કુશન ખુરશીઓ સાથે)"
            elif lang == "hi":
                price = "₹38,000 – ₹55,000 (सॉलिड सागवान/शीशम ६-सीटर टेबल ६ कुशन कुर्सियों के साथ)"
            else:
                price = "₹38,000 – ₹55,000 (Solid Teak/Sheesham 6-seater with 6 cushioned chairs)"
        if lang == "gu":
            timeline = "15 થી 20 કામકાજના દિવસો લાકડાની સીઝનિંગ, મજબૂત સાંધા અને 4-કોટ PU પોલિશ માટે"
        elif lang == "hi":
            timeline = "15 से 20 कार्य दिवस लकड़ी की सीजनिंग, मजबूत जोड़ और 4-कोट PU पॉलिश के लिए"
        else:
            timeline = "15 to 20 working days for timber seasoning, mortise & tenon joinery, and 4-coat PU polish"
    elif "door" in p_type or "દરવાજો" in p_type or "દરવાજા" in p_type or "दरवाज़ा" in p_type or "दरवाजा" in p_type:
        if lang == "gu":
            price = "₹28,000 – ₹45,000 (સીઝન્ડ સીપી/બર્મા સાગવાન મેચિંગ ચોખટ સાથે)"
            timeline = "10 થી 14 કામકાજના દિવસો"
        elif lang == "hi":
            price = "₹28,000 – ₹45,000 (सीजन्ड सीपी/बर्मा सागवान मैचिंग चौखट के साथ)"
            timeline = "10 से 14 कार्य दिवस"
        else:
            price = "₹28,000 – ₹45,000 in seasoned CP/Burma Teak with matching chaukhat frame"
            timeline = "10 to 14 working days"
    elif "bed" in p_type or "palang" in p_type or "પલંગ" in p_type or "पलंग" in p_type:
        if lang == "gu":
            price = "₹45,000 – ₹70,000 (કિંગ સાઈઝ હાઇડ્રોલિક સ્ટોરેજ અને કુશન્ડ હેડબોર્ડ સાથે)"
            timeline = "12 થી 15 કામકાજના દિવસો"
        elif lang == "hi":
            price = "₹45,000 – ₹70,000 (किंग साइज़ हाइड्रोलिक स्टोरेज और कुशन हेडबोर्ड के साथ)"
            timeline = "12 से 15 कार्य दिवस"
        else:
            price = "₹45,000 – ₹70,000 (King Size with hydraulic storage & cushioned headboard)"
            timeline = "12 to 15 working days"
    elif any(k in p_type for k in ["cabinet", "cabinets", "cabinate", "cabinates", "cabinat", "cabenet", "sideboard", "credenza"]):
        if lang == "gu":
            price = "₹1,200 – ₹1,800 પ્રતિ ચોરસ ફૂટ (18mm મરીન પ્લાય + લેમિનેટ/PU પોલિશ)"
            timeline = "12 થી 16 કામકાજના દિવસો વર્કશોપ ફેબ્રિકેશન + 2 દિવસ સાઇટ ફિટિંગ"
        elif lang == "hi":
            price = "₹1,200 – ₹1,800 प्रति स्क्वायर फीट (18mm मरीन प्लाई + लैमिनेट/PU पॉलिश)"
            timeline = "12 से 16 कार्य दिवस वर्कशॉप निर्माण + 2 दिन साइट इंस्टॉलेशन"
        else:
            price = "₹1,200 – ₹1,800 per sq. ft. (18mm Marine Ply + 1mm Laminate or PU polish with German soft-close fittings)"
            timeline = "12 to 16 working days workshop fabrication + 2 days on-site installation"
    elif "window" in p_type or "khidkhi" in p_type or "khidki" in p_type or "bari" in p_type or "બારી" in p_type or "बारी" in p_type or "खिड़की" in p_type:
        if lang == "gu":
            price = "₹1,600 – ₹2,200 પ્રતિ ચોરસ ફૂટ (સીઝન્ડ સાગવાન ચોખટ, 5mm ગ્લાસ અને એસએસ મચ્છર જાળી શટર સાથે)"
            timeline = "10 થી 14 કામકાજના દિવસો"
        elif lang == "hi":
            price = "₹1,600 – ₹2,200 प्रति स्क्वायर फीट (सीजन्ड सागवान चौखट, 5mm ग्लास और SS मच्छर जाली पल्ले सहित)"
            timeline = "10 से 14 कार्य दिवस"
        else:
            price = "₹1,600 – ₹2,200 per sq. ft. in seasoned CP Teak with 5mm glass & SS mosquito mesh shutter"
            timeline = "10 to 14 working days"
    else:
        if lang == "gu":
            price = "₹1,200 – ₹2,000 પ્રતિ ચોરસ ફૂટ (સાગવાન/મરીન પ્લાય અને પોલિશ મુજબ)"
            timeline = "12 થી 18 કામકાજના દિવસો"
        elif lang == "hi":
            price = "₹1,200 – ₹2,000 प्रति स्क्वायर फीट (सागवान/मरीन प्लाई और पॉलिश के अनुसार)"
            timeline = "12 से 18 कार्य दिवस"
        else:
            price = "₹1,200 – ₹2,000 per sq. ft. depending on solid wood vs marine ply + PU/laminate finish"
            timeline = "12 to 18 working days"

    return price, timeline


def parse_dimension_details(dim_str: Optional[str], text_lower: str = "") -> Dict[str, Any]:
    """Parse length, width, area (sqft), seats, or unit counts dynamically."""
    res: Dict[str, Any] = {
        "length": None,
        "width": None,
        "sqft": None,
        "unit": "ft",
        "seats": None,
        "quantity": 1,
        "raw": dim_str or "",
    }
    target = f"{dim_str or ''} {text_lower}"

    # Check quantity like '2 khidkhi', '2 windows'
    q_match = re.search(r"(\d+)\s*(?:khidkhi|khidki|windows?|doors?|kabaat|बारी|બારી|खिड़की|દરવાજા)", target)
    if q_match:
        res["quantity"] = int(q_match.group(1))

    # Parse rectangular dimensions (e.g. 10*20, 10x20, 10 by 20, 12x9, 4x4, 10×10)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|X|×|\*|by|બાય|बाय)\s*(\d+(?:\.\d+)?)", target)
    if match:
        l = float(match.group(1))
        w = float(match.group(2))
        res["length"] = l
        res["width"] = w
        # Check if inches
        if "inch" in target:
            res["sqft"] = round((l * w) / 144.0, 1)
            res["unit"] = "inch"
        else:
            res["sqft"] = round(l * w, 1)
            res["unit"] = "ft"
        return res

    # Seater / sofa count (e.g. '3 seater', '3 sofa', '5 seater', '3 seat', '3-seater')
    s_match = re.search(r"(\d+)\s*[-]?\s*(?:seater|seat|sofa|સીટર|सीटर|સોફા|सोफा)", target)
    if s_match:
        res["seats"] = int(s_match.group(1))
        return res

    # King / Queen beds
    if "king" in target:
        res["sqft"] = 39.0  # 6.5 x 6 ft
        res["length"] = 6.5
        res["width"] = 6.0
    elif "queen" in target:
        res["sqft"] = 32.5  # 6.5 x 5 ft
        res["length"] = 6.5
        res["width"] = 5.0

    return res


def calculate_turnkey_quote(
    project_type: Optional[str],
    dim_info: Dict[str, Any],
    lang: str = "en",
) -> Dict[str, Any]:
    """Calculate mathematically exact turn-key quotes, materials, labour, and transport breakdown."""
    p_type = (project_type or "cabinet").lower()
    sqft = dim_info.get("sqft") or 80.0
    qty = dim_info.get("quantity") or 1
    seats = dim_info.get("seats")

    # 1. Custom Wardrobe / Cabinet / Storage
    if any(k in p_type for k in ["cabinet", "cabinets", "cabinate", "cabinates", "cabinat", "cabenet", "sideboard", "credenza", "wardrobe", "cupboard", "almirah", "almari", "કબાટ", "अलमारी"]):
        total_sqft = float(sqft * qty)
        rate_lam = 1380
        total_lam = int(round(total_sqft * rate_lam))
        rate_pu = 1750
        total_pu = int(round(total_sqft * rate_pu))

        # Itemized breakdown for Laminate
        mat_lam = int(round(total_lam * 0.50))
        fit_lam = int(round(total_lam * 0.12))
        surf_lam = int(round(total_lam * 0.15))
        labour_lam = int(round(total_lam * 0.19))
        transport_lam = total_lam - (mat_lam + fit_lam + surf_lam + labour_lam)

        # Itemized breakdown for PU
        mat_pu = int(round(total_pu * 0.42))
        fit_pu = int(round(total_pu * 0.10))
        surf_pu = int(round(total_pu * 0.22))
        labour_pu = int(round(total_pu * 0.22))
        transport_pu = total_pu - (mat_pu + fit_pu + surf_pu + labour_pu)

        timeline = "14 થી 18 કામકાજના દિવસો" if lang == "gu" else ("14 से 18 कार्य दिवस" if lang == "hi" else "14 to 18 working days")
        return {
            "sqft": total_sqft,
            "rate_lam": rate_lam,
            "total_lam": total_lam,
            "rate_pu": rate_pu,
            "total_pu": total_pu,
            "breakdown_lam": {
                "materials": mat_lam,
                "fittings": fit_lam,
                "finish": surf_lam,
                "labour": labour_lam,
                "transport": transport_lam,
            },
            "breakdown_pu": {
                "materials": mat_pu,
                "fittings": fit_pu,
                "finish": surf_pu,
                "labour": labour_pu,
                "transport": transport_pu,
            },
            "timeline": timeline,
            "type": "cabinet_wardrobe"
        }

    # 2. Windows / Khidkhi
    elif any(k in p_type for k in ["window", "khidkhi", "khidki", "bari", "બારી", "बारी", "खिड़की"]):
        base_sqft = sqft if (dim_info.get("length") and dim_info.get("width")) else 16.0
        total_sqft = float(base_sqft * qty)
        rate = 1950
        total_cost = int(round(total_sqft * rate))

        mat = int(round(total_cost * 0.55))
        glass_mesh = int(round(total_cost * 0.15))
        fittings = int(round(total_cost * 0.08))
        labour = int(round(total_cost * 0.18))
        transport = total_cost - (mat + glass_mesh + fittings + labour)

        timeline = "10 થી 14 કામકાજના દિવસો" if lang == "gu" else ("10 से 14 कार्य दिवस" if lang == "hi" else "10 to 14 working days")
        return {
            "sqft": total_sqft,
            "rate": rate,
            "total": total_cost,
            "quantity": qty,
            "breakdown": {
                "timber": mat,
                "glass_mesh": glass_mesh,
                "fittings": fittings,
                "labour": labour,
                "transport": transport,
            },
            "timeline": timeline,
            "type": "window"
        }

    # 3. Modular Kitchen
    elif any(k in p_type for k in ["kitchen", "રસોઈ", "रसोई"]):
        total_sqft = float(sqft * qty)
        rate = 1850
        total_cost = int(round(total_sqft * rate))

        mat = int(round(total_cost * 0.46))
        fittings = int(round(total_cost * 0.23))
        finish = int(round(total_cost * 0.15))
        labour = int(round(total_cost * 0.13))
        transport = total_cost - (mat + fittings + finish + labour)

        timeline = "14 થી 18 કામકાજના દિવસો" if lang == "gu" else ("14 से 18 कार्य दिवस" if lang == "hi" else "14 to 18 working days")
        return {
            "sqft": total_sqft,
            "rate": rate,
            "total": total_cost,
            "breakdown": {
                "materials": mat,
                "fittings": fittings,
                "finish": finish,
                "labour": labour,
                "transport": transport,
            },
            "timeline": timeline,
            "type": "kitchen"
        }

    # 4. Dining Table
    elif any(k in p_type for k in ["dining", "table", "ટેબલ", "मेज"]):
        is_8_seater = seats == 8 or "8" in str(dim_info.get("raw", ""))
        total_cost = 68000 if is_8_seater else 46000
        timber = int(round(total_cost * 0.56))
        cushions = int(round(total_cost * 0.15))
        labour = int(round(total_cost * 0.20))
        transport = total_cost - (timber + cushions + labour)

        timeline = "15 થી 20 કામકાજના દિવસો" if lang == "gu" else ("15 से 20 कार्य दिवस" if lang == "hi" else "15 to 20 working days")
        return {
            "total": total_cost,
            "is_8_seater": is_8_seater,
            "breakdown": {
                "timber": timber,
                "cushions": cushions,
                "labour": labour,
                "transport": transport,
            },
            "timeline": timeline,
            "type": "dining"
        }

    # 5. Wooden Sofa Set
    elif any(k in p_type for k in ["sofa", "couch", "સોફા", "सोफा"]):
        raw_dim = str(dim_info.get("raw", "")).lower()
        is_l_shape = "l-shape" in raw_dim or "corner" in raw_dim
        is_5_seater = seats == 5 or "5" in raw_dim
        if is_l_shape:
            total_cost = 62000
        elif is_5_seater:
            total_cost = 46000
        else:
            total_cost = 28500

        timber = int(round(total_cost * 0.56))
        foam = int(round(total_cost * 0.23))
        labour = int(round(total_cost * 0.16))
        transport = total_cost - (timber + foam + labour)

        timeline = "12 થી 16 કામકાજના દિવસો" if lang == "gu" else ("12 से 16 कार्य दिवस" if lang == "hi" else "12 to 16 working days")
        return {
            "total": total_cost,
            "breakdown": {
                "timber": timber,
                "foam": foam,
                "labour": labour,
                "transport": transport,
            },
            "timeline": timeline,
            "type": "sofa"
        }

    # 6. Custom Storage Bed
    elif any(k in p_type for k in ["bed", "palang", "પલંગ", "पलंग"]):
        is_king = "king" in str(dim_info.get("raw", "")).lower() or sqft >= 36.0
        total_cost = 56000 if is_king else 34000
        ply = int(round(total_cost * 0.50))
        mechanism = int(round(total_cost * 0.12))
        headboard = int(round(total_cost * 0.14))
        labour = int(round(total_cost * 0.20))
        transport = total_cost - (ply + mechanism + headboard + labour)

        timeline = "12 થી 15 કામકાજના દિવસો" if lang == "gu" else ("12 से 15 कार्य दिवस" if lang == "hi" else "12 to 15 working days")
        return {
            "total": total_cost,
            "breakdown": {
                "ply": ply,
                "mechanism": mechanism,
                "headboard": headboard,
                "labour": labour,
                "transport": transport,
            },
            "timeline": timeline,
            "type": "bed"
        }

    # Default / General
    total_sqft = float(sqft * qty)
    rate = 1400
    total_cost = int(round(total_sqft * rate))
    return {
        "sqft": total_sqft,
        "rate": rate,
        "total": total_cost,
        "timeline": "12 થી 18 કામકાજના દિવસો" if lang == "gu" else ("12 से 18 कार्य दिवस" if lang == "hi" else "12 to 18 working days"),
        "type": "general"
    }


def generate_bargaining_response(session: CustomerSession, budget: Optional[int], user_text: str) -> str:
    """Generate master craftsman negotiation, value-engineering compromise, and counter-offer."""
    p_type = (session.project_type or "woodwork").lower()
    b_val = budget or session.customer_budget
    lang = getattr(session, "language", "en") or "en"

    # 1. Custom Bed Bargaining
    if "bed" in p_type or "palang" in p_type or "પલંગ" in p_type or "पलंग" in p_type:
        if b_val and b_val < 20000:
            if lang == "gu":
                return (
                    f"હું તમારા *₹{b_val:,}* ના બજેટને સંપૂર્ણ માન આપું છું, જી! 🙏\n\n"
                    f"કારીગર તરીકે હું સ્પષ્ટ કહું તો: IS 710 વોટરપ્રૂફ મરીન પ્લાય અને હેવી-ડ્યુટી હાઇડ્રોલિક પંપ સાથે કિંગ બેડ બનાવવા માટે માત્ર કાચો માલ જ ₹22,000+ નો આવે છે.\n\n"
                    f"પરંતુ આપણે મજબૂત અને ટકાઉ વિકલ્પ બનાવી શકીએ છીએ:\n\n"
                    f"• *મજબૂત ક્વીન પ્લેટફોર્મ બેડ*: સીઝન્ડ હાર્ડવુડ પ્લાયવુડ અને 1mm મેટ લેમિનેટ સાથે આશરે *₹22,000 – ₹25,000* માં બની જશે (જે માર્કેટના સસ્તા પાર્ટિકલ બોર્ડ કરતાં વર્ષો સુધી ટકશે).\n"
                    f"• *ડ્રોઅર સ્ટોરેજ*: મોંઘા હાઇડ્રોલિક પંપને બદલે નીચે સ્મૂધ પુલ-આઉટ ડ્રોઅર્સ રાખી શકીએ.\n"
                    f"• *કારીગર ઓફર*: જો તમે *₹22,000* સુધી કરી શકો, તો હું વ્યક્તિગત રીતે ઉત્તમ ક્વોલિટીનો બેડ બનાવી આપીશ!\n\n"
                    f"શું આપણે આ *₹22,000* ની ડિઝાઇન આગળ વધારીએ, કે પછી રૂબરૂ માપણી રાખીને સેમ્પલ્સ જોઈ લઈએ? 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"मैं आपके *₹{b_val:,}* के बजट का पूरा सम्मान करता हूँ, जी! 🙏\n\n"
                    f"एक कारीगर के नाते सच्ची बात बताऊं तो: IS 710 वाटरप्रूफ मरीन प्लाई और हैवी हाइड्रोलिक पंप के साथ किंग बेड का केवल कच्चा माल और हार्डवेयर ही ₹22,000+ का आता है।\n\n"
                    f"लेकिन हम आपके बजट में बहुत बढ़िया विकल्प बना सकते हैं:\n\n"
                    f"• *मजबूत क्वीन प्लेटफॉर्म बेड*: सीजन्ड हार्डवुड प्लाई और 1mm मैट लैमिनेट में लगभग *₹22,000 – ₹25,000* में आजीवन चलने वाला बेड बन जाएगा।\n"
                    f"• *ड्रॉअर स्टोरेज*: महंगे हाइड्रोलिक पंप की जगह नीचे स्मूथ पुल-आउट ड्रॉअर्स दे सकते हैं।\n"
                    f"• *कारीगर काउंटर-ऑफर*: अगर आप *₹22,000* तक कर सकते हैं, तो मैं खुद आपके लिए बेहतरीन फिनिश में तैयार करवा दूंगा!\n\n"
                    f"क्या आप यह *₹22,000* का डिज़ाइन देखना चाहेंगे, या फिर घर पर नाप लेकर सैंपल्स दिखा दें? 🪵✨"
                )
            else:
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
            if lang == "gu":
                return (
                    f"તમારું *₹{b_val:,}* નું બજેટ જણાવવા બદલ આભાર! 🪵\n\n"
                    f"જ્યારે અમારો કિંગ હાઇડ્રોલિક બેડ ₹45k–₹70k નો છે, અમે તમારા બજેટમાં જ *₹26,000 – ₹32,000* માં પ્રીમિયમ હાર્ડવુડ પ્લાય સાથે ૨ ડ્રોઅર સ્ટોરેજ વાળો સુંદર *ક્વીન પ્લેટફોર્મ બેડ* બનાવી શકીએ છીએ!\n\n"
                    f"શું અમારી ટીમ લાકડા અને લેમિનેટના સેમ્પલ્સ લઈને તમને બતાવવા આવે? 📐"
                )
            elif lang == "hi":
                return (
                    f"अपना *₹{b_val:,}* का बजट साझा करने के लिए धन्यवाद! 🪵\n\n"
                    f"जहाँ हमारा किंग हाइड्रोलिक बेड ₹45k–₹70k का है, वहीं हम आपके बजट में *₹26,000 – ₹32,000* के अंदर प्रीमियम हार्डवुड प्लाई से २ बॉटम स्टोरेज ड्रॉअर्स वाला मजबूत *क्वीन प्लेटफॉर्म बेड* बना सकते हैं!\n\n"
                    f"क्या हमारी टीम लकड़ी और लैमिनेट के सैंपल्स लेकर आपके पास आए? 📐"
                )
            else:
                return (
                    f"Thank you for sharing your budget of *₹{b_val:,}*! 🪵\n\n"
                    f"While our King Size hydraulic bed with cushioned headboard is ₹45k–₹70k, we can handcraft a beautiful *Queen Platform Bed with 2 bottom storage drawers* in premium commercial hardwood ply for *₹26,000 – ₹32,000*, right in your range!\n\n"
                    f"Would you like our team to bring timber and laminate swatches to show you how sturdy this build is? 📐"
                )

    # 2. Sofa Bargaining
    if "sofa" in p_type or "couch" in p_type or "સોફા" in p_type or "सोफा" in p_type:
        if b_val and b_val < 20000:
            if lang == "gu":
                return (
                    f"હું તમારા *₹{b_val:,}* ના બજેટને માન આપું છું, જી! 🙏\n\n"
                    f"સોલિડ સાગવાન/શીશમ ફ્રેમ અને 40D હાઈ-ડેન્સિટી ફોમ સાથે ૩-સીટર સોફા માટે લાકડું, ફેબ્રિક અને કુશનનો ખર્ચ ₹18,000+ થાય છે.\n\n"
                    f"જો તમે *₹20,000 – ₹22,000* સુધી કરી શકો, તો અમે શીશમ વુડ ફ્રેમ અને પ્રીમિયમ કુશનિંગ સાથે મજબૂત સોફા તૈયાર કરી આપીશું!\n\n"
                    f"શું અમે સેમ્પલ્સ સાથે તમારી મુલાકાત ગોઠવીએ? 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"मैं आपके *₹{b_val:,}* के बजट का आदर करता हूँ, जी! 🙏\n\n"
                    f"सॉलिड सागवान/शीशम लकड़ी और 40D हाई-डेंसिटी फोम वाले ३-सीटर सोफे के लिए लकड़ी, कुशन और फैब्रिक का खर्च ही ₹18,000+ आता है।\n\n"
                    f"अगर आप *₹20,000 – ₹22,000* तक खींच सकें, तो हम मजबूत शीशम वुड फ्रेम और वॉशेबल फैब्रिक में टिकाऊ सोफा तैयार कर देंगे!\n\n"
                    f"क्या हम कपड़े और लकड़ी के सैंपल लेकर आपके घर आएं? 🪵✨"
                )
            else:
                return (
                    f"I respect your budget of *₹{b_val:,}*, Ji! 🙏\n\n"
                    f"For a solid hardwood 3-seater sofa with 40D high-resilience foam, raw timber, cushions, and washable fabric alone cost ₹18,000+.\n\n"
                    f"If you can meet us around *₹20,000 – ₹22,000*, we can craft a sturdy solid Sheesham 3-seater with washable fabric covers for you!\n\n"
                    f"Shall we bring fabric and wood samples to your site? 🪵✨"
                )

    # 3. Modular Kitchen Bargaining
    if "kitchen" in p_type or "રસોઈ" in p_type or "रसोई" in p_type:
        if b_val and b_val < 100000:
            if lang == "gu":
                return (
                    f"હું તમારી વાત સમજી શકું છું, જી! *₹{b_val:,}* ના બજેટમાં આપણે સ્માર્ટ પ્લાનિંગ કરી શકીએ છીએ.\n\n"
                    f"મોડ્યુલર કિચનમાં સિંક નીચે બોઇલિંગ વોટરપ્રૂફ (IS 710) પ્લાય જરૂરી છે. ખર્ચ ઘટાડવા માટે:\n"
                    f"• *મિક્સ મટિરિયલ*: નીચેના ભીના ભાગમાં BWP મરીન પ્લાય અને ઉપરના સૂકા કબાટમાં કોમર્શિયલ પ્લાય વાપરીને કિંમત *₹90,000 – ₹1,10,000* સુધી લાવી શકીએ.\n"
                    f"• *ઓપન શેલ્વ્સ*: મોંઘા બોક્સને બદલે ફ્લોટિંગ શેલ્વ્સ.\n\n"
                    f"જો તમે *₹90,000 – ₹95,000* સુધી પહોંચી શકો, તો જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ સાથે ટકાઉ કિચન બની જશે! શું અમે સાઇટ પર આવીને લેઆઉટ પ્લાન બતાવીએ? 📐✨"
                )
            elif lang == "hi":
                return (
                    f"मैं समझता हूँ, जी! *₹{b_val:,}* के बजट में हम स्मार्ट तरीके से काम कर सकते हैं।\n\n"
                    f"किचन में सिंक के नीचे बॉइलिंग वाटरप्रूफ (IS 710) प्लाई जरूरी है। बजट में लाने के लिए:\n"
                    f"• *स्मार्ट मटेरियल मिक्स*: नीचे के हिस्से में BWP मरीन प्लाई और ऊपर सूखे कैबिनेट में कमर्शियल प्लाई का इस्तेमाल करके बजट *₹90,000 – ₹1,10,000* पर लाया जा सकता है।\n"
                    f"• *सॉफ्ट-क्लोज फिटिंग्स*: अगर आप *₹90,000 – ₹95,000* तक कर सकें, तो जर्मन फिटिंग्स के साथ वाटरप्रूफ किचन तैयार हो जाएगा!\n\n"
                    f"क्या हम साइट पर आकर लेआउट समझा दें? 📐✨"
                )
            else:
                return (
                    f"I hear you, Ji! Working within *₹{b_val:,}* is something we can help optimize smartly.\n\n"
                    f"For modular kitchens, using boiling water-proof (IS 710) ply is essential near sinks so wood never rots or swells. To bring the cost down closer to your budget:\n\n"
                    f"• *Value Material Mix*: We can use BWP marine ply for wet base units and durable commercial ply with 0.8mm laminate for dry overhead cabinets, bringing the cost down to *₹90,000 – ₹1,10,000*.\n"
                    f"• *Layout Optimization*: Mixing open floating shelves with core modular base cabinets.\n\n"
                    f"If you can meet us around *₹90,000 – ₹95,000*, we can deliver a dependable, moisture-proof kitchen with soft-close German fittings. Shall we visit your site to suggest a budget-optimized layout? 📐✨"
                )

    # 4. Custom Wardrobe Bargaining
    if "wardrobe" in p_type or "cupboard" in p_type or "closet" in p_type or "કબાટ" in p_type or "अलमारी" in p_type:
        if b_val and b_val < 60000:
            if lang == "gu":
                return (
                    f"તમારું *₹{b_val:,}* નું બજેટ જણાવવા બદલ આભાર! 🪵\n\n"
                    f"સ્લાઇડિંગ ડોર ટ્રેકનો ખર્ચ જ ₹15k–₹20k થઈ જાય છે. તમારા બજેટમાં:\n"
                    f"• *હિન્જ્ડ શટર્સ*: સાદા ખુલ્લા થતા દરવાજા જર્મન સોફ્ટ-ક્લોઝ હિન્જિસ સાથે ₹18,000 ની સીધી બચત કરાવશે.\n"
                    f"• *કુલ કિંમત*: આ રીતે વોર્ડરોબ *₹55,000 – ₹65,000* માં મજબૂત બની જશે.\n\n"
                    f"શું અમે દીવાલની સાઇઝ માપીને પક્કો હિસાબ કાઢી આપીએ? 🪚"
                )
            elif lang == "hi":
                return (
                    f"अपना *₹{b_val:,}* का बजट साझा करने के लिए धन्यवाद! 🪵\n\n"
                    f"स्लाइडिंग डोर ट्रैक का खर्च ही ₹15k–₹20k होता है। आपके बजट के अनुसार:\n"
                    f"• *हिन्ज्ड शटर्स*: सामान्य खुलने वाले दरवाज़े जर्मन सॉफ्ट-क्लोज़ कब्जों के साथ ₹18,000 तुरंत बचाते हैं।\n"
                    f"• *कुल लागत*: कुल खर्च *₹55,000 – ₹65,000* के अंदर आ जाएगा।\n\n"
                    f"क्या हम दीवार का नाप लेकर बिना लकड़ी की बर्बादी के पक्का कोटेशन दे दें? 🪚"
                )
            else:
                return (
                    f"I appreciate you sharing your budget of *₹{b_val:,}*! 🪵\n\n"
                    f"Sliding door track mechanisms alone cost ₹15k–₹20k. To give you the best durability for your budget:\n\n"
                    f"• *Hinged Shutters*: Classic hinged doors with soft-close German hinges save you ₹18,000 instantly.\n"
                    f"• *Smart Partitioning*: Streamlined internal drawers with commercial hardwood ply, bringing the total to *₹55,000 – ₹65,000*.\n\n"
                    f"Shall we measure your wall space during our free visit to calculate an exact quote with zero wood wastage? 🪚"
                )

    # 5. Dining Table Bargaining
    if "dining" in p_type or "table" in p_type or "ટેબલ" in p_type or "मेज" in p_type:
        if b_val and b_val < 25000:
            if lang == "gu":
                return (
                    f"હું તમારા *₹{b_val:,}* ના બજેટને સમજું છું! 🙏\n\n"
                    f"સીઝન્ડ સાગવાન કે શીશમ પેઢીઓ સુધી ટકે છે. *₹24,000 – ₹28,000* માં અમે સોલિડ શીશમ ૪-સીટર ટેબલ, અથવા ૬-સીટર ટેબલ સાથે એક બાજુ લાકડાની બેન્ચ બનાવી શકીએ છીએ (જે ૨ ખુરશીઓનો ખર્ચ બચાવે છે)!\n\n"
                    f"શું તમને *₹24,000* માં બેન્ચ કોમ્બિનેશન અનુકૂળ રહેશે? 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"मैं आपके *₹{b_val:,}* के बजट को समझता हूँ! 🙏\n\n"
                    f"सीजन्ड सागवान या शीशम पीढ़ियों तक चलता है। लगभग *₹24,000 – ₹28,000* में हम सॉलिड शीशम ४-सीटर टेबल, या ६-सीटर टेबल के साथ एक तरफ वुडन बेंच बना सकते हैं (जिससे २ कुर्सियों का खर्च बचता है)!\n\n"
                    f"क्या आप *₹24,000* के आसपास बेंच कॉम्बिनेशन देखना चाहेंगे? 🪵✨"
                )
            else:
                return (
                    f"I understand your budget of *₹{b_val:,}*! 🙏\n\n"
                    f"Solid seasoned Teak or Sheesham is dense timber that lasts generations. For around *₹24,000 – ₹28,000*, we can craft a solid Sheesham 4-seater table, or a 6-seater table paired with a wooden dining bench on one side (which looks modern and saves the cost of 2 individual chairs)!\n\n"
                    f"Would you be open to a 4-seater or a bench combination around *₹24,000*? 🪵✨"
                )

    # 6. General Discount or Bargaining Request
    budget_mention = f" of *₹{b_val:,}*" if b_val else ""
    if lang == "gu":
        return (
            f"હું તમારા બજેટ{budget_mention} ને સંપૂર્ણ સમજું છું, જી! 🙏\n\n"
            f"વર્કશોપ-ડાયરેક્ટ કારીગર તરીકે અમારા ભાવ શોરૂમ કરતાં પહેલેથી જ 25–30% ઓછા છે.\n\n"
            f"છતાં, જો તમે માપણી વિઝિટ વખતે ફાઇનલ કરશો, તો હું *5% થી 8% કારીગર ડિસ્કાઉન્ટ* અથવા *જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ ફ્રી* કરી આપીશ! 🪵✨\n\n"
            f"શું આ *શનિવારે સવારે 11:30 વાગ્યે* અથવા *રવિવારે સાંજે 4:00 વાગ્યે* ફ્રી માપણી મુલાકાત ગોઠવીએ? 📐"
        )
    elif lang == "hi":
        return (
            f"मैं आपके बजट{budget_mention} को पूरी तरह समझता हूँ, जी! 🙏\n\n"
            f"वर्कशॉप-डायरेक्ट होने के कारण हमारे दाम बड़े शोरूम से 25–30% कम रहते हैं क्योंकि हमारा शोरूम का किराया नहीं होता।\n\n"
            f"फिर भी, अगर आप हमारी नाप विज़िट के दौरान फाइनल करते हैं, तो मैं *5% से 8% कारीगर डिस्काउंट* या *जर्मन सॉफ्ट-क्लोज़ फिटिंग्स मुफ्त* लगा दूंगा! 🪵✨\n\n"
            f"क्या हम इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* 15 मिनट की फ्री विज़िट तय कर लें? 📐"
        )
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
    language: str = "en"  # "en", "gu", "hi"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    history: List[Dict[str, Any]] = field(default_factory=list)  # [{"role": "user"|"model", "text": "..."}]
    project_type: Optional[str] = None
    dimensions: Optional[str] = None
    preferred_materials: List[str] = field(default_factory=list)
    customer_budget: Optional[int] = None
    negotiation_stage: str = "none"  # "none", "bargaining", "compromise_offered", "accepted"
    appointment_status: str = "none"  # "none", "requested", "confirmed"
    appointment_slot: Optional[str] = None
    consultation_mode: str = "in_person"  # "in_person" or "virtual"
    notes: List[str] = field(default_factory=list)
    # Phase 1: State Machine & CRM integration
    lead_status: str = "NEW_ENQUIRY"
    locality: Optional[str] = None
    site_address: Optional[str] = None
    human_handover: bool = False
    answered_fields: Set[str] = field(default_factory=set)
    just_confirmed_booking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("answered_fields"), set):
            d["answered_fields"] = list(d["answered_fields"])
        return d


class SessionStore:
    """Thread-safe multi-turn session repository."""

    def __init__(self, persist_db: bool = False) -> None:
        self._sessions: Dict[str, CustomerSession] = {}
        self._lock = threading.Lock()
        self.persist_db = persist_db

    def get_or_create(self, phone_number: str, customer_name: Optional[str] = None) -> CustomerSession:
        with self._lock:
            clean_phone = phone_number.strip().lstrip("+")
            invalid_names = {
                "others", "other", "customer", "client", "user", "admin", "contact",
                "unknown", "test", "demo", "none", "null", "false", "true", "undefined",
                "whatsapp", "someone", "person", "guest", "friend", "caller", "profile"
            }
            valid_name = customer_name.strip() if customer_name else None
            if valid_name and (valid_name.lower() in invalid_names or valid_name.lower().startswith("client")):
                valid_name = None

            if clean_phone not in self._sessions:
                # Hydrate from persistent SQLite CRM if enabled
                db_cust = None
                if self.persist_db:
                    try:
                        db_cust = crm.get_customer(clean_phone)
                    except Exception:
                        pass

                if db_cust:
                    stored_history = []
                    try:
                        stored_history = crm.get_conversation_history(clean_phone)
                    except Exception:
                        pass
                    sess = CustomerSession(
                        phone_number=clean_phone,
                        customer_name=valid_name or db_cust.get("name") or f"Client {clean_phone[-4:]}",
                        language=db_cust.get("language") or "en",
                        created_at=db_cust.get("created_at") or time.time(),
                        updated_at=db_cust.get("updated_at") or time.time(),
                        project_type=db_cust.get("project_type"),
                        dimensions=db_cust.get("dimensions"),
                        preferred_materials=db_cust.get("preferred_materials") or [],
                        customer_budget=db_cust.get("budget"),
                        consultation_mode=db_cust.get("consultation_mode") or "in_person",
                        lead_status=db_cust.get("lead_status") or "NEW_ENQUIRY",
                        locality=db_cust.get("locality"),
                        human_handover=bool(db_cust.get("human_handover", False)),
                        notes=[db_cust.get("notes")] if db_cust.get("notes") else [],
                        history=stored_history,
                    )
                else:
                    sess = CustomerSession(
                        phone_number=clean_phone,
                        customer_name=valid_name or f"Client {clean_phone[-4:]}",
                    )
                self._sessions[clean_phone] = sess

            session = self._sessions[clean_phone]
            if valid_name and session.customer_name != valid_name:
                session.customer_name = valid_name
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


ADDRESS_WORDS = [
    # Premises, buildings, and unit types
    "flat", "apartment", "apartments", "tower", "towers", "road", "street",
    "sector", "phase", "block", "society", "colony", "layout", "nagar", "nagor",
    "bungalow", "bunglow", "villa", "villas", "circle", "cross", "plaza", "wing",
    "complex", "arcade", "residency", "heights", "enclave", "building",
    "floor", "house", "makan", "ghar", "nivas", "niwas", "kunj", "kutir",
    "lane", "gali", "rasta", "marg", "pole", "pol", "khadki", "plot",
    "estate", "chawl", "avenue",
    # Landmarks
    "opposite", "near", "beside", "behind", "next to", "close to", "in front",
    # Prominent cities & areas (Gujarat and major metros)
    "ahmedabad", "amdavad", "surat", "vadodara", "baroda", "rajkot", "gandhinagar",
    "bhavnagar", "jamnagar", "junagadh", "anand", "nadiad", "morbi", "mehsana",
    "mumbai", "pune", "delhi", "bangalore", "bengaluru", "hyderabad", "chennai",
    "nehrunagar", "nehrunager", "satellite", "paldi", "bopal", "south bopal",
    "gota", "adajan", "vesu", "varachha", "vastrapur", "maninagar", "thaltej",
    "bodakdev", "navrangpura", "prahladnagar", "chandkheda", "ranip", "ghatlododia",
    "ghatlodia", "naranpura", "sabarmati", "motera", "memnagar", "ambawadi",
    "ellisbridge", "vejalpur", "jodhpur", "shilaj", "shela", "science city",
    "nikol", "naroda", "odhav", "narol", "vatva", "iscon", "sg highway",
    "s.g. highway", "c.g. road", "cg road", "ashram road", "sindhu bhavan",
    # Gujarati script
    "સોસાયટી", "નગર", "રોડ", "બંગલો", "ફ્લેટ", "સર્કલ", "પ્લાઝા", "વિંગ",
    "કોમ્પ્લેક્સ", "રેસિડેન્સી", "રેસીડેન્સી", "હાઈટ્સ", "બિલ્ડીંગ", "ઘર",
    "મકાન", "પાસે", "સામે", "પાછળ", "અમદાવાદ", "સુરત", "વડોદરા", "રાજકોટ",
    "ગાંધીનગર", "નહેરુનગર", "બોપલ", "સેટેલાઇટ", "ચાંદખેડા", "રાણીપ", "ગોટા",
    # Hindi script
    "सोसायटी", "नगर", "रोड", "बंगला", "फ्लैट", "सर्कल", "प्लाज़ा", "प्लाजा",
    "विंग", "कॉम्प्लेक्स", "रेसीडेंसी", "रेसिडेंसी", "हाइट्स", "बिल्डिंग",
    "घर", "मकान", "पास", "सामने", "पीछे", "अहमदाबाद", "सूरत", "वडोदरा",
    "राजकोट", "गांधीनगर", "नेहरूनगर", "बोपल", "सैटेलाइट"
]
ADDRESS_SHORT_WORDS = {"rd", "st", "nr", "opp", "flr", "apt", "bldg"}

def has_address_marker(text: str) -> bool:
    text_lower = text.lower()
    words = set(re.findall(r"\b\w+\b", text_lower))
    if any(marker in text_lower for marker in ADDRESS_WORDS):
        return True
    if bool(words.intersection(ADDRESS_SHORT_WORDS)) or "b/h" in text_lower:
        return True
    return False


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
        clean_tokens = set(re.sub(r"[^\w\s\u0900-\u097F\u0A80-\u0AFF]", " ", text_lower).split())
        words = set(re.findall(r"\b\w+\b", text_lower)).union(clean_tokens)

        # Extract Ahmedabad locality if present
        loc = detect_ahmedabad_locality(user_text)
        if loc:
            session.locality = loc

        # Detect and persist language
        detected_lang = detect_language(user_text)
        english_intent_words = {
            "i", "want", "to", "make", "need", "looking", "for", "please", "price",
            "how", "much", "cost", "can", "you", "build", "create", "what", "is"
        }
        if detected_lang in ("gu", "hi"):
            session.language = detected_lang
        elif len(words.intersection(english_intent_words)) >= 2:
            if not any("\u0a80" <= ch <= "\u0aff" or "\u0900" <= ch <= "\u097f" for ch in user_text):
                session.language = "en"
        elif not getattr(session, "language", None):
            session.language = detected_lang or "en"

        # Project type detection (Multilingual: Gujarati, Hindi, English, and common typos)
        matched_items: List[str] = []

        # 1. Wardrobe / Cupboard / Almirah
        if any(w in text_lower for w in [
            "wardrobe", "wardrobes", "wardrob", "wardroob", "vadrob", "wadrobe", "ward robe",
            "cupboard", "cupbord", "cubboard", "closet", "almirah", "almari", "kabaat", "kapat",
            "કબાટ", "अलमारी", "अलमीरा"
        ]):
            matched_items.append("Custom Wardrobe")

        # 2. Cabinet / Credenza / Sideboard
        if any(w in text_lower for w in [
            "cabinet", "cabinets", "cabinate", "cabinates", "cabinat", "cabenet", "cabenat", "kabinet",
            "sideboard", "credenza", "crockery unit", "crockery cabinet", "crockery",
            "storage cabinet", "કેબિનેટ", "कैबिनेट"
        ]) and "Custom Wardrobe" not in matched_items:
            matched_items.append("Custom Storage Cabinet")

        # 3. Modular Kitchen
        if any(w in text_lower for w in [
            "kitchen", "kitchens", "kichen", "kitcen", "kicthan", "modular kitchen",
            "rasoi", "રસોઈ", "રંસોઈ", "રંસોઇ", "રંગોઈ", "रसोई", "किचन"
        ]):
            matched_items.append("Modular Kitchen")

        # 4. Windows
        if any(w in text_lower for w in [
            "window", "windows", "khidki", "khidkhi", "khidaki", "khidkiya", "khidkiyan",
            "bari", "બારી", "બારીઓ", "बारी", "खिड़की", "खिड़कियां", "खिडकी", "खिडकिया"
        ]):
            matched_items.append("Custom Wooden Windows")

        # 5. Dining Table
        if any(w in text_lower for w in [
            "dining", "dinning", "dining table", "dinning table", "dinner table", "table",
            "chair", "mej", "ટેબલ", "ડાઇનિંગ", "मेज", "डाइनिंग", "डाइनिंग टेबल", "ડાઇનિંગ ટેબલ"
        ]) and not any(k in text_lower for k in ["study table", "dressing table", "coffee table"]):
            matched_items.append("Solid Wood Dining Table")

        # 6. Wooden Sofa
        if any(w in text_lower for w in [
            "sofa", "sofas", "soffa", "couch", "setee", "diwan",
            "સોફા", "સોફો", "सोफा", "बैठक", "दीवान"
        ]):
            matched_items.append("Custom Wooden Sofa")

        # 7. Bed
        if any(w in words for w in ["bed", "beds", "palang", "khat", "khatiya", "પલંગ", "ખાટલો", "पलंग", "खाट"]) or any(
            k in text_lower for k in ["storage bed", "hydraulic bed", "king bed", "queen bed", "bed with storage", "box bed"]
        ):
            matched_items.append("Custom Storage Bed")

        # 8. Wooden Door & Frame
        if any(w in text_lower for w in [
            "door", "doors", "entrance door", "chaukhat", "carving door", "darwaza", "darwaja", "darwajo",
            "દરવાજો", "દરવાજા", "ચોખટ", "દરવાજાઓ", "दरवाज़ा", "दरवाजा", "चौखट", "दरवाजे"
        ]):
            matched_items.append("Wooden Door & Frame")

        # 9. TV Entertainment Unit
        if any(w in text_lower for w in [
            "tv unit", "tv cabinet", "tv stand", "tv console", "tv panel", "entertainment unit",
            "ટીવી", "ટીવી યુનિટ", "टीवी यूनिट", "टीवी"
        ]):
            matched_items.append("TV Entertainment Unit")

        # 10. Pooja Mandir
        if any(w in text_lower for w in [
            "mandir", "pooja", "pooja mandir", "temple", "devghar", "mandir unit",
            "મંદિર", "પૂજા", "પૂજા મંદિર", "मंदिर", "पूजा", "पूजा घर", "देवघर"
        ]):
            matched_items.append("Pooja Mandir")

        # 11. Study Table / Bookshelf
        if any(w in text_lower for w in [
            "bookshelf", "book shelf", "bookcase", "study table", "study desk", "office table",
            "ચોપડીઓ", "ડેસ્ક", "किताबों की अलमारी", "स्टडी टेबल"
        ]):
            matched_items.append("Bookshelf & Study Table")

        # 12. Shoe Cabinet
        if any(w in text_lower for w in [
            "shoe rack", "shoe cabinet", "shoes rack", "ચંપલ સ્ટેન્ડ", "जूता स्टैंड", "शू रैक"
        ]):
            matched_items.append("Shoe Cabinet")

        # Regex fallback for generic furniture requests (e.g. "i want to make bar cabinet")
        if not matched_items:
            intent_match = re.search(
                r"(?:want to make|want to build|looking to make|looking for|need to make|need|banana hai|banani hai|banwani hai|banwana hai|banavvu che|banavvi che)\s+([a-zA-Z\s]{3,30})",
                text_lower
            )
            if intent_match:
                extracted = intent_match.group(1).strip()
                extracted = re.sub(r"\b(?:a|an|the|some|one|two|three|new|custom|wood|wooden)\b", "", extracted).strip()
                if extracted and len(extracted) >= 3 and not any(ex in extracted for ex in ["appointment", "visit", "measurement", "call"]):
                    matched_items.append(extracted.title())

        # Update session with matched items
        dim_in_current_text = bool(
            re.search(r"(\d+(?:\.\d+)?\s*(?:x|X|×|\*|by|બાય|बाय)\s*\d+)", text_lower)
            or re.search(r"\b(\d+)\s*[-]?\s*(?:seater|seat|sofa|સોફા|सोफा|સીટર|सीटर)\b", text_lower)
            or any(k in text_lower for k in ["king size", "queen size", "feet", "ft", "inch", "l-shape", "l shape"])
        )
        if matched_items:
            if len(matched_items) == 1:
                new_project = matched_items[0]
                if session.project_type != new_project:
                    session.project_type = new_project
                    if not dim_in_current_text:
                        session.dimensions = None  # Reset old dimensions when customer asks for a new item!
            else:
                session.project_type = " & ".join(matched_items)
                if not dim_in_current_text:
                    session.dimensions = None

        # Dimensions detection (e.g. 10x8, 10x8 ft, 10*20, 10×10, 3 seater, 3 sofa, 6 seater, 7x3)
        dim_match = re.search(
            r"(\d+(?:\.\d+)?\s*(?:x|X|×|\*|by|બાય|बाय)\s*\d+(?:\.\d+)?\s*(?:ft|feet|inch|in|m|meter|ફૂટ|ફીટ|फुट|फीट)?)",
            text_lower
        )
        if dim_match:
            session.dimensions = dim_match.group(0).strip().replace("×", "x").replace("X", "x")
        else:
            sofa_match = re.search(r"\b(\d+)\s*[-]?\s*(?:seater|seat|sofa|સોફા|सोफा|સીટર|सीटर)\b", text_lower)
            if sofa_match:
                sc = int(sofa_match.group(1))
                if sc in (1, 2, 3):
                    session.dimensions = f"{sc}-Seater" if sc == 3 else "3-Seater"
                elif sc in (4, 5):
                    session.dimensions = "5-Seater (3+1+1)"
                elif sc in (6, 7):
                    session.dimensions = "6-Seater (approx 6ft x 3ft)"
                elif sc >= 8:
                    session.dimensions = "8-Seater (approx 8ft x 3.5ft)"
            elif any(k in text_lower for k in ["l-shape", "l shape", "corner sofa"]):
                session.dimensions = "L-Shape Sectional"
            elif any(k in text_lower for k in ["king size", "king bed", "કિંગ સાઈઝ", "किंग साइज"]):
                session.dimensions = "King Size (approx 6.5ft x 6ft)"
            elif any(k in text_lower for k in ["queen size", "queen bed", "ક્વીન સાઈઝ", "क्वीन साइज"]):
                session.dimensions = "Queen Size (approx 6.5ft x 5ft)"

        # Materials detection
        materials_map = {
            "teak": "First-Grade Teak (Sagwan)",
            "sagwan": "First-Grade Teak (Sagwan)",
            "sag": "First-Grade Teak (Sagwan)",
            "સાગવાન": "First-Grade Teak (Sagwan)",
            "સાગ": "First-Grade Teak (Sagwan)",
            "सागवान": "First-Grade Teak (Sagwan)",
            "sheesham": "Solid Indian Rosewood (Sheesham)",
            "shisham": "Solid Indian Rosewood (Sheesham)",
            "rosewood": "Solid Indian Rosewood (Sheesham)",
            "સીસમ": "Solid Indian Rosewood (Sheesham)",
            "શીશમ": "Solid Indian Rosewood (Sheesham)",
            "शीशम": "Solid Indian Rosewood (Sheesham)",
            "ply": "IS 710 Marine Plywood (BWP)",
            "plywood": "IS 710 Marine Plywood (BWP)",
            "પ્લાય": "IS 710 Marine Plywood (BWP)",
            "प्लाई": "IS 710 Marine Plywood (BWP)",
            "laminate": "1mm Anti-Scratch Laminate",
            "લેમિનેટ": "1mm Anti-Scratch Laminate",
            "लैमिनेट": "1mm Anti-Scratch Laminate",
            "veneer": "Natural Wood Veneer",
            "વિનિયર": "Natural Wood Veneer",
            "pu": "Polyurethane (PU) Polish",
            "acrylic": "High-Gloss Acrylic Finish",
            "એક્રેલિક": "High-Gloss Acrylic Finish",
            "ash": "Solid White Ash",
            "oak": "White Oak",
        }
        for kw, mat_name in materials_map.items():
            if kw in text_lower and mat_name not in session.preferred_materials:
                session.preferred_materials.append(mat_name)

        # Appointment / Scheduling intent detection (including multilingual words & typos)
        scheduling_keywords = {
            "visit", "measurement", "measurements", "appointment", "book", "booking",
            "schedule", "sechudel", "schedul", "skedule", "meeting", "meet", "come", "slot", "slots",
            "aao", "aaiye", "aajao", "aajaiye", "aavo", "aavjo", "ghar", "ghare", "home",
            "મુલાકાત", "માપણી", "માપ", "બુક", "વિઝિટ", "આવો", "આવજો", "ઘરે",
            "मुलाकात", "विज़िट", "नाप", "बुक", "आओ", "आ जाइए", "आइए", "घर"
        }
        affirmative_words = {
            "yes", "yeah", "yep", "sure", "ok", "okay", "yup", "done", "please", "pls",
            "confirm", "confirmed", "go ahead", "why not", "sounds good", "perfect", "good", "fine", "works", "suits",
            "haa", "ha", "haan", "han", "hnn", "theek", "achha", "bilkul", "avashya",
            "હા", "હાજી", "ચાલશે", "બરાબર", "પાક્કું", "ચોક્કસ",
            "हाँ", "हां", "हाँजी", "ठीक है", "चलेगा", "पक्का", "ज़रूर", "अवश्य"
        }

        # Budget detection (e.g. "my budget is 15000 Rs", "15k", "budget 20000", "can do in 18k", "max 25000")
        budget_patterns = [
            r"(?:budget\s*(?:is|of|around)?|have|max|for|in|only|બજેટ|ખર્ચ|ખર્ચા|बजट)\s*[:=]?\s*(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{3})+|\d+)\s*(k|thousand|l|lakh|rs\.?|inr|rupees|હજાર|લાખ|हजार|लाख)?",
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
                    if "k" in mult or "હજાર" in mult or "हजार" in mult:
                        b_num *= 1000
                    elif "l" in mult or "lakh" in mult or "લાખ" in mult or "लाख" in mult:
                        b_num *= 100000
                    if 1000 <= b_num <= 10000000:
                        session.customer_budget = b_num
                        session.negotiation_stage = "bargaining"
                        break
                except ValueError:
                    pass

        # No time / Cannot visit / Prefers chat confirmation detection
        no_time_keywords = [
            "no time", "don't have time", "dont have time", "not have time", "busy",
            "cannot visit", "cant visit", "can't visit", "cannot meet", "cant meet", "can't meet",
            "not free", "not available", "online only", "in chat", "on chat", "over chat",
            "send photos", "send pics", "share photos", "share pics", "chat mein batao",
            "chat ma kaho", "time nathi", "samay nahi", "time nahi",
            "સમય નથી", "ટાઇમ નથી", "વ્યસ્ત છું", "ચેટમાં કહો", "ચેટ પર", "ચેટમાં જણાવો", "સમય નથી મળતો",
            "समय नहीं है", "टाइम नहीं है", "व्यस्त हूँ", "विज़िट नहीं हो पाएगी", "चैट पर बताओ", "चैट में बताओ", "ऑनलाइन बताओ"
        ]
        if any(nt in text_lower for nt in no_time_keywords):
            session.consultation_mode = "virtual"

        # Check if customer mentions sharing / sending photos
        photos_shared_keywords = [
            "sent photo", "sent photos", "sent pics", "sending photos", "attached photo",
            "here are photos", "here are the photos", "here is the photo", "here are pics",
            "here are the pics", "check this picture", "check this photo",
            "photo bhej diya", "photo bheja", "photo bhej raha", "photo moklya", "photo moklu",
            "ફોટા મોકલ્યા", "ફોટો મોકલ્યો", "ફોટો મોકલું", "ફોટા મોકલો",
            "फोटो भेज दिया", "फोटो भेजी", "फोटो भेज दी", "फोटो भेजा"
        ]
        if bool(re.search(r"(?:sent|send|sending|attached|share|sharing|bhej|mokl)\w*\s*(?:the\s*)?(?:photos?|pics?|pictures?|images?|design|ફોટા|ફોટો|फोटो)", text_lower)) or any(ps in text_lower for ps in photos_shared_keywords):
            session.consultation_mode = "virtual"
            if "customer_shared_photos" not in session.notes:
                session.notes.append("customer_shared_photos")

        # Check if previous agent turn offered a measurement visit
        prev_agent_offered_visit = False
        for turn in reversed(session.history[:-1]):
            if turn.get("role") == "model":
                prev_text = turn.get("text", "").lower()
                if any(k in prev_text for k in [
                    "visit", "schedule", "measurement", "slot", "workshop", "માપણી", "મુલાકાત", "નાપ", "વિઝિટ",
                    "to your site", "bring fabric", "bring timber", "bring physical", "samples", "swatches",
                    "घर आएं", "घर आए", "घर आकर", "घर आ सकते", "सैंपल", "सैंपल्स", "विज़िट", "नाप लेने", "नाप लेकर", "लेआउट",
                    "ઘરે આવીએ", "ઘરે આવો", "સેમ્પલ", "સેમ્પલ્સ", "શનિવારે", "રવિવારે", "શનિવાર", "રવિવાર",
                    "शनिवार", "रविवार", "saturday at", "sunday at", "which slot", "કયો સમય", "कौन सा समय"
                ]):
                    prev_agent_offered_visit = True
                break

        affirming_phrases = [
            "haa aa jaiye", "ha aa jaiye", "haan aa jaiye", "aa jaiye", "aa jao", "aao ji",
            "aaiye", "aaiye ji", "ghar aa jao", "ghar aao", "ghar aaiye", "ghar aa jaiye",
            "ha aavo", "haa aavo", "aavo ji", "aavjo", "aavo", "ghare aavo", "ghare aavjo",
            "haa chalega", "ha chalega", "haan chalega", "chalega ji", "chalega", "chalse", "chalshe", "chalshe ji",
            "yes please", "sure come", "come home", "come over", "please come", "come on saturday",
            "come on sunday", "bhej do", "bhejo", "bhejiye", "aajao", "aajaiye", "ha bhai", "haa bhai",
            "yes come", "ok come", "okay come"
        ]
        has_affirming_phrase = any(phrase in text_lower for phrase in affirming_phrases)

        has_scheduling_word = bool(words.intersection(scheduling_keywords)) or any(
            k in text_lower for k in ["site visit", "laser measurement", "come over", "come to", "ઘરે આવો", "રૂબરૂ મળો", "घर आ जाओ", "नाप लेने आओ", "aa jaiye", "aa jao", "aavo", "aaiye"]
        )
        is_affirming_visit = (prev_agent_offered_visit and bool(words.intersection(affirmative_words))) or (prev_agent_offered_visit and has_affirming_phrase)

        if has_scheduling_word or is_affirming_visit or has_affirming_phrase:
            if session.appointment_status == "none":
                session.appointment_status = "requested"
            if not session.appointment_slot:
                if any(w in text_lower for w in ["sunday", "રવિવાર", "रविवार", "4 pm", "સાંજે", "शाम"]):
                    session.appointment_slot = "રવિવારે સાંજે 4:00 વાગ્યે (Sunday 4:00 PM)" if session.language == "gu" else ("रविवार शाम 4:00 बजे (Sunday 4:00 PM)" if session.language == "hi" else "Sunday at 4:00 PM")
                else:
                    session.appointment_slot = "શનિવારે સવારે 11:30 વાગ્યે (Saturday 11:30 AM)" if session.language == "gu" else ("शनिवार सुबह 11:30 बजे (Saturday 11:30 AM)" if session.language == "hi" else "Saturday at 11:30 AM")

        # Check specific day / time slots
        sat_label = "શનિવારે સવારે 11:30 વાગ્યે (Saturday 11:30 AM)" if session.language == "gu" else ("शनिवार सुबह 11:30 बजे (Saturday 11:30 AM)" if session.language == "hi" else "Saturday at 11:30 AM")
        sun_label = "રવિવારે સાંજે 4:00 વાગ્યે (Sunday 4:00 PM)" if session.language == "gu" else ("रविवार शाम 4:00 बजे (Sunday 4:00 PM)" if session.language == "hi" else "Sunday at 4:00 PM")
        days_and_slots = [
            ("saturday", sat_label),
            ("sunday", sun_label),
            ("શનિવાર", sat_label),
            ("રવિવાર", sun_label),
            ("शनिवार", sat_label),
            ("रविवार", sun_label),
            ("11:30", sat_label),
            ("4 pm", sun_label),
            ("weekend", sat_label),
            ("tomorrow", "કાલે (Tomorrow)" if session.language == "gu" else ("कल (Tomorrow)" if session.language == "hi" else "Tomorrow")),
        ]
        for slot_kw, slot_val in days_and_slots:
            if slot_kw in text_lower:
                if session.appointment_status != "confirmed":
                    session.appointment_status = "requested"
                session.appointment_slot = slot_val
                break

        # Address / Location detection
        has_slot_time = any(w in words for w in ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "weekend", "tomorrow", "morning", "evening", "શનિવાર", "રવિવાર", "शनिवार", "रविवार"]) or any(t in text_lower for t in ["11:30", "11 am", "4 pm", "10 am", "4:00"])
        has_detected_address = has_address_marker(user_text) or (
            session.appointment_status == "requested"
            and not has_affirming_phrase
            and not bool(words.intersection(affirmative_words))
            and not has_scheduling_word
            and not has_slot_time
            and not any(c in text_lower for c in ["cancel", "nahi aana", "rehne do", "nathi joiye", "nathi karvu", "dont want", "no thanks", "stop"])
            and not any(q in text_lower for q in ["price", "cost", "rate", "bhav", "kitna", "ketla", "final price", "last price", "discount"])
            and not words.issubset({"hi", "hello", "hey", "namaste", "kem", "cho", "good", "morning", "evening"})
            and not any(k in text_lower for k in [
                "seater", "સીટર", "सीटर", "x", "*", "by", "feet", "inch", "khidki", "khidkhi",
                "sofa", "table", "wardrobe", "kitchen", "cabinet", "banani", "banvana", "banana"
            ])
            and (
                any(c.isdigit() for c in user_text)
                or "," in user_text
                or "-" in user_text
                or len(words) >= 2
            )
        )
        if has_detected_address:
            session.appointment_status = "confirmed"
            session.just_confirmed_booking = True
            clean_addr = user_text.strip()
            session.site_address = clean_addr
            if not session.appointment_slot:
                session.appointment_slot = "શનિવારે સવારે 11:30 વાગ્યે (Saturday 11:30 AM)" if session.language == "gu" else ("शनिवार सुबह 11:30 बजे (Saturday 11:30 AM)" if session.language == "hi" else "Saturday at 11:30 AM")
            if not any(n.startswith("address:") for n in session.notes):
                session.notes.append(f"address: {clean_addr}")

    def _generate_fallback_response(self, session: CustomerSession, user_text: str) -> str:
        """Intelligent offline Master Carpenter response generator with multi-turn multilingual state."""
        text_lower = user_text.lower()
        clean_tokens = set(re.sub(r"[^\w\s\u0900-\u097F\u0A80-\u0AFF]", " ", text_lower).split())
        words = set(re.findall(r"\b\w+\b", text_lower)).union(clean_tokens)
        lang = getattr(session, "language", "en") or "en"

        # Extract caller name for personal addressing (filter out invalid / placeholder names)
        caller_name = session.customer_name or ""
        first_name = ""
        invalid_names = {
            "others", "other", "customer", "client", "user", "admin", "contact",
            "unknown", "test", "demo", "none", "null", "false", "true", "undefined",
            "whatsapp", "someone", "person", "guest", "friend", "caller", "profile"
        }
        if caller_name:
            raw_first = caller_name.split()[0].strip()
            clean_n = re.sub(r"[^a-zA-Z\u0900-\u097F\u0A80-\u0AFF]", "", raw_first)
            if clean_n and len(clean_n) >= 2 and clean_n.lower() not in invalid_names and not clean_n.lower().startswith("client"):
                first_name = clean_n

        if lang == "gu":
            name_title = f"{first_name}જી" if first_name else "જી"
        elif lang == "hi":
            name_title = f"{first_name} जी" if first_name else "जी"
        else:
            name_title = f"{first_name} ji" if first_name else "Ji"

        # Check previous turn context
        prev_agent_msg = ""
        for turn in reversed(session.history[:-1]):
            if turn.get("role") == "model":
                prev_agent_msg = turn.get("text", "").lower()
                break

        visit_offer_keywords = [
            "visit", "schedule", "measurement", "slot", "workshop", "માપણી", "મુલાકાત", "નાપ", "વિઝિટ",
            "to your site", "bring fabric", "bring timber", "bring physical", "samples", "swatches",
            "घर आएं", "घर आए", "घर आकर", "घर आ सकते", "सैंपल", "सैंपल्स", "विज़िट", "नाप लेने", "नाप लेकर", "लेआउट",
            "ઘરે આવીએ", "ઘરે આવો", "સેમ્પલ", "સેમ્પલ્સ", "શનિવારે", "રવિવારે", "શનિવાર", "રવિવાર",
            "शनिवार", "रविवार", "saturday at", "sunday at", "which slot", "કયો સમય", "कौन सा समय"
        ]
        prev_agent_offered_visit = any(k in prev_agent_msg for k in visit_offer_keywords)

        scheduling_keywords = {
            "visit", "measurement", "measurements", "appointment", "book", "booking",
            "schedule", "sechudel", "schedul", "skedule", "meeting", "meet", "slot", "slots",
            "aao", "aaiye", "aajao", "aajaiye", "aavo", "aavjo", "ghar", "ghare", "home",
            "મુલાકાત", "માપણી", "માપ", "બુક", "વિઝિટ", "આવો", "આવજો", "ઘરે",
            "मुलाकात", "विज़िट", "नाप", "बुक", "आओ", "आ जाइए", "आइए", "घर"
        }
        affirmative_words = {
            "yes", "yeah", "yep", "sure", "ok", "okay", "yup", "done", "please", "pls",
            "confirm", "confirmed", "go ahead", "why not", "sounds good", "perfect",
            "haa", "ha", "haan", "han", "hnn", "theek", "achha", "bilkul", "avashya",
            "હા", "હાજી", "ચાલશે", "બરાબર", "પાક્કું", "ચોક્કસ",
            "हाँ", "हां", "हाँजी", "ठीक है", "चलेगा", "पक्का", "ज़रूर", "अवश्य"
        }
        affirming_phrases = [
            "haa aa jaiye", "ha aa jaiye", "haan aa jaiye", "aa jaiye", "aa jao", "aao ji",
            "aaiye", "aaiye ji", "ghar aa jao", "ghar aao", "ghar aaiye", "ghar aa jaiye",
            "ha aavo", "haa aavo", "aavo ji", "aavjo", "aavo", "ghare aavo", "ghare aavjo",
            "haa chalega", "ha chalega", "haan chalega", "chalega ji", "chalega", "chalse", "chalshe", "chalshe ji",
            "yes please", "sure come", "come home", "come over", "please come", "come on saturday",
            "come on sunday", "bhej do", "bhejo", "bhejiye", "aajao", "aajaiye", "ha bhai", "haa bhai",
            "yes come", "ok come", "okay come"
        ]
        has_affirming_phrase = any(phrase in text_lower for phrase in affirming_phrases)
        courtesy_words = {
            "ok", "okay", "thank", "thanks", "thx", "great", "perfect", "good", "bye", "see", "alright", "done",
            "theek", "theek hai", "thik", "thik hai", "badiya", "saras", "chalega", "thek",
            "આભાર", "ધન્યવાદ", "ધન્યવાદ જી", "સારું", "બરાબર",
            "धन्यवाद", "शुक्रिया", "बहुत अच्छा", "नमस्ते", "ठीक है", "ठीक"
        }

        user_is_scheduling = bool(words.intersection(scheduling_keywords)) or any(
            k in text_lower for k in ["site visit", "come over", "come to", "laser measurement", "ઘરે આવો", "घर आ जाओ", "aa jaiye", "aa jao", "aavo", "aaiye"]
        )
        user_is_affirming = (bool(words.intersection(affirmative_words)) or has_affirming_phrase) and (
            prev_agent_offered_visit or session.appointment_status == "requested"
        )
        has_time_slot = any(w in words for w in ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "weekend", "tomorrow", "morning", "evening", "શનિવાર", "રવિવાર", "शनिवार", "रविवार"]) or any(t in text_lower for t in ["11:30", "11 am", "4 pm", "10 am"])
        has_address = has_address_marker(user_text) or (
            session.appointment_status == "requested"
            and not has_affirming_phrase
            and not bool(words.intersection(affirmative_words))
            and not user_is_scheduling
            and not has_time_slot
            and not any(c in text_lower for c in ["cancel", "nahi aana", "rehne do", "nathi joiye", "nathi karvu", "dont want", "no thanks", "stop"])
            and not any(q in text_lower for q in ["price", "cost", "rate", "bhav", "kitna", "ketla", "final price", "last price", "discount"])
            and not words.issubset({"hi", "hello", "hey", "namaste", "kem", "cho", "good", "morning", "evening"})
            and not any(k in text_lower for k in [
                "seater", "સીટર", "सीटर", "x", "*", "by", "feet", "inch", "khidki", "khidkhi",
                "sofa", "table", "wardrobe", "kitchen", "cabinet", "banani", "banvana", "banana"
            ])
            and (
                any(c.isdigit() for c in user_text)
                or "," in user_text
                or "-" in user_text
                or len(words) >= 2
            )
        )

        # 1. Post-Booking Confirmation Courtesy (only when customer is closing after confirmation)
        is_courtesy_close = (
            (words.intersection(courtesy_words) or any(c in text_lower for c in ["thank you", "thanks", "theek hai", "thik hai", "theek", "thik", "આભાર", "ધન્યવાદ", "धन्यवाद", "शुक्रिया", "ठीक है"]))
            and not has_time_slot
            and not has_address
            and len(words) <= 4
        )
        if session.appointment_status == "confirmed" and is_courtesy_close:
            slot_str = session.appointment_slot or "your scheduled appointment"
            if lang == "gu":
                return (
                    f"તમારો ખૂબ ખૂબ આભાર! 🙏 તમારી લેસર માપણી મુલાકાત *{slot_str}* માટે પાકી થઈ ગઈ છે.\n\n"
                    f"કોઈ પણ ફોટો કે ડિઝાઇન રેફરન્સ હોય તો અહીં ગમે ત્યારે મોકલી શકો છો. મળીએ છીએ! 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"आपका बहुत-बहुत धन्यवाद! 🙏 आपकी लेज़र मेज़रमेंट विज़िट *{slot_str}* के लिए पक्की हो चुकी है।\n\n"
                    f"कोई भी फोटो या डिज़ाइन रेफरेंस हो तो आप यहां कभी भी भेज सकते हैं। आपसे मिलने की प्रतीक्षा रहेगी! 🪵✨"
                )
            return (
                f"You're very welcome! 🙏 Everything is set for your laser measurement visit on *{slot_str}*.\n\n"
                f"Feel free to share any photo references or design ideas here anytime before we arrive. Looking forward to meeting you! 🪵✨"
            )

        # 1b. Customer shared room photos or design pictures
        has_sent_photos = "customer_shared_photos" in session.notes or bool(re.search(r"(?:sent|send|sending|attached|share|sharing|bhej|mokl)\w*\s*(?:the\s*)?(?:photos?|pics?|pictures?|images?|design|ફોટા|ફોટો|फोटो)", text_lower)) or any(
            ps in text_lower for ps in [
                "sent photo", "sent photos", "sent pics", "photo bhej", "photo mokl",
                "photos mokl", "photo send", "pics send", "here is photo", "here are the photos", "here is the pic"
            ]
        )
        if has_sent_photos:
            if lang == "gu":
                return (
                    f"ફોટા અને વિગતો મોકલવા બદલ ખૂબ ખૂબ આભાર! 📸✨\n\n"
                    f"અમારી માસ્ટર કારીગર ટીમ તમારી જગ્યા, સ્કીર્ટિંગ, સ્વિચબોર્ડ અને દરવાજાનું ક્લીયરન્સ ચેક કરી રહી છે.\n\n"
                    f"આ ફોટાના આધારે અમે આગામી ૨ કલાકમાં તમારા માટે સંપૂર્ણ આઇટમવાઇઝ ક્વોટેશન અને મટિરિયલ વિકલ્પો (સાગવાન/શીશમ vs મરીન પ્લાય + લેમિનેટ) તૈયાર કરીને અહીં ચેટમાં જ મોકલી આપીશું! 🪵📐\n\n"
                    f"જો આ દરમિયાન કોઈ ચોક્કસ કલર કે ફિનિશ તમારા મનમાં હોય તો જરૂર જણાવશો! 🙏"
                )
            elif lang == "hi":
                return (
                    f"फोटो और जानकारी भेजने के लिए बहुत-बहुत धन्यवाद! 📸✨\n\n"
                    f"हमारी मास्टर कारिगर टीम आपकी जगह, स्कर्टिंग, स्विचबोर्ड और दरवाजे का क्लीयरेंस देख रही है।\n\n"
                    f"इन तस्वीरों के आधार पर हम अगले २ घंटे में आपके लिए पूरा पक्का कोटेशन और मटेरियल विकल्प (सागवान/शीशम vs मरीन प्लाई + लैमिनेट) तैयार करके यहीं चैट पर भेज देंगे! 🪵📐\n\n"
                    f"अगर कोई खास रंग या फिनिश आपके दिमाग में हो तो ज़रूर बताएं! 🙏"
                )
            return (
                f"Thank you so much for sharing the photos! 📸✨\n\n"
                f"Our master artisan team is reviewing the space, skirting, electrical boards, and door clearance right now.\n\n"
                f"Based on your photos, we will prepare a firm itemized quotation, material breakdown (Solid Teak/Sheesham vs BWP Marine Ply with 1mm Laminate/PU), and send it right here in this chat within 2 hours! 🪵📐\n\n"
                f"If you have any specific color or finish preferences, feel free to share them anytime! 🙏"
            )

        # 1c. Customer has no time to visit / is busy / prefers chat confirmation
        is_no_time = getattr(session, "consultation_mode", "in_person") == "virtual" or any(
            nt in text_lower for nt in [
                "no time", "don't have time", "dont have time", "not have time", "busy",
                "cannot visit", "cant visit", "can't visit", "cannot meet", "cant meet", "can't meet",
                "not free", "not available", "in chat", "on chat", "over chat", "online estimate",
                "confirm in chat", "chat confirmation", "time nathi", "samay nahi", "time nahi",
                "સમય નથી", "ટાઇમ નથી", "વ્યસ્ત છું", "ચેટમાં કહો", "ચેટ પર", "ચેટમાં જણાવો", "સમય નથી મળતો",
                "समय नहीं है", "टाइम नहीं है", "व्यस्त हूँ", "विज़िट नहीं हो पाएगी", "चैट पर बताओ", "चैट में बताओ", "ऑनलाइन बताओ"
            ]
        )
        if is_no_time:
            session.consultation_mode = "virtual"
            p_name = session.project_type or "custom furniture"
            if lang == "gu":
                return (
                    f"બિલકુલ ચિંતા કરશો નહીં! 🙏 અમે સંપૂર્ણ સમજીએ છીએ કે તમારો સમય કીમતી છે. તમારે રૂબરૂ મુલાકાત માટે સમય કાઢવાની બિલકુલ જરૂર નથી — આપણે અહીં ચેટમાં જ તમારા *{p_name}* નું સંપૂર્ણ કામ ફાઇનલ કરી શકીએ છીએ! 📐✨\n\n"
                    f"સચોટ ક્વોટેશન અને 3D ડિઝાઇન તૈયાર કરવા માટે, કૃપા કરીને અહીં ચેટમાં આ ૪ વિગતો મોકલી આપો:\n"
                    f"1. 📸 *જગ્યા / દીવાલના ફોટા*: જ્યાં ફર્નિચર બનાવવું છે તેના ૨–૩ સ્પષ્ટ ફોટા અથવા નાનો વિડીયો (જેથી અમે સ્વિચબોર્ડ, સ્કીર્ટિંગ અને દરવાજાનું માપ સમજી શકીએ).\n"
                    f"2. 📏 *અંદાજિત માપ*: દીવાલ કે જગ્યાની લંબાઈ અને ઊંચાઈ (ફૂટ અથવા ઈંચમાં).\n"
                    f"3. 🖼️ *ડિઝાઇન રેફરન્સ*: તમારી પસંદગીનો કોઈ ફોટો, સ્કેચ કે Pinterest ડિઝાઇન જે તમે બનાવવા માંગો છો.\n"
                    f"4. 🪵 *પસંદગીનું મટિરિયલ*: ઓરિજિનલ સાગ/શીશમ લાકડું કે વોટરપ્રૂફ મરીન પ્લાય સાથે લેમિનેટ/PU પોલિશ.\n\n"
                    f"તમે આ ફોટા મોકલશો એટલે અમારી કારીગર ટીમ તરત જ ચેક કરીને પાક્કો હિસાબ અને પ્લાન અહીં જ મોકલી આપશે! 🪚✨"
                )
            elif lang == "hi":
                return (
                    f"बिल्कुल कोई बात नहीं! 🙏 हम समझते हैं कि आपका समय कीमती है। आपको विज़िट के लिए समय निकालने की ज़रूरत नहीं है — हम यहीं चैट पर ही आपके *{p_name}* का पूरा काम और कोटेशन तय कर सकते हैं! 📐✨\n\n"
                    f"पक्का कोटेशन और 3D डिज़ाइन बनाने के लिए, कृपया चैट में ये ४ चीजें भेज दीजिए:\n"
                    f"1. 📸 *कमरे / दीवार की फोटो*: जहाँ फर्नीचर बनना है, उस जगह की २–३ साफ फोटो या छोटा वीडियो (ताकि हम स्विचबोर्ड, स्कर्टिंग और दरवाज़े का क्लीयरेंस देख सकें)।\n"
                    f"2. 📏 *अंदाज़न नाप*: जगह की लंबाई और ऊंचाई (फीट या इंच में)।\n"
                    f"3. 🖼️ *डिज़ाइन रेफरेंस*: आपकी पसंद की कोई फोटो, स्केच या Pinterest डिज़ाइन जो आप बनवाना चाहते हैं।\n"
                    f"4. 🪵 *पसंदीदा मटेरियल*: सागवान/शीशम लकड़ी या वाटरप्रूफ मरीन प्लाई के साथ लैमिनेट/PU पॉलिश।\n\n"
                    f"जैसे ही आप फोटो भेजेंगे, हमारी मास्टर कारिगर टीम देखकर आपको पक्का कोटेशन यहीं भेज देगी! 🪚✨"
                )
            return (
                f"No problem at all! 🙏 We completely understand you are busy. You don't need to take time out for an in-person visit — we can finalize 100% of your *{p_name}* quotation right here in this chat! 📐✨\n\n"
                f"To prepare your exact itemized quote and 3D drawing, please share these 4 details:\n"
                f"1. 📸 *Room / Wall Photos*: 2–3 clear pictures or a quick video of the space where you want to place the furniture (so we can check skirting, switchboards, and door clearance).\n"
                f"2. 📏 *Approximate Measurements*: Rough length and height of the wall/floor in feet or inches.\n"
                f"3. 🖼️ *Design Reference*: Any photo, sketch, or Pinterest idea you have in mind.\n"
                f"4. 🪵 *Preferred Material*: Solid Teak / Sheesham vs BWP Marine Ply with Laminate/PU polish.\n\n"
                f"Once you send these photos, our master workshop team will review them and send you a firm price quote right here! 🪚✨"
            )

        # 2. Booking confirmed when customer provides a specific address or day/time slot with address
        if getattr(session, "just_confirmed_booking", False) or has_address:
            session.just_confirmed_booking = False
            session.appointment_status = "confirmed"
            slot_name = session.appointment_slot or ("શનિવારે સવારે 11:30 વાગ્યે" if lang == "gu" else ("शनिवार सुबह 11:30 बजे" if lang == "hi" else "Saturday at 11:30 AM"))
            project_name = session.project_type or ("કસ્ટમ ફર્નિચર" if lang == "gu" else ("कस्टम फर्नीचर" if lang == "hi" else "custom woodwork"))
            addr_text = session.site_address or user_text.strip()
            if not any(n.startswith("address:") for n in session.notes):
                session.notes.append(f"address: {addr_text}")
            if lang == "gu":
                return (
                    f"બુકિંગ પાકું થઈ ગયું! 📅✨ અમે *{slot_name}* ના રોજ તમારા સરનામે (*{addr_text}*) તમારા *{project_name}* માટે પહોંચી જઈશું.\n\n"
                    f"અમારી ટીમ સાથે લેઝર મેઝરમેન્ટ ટેપ અને લાકડા/PU ફિનિશના અસલી સેમ્પલ્સ (સાગવાન, શીશમ, મરીન પ્લાય, PU પોલિશ swatches) લઈને આવશે. પહોંચવાના ૩૦ મિનિટ પહેલાં તમને ફોન કરીશું. મળવા માટે ઉત્સુક છીએ! 🙏🪵"
                )
            elif lang == "hi":
                return (
                    f"बुकिंग पक्की हो गई! 📅✨ हम *{slot_name}* को आपके पते (*{addr_text}*) पर *{project_name}* के लिए पहुँच जाएंगे।\n\n"
                    f"हमारी मास्टर कारिगर टीम साथ में लेज़र मेज़रमेंट टूल्स और लकड़ी/PU फिनिश के असली सैंपल्स (सागवान, शीशम, मरीन प्लाई, PU swatches) लेकर आएगी। आने से 30 मिनट पहले आपको फोन करेंगे। आपसे मिलने की प्रतीक्षा रहेगी! 🙏🪵"
                )
            return (
                f"Booking confirmed! 📅✨ We will visit you on *{slot_name}* at *{addr_text}* for your *{project_name}*.\n\n"
                f"Our master carpenter team will bring laser measurement tools and physical wood/PU finish samples (Teak, Sheesham, Marine Ply swatches). We will call you 30 minutes before arrival. Looking forward to meeting you! 🙏🪵"
            )

        # 4b. Customer asked for Final Price / Net Rate / Best Price (Return Final Price ONLY with zero questions, timeline, or visit pitches)
        is_final_price_inquiry = any(
            k in text_lower for k in [
                "final price", "final rate", "final cost", "final quote", "what your final price",
                "what is your final price", "whats your final price", "what is final price",
                "give final price", "tell final price", "what final price", "last price",
                "last rate", "lowest price", "bottom price", "rock bottom", "fixed price",
                "net price", "cheapest price", "minimum price", "kam se kam",
                "फाइनल प्राइस", "लास्ट प्राइस", "फाइनल रेट", "फाइनल भाव", "आखिरी रेट",
                "पक्का रेट", "अंतिम रेट", "अंतिम भाव", "फाइनल कितना", "लास्ट कितना",
                "ફાઇનલ ભાવ", "છેલ્લો ભાવ", "લાસ્ટ પ્રાઇસ", "ફાઇનલ કિંમત", "છેલ્લી કિંમત",
                "પાક્કો ભાવ", "છેલ્લે કેટલા"
            ]
        ) or any(
            phrase in text_lower for phrase in [
                "your final price", "the final price", "tell me final", "give me final",
                "bhav final", "rate final", "final bolo", "last bolo"
            ]
        )
        if is_final_price_inquiry:
            p_name = session.project_type or "Custom Furniture"
            dim_info = parse_dimension_details(session.dimensions, text_lower) if session.dimensions else {}
            quote = calculate_turnkey_quote(session.project_type, dim_info, lang) if (session.project_type and session.dimensions) else {}
            sqft = int(quote.get("sqft") or 0) if session.dimensions else 0
            dim_str = session.dimensions or ""
            p_lower = p_name.lower()

            # 1. Sofa
            if any(k in p_lower for k in ["sofa", "couch", "સોફા", "सोफा"]):
                if "3" in (session.dimensions or "") or "three" in (session.dimensions or "").lower():
                    if lang == "gu":
                        return (
                            f"અમારા *Custom Wooden Sofa (3-Seater)* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                            f"• *3-સીટર સોલિડ વુડ સોફા*: *₹22,000 નેટ*\n\n"
                            f"*(સીઝન્ડ સાગ/શીશમ લાકડું, 40D હાઈ-ડેન્સિટી કુશન્સ, વોશેબલ ફેબ્રિક અને ડિલિવરી સહિત, કોઈ છુપો ખર્ચ નથી.)*"
                        )
                    elif lang == "hi":
                        return (
                            f"हमारे *Custom Wooden Sofa (3-Seater)* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                            f"• *3-सीटर सॉलिड वुड सोफा*: *₹22,000 नेट*\n\n"
                            f"*(सागवान/शीशम लकड़ी, 40D हाई-डेंसिटी कुशन, वॉशेबल फैब्रिक और डोरस्टेप डिलीवरी सहित, कोई छिपा हुआ खर्च नहीं है।)*"
                        )
                    return (
                        f"Our final workshop-direct price for *Custom Wooden Sofa (3-Seater)* is:\n\n"
                        f"• *3-Seater Solid Wood Sofa*: *₹22,000 net*\n\n"
                        f"*(Includes seasoned solid Teak/Sheesham timber, 40D high-density cushions, washable fabric covers, and doorstep delivery with zero hidden charges.)*"
                    )
                elif "5" in (session.dimensions or "") or "five" in (session.dimensions or "").lower():
                    if lang == "gu":
                        return (
                            f"અમારા *Custom Wooden Sofa (5-Seater 3+1+1)* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                            f"• *5-સીટર સોફા સેટ (3+1+1)*: *₹35,000 નેટ*\n\n"
                            f"*(સોલિડ સીઝન્ડ લાકડું, 40D કુશન્સ અને ડિલિવરી સહિત, કોઈ છુપો ખર્ચ નથી.)*"
                        )
                    elif lang == "hi":
                        return (
                            f"हमारे *Custom Wooden Sofa (5-Seater 3+1+1)* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                            f"• *5-सीटर सोफा सेट (3+1+1)*: *₹35,000 नेट*\n\n"
                            f"*(सॉलिड सीजन्ड लकड़ी, 40D कुशन और डोरस्टेप डिलीवरी सहित, कोई अतिरिक्त चार्ज नहीं है।)*"
                        )
                    return (
                        f"Our final workshop-direct price for *Custom Wooden Sofa (5-Seater 3+1+1)* is:\n\n"
                        f"• *5-Seater Sofa Set (3+1+1)*: *₹35,000 net*\n\n"
                        f"*(Includes solid seasoned timber, 40D high-resilience cushions, washable fabric covers, and delivery with zero hidden charges.)*"
                    )
                else:
                    if lang == "gu":
                        return (
                            f"અમારા *Custom Wooden Sofa* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                            f"• *3-સીટર*: *₹22,000 નેટ*\n\n"
                            f"• *5-સીટર (3+1+1)*: *₹35,000 નેટ*\n\n"
                            f"• *L-શેપ સેક્શનલ*: *₹48,000 નેટ*\n\n"
                            f"*(સોલિડ સાગ/શીશમ લાકડું, 40D કુશન્સ અને ડિલિવરી સહિત, કોઈ છુપો ખર્ચ નથી.)*"
                        )
                    elif lang == "hi":
                        return (
                            f"हमारे *Custom Wooden Sofa* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                            f"• *3-सीटर*: *₹22,000 नेट*\n\n"
                            f"• *5-सीटर (3+1+1)*: *₹35,000 नेट*\n\n"
                            f"• *L-शेप सेक्शनल*: *₹48,000 नेट*\n\n"
                            f"*(सागवान/शीशम लकड़ी, 40D कुशन और डोरस्टेप डिलीवरी सहित, कोई अतिरिक्त चार्ज नहीं है।)*"
                        )
                    return (
                        f"Our final workshop-direct price for *Custom Wooden Sofa* is:\n\n"
                        f"• *3-Seater*: *₹22,000 net*\n\n"
                        f"• *5-Seater (3+1+1)*: *₹35,000 net*\n\n"
                        f"• *L-Shape Sectional*: *₹48,000 net*\n\n"
                        f"*(Includes solid seasoned timber, 40D high-resilience foam, washable fabric covers, and delivery with zero hidden charges.)*"
                    )

            # 2. Dining Table
            if any(k in p_lower for k in ["dining", "table", "ટેબલ", "मेज"]):
                if lang == "gu":
                    return (
                        f"અમારા *Solid Wood Dining Table* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                        f"• *6-સીટર ડાઇનિંગ ટેબલ (આશરે 6x3 ફૂટ)*: *₹36,000 નેટ* (સોલિડ ટેબલ + ૬ કુશન ખુરશીઓ & PU ફિનિશ)\n\n"
                        f"• *8-સીટર ડાઇનિંગ ટેબલ (આશરે 8x3.5 ફૂટ)*: *₹52,000 નેટ* (સોલિડ ટેબલ + ૮ કુશન ખુરશીઓ)\n\n"
                        f"*(100% સીઝન્ડ સાગ/શીશમ લાકડું, મોર્ટાઈઝ જોઈનરી અને ડિલિવરી સહિત, કોઈ છુપો ચાર્જ નથી.)*"
                    )
                elif lang == "hi":
                    return (
                        f"हमारे *Solid Wood Dining Table* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                        f"• *6-सीटर डाइनिंग टेबल (लगभग 6x3 फीट)*: *₹36,000 नेट* (सॉलिड टेबल + ६ कुशन कुर्सियां और PU फिनिश)\n\n"
                        f"• *8-सीटर डाइनिंग टेबल (लगभग 8x3.5 फीट)*: *₹52,000 नेट* (सॉलिड टेबल + ८ कुशन कुर्सियां)\n\n"
                        f"*(100% सीजन्ड सागवान/शीशम लकड़ी, मजबूत जोड़ और डोरस्टेप डिलीवरी सहित, कोई अतिरिक्त चार्ज नहीं है।)*"
                    )
                return (
                    f"Our final workshop-direct price for *Solid Wood Dining Table* is:\n\n"
                    f"• *6-Seater Dining Table (approx 6ft x 3ft)*: *₹36,000 net* (Solid Teak/Sheesham table with 6 cushioned chairs & 4-coat PU finish)\n\n"
                    f"• *8-Seater Dining Table (approx 8ft x 3.5ft)*: *₹52,000 net* (Solid Teak/Sheesham with 8 cushioned chairs)\n\n"
                    f"*(Includes 100% seasoned timber, precision mortise & tenon joinery, and doorstep delivery with zero hidden charges.)*"
                )

            # 3. Custom Storage Bed
            if any(k in p_lower for k in ["bed", "palang", "પલંગ", "पलंग"]):
                if lang == "gu":
                    return (
                        f"અમારા *Custom Storage Bed* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                        f"• *ક્વીન પ્લેટફોર્મ બેડ (આશરે 6.5x5 ફૂટ)*: *₹26,000 નેટ* (હાર્ડવુડ પ્લાય, 1mm લેમિનેટ અને ૨ સ્ટોરેજ ડ્રોઅર્સ)\n\n"
                        f"• *કિંગ હાઇડ્રોલિક બેડ (આશરે 6.5x6 ફૂટ)*: *₹42,000 નેટ* (IS 710 મરીન પ્લાય, હેવી હાઇડ્રોલિક પંપ અને કુશન હેડબોર્ડ)\n\n"
                        f"*(ડિલિવરી અને ઓન-સાઇટ ફિટિંગ સહિત, કોઈ છુપો ચાર્જ નથી.)*"
                    )
                elif lang == "hi":
                    return (
                        f"हमारे *Custom Storage Bed* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                        f"• *क्वीन प्लेटफॉर्म बेड (लगभग 6.5x5 फीट)*: *₹26,000 नेट* (हार्डवुड प्लाई, 1mm लैमिनेट और २ बॉटम ड्रॉअर्स)\n\n"
                        f"• *किंग हाइड्रोलिक बेड (लगभग 6.5x6 फीट)*: *₹42,000 नेट* (IS 710 मरीन प्लाई, हैवी हाइड्रोलिक पंप और कुशन हेडबोर्ड)\n\n"
                        f"*(डोरस्टेप डिलीवरी और असेंबली सहित, कोई अतिरिक्त चार्ज नहीं है।)*"
                    )
                return (
                    f"Our final workshop-direct price for *Custom Storage Bed* is:\n\n"
                    f"• *Queen Size Platform Bed (approx 6.5ft x 5ft)*: *₹26,000 net* (Hardwood ply with 1mm laminate & 2 bottom storage drawers)\n\n"
                    f"• *King Size Hydraulic Bed (approx 6.5ft x 6ft)*: *₹42,000 net* (IS 710 marine ply, heavy-duty hydraulic pump & cushioned headboard)\n\n"
                    f"*(All-inclusive with doorstep delivery and on-site assembly with zero hidden charges.)*"
                )

            # 4. Wooden Windows
            if any(k in p_lower for k in ["window", "windows", "khidki", "khidkhi", "બારી", "बारी", "खिड़की"]):
                if lang == "gu":
                    return (
                        f"અમારી *Custom Wooden Windows* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                        f"• *સીઝન્ડ સીપી સાગવાન બારી*: *₹1,250 પ્રતિ ચોરસ ફૂટ* (વેધરપ્રૂફ ચોખટ, 5mm ટફન્ડ ગ્લાસ અને SS-304 મચ્છર જાળી શટર સહિત નેટ ભાવ).\n\n"
                        f"*(કોઈ છુપો ચાર્જ નથી.)*"
                    )
                elif lang == "hi":
                    return (
                        f"हमारी *Custom Wooden Windows* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                        f"• *सीजन्ड सीपी सागवान खिड़की*: *₹1,250 प्रति स्क्वायर फीट* (वेदरप्रूफ चौखट, 5mm टफन्ड ग्लास और SS-304 मच्छर जाली पल्ले सहित नेट रेट)।\n\n"
                        f"*(कोई अतिरिक्त चार्ज नहीं है।)*"
                    )
                return (
                    f"Our final workshop-direct price for *Custom Wooden Windows* is:\n\n"
                    f"• *Seasoned CP Teak (Sagwan) Window*: *₹1,250 per sq. ft.* (Net price including weather-proof frame, 5mm toughened glass, and SS-304 insect mesh shutter).\n\n"
                    f"*(Zero hidden charges.)*"
                )

            # 5. Cabinet / Wardrobe / Modular Kitchen / General Sheet-good Millwork
            if sqft > 0:
                tot_lam = sqft * 1320
                tot_pu = sqft * 1680
                dim_title = f" ({dim_str}, {sqft} ચોરસ ફૂટ)" if lang == "gu" else (f" ({dim_str}, {sqft} स्क्वायर फीट)" if lang == "hi" else f" ({dim_str}, {sqft} sq.ft.)")
                if lang == "gu":
                    return (
                        f"તમારી *{p_name}*{dim_title} નો અમારો છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                        f"• *1mm એન્ટી-સ્ક્રેચ લેમિનેટ ફિનિશ*: *₹1,320/ચોરસ ફૂટ* → *₹{tot_lam:,} નેટ*\n\n"
                        f"• *પ્રીમિયમ 4-કોટ PU પોલિશ (ઇટાલિયન ફિનિશ)*: *₹1,680/ચોરસ ફૂટ* → *₹{tot_pu:,} નેટ*\n\n"
                        f"*(આમાં 18mm IS 710 BWP વોટરપ્રૂફ મરીન પ્લાય, હેટીચ જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ, કારીગરી, ટ્રાન્સપોર્ટ અને ફિટિંગ બધું જ સામેલ છે, કોઈ પણ છુપો ચાર્જ નથી.)*"
                    )
                elif lang == "hi":
                    return (
                        f"आपकी *{p_name}*{dim_title} के लिए हमारा अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                        f"• *1mm एंटी-स्क्रैच लैमिनेट फिनिश*: *₹1,320/स्क्वायर फीट* → *₹{tot_lam:,} net*\n\n"
                        f"• *प्रीमियम 4-कोट PU पॉलिश (इटैलियन फिनिश)*: *₹1,680/स्क्वायर फीट* → *₹{tot_pu:,} net*\n\n"
                        f"*(इसमें 18mm IS 710 BWP वाटरप्रूफ मरीन प्लाई, हेटिच जर्मन सॉफ्ट-क्लोज़ फिटिंग्स, कुशल लेबर, ट्रांसपोर्ट और ऑन-साइट फिटिंग सब शामिल है, कोई अतिरिक्त चार्ज नहीं है।)*"
                    )
                return (
                    f"Our final workshop-direct price for your *{p_name}*{dim_title} is:\n\n"
                    f"• *1mm Anti-Scratch Laminate Finish*: *₹1,320/sq.ft* → *₹{tot_lam:,} net*\n\n"
                    f"• *Premium 4-Coat PU Polish (Italian Finish)*: *₹1,680/sq.ft* → *₹{tot_pu:,} net*\n\n"
                    f"*(Includes 18mm IS 710 BWP Waterproof Marine Ply, Hettich German soft-close fittings, skilled labour, transport, and complete fitting with zero hidden charges.)*"
                )
            else:
                if lang == "gu":
                    return (
                        f"અમારી *{p_name}* માટે છેલ્લો અને પાક્કો વર્કશોપ ભાવ:\n\n"
                        f"• *1mm એન્ટી-સ્ક્રેચ લેમિનેટ ફિનિશ*: *₹1,250 થી ₹1,350 પ્રતિ ચોરસ ફૂટ* (નેટ ફાઇનલ ભાવ)\n\n"
                        f"• *પ્રીમિયમ 4-કોટ PU પોલિશ (ઇટાલિયન ફિનિશ)*: *₹1,650 થી ₹1,750 પ્રતિ ચોરસ ફૂટ* (નેટ ફાઇનલ ભાવ)\n\n"
                        f"*(આ અમારો વર્કશોપ-ડાયરેક્ટ આખરી ભાવ છે જેમાં 18mm IS 710 મરીન પ્લાય, હેટીચ જર્મન ફિટિંગ્સ, મજૂરી અને સાઇટ ફિટિંગ બધું જ આવી ગયું, કોઈ છુપો ખર્ચ નથી.)*"
                    )
                elif lang == "hi":
                    return (
                        f"हमारी *{p_name}* के लिए अंतिम और फाइनल वर्कशॉप रेट:\n\n"
                        f"• *1mm एंटी-स्क्रैच लैमिनेट फिनिश*: *₹1,250 से ₹1,350 प्रति स्क्वायर फीट* (ऑल-इन्क्लूसिव नेट रेट)\n\n"
                        f"• *प्रीमियम 4-कोट PU पॉलिश (इटैलियन फिनिश)*: *₹1,650 से ₹1,750 प्रति स्क्वायर फीट* (ऑल-इन्क्लूसिव नेट रेट)\n\n"
                        f"*(यह हमारा सीधा वर्कशॉप का सबसे वाजिब रेट है जिसमें 18mm IS 710 मरीन प्लाई, हेटिच जर्मन फिटिंग्स, लेबर और फिटिंग सब शामिल है, कोई छिपा हुआ खर्च नहीं है।)*"
                    )
                return (
                    f"Our final workshop-direct price for *{p_name}* is:\n\n"
                    f"• *1mm Anti-Scratch Laminate Finish*: *₹1,250 – ₹1,350 per sq. ft.* (all-inclusive net price)\n\n"
                    f"• *Premium 4-Coat PU Polish (Italian Finish)*: *₹1,650 – ₹1,750 per sq. ft.* (all-inclusive net price)\n\n"
                    f"*(This is our absolute best workshop-direct rate including 18mm IS 710 BWP Marine Ply, Hettich German soft-close fittings, skilled joinery, transport, and on-site installation with zero hidden charges.)*"
                )

        # 3. Customer agreed to schedule a visit or affirmed visit offer ("Haa aa jaiye", "Sure", "Saturday 11:30")
        if (user_is_scheduling or user_is_affirming or has_affirming_phrase) and session.appointment_status != "confirmed":
            session.appointment_status = "requested"
            if not session.appointment_slot:
                if any(w in text_lower for w in ["sunday", "રવિવાર", "रविवार", "4 pm", "સાંજે", "शाम"]):
                    session.appointment_slot = "રવિવારે સાંજે 4:00 વાગ્યે (Sunday 4:00 PM)" if lang == "gu" else ("रविवार शाम 4:00 बजे (Sunday 4:00 PM)" if lang == "hi" else "Sunday at 4:00 PM")
                else:
                    session.appointment_slot = "શનિવારે સવારે 11:30 વાગ્યે (Saturday 11:30 AM)" if lang == "gu" else ("शनिवार सुबह 11:30 बजे (Saturday 11:30 AM)" if lang == "hi" else "Saturday at 11:30 AM")

            slot_name = session.appointment_slot
            project_context = f" ({session.project_type})" if session.project_type else ""

            if lang == "gu":
                return (
                    f"બહુ સરસ! અમે આ *{slot_name}* નો સમય તમારા માટે નોંધી લીધો છે. 📅✨\n\n"
                    f"કૃપા કરીને તમારું પૂરું સરનામું (ફ્લેટ/મકાન નંબર, સોસાયટી/એપાર્ટમેન્ટ) અને નજીકનો લેન્ડમાર્ક જણાવી દેશો જેથી અમારી ટીમ સમયસર પહોંચી શકે. 📍\n\n"
                    f"(જો રવિવારે સાંજે 4:00 વાગ્યાનો સમય વધુ અનુકૂળ હોય તો એ પણ જણાવી શકો છો.)\n\n"
                    f"અમારી માસ્ટર કારીગર ટીમ લેસર મેઝરમેન્ટ ટૂલ્સ અને લાકડા/PU ફિનિશના અસલી સેમ્પલ્સ સાથે લાવશે{project_context}! 📐🪵"
                )
            elif lang == "hi":
                return (
                    f"बहुत बढ़िया! हमने इस *{slot_name}* का समय आपके लिए नोट कर लिया है। 📅✨\n\n"
                    f"कृपया अपना पूरा पता (मकान/फ्लैट नंबर, सोसायटी/अपार्टमेंट) और नज़दीकी लैंडमार्क शेयर कर दीजिए ताकि हमारी टीम समय पर पहुँच सके। 📍\n\n"
                    f"(अगर रविवार शाम 4:00 बजे का समय ज्यादा सुविधाजनक हो तो वो भी बता सकते हैं।)\n\n"
                    f"हमारी मास्टर कारिगर टीम लेज़र मेज़रमेंट टूल्स और लकड़ी/PU फिनिश के असली सैंपल्स साथ लाएगी{project_context}! 📐🪵"
                )
            return (
                f"Wonderful! We have noted *{slot_name}* for your home visit. 📅✨\n\n"
                f"Please share your complete address (Flat/House No., Society/Apartment name) and nearest landmark so our team can arrive on time. 📍\n\n"
                f"(If Sunday at 4:00 PM works better for you, just let us know!)\n\n"
                f"Our master carpenter team will bring laser measurement tools and physical wood/PU finish swatches{project_context}! 📐🪵"
            )

        # 3b. Follow-up reminder if appointment already requested but address pending
        if session.appointment_status == "requested" and not has_address:
            slot_name = session.appointment_slot or ("શનિવારે સવારે 11:30 વાગ્યે" if lang == "gu" else ("शनिवार सुबह 11:30 बजे" if lang == "hi" else "Saturday at 11:30 AM"))
            if lang == "gu":
                return (
                    f"જી! અમે તમારી મુલાકાત માટે *{slot_name}* નો સમય ધ્યાનમાં લીધો છે. 📅✨\n\n"
                    f"કૃપા કરીને તમારું પૂરું સરનામું (ફ્લેટ/મકાન નંબર, સોસાયટી) અને નજીકનો લેન્ડમાર્ક જણાવી દેશો જેથી અમારી ટીમ સમયસર પહોંચી શકે! 📍"
                )
            elif lang == "hi":
                return (
                    f"जी! हमने आपकी विज़िट के लिए *{slot_name}* का समय ध्यान में रखा है। 📅✨\n\n"
                    f"कृपया अपना पूरा पता (मकान/फ्लैट नंबर, सोसायटी/अपार्टमेंट) और नज़दीकी लैंडमार्क शेयर कर दीजिए ताकि हमारी टीम समय पर पहुँच सके! 📍"
                )
            return (
                f"Understood! We have noted *{slot_name}* for your site visit. 📅✨\n\n"
                f"Please share your complete address (Flat/House No., Society/Apartment name) and nearest landmark so our team can arrive on time! 📍"
            )

        # 3c. Reassurance if appointment already confirmed
        if session.appointment_status == "confirmed":
            slot_name = session.appointment_slot or ("શનિવારે સવારે 11:30 વાગ્યે" if lang == "gu" else ("शनिवार सुबह 11:30 बजे" if lang == "hi" else "Saturday at 11:30 AM"))
            if lang == "gu":
                return (
                    f"જી ચોક્કસ! તમારી વિઝિટ *{slot_name}* માટે પહેલેથી જ કન્ફર્મ છે. 👍\n\n"
                    f"અમારી ટીમ પહોંચવાના 30 મિનિટ પહેલાં તમને ફોન કરશે. જો કોઈ ડિઝાઇન કે ફોટો હોય તો અહીં મોકલી શકો છો! 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"जी बिल्कुल! आपकी विज़िट *{slot_name}* के लिए पहले से ही पक्की है। 👍\n\n"
                    f"हमारी टीम पहुंचने से 30 मिनट पहले आपको कॉल करेगी। अगर कोई डिज़ाइन या फोटो हो तो आप यहां भेज सकते हैं! 🪵✨"
                )
            return (
                f"Yes, certainly! Your visit is confirmed for *{slot_name}*. 👍\n\n"
                f"Our team will call you 30 minutes before arrival. Feel free to share any photos or design ideas here anytime! 🪵✨"
            )


        # 4. Greetings & Initial Discovery
        greetings = {"hi", "hello", "hey", "namaste", "start", "greetings", "kemcho", "kem cho", "કેમ છો", "નમસ્તે", "પ્રણામ", "नमस्ते", "प्रणाम", "राधे राधे", "जय श्री कृष्णा"}
        has_greeting_word = bool(words.intersection(greetings)) or any(g in text_lower for g in ["kem cho", "કેમ છો", "નમસ્તે", "नमस्ते"])
        is_greeting = has_greeting_word and (
            len(words) <= 3 or (not session.project_type and not session.dimensions and not session.preferred_materials)
        )
        if is_greeting and len(session.history) <= 2:
            if lang == "gu":
                return (
                    f"નમસ્તે {name_title}! 🙏\n\n"
                    f"હું *રાજેશ શર્મા*, હેરિટેજ વુડવર્ક્સ (Heritage Woodworks) થી. "
                    f"અમે સાગવાન (Teak), શીશમ અને વોટરપ્રૂફ મરીન પ્લાયવુડમાંથી કબાટ/વોર્ડરોબ, મોડ્યુલર કિચન, સોફા સેટ, ડાઇનિંગ ટેબલ અને બારી-બારણા બનાવીએ છીએ.\n\n"
                    f"તમારે તમારા ઘર માટે શું બનાવવું છે? 🪵"
                )
            elif lang == "hi":
                return (
                    f"नमस्ते {name_title}! 🙏\n\n"
                    f"मैं *राजेश शर्मा*, हेरिटेज वुडवर्क्स (Heritage Woodworks) से। "
                    f"हम सागवान, शीशम और वाटरप्रूफ मरीन प्लाईवुड में कस्टमाइज्ड कबाट/वार्डरोब, मॉड्युलर किचन, लकड़ी के सोफा सेट, डाइनिंग टेबल और मेन डोर-खिड़कियां बनाते हैं।\n\n"
                    f"आप अपने घर के लिए क्या बनवाना चाहते हैं? 🪵"
                )
            return (
                f"Namaste {name_title}! 🙏\n\n"
                f"I am *Rajesh Sharma* from *Heritage Woodworks*. "
                f"We make custom wardrobes, modular kitchens, solid Teak/Sheesham sofas & dining sets, and architectural doors & windows.\n\n"
                f"What piece are you planning to make for your home? 🪵"
            )

        # Check if customer inquiry asks about Labour, Transport, or Total All-Inclusive Turnkey Cost
        is_labour_transport_inquiry = any(
            k in text_lower for k in [
                "labour", "labor", "transport", "transportation", "shipping", "delivery", "fitting charge",
                "total cost including", "including labour", "including transport", "labour and transport",
                "total cost", "all inclusive", "hidden charge",
                "લેબર", "ટ્રાન્સપોર્ટ", "ડિલિવરી", "મજૂરી", "ભાડું",
                "मजदूरी", "लेबर", "ट्रांसपोर्ट", "डिलीवरी", "भाड़ा"
            ]
        )
        if is_labour_transport_inquiry and (session.dimensions or session.project_type):
            dim_info = parse_dimension_details(session.dimensions, text_lower)
            quote = calculate_turnkey_quote(session.project_type, dim_info, lang)
            p_name = session.project_type or "Custom Woodwork"
            dim_str = session.dimensions or f"{int(quote.get('sqft', 80))} sq.ft."

            if quote.get("type") == "cabinet_wardrobe":
                b_lam = quote["breakdown_lam"]
                if lang == "gu":
                    return (
                        f"હા {name_title}! 🙏 અમારો ભાવ સંપૂર્ણ ટર્ન-કી (લેબર અને ટ્રાન્સપોર્ટ સહિત) નો હોય છે.\n\n"
                        f"તમારા *{p_name}* ({dim_str}, {int(quote['sqft'])} ચોરસ ફૂટ) નો સંપૂર્ણ હિસાબ:\n\n"
                        f"• *18mm IS 710 BWP મરીન પ્લાય*: ₹{b_lam['materials']:,}\n"
                        f"• *જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ (Hettich)*: ₹{b_lam['fittings']:,}\n"
                        f"• *1mm એન્ટી-સ્ક્રેચ લેમિનેટ ફિનિશ*: ₹{b_lam['finish']:,}\n"
                        f"• 🔨 *માસ્ટર કારીગરી & જોઈનરી લેબર*: *₹{b_lam['labour']:,}*\n"
                        f"• 🚚 *ઘર સુધી સેફ ટ્રાન્સપોર્ટ & ફિટિંગ*: *₹{b_lam['transport']:,}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"• *કુલ ટર્ન-કી કિંમત (લેમિનેટ)*: *₹{quote['total_lam']:,}* (આશરે ₹{quote['rate_lam']}/ચોરસ ફૂટ)\n"
                        f"• *(અથવા પ્રીમિયમ 4-કોટ PU પોલિશમાં*: *₹{quote['total_pu']:,}* ઓલ-ઇન્ક્લુઝિવ)\n\n"
                        f"✅ *ઝીરો હિડન ચાર્જ*: સાઇટ પર કોઈ અલગથી મજૂરી કે ડિલિવરી ચાર્જ નથી લાગતો. બધું જ આમાં આવી ગયું!\n\n"
                        f"• *સમય*: {quote['timeline']} + 2 દિવસ ફિટિંગ.\n\n"
                        f"લેવલ અને સાઇઝ ચેક કરવા માટે શું અમે આ *શનિવારે સવારે 11:30 વાગ્યે* કે *રવિવારે સાંજે 4:00 વાગ્યે* ફ્રી માપણી મુલાકાત રાખીએ? 📐🪵"
                    )
                elif lang == "hi":
                    return (
                        f"जी हाँ {name_title}! 🙏 हमारा कोटेशन पूरी तरह से टर्न-की और ऑल-इन्क्लूसिव (लेबर और ट्रांसपोर्ट सहित) होता है।\n\n"
                        f"आपकी *{p_name}* ({dim_str}, {int(quote['sqft'])} स्क्वायर फीट) का पूरा हिसाब:\n\n"
                        f"• *18mm IS 710 BWP मरीन प्लाई*: ₹{b_lam['materials']:,}\n"
                        f"• *जर्मन सॉफ्ट-क्लोज़ फिटिंग्स (Hettich)*: ₹{b_lam['fittings']:,}\n"
                        f"• *1mm एंटी-स्क्रैच लैमिनेट फिनिश*: ₹{b_lam['finish']:,}\n"
                        f"• 🔨 *प्रिसिजन कारपेंट्री & वर्कशॉप लेबर*: *₹{b_lam['labour']:,}*\n"
                        f"• 🚚 *डोरस्टेप सेफ ट्रांसपोर्ट & ऑन-साइट फिटिंग*: *₹{b_lam['transport']:,}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"• *कुल टर्न-की लागत (लैमिनेट)*: *₹{quote['total_lam']:,}* (लगभग ₹{quote['rate_lam']}/स्क्वायर फीट)\n"
                        f"• *(अथवा प्रीमियम 4-कोट PU पॉलिश में*: *₹{quote['total_pu']:,}* ऑल-इन्क्लूसिव)\n\n"
                        f"✅ *ज़ीरो हिडन चार्ज गारंटी*: इसमें पूरा मटेरियल, हार्डवेयर, लेबर और साइट पर इंस्टॉलेशन शामिल है। डिलीवरी पर कोई अतिरिक्त लेबर या किराया नहीं देना होगा!\n\n"
                        f"• *समय*: {quote['timeline']} + 2 दिन साइट फिटिंग।\n\n"
                        f"क्या हम इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* 15 मिनट की फ्री विज़िट तय कर लें? 📐🪵"
                    )
                return (
                    f"Yes {name_title}! 🙏 Our quotation is 100% turn-key and all-inclusive of labour, transport, and fitting.\n\n"
                    f"Here is the complete turn-key cost breakdown for your *{p_name}* ({dim_str}, {int(quote['sqft'])} sq.ft.):\n\n"
                    f"• *18mm IS 710 BWP Marine Plywood*: ₹{b_lam['materials']:,}\n"
                    f"• *German Soft-Close Hardware (Hettich)*: ₹{b_lam['fittings']:,}\n"
                    f"• *1mm Anti-Scratch Laminate Finish*: ₹{b_lam['finish']:,}\n"
                    f"• 🔨 *Precision Carpentry & Workshop Joinery Labour*: *₹{b_lam['labour']:,}*\n"
                    f"• 🚚 *Doorstep Safe Transport & On-site Fitting*: *₹{b_lam['transport']:,}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"• *Total Turn-key Cost (Laminate)*: *₹{quote['total_lam']:,}* (around ₹{quote['rate_lam']}/sq.ft)\n"
                    f"• *(Or in Premium 4-Coat PU Polish*: *₹{quote['total_pu']:,}* all-inclusive)\n\n"
                    f"✅ *Zero Hidden Charges Guarantee*: This includes complete raw materials, hardware, workshop fabrication, transport, and on-site alignment. No extra labour or delivery fee is charged at site!\n\n"
                    f"• *Timeline*: {quote['timeline']} + 2 days installation.\n\n"
                    f"Shall we arrange a quick 15-minute measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM* to verify site levels? 📐🪵"
                )
            else:
                tot = quote.get("total", 50000)
                b = quote.get("breakdown", {})
                labour_val = b.get("labour", int(tot * 0.18))
                transport_val = b.get("transport", int(tot * 0.05))
                if lang == "gu":
                    return (
                        f"હા {name_title}! 🙏 અમારો ભાવ ટર્ન-કી હોય છે, જેમાં મજૂરી અને ટ્રાન્સપોર્ટ બધું જ સામેલ છે:\n\n"
                        f"• *કામ*: *{p_name}* ({dim_str})\n"
                        f"• 🔨 *કારીગરી અને લેબર*: *₹{labour_val:,}*\n"
                        f"• 🚚 *ટ્રાન્સપોર્ટ અને ફિટિંગ*: *₹{transport_val:,}*\n"
                        f"• *કુલ કિંમત*: *₹{tot:,}* (ઓલ-ઇન્ક્લુઝિવ)\n\n"
                        f"સાઇટ પર કોઈ અલગ ખર્ચ નથી થતો. શું અમે રૂબરૂ માપણી માટે આવીએ? 📐"
                    )
                elif lang == "hi":
                    return (
                        f"जी हाँ {name_title}! 🙏 हमारा कोटेशन ऑल-इन्क्लूसिव होता है, जिसमें लेबर और ट्रांसपोर्ट सब शामिल है:\n\n"
                        f"• *प्रोजेक्ट*: *{p_name}* ({dim_str})\n"
                        f"• 🔨 *कारीगरी और लेबर*: *₹{labour_val:,}*\n"
                        f"• 🚚 *ट्रांसपोर्ट और फिटिंग*: *₹{transport_val:,}*\n"
                        f"• *कुल लागत*: *₹{tot:,}* (ऑल-इन्क्लूसिव)\n\n"
                        f"डिलीवरी पर कोई अलग चार्ज नहीं लगेगा। क्या हम नाप लेने के लिए विज़िट तय करें? 📐"
                    )
                return (
                    f"Yes {name_title}! 🙏 Our quotation is all-inclusive of labour, transport, and fitting:\n\n"
                    f"• *Project*: *{p_name}* ({dim_str})\n"
                    f"• 🔨 *Skilled Labour*: *₹{labour_val:,}*\n"
                    f"• 🚚 *Transport & On-site Assembly*: *₹{transport_val:,}*\n"
                    f"• *Total Turn-key Cost*: *₹{tot:,}* (all-inclusive)\n\n"
                    f"There are zero hidden costs on delivery. Shall we schedule a site measurement visit? 📐"
                )

        # Check if customer asks for an Exact / Instant Quote
        is_exact_quote_inquiry = any(
            k in text_lower for k in [
                "exact quote", "share me the exact quote", "share quote", "give quote", "instant quote",
                "quotation", "final quote", "pukka quote", "exact cost", "send quote",
                "कोटेशन", "पक्का कोटेशन", "पक्का भाव", "हिसाब", "ક્વોટેશન", "પાક્કો ભાવ"
            ]
        ) or (words == {"quote"} or words == {"rates"})
        if is_exact_quote_inquiry and (session.dimensions or session.project_type):
            dim_info = parse_dimension_details(session.dimensions, text_lower)
            quote = calculate_turnkey_quote(session.project_type, dim_info, lang)
            p_name = session.project_type or "Custom Cabinet"
            dim_str = session.dimensions or f"{int(quote.get('sqft', 80))} sq.ft."

            if quote.get("type") == "cabinet_wardrobe":
                if lang == "gu":
                    return (
                        f"અહીં તમારી *{p_name}* ({dim_str}, {int(quote['sqft'])} ચોરસ ફૂટ) નું સત્તાવાર ક્વોટેશન છે, {name_title}:\n\n"
                        f"📐 *માપ*: {int(quote['sqft'])} ચોરસ ફૂટ\n"
                        f"🪵 *મટિરિયલ*: 18mm IS 710 BWP વોટરપ્રૂફ મરીન પ્લાય (10 વર્ષની વોરંટી)\n"
                        f"⚙️ *હાર્ડવેર*: હેટીચ (Hettich) જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ\n\n"
                        f"📦 *ટર્ન-કી પેકેજ (લેબર & ટ્રાન્સપોર્ટ સહિત)*:\n"
                        f"1️⃣ *વિકલ્પ A — 1mm એન્ટી-સ્ક્રેચ લેમિનેટ ફિનિશ*:\n"
                        f"   • કુલ: *₹{quote['total_lam']:,}* (આશરે ₹{quote['rate_lam']}/ચોરસ ફૂટ)\n"
                        f"2️⃣ *વિકલ્પ B — પ્રીમિયમ 4-કોટ PU પોલિશ (ઇટાલિયન ફિનિશ)*:\n"
                        f"   • કુલ: *₹{quote['total_pu']:,}* (આશરે ₹{quote['rate_pu']}/ચોરસ ફૂટ)\n\n"
                        f"⏳ *બનાવવાનો સમય*: {quote['timeline']} + 2 દિવસ ફિટિંગ.\n"
                        f"🛡️ *વોરંટી*: લાકડા અને પ્લાયવુડ સ્ટ્રક્ચર પર 10 વર્ષની ગેરંટી.\n\n"
                        f"તમે કયું ફિનિશ પસંદ કરશો — *લેમિનેટ* કે *PU પોલિશ*? 🪵✨"
                    )
                elif lang == "hi":
                    return (
                        f"यह रहा आपकी *{p_name}* ({dim_str}, {int(quote['sqft'])} स्क्वायर फीट) का पक्का कोटेशन, {name_title}:\n\n"
                        f"📐 *क्षेत्रफल*: {int(quote['sqft'])} स्क्वायर फीट\n"
                        f"🪵 *कोर मटेरियल*: 18mm IS 710 BWP वाटरप्रूफ मरीन प्लाई (10 साल वारंटी)\n"
                        f"⚙️ *हार्डवेयर*: हेटिच (Hettich) जर्मन सॉफ्ट-क्लोज़ हिन्जेस और चैनल्स\n\n"
                        f"📦 *टर्न-की पैकेज (लेबर और ट्रांसपोर्ट सहित)*:\n"
                        f"1️⃣ *विकल्प A — 1mm एंटी-स्क्रैच लैमिनेट फिनिश*:\n"
                        f"   • कुल लागत: *₹{quote['total_lam']:,}* (लगभग ₹{quote['rate_lam']}/स्क्वायर फीट)\n"
                        f"2️⃣ *विकल्प B — प्रीमियम 4-कोट PU पॉलिश (इटैलियन फिनिश)*:\n"
                        f"   • कुल लागत: *₹{quote['total_pu']:,}* (लगभग ₹{quote['rate_pu']}/स्क्वायर फीट)\n\n"
                        f"⏳ *निर्माण समय*: {quote['timeline']} + 2 दिन ऑन-साइट इंस्टॉलेशन।\n"
                        f"🛡️ *वारंटी*: प्लाईवुड और फ्रेम पर 10 साल की मजबूती गारंटी।\n\n"
                        f"आप कौन सा फिनिश पसंद करेंगे — *लैमिनेट* या *PU पॉलिश*? 🪵✨"
                    )
                return (
                    f"Here is your official workshop quotation for *{p_name}* ({dim_str}, {int(quote['sqft'])} sq.ft.), {name_title}:\n\n"
                    f"📐 *Project Area*: {int(quote['sqft'])} sq. ft.\n"
                    f"🪵 *Core Material*: 18mm IS 710 Boiling Water Proof (BWP) Marine Ply (10-Year Warranty)\n"
                    f"⚙️ *Hardware*: German Soft-Close Hinges & Heavy-Duty Telescopic Channels (Hettich)\n\n"
                    f"📦 *Turn-key Packages (All-Inclusive of Labour & Transport)*:\n"
                    f"1️⃣ *Option A — 1mm Anti-Scratch Laminate (Merino/Century)*:\n"
                    f"   • Total: *₹{quote['total_lam']:,}* (around ₹{quote['rate_lam']}/sq.ft)\n"
                    f"   • Includes: Ply + German Fittings + Finish + Labour + Transport & Fitting.\n"
                    f"2️⃣ *Option B — Premium 4-Coat PU Polish (Italian Finish)*:\n"
                    f"   • Total: *₹{quote['total_pu']:,}* (around ₹{quote['rate_pu']}/sq.ft)\n"
                    f"   • Seamless, luxurious matte/satin showroom finish.\n\n"
                    f"⏳ *Completion Timeline*: {quote['timeline']}.\n"
                    f"🛡️ *Warranty*: 10 Years on core timber & plywood structure.\n\n"
                    f"Which finish would you prefer — *Laminate* or *PU Polish*? Or shall we book a quick visit to inspect the site? 📐✨"
                )

        # Check if customer selects a specific finish: Laminate, PU, Acrylic
        is_finish_selection = any(
            f in text_lower for f in [
                "laminate", "pu", "pu polish", "acrylic", "veneer",
                "લેમિનેટ", "પીયુ", "એક્રેલિક", "વિનિયર",
                "लैमिनेट", "पीयू", "एक्रेलिक", "विनीयर"
            ]
        ) and len(words) <= 4
        if is_finish_selection:
            dim_info = parse_dimension_details(session.dimensions, text_lower)
            quote = calculate_turnkey_quote(session.project_type, dim_info, lang)
            p_name = session.project_type or "Custom Furniture"
            dim_str = session.dimensions or f"{int(quote.get('sqft', 80))} sq.ft."

            if "pu" in text_lower or "પીયુ" in text_lower or "पीयू" in text_lower:
                pu_cost = quote.get("total_pu") or quote.get("total") or 150000
                if lang == "gu":
                    return (
                        f"ઉત્તમ પસંદગી, {name_title}! ✨ PU (Polyurethane) ઇટાલિયન પોલિશ તમારા *{p_name}* ({dim_str}) માટે સિલેક્ટ થઈ ગયું છે.\n\n"
                        f"• *કુલ ટર્ન-કી કિંમત*: *₹{pu_cost:,}* (18mm મરીન પ્લાય, હેટીચ ફિટિંગ્સ, 4-કોટ PU ફિનિશ, લેબર અને ટ્રાન્સપોર્ટ સહિત).\n"
                        f"• *બનાવવાનો સમય*: {quote['timeline']}.\n\n"
                        f"PU માં આપણે મેટ (Matte), સેટિન (Satin) કે હાઈ-ગ્લોસ (High-Gloss) લૂક રાખી શકીએ છીએ.\n\n"
                        f"શું અમે આ *શનિવારે સવારે 11:30 વાગ્યે* કે *રવિવારે સાંજે 4:00 વાગ્યે* અસલી PU સેમ્પલ્સ સાથે માપણી માટે આવીએ? 📐🪵"
                    )
                elif lang == "hi":
                    return (
                        f"शानदार पसंद, {name_title}! ✨ PU (Polyurethane) इटैलियन पॉलिश आपकी *{p_name}* ({dim_str}) के लिए तय हो गई है।\n\n"
                        f"• *कुल टर्न-की लागत*: *₹{pu_cost:,}* (18mm मरीन प्लाई, हेटिच फिटिंग्स, 4-कोट PU फिनिश, कुशल लेबर और ट्रांसपोर्ट सहित)।\n"
                        f"• *निर्माण समय*: {quote['timeline']}.\n\n"
                        f"PU में हम मैट (Matte), सैटिन (Satin) अथवा हाई-ग्लॉस (High-Gloss) बना सकते हैं।\n\n"
                        f"क्या हम इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* असली PU फिनिश सैंपल दिखाने आपके घर आएं? 📐🪵"
                    )
                return (
                    f"Excellent choice, {name_title}! ✨ PU (Polyurethane) Italian Polish is selected for your *{p_name}* ({dim_str}).\n\n"
                    f"• *Total Turn-key Cost*: *₹{pu_cost:,}* (Includes 18mm Marine Ply, Hettich German soft-close fittings, 4-coat PU finish, skilled polish labour, and transport/fitting).\n"
                    f"• *Timeline*: {quote['timeline']}.\n\n"
                    f"We can execute Matte, Satin, or High-Gloss PU. Shall we arrange a quick measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM* to show you physical PU swatches? 📐🪵"
                )
            else:
                lam_cost = quote.get("total_lam") or quote.get("total") or 120000
                if lang == "gu":
                    return (
                        f"સમજી ગયો, {name_title}! 🪵 1mm એન્ટી-સ્ક્રેચ લેમિનેટ તમારા *{p_name}* ({dim_str}) માટે સિલેક્ટ થઈ ગયું છે.\n\n"
                        f"• *કુલ ટર્ન-કી કિંમત*: *₹{lam_cost:,}* (18mm IS 710 મરીન પ્લાય, હેટીચ ફિટિંગ્સ, લેમિનેટ, લેબર અને ટ્રાન્સપોર્ટ સહિત).\n"
                        f"• *બનાવવાનો સમય*: {quote['timeline']}.\n\n"
                        f"લેમિનેટમાં મેટ, સુએડ (Suede) અને ટેક્ષ્ચર વુડ ગ્રેઇન ઉપલબ્ધ છે.\n\n"
                        f"શું અમે લેમિનેટ કેટલોગ સાથે આ *શનિવારે સવારે 11:30 વાગ્યે* કે *રવિવારે સાંજે 4:00 વાગ્યે* માપણી મુલાકાત ગોઠવીએ? 📐✨"
                    )
                elif lang == "hi":
                    return (
                        f"समझ गया, {name_title}! 🪵 1mm एंटी-स्क्रैच लैमिनेट आपकी *{p_name}* ({dim_str}) के लिए तय हो गया है।\n\n"
                        f"• *कुल टर्न-की लागत*: *₹{lam_cost:,}* (18mm IS 710 मरीन प्लाई, हेटिच फिटिंग्स, 1mm लैमिनेट, लेबर और ट्रांसपोर्ट सहित)।\n"
                        f"• *निर्माण समय*: {quote['timeline']}.\n\n"
                        f"लैमिनेट में मैट, सुएड (Suede) और वुड-ग्रेन टेक्सचर के बहुत शानदार शेड्स उपलब्ध हैं।\n\n"
                        f"क्या हम शेड कैटलॉग के साथ इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* विज़िट तय करें? 📐✨"
                    )
                return (
                    f"Understood, {name_title}! 🪵 1mm Anti-Scratch Laminate (Merino / Century) is selected for your *{p_name}* ({dim_str}).\n\n"
                    f"• *Total Turn-key Cost*: *₹{lam_cost:,}* (Includes 18mm BWP Marine Ply, Hettich German soft-close fittings, 1mm laminate, skilled labour, and transport/fitting).\n"
                    f"• *Timeline*: {quote['timeline']}.\n\n"
                    f"We have great texture options: Matte, Suede, and Wood-Grain solid patterns.\n\n"
                    f"Would you like us to bring physical laminate shade cards to your site this *Saturday at 11:30 AM* or *Sunday at 4:00 PM*? 📐✨"
                )

        # 5. Customer states a Budget or requests Bargaining / Discount / Negotiation in current turn
        has_new_budget_number = bool(
            re.search(r"(?:budget\s*(?:is|of|around)?|have|max|for|in|only|બજેટ|ખર્ચ|बजट)\s*[:=]?\s*(?:rs\.?|inr|₹)?\s*(\d{1,3}(?:,\d{3})+|\d+)", text_lower)
            or re.search(r"\b(\d{1,3})\s*k\b", text_lower)
        )
        has_bargaining_words = bool(
            any(w in words for w in [
                "budget", "discount", "expensive", "costly", "cheaper", "reduce", "less", "concession", "afford",
                "બજેટ", "ઓછું", "ઓછા", "બજેટમાં", "ઓછો", "બજેટની",
                "बजट", "कम", "कम करो", "डिस्काउंट", "रियायत", "गुंजाइश", "कमती"
            ])
            or any(k in text_lower for k in [
                "too high", "too much", "can you do", "my budget", "within", "max",
                "ભાવ ઓછો", "ભાવ ઘટાડો", "ભાવ ઓછો કરો", "ભાવમાં કંઈક કરો",
                "भाव कम", "कुछ कम करो", "कम हो सकता", "कम करिए", "कम करो", "ज्यादा है", "बहुत महंगा"
            ])
        )
        is_current_bargaining_intent = (has_new_budget_number or has_bargaining_words) and not (
            user_is_affirming or bool(words.intersection(affirmative_words)) or has_affirming_phrase
        )
        if is_current_bargaining_intent:
            return generate_bargaining_response(session, session.customer_budget, user_text)

        # 6. Customer provided Dimensions & Requirements -> Approximate Budget, Timeline in Days, then Slot Booking
        has_dimensions = bool(session.dimensions) or bool(
            re.search(r"(\d+(?:\.\d+)?\s*(?:x|X|×|\*|by|બાય|बाय)\s*\d+)", text_lower)
            or re.search(r"\b(\d+)\s*[-]?\s*(?:seater|seat|sofa|સોફા|સોફો|सोफा|સીટર|सीटर)\b", text_lower)
            or any(w in text_lower for w in ["seater", "સીટર", "सीटर", "king size", "queen size", "feet", "inch", "l-shape", "l shape"])
        )

        if session.project_type and has_dimensions and session.appointment_status not in ("requested", "confirmed"):
            dim_info = parse_dimension_details(session.dimensions, text_lower)
            quote = calculate_turnkey_quote(session.project_type, dim_info, lang)
            p_name = session.project_type or "Custom Furniture"
            dim_str = session.dimensions or f"{int(quote.get('sqft', 80))} sq.ft."

            if quote.get("type") == "cabinet_wardrobe":
                if lang == "gu":
                    return (
                        f"માપ મળી ગયું {name_title}! {dim_str} એટલે આશરે {int(quote['sqft'])} ચોરસ ફૂટ.\n\n"
                        f"18mm IS 710 વોટરપ્રૂફ મરીન પ્લાય અને હેટીચ જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ સાથે:\n"
                        f"- 1mm એન્ટી-સ્ક્રેચ લેમિનેટમાં કુલ ખર્ચ આશરે *₹{quote['total_lam']:,}* થશે (આશરે ₹{quote['rate_lam']}/ચોરસ ફૂટ).\n"
                        f"- પ્રીમિયમ 4-કોટ PU પોલિશમાં આશરે *₹{quote['total_pu']:,}* થશે (આશરે ₹{quote['rate_pu']}/ચોરસ ફૂટ).\n\n"
                        f"આમાં મટિરિયલ, મજૂરી, ટ્રાન્સપોર્ટ અને સાઇટ ફિટિંગ બધું જ આવી ગયું, કોઈ વધારાનો ખર્ચ નથી. વર્કશોપમાં {quote['timeline']} લાગે છે.\n\n"
                        f"દીવાલનું લેવલ અને સાચું માપ લેવા માટે શું અમે આ *શનિવારે સવારે 11:30 વાગ્યે* કે *રવિવારે સાંજે 4:00 વાગ્યે* ફ્રી માપણી માટે આવીએ? 📐🪵"
                    )
                elif lang == "hi":
                    return (
                        f"नाप समझ आ गया {name_title}! {dim_str} यानी लगभग {int(quote['sqft'])} स्क्वायर फीट।\n\n"
                        f"18mm IS 710 वाटरप्रूफ मरीन प्लाई और हेटिच जर्मन सॉफ्ट-क्लोज़ फिटिंग्स के साथ:\n"
                        f"- 1mm एंटी-स्क्रैच लैमिनेट में कुल खर्च लगभग *₹{quote['total_lam']:,}* आएगा (लगभग ₹{quote['rate_lam']}/स्क्वायर फीट)।\n"
                        f"- प्रीमियम 4-कोट PU पॉलिश में लगभग *₹{quote['total_pu']:,}* बैठेगा (लगभग ₹{quote['rate_pu']}/स्क्वायर फीट)।\n\n"
                        f"इसमें पूरा मटेरियल, फिटिंग्स, कुशल लेबर, डिलीवरी और ऑन-साइट फिटिंग सब शामिल है, अलग से कोई खर्च नहीं लगेगा। वर्कशॉप में {quote['timeline']} लगते हैं।\n\n"
                        f"दीवार का सही नाप लेने के लिए क्या हम इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* 15 मिनट की फ्री नाप विज़िट रख लें? 📐🪵"
                    )
                return (
                    f"Got your measurements, {name_title}! {dim_str} comes to around {int(quote['sqft'])} sq.ft.\n\n"
                    f"In 18mm IS 710 waterproof marine ply with Hettich German soft-close fittings:\n"
                    f"- In 1mm anti-scratch laminate, total cost comes to around *₹{quote['total_lam']:,}* net (around ₹{quote['rate_lam']}/sq.ft).\n"
                    f"- In premium 4-coat PU polish, it comes to around *₹{quote['total_pu']:,}* net (around ₹{quote['rate_pu']}/sq.ft).\n\n"
                    f"This is turn-key all-inclusive of raw materials, German hardware, workshop carpentry, transport, and complete site fitting with zero hidden charges. Workshop completion takes about {quote['timeline']}.\n\n"
                    f"Shall we arrange a quick measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM* so we can check wall levels and show you finish swatches? 📐🪵"
                )
            else:
                price_est, timeline_est = get_price_and_timeline_estimate(session.project_type, session.dimensions, lang)
                if lang == "gu":
                    return (
                        f"તમારી *{p_name}* ({dim_str}) ની વિગત મળી ગઈ, {name_title}! 🪵\n\n"
                        f"અમારો અંદાજિત બજેટ ભાવ {price_est} છે, અને વર્કશોપમાં {timeline_est} માં તૈયાર થઈ જાય છે. અમે સીઝન્ડ સાગ/શીશમ લાકડું અને હાઈ-ડેન્સિટી કુશન્સ વાપરીએ છીએ.\n\n"
                        f"સાચું માપ લેવા માટે, શું અમે આ *શનિવારે સવારે 11:30 વાગ્યે* અથવા *રવિવારે સાંજે 4:00 વાગ્યે* ફ્રી લેસર માપણી મુલાકાત ગોઠવીએ? 📐🪵"
                    )
                elif lang == "hi":
                    return (
                        f"आपकी *{p_name}* ({dim_str}) की जानकारी मिल गई, {name_title}! 🪵\n\n"
                        f"हमारा अंदाज़न बजट {price_est} आता है, और वर्कशॉप में {timeline_est} में तैयार हो जाता है। हम सीजन्ड सागवान/शीशम लकड़ी और हाई-डेंसिटी कुशन इस्तेमाल करते हैं।\n\n"
                        f"सटीक नाप लेने के लिए, क्या हम इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* 15 मिनट की फ्री विज़िट रख लें? 📐🪵"
                    )
                return (
                    f"Got your specifications for *{p_name}* ({dim_str}), {name_title}! 🪵\n\n"
                    f"Our approximate Budget Guide comes to {price_est}, with a completion Timeline of {timeline_est}. We use seasoned solid timber and 40D high-density cushions with washable covers.\n\n"
                    f"To verify exact site measurements, shall we book a free 15-minute measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM*? 📐🪵"
                )

        # 6b. Dimensions provided but project type unknown (e.g. user starts by saying '10x10' or '10×10')
        if has_dimensions and not session.project_type and session.appointment_status not in ("requested", "confirmed"):
            dim_info = parse_dimension_details(session.dimensions, text_lower)
            sqft = int(dim_info.get("sqft") or 100)
            dim_label = session.dimensions or f"{sqft} sq.ft."
            if lang == "gu":
                return (
                    f"તમારું માપ *{dim_label}* ({sqft} ચોરસ ફૂટ) નોંધી લીધું છે, {name_title}! 📏\n\n"
                    f"આ માપમાં તમે કયું ફર્નિચર બનાવવા માંગો છો?\n"
                    f"• *વોર્ડરોબ / કબાટ* (કુલ ખર્ચ આશરે ₹{sqft * 1380:,} થી ₹{sqft * 1750:,})\n"
                    f"• *મોડ્યુલર કિચન* (18mm વોટરપ્રૂફ મરીન પ્લાય)\n"
                    f"• *સ્ટોરેજ કેબિનેટ / ટીવી યુનિટ*\n\n"
                    f"તમારે કયું ફર્નિચર બનાવવું છે? 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"आपका नाप *{dim_label}* ({sqft} स्क्वायर फीट) हमने नोट कर लिया है, {name_title}! 📏\n\n"
                    f"इस साइज में आप क्या बनवाना चाहते हैं?\n"
                    f"• *वार्डरोब / अलमारी* (टर्न-की लागत लगभग ₹{sqft * 1380:,} से ₹{sqft * 1750:,})\n"
                    f"• *मॉड्युलर किचन* (18mm वाटरप्रूफ मरीन प्लाई)\n"
                    f"• *स्टोरेज कैबिनेट / टीवी यूनिट*\n\n"
                    f"आप इनमें से क्या बनवाना पसंद करेंगे? 🪵✨"
                )
            return (
                f"Got your measurements of *{dim_label}* ({sqft} sq.ft.), {name_title}! 📏\n\n"
                f"What piece are you looking to handcraft for this space?\n"
                f"• *Fitted Wardrobe* (Turn-key ₹{sqft * 1380:,} to ₹{sqft * 1750:,})\n"
                f"• *Modular Kitchen* (IS 710 Waterproof Marine Ply)\n"
                f"• *Storage Cabinet / TV Unit*\n\n"
                f"Which one would you like to build? 🪵✨"
            )

        # Multi-Item Inquiry (Customer asked for 2 or more pieces)
        if session.project_type and " & " in session.project_type:
            items_list = session.project_type.split(" & ")
            if lang == "gu":
                lines = [f"નમસ્તે {name_title}! 🙏 અમે તમારી જરૂરિયાત મુજબ આ બંને વસ્તુઓ ઉત્તમ કારીગરીથી બનાવી આપીશું:\n"]
                for idx, itm in enumerate(items_list, 1):
                    pr, tm = get_price_and_timeline_estimate(itm, None, "gu")
                    lines.append(f"{idx}. *{itm}*:\n   • *અંદાજિત બજેટ*: {pr}\n   • *સમય*: *{tm}*")
                lines.append(f"\nસચોટ માપ અને કિંમત નક્કી કરવા માટે, શું તમે આ બંનેના અંદાજિત માપ (રૂમ સાઈઝ અથવા બેઠક) જણાવી શકો છો? 📐🪵\n\n*(જો રૂબરૂ મળવાનો સમય ન હોય, તો તમે અહીં ચેટમાં રૂમ/જગ્યાના ફોટા મોકલીને પણ ઓનલાઈન ક્વોટ મેળવી શકો છો! 📸)*")
                return "\n".join(lines)
            elif lang == "hi":
                lines = [f"नमस्ते {name_title}! 🙏 हमें आपकी पसंद के अनुसार ये दोनों आइटम पूरी मजबूती से बनाने में खुशी होगी:\n"]
                for idx, itm in enumerate(items_list, 1):
                    pr, tm = get_price_and_timeline_estimate(itm, None, "hi")
                    lines.append(f"{idx}. *{itm}*:\n   • *अनुमानित बजट*: {pr}\n   • *समय*: *{tm}*")
                lines.append(f"\nसटीक कोटेशन बनाने के लिए, क्या आप दोनों का अंदाज़न साइज़ या जगह का नाप बता सकते हैं? 📐🪵\n\n*(सुझाव: अगर विज़िट का समय न हो, तो आप यहीं चैट पर कमरे की फोटो भेजकर तुरंत ऑनलाइन फाइनल कर सकते हैं! 📸)*")
                return "\n".join(lines)
            else:
                lines = [f"Namaste {name_title}! 🙏 We would be delighted to handcraft these bespoke pieces for you:\n"]
                for idx, itm in enumerate(items_list, 1):
                    pr, tm = get_price_and_timeline_estimate(itm, None, "en")
                    lines.append(f"{idx}. *{itm}*:\n   • *Approximate Budget Guide*: {pr}\n   • *Timeline*: *{tm}*")
                lines.append(f"\nTo calculate your firm turnkey quotation: What are the approximate dimensions or seating requirements for each? 📐🪵\n\n*(Tip: If you don't have time for a visit, you can also share room photos right here in chat for an instant online quote! 📸)*")
                return "\n".join(lines)

        # Check Windows / Khidkhi inquiry (when dimensions not yet provided)
        is_window_inquiry = any(w in text_lower for w in ["khidkhi", "khidki", "khidkiya", "khidkiyan", "window", "windows", "bari", "બારી", "बारी", "खिड़की", "खिड़कियां", "खिडकी"])
        if is_window_inquiry and not session.dimensions:
            session.project_type = "Custom Wooden Windows"
            qty_match = re.search(r"\b(\d+)\s*(?:windows?|khidki|khidkhi|bari|બારી|बारी|खिड़की|खिडकी)\b", text_lower) or re.search(r"(?:make|build|need|want|chahiye|જોઈએ|બનાવવી)\s*(\d+)", text_lower)
            qty = int(qty_match.group(1)) if qty_match else 1
            if qty > 1:
                price_en = f"Standard 4x4 ft seasoned CP Teak (Sagwan) windows with 5mm toughened glass and SS-304 mosquito mesh come to around ₹18,000 – ₹22,000 per window, so for {qty} windows it will be around ₹{qty * 18000:,} to ₹{qty * 22000:,} turnkey with fitting."
                price_hi = f"सीजन्ड सीपी सागवान में 5mm टफन्ड ग्लास और SS-304 मच्छर जाली पल्ले के साथ मानक 4x4 फीट की एक खिड़की लगभग ₹18,000 से ₹22,000 में तैयार होती है। {qty} खिड़कियों का फिटिंग सहित लगभग ₹{qty * 18000:,} से ₹{qty * 22000:,} का खर्च आएगा।"
                price_gu = f"સીઝન્ડ સીપી સાગવાનમાં 5mm ટફન્ડ ગ્લાસ અને SS-304 મચ્છર જાળી શટર સાથે સ્ટાન્ડર્ડ 4x4 ફૂટની એક બારી આશરે ₹18,000 થી ₹22,000 માં બને છે. {qty} બારીઓનું ફિટિંગ સહિત આશરે ₹{qty * 18000:,} થી ₹{qty * 22000:,} જેવું થશે."
            else:
                price_en = "Standard 4x4 ft seasoned CP Teak (Sagwan) window with 5mm toughened glass and SS-304 mosquito mesh shutter comes to around ₹18,000 – ₹22,000 turnkey with fitting (or around ₹1,200 – ₹1,350 per sq.ft)."
                price_hi = "सीजन्ड सीपी सागवान में 5mm टफन्ड ग्लास और SS-304 मच्छर जाली पल्ले के साथ मानक 4x4 फीट की खिड़की लगभग ₹18,000 से ₹22,000 में तैयार होती है (लगभग ₹1,200 से ₹1,350 प्रति स्क्वायर फीट)।"
                price_gu = "સીઝન્ડ સીપી સાગવાનમાં 5mm ટફન્ડ ગ્લાસ અને SS-304 મચ્છર જાળી શટર સાથે સ્ટાન્ડર્ડ 4x4 ફૂટની બારી આશરે ₹18,000 થી ₹22,000 માં તૈયાર થાય છે (આશરે ₹1,200 થી ₹1,350 પ્રતિ ચોરસ ફૂટ)."

            if lang == "gu":
                return (
                    f"નમસ્તે {name_title}! 🙏 બારીઓ બિલકુલ બની જશે.\n\n"
                    f"{price_gu}\n\n"
                    f"કારીગરીમાં 10 થી 14 દિવસ લાગે છે. તમારી બારીઓનું અંદાજિત માપ શું છે (જેમ કે 4x4 ફૂટ કે 5x4 ફૂટ)? 📐"
                )
            elif lang == "hi":
                return (
                    f"नमस्ते {name_title}! 🙏 खिड़कियां बिल्कुल बन जाएंगी।\n\n"
                    f"{price_hi}\n\n"
                    f"वर्कशॉप में 10 से 14 दिन लगते हैं। आपकी खिड़कियों का अंदाज़न साइज़ क्या है (जैसे 4x4 फीट या 5x4 फीट)? 📐"
                )
            return (
                f"Namaste {name_title}! 🙏 Yes, we make custom wooden windows.\n\n"
                f"{price_en}\n\n"
                f"It takes around 10 to 14 working days in our workshop. What are the approximate dimensions of your windows (e.g., 4x4 ft or 5x4 ft)? 📐"
            )

        # 7. Customer mentioned what they want to make (without dimensions yet) -> Budget range, Timeline, Ask for Size
        if session.project_type and not session.dimensions and session.appointment_status not in ("requested", "confirmed"):
            p_name = session.project_type
            p_lower = p_name.lower()
            price_est, timeline_est = get_price_and_timeline_estimate(p_name, None, lang)

            # Item-specific questions
            if any(k in p_lower for k in ["sofa", "couch", "સોફા", "सोफा"]):
                ask_q_en = "What seating size are you planning (e.g., 3-seater, 5-seater 3+1+1, or L-shape sectional)? 🪵"
                ask_q_hi = "आप कितने सीटर का सोफा बनवाना चाहते हैं (जैसे 3-सीटर, 5-सीटर 3+1+1, या L-शेप)? 🪵"
                ask_q_gu = "તમે કેટલા સીટરનો સોફો બનાવવા માંગો છો (જેમ કે 3-સીટર, 5-સીટર 3+1+1, કે L-શેપ)? 🪵"
            elif any(k in p_lower for k in ["dining", "table", "ટેબલ", "मेज"]):
                ask_q_en = "Are you looking for a 4-seater, 6-seater, or 8-seater dining set? 🪑"
                ask_q_hi = "आप कितने सीटर का डाइनिंग सेट बनवाना चाहते हैं (जैसे 4-सीटर, 6-सीटर, या 8-सीटर)? 🪑"
                ask_q_gu = "તમે કેટલા સીટરનું ડાઇનિંગ સેટ બનાવવા માંગો છો (જેમ કે 4-સીટર, 6-સીટર, કે 8-સીટર)? 🪑"
            elif any(k in p_lower for k in ["bed", "palang", "પલંગ", "पलंग"]):
                ask_q_en = "Are you looking for a Queen Size (approx 5x6.5 ft) or King Size (approx 6x6.5 ft)? 🛏️"
                ask_q_hi = "आप क्वीन साइज़ (लगभग 5x6.5 फीट) या किंग साइज़ (लगभग 6x6.5 फीट) बनवाना चाहते हैं? 🛏️"
                ask_q_gu = "તમે ક્વીન સાઇઝ (આશરે 5x6.5 ફૂટ) કે કિંગ સાઇઝ (આશરે 6x6.5 ફૂટ) બનાવવા માંગો છો? 🛏️"
            elif any(k in p_lower for k in ["door", "darwaza", "दरवाजा", "દરવાજો"]):
                ask_q_en = "What is the approximate size of your door frame (standard is usually 7x3 ft or 7x3.5 ft)? 🚪"
                ask_q_hi = "दरवाज़े की चौखट का अंदाज़न साइज़ क्या है (आमतौर पर 7x3 फीट या 7x3.5 फीट)? 🚪"
                ask_q_gu = "દરવાજાની ચોખટનું અંદાજિત માપ શું છે (સામાન્ય રીતે 7x3 ફૂટ કે 7x3.5 ફૂટ)? 🚪"
            elif any(k in p_lower for k in ["mandir", "temple", "મંદિર", "मंदिर"]):
                ask_q_en = "What approximate height and width do you have in mind for your mandir? 🪔"
                ask_q_hi = "मंदिर के लिए अंदाज़न कितनी ऊंचाई और चौड़ाई की जगह है? 🪔"
                ask_q_gu = "મંદિર માટે તમારી પાસે અંદાજિત કેટલી ઊંચાઈ અને પહોળાઈની જગ્યા છે? 🪔"
            else:
                ask_q_en = "What is the approximate size of your wall or space (for example, 6x4 ft or 8x6 ft)? 📐"
                ask_q_hi = "कमरे या दीवार का अंदाज़न साइज़ क्या है (जैसे 6x4 फीट या 8x6 फीट)? 📐"
                ask_q_gu = "તમારી દીવાલ અથવા જગ્યાનું અંદાજિત માપ શું છે (જેમ કે 6x4 ફૂટ કે 8x6 ફૂટ)? 📐"

            is_solid_wood = any(k in p_lower for k in [
                "sofa", "couch", "dining", "table", "bed", "palang", "mandir", "temple", "door",
                "સોફા", "ડાઇનિંગ", "ટેબલ", "પલંગ", "મંદિર", "દરવાજો",
                "सोफा", "डाइनिंग", "मेज", "पलंग", "मंदिर", "दरवाजा"
            ])
            if lang == "gu":
                name_suffix = f", {name_title}" if first_name else ""
                mat_str = "અમે સીઝન્ડ સાગવાન/શીશમ લાકડું અને ઉત્કૃષ્ટ કારીગરી વાપરીએ છીએ." if is_solid_wood else "અમે 18mm IS 710 વોટરપ્રૂફ મરીન પ્લાય અને હેટીચ જર્મન ફિટિંગ્સ વાપરીએ છીએ."
                return (
                    f"નમસ્તે{name_suffix}! તમારી *{p_name}* બિલકુલ બનાવી આપીશું. 🪵\n\n"
                    f"અમારો અંદાજિત ભાવ {price_est} ની આસપાસ રહે છે, અને વર્કશોપમાં {timeline_est} માં તૈયાર થઈ જાય છે. {mat_str}\n\n"
                    f"{ask_q_gu}"
                )
            elif lang == "hi":
                name_suffix = f", {name_title}" if first_name else ""
                mat_str = "हम सीजन्ड सागवान/शीशम लकड़ी और बेहतरीन कारीगरी इस्तेमाल करते हैं।" if is_solid_wood else "हम 18mm IS 710 वाटरप्रूफ मरीन प्लाई और हेटिच जर्मन फिटिंग्स इस्तेमाल करते हैं।"
                return (
                    f"नमस्ते{name_suffix}! आपकी *{p_name}* बिल्कुल बना देंगे। 🪵\n\n"
                    f"हमारा अंदाज़न बजट {price_est} आता है, और वर्कशॉप में {timeline_est} में तैयार हो जाता है। {mat_str}\n\n"
                    f"{ask_q_hi}"
                )
            name_suffix = f", {first_name} ji" if first_name else " ji"
            mat_str = "We use seasoned solid Teak/Sheesham timber and handcrafted mortise & tenon joinery." if is_solid_wood else "We use 18mm IS 710 waterproof marine ply with Hettich German soft-close fittings."
            return (
                f"Namaste{name_suffix}! We can certainly make your *{p_name}*. 🪵\n\n"
                f"Our approximate budget comes to around {price_est}, and it takes about {timeline_est}. {mat_str}\n\n"
                f"{ask_q_en}"
            )

        # 8. Material inquiry
        if any(w in text_lower for w in ["teak", "sheesham", "ply", "laminate", "material", "wood", "difference", "લાકડું", "સાગવાન", "લાકડા", "लकड़ी", "सागवान"]):
            if lang == "gu":
                name_suffix = f", {name_title}" if first_name else ""
                return (
                    f"ઉત્તમ સવાલ{name_suffix}! સાચું લાકડું પસંદ કરવું એ જ સારા ફર્નિચરનું રહસ્ય છે:\n\n"
                    f"- *સાગવાન (Teak)*: કુદરતી તેલ વાળું લાકડું, 100% ઊધઈ-પ્રૂફ, આજીવન ચાલતા ફર્નિચર અને દરવાજા માટે શ્રેષ્ઠ.\n"
                    f"- *શીશમ (Rosewood)*: વજનદાર, મજબૂત અને ડ્યુઅલ-ટોન કુદરતી રેસા વાળું. ડાઇનિંગ ટેબલ અને સોફા માટે શ્રેષ્ઠ.\n"
                    f"• *IS 710 BWP મરીન પ્લાય*: વોટરપ્રૂફ, કિચન અને કબાટ માટે શ્રેષ્ઠ, 1mm મેટ/એક્રેલિક ફિનિશ સાથે.\n\n"
                    f"તમે કેવો લૂક પસંદ કરો છો — કુદરતી લાકડાનો કે મોર્ડન મેટ કલર? 🪵"
                )
            elif lang == "hi":
                name_suffix = f", {name_title}" if first_name else ""
                return (
                    f"बहुत अच्छा सवाल{name_suffix}! सही लकड़ी चुनना ही मजबूत फर्नीचर का राज़ है:\n\n"
                    f"- *सागवान (Teak)*: प्राकृतिक तेल से भरपूर, 100% दीमक-रोधी, हमेशा चलने वाले फर्नीचर और दरवाजों के लिए सर्वश्रेष्ठ।\n"
                    f"- *शीशम (Rosewood)*: भारी, मजबूत और शानदार प्राकृतिक रेशों वाला। डाइनिंग और सोफा के लिए उत्तम।\n"
                    f"• *IS 710 BWP मरीन प्लाई*: वाटरप्रूफ, किचन और वार्डरोब के लिए बेस्ट, 1mm मैट/PU फिनिश के साथ।\n\n"
                    f"आप किस तरह का फिनिश पसंद करेंगे — नेचुरल वुड ग्रेन या मॉडर्न मैट? 🪵"
                )
            name_suffix = f", {first_name}" if first_name else ""
            return (
                f"Excellent question{name_suffix}! Choosing the right timber is 80% of fine woodworking:\n\n"
                f"- *Teak (Sagwan)*: High natural oil content, 100% termite proof, ideal for lifetime pieces and doors.\n"
                f"- *Sheesham*: Hard, dense, with striking dual-tone grain. Perfect for dining sets & sturdy beds.\n"
                f"- *IS 710 BWP Marine Ply*: Waterproof, best for kitchens & wardrobes, paired with *1mm Matte/PU finish*.\n\n"
                f"Do you have a specific finish in mind, like warm natural grains or modern matte solid colors? 🪵"
            )

        # 9. General project advice / Fallback
        if session.project_type:
            p_name = session.project_type
            if lang == "gu":
                return (
                    f"નમસ્તે {name_title}! 🙏 અમે તમારી જરૂરિયાત મુજબ *{p_name}* ઉત્તમ કારીગરીથી બનાવી આપીશું.\n\n"
                    f"અમે સીઝન્ડ સાગવાન લાકડું અને IS 710 વોટરપ્રૂફ મરીન પ્લાય સાથે જર્મન ફિટિંગ્સ વાપરીએ છીએ. સચોટ ક્વોટેશન માટે, શું તમે અંદાજિત સાઈઝ અથવા રૂમનો ફોટો શેર કરી શકો છો? 📐📸"
                )
            elif lang == "hi":
                return (
                    f"नमस्ते {name_title}! 🙏 हम आपकी पसंद के अनुसार *{p_name}* पूरी मजबूती और फिनिशिंग से बनाएंगे।\n\n"
                    f"हम सीजन्ड सागवान लकड़ी और IS 710 वाटरप्रूफ मरीन प्लाई के साथ जर्मन फिटिंग्स इस्तेमाल करते हैं। पक्के कोटेशन के लिए, क्या आप अंदाज़न साइज़ या कमरे की फोटो भेज सकते हैं? 📐📸"
                )
            return (
                f"Thank you for reaching out to Heritage Woodworks, {name_title}! 🪵\n\n"
                f"We would love to handcraft your *{p_name}*. We use seasoned timber and IS 710 waterproof marine ply with German fittings.\n\n"
                f"To share an exact quotation, what are your approximate room dimensions, or feel free to share a photo of your space here! 📐📸"
            )

        if lang == "gu":
            name_suffix = f" {name_title}" if first_name else ""
            return (
                f"નમસ્તે{name_suffix}! 🙏 હેરિટેજ વુડવર્ક્સમાં આપનું સ્વાગત છે.\n\n"
                f"અમે સીઝન્ડ સાગવાન લાકડું અને IS 710 વોટરપ્રૂફ મરીન પ્લાય સાથે જર્મન ફિટિંગ્સ વાપરીએ છીએ. દરેક ફર્નિચર 12 થી 18 કામકાજના દિવસોમાં તૈયાર થાય છે.\n\n"
                f"તમારે તમારા ઘર માટે કયું ફર્નિચર બનાવવું છે? (જેમ કે વોર્ડરોબ, મોડ્યુલર કિચન, સોફા કે ડાઇનિંગ ટેબલ) 🪵✨"
            )
        elif lang == "hi":
            name_suffix = f" {name_title}" if first_name else " जी"
            return (
                f"नमस्ते{name_suffix}! 🙏 हेरिटेज वुडवर्क्स में आपका स्वागत है।\n\n"
                f"हम सीजन्ड सागवान लकड़ी और IS 710 वाटरप्रूफ मरीन प्लाई के साथ जर्मन फिटिंग्स इस्तेमाल करते हैं। हर फर्नीचर 12 से 18 कार्य दिवसों में मजबूती से तैयार होता है।\n\n"
                f"आप अपने घर के लिए कौन सा फर्नीचर बनवाना चाहते हैं? (जैसे वार्डरोब, किचन, सोफा या डाइनिंग) 🪵✨"
            )
        name_suffix = f", {first_name}" if first_name else ""
        return (
            f"Thank you for reaching out to Heritage Woodworks{name_suffix}! 🪵\n\n"
            f"We handcraft bespoke wardrobes, modular kitchens, solid Teak/Sheesham dining tables, and architectural woodwork in 12–18 working days.\n\n"
            f"What piece are you looking to create for your home? 📐✨"
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

        # 1. Human Handover Mode check (suppress AI auto-replies when artisan is active)
        if getattr(session, "human_handover", False):
            logger.info(f"[HANDOVER SUPPRESSED] AI auto-reply suppressed for {session.phone_number} (Master Carpenter in control)")
            return {
                "recipient_id": session.phone_number,
                "response_text": "",
                "suppressed": True,
                "source": "human_handover",
                "latency_ms": 0,
                "session": session.to_dict(),
            }

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

        # Sync state machine enquiry memory
        mem = state_machine.get_or_create(session.phone_number, session.customer_name)
        mem.project_type = session.project_type
        mem.dimensions = session.dimensions
        mem.preferred_materials = session.preferred_materials
        mem.customer_budget = session.customer_budget
        mem.human_handover = session.human_handover
        mem.locality = session.locality

        response_text = ""
        source = "domain_engine"

        # Real-time Master Carpenter Engine (Executes in <5ms to guarantee 3-4s WhatsApp replies with typing presence)
        response_text = self._generate_fallback_response(session, message_text)
        source = "master_carpenter_engine"

        # Update stage transition
        session.lead_status = state_machine.evaluate_transition(mem, message_text)

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

        # Persist conversation turns and customer profile to SQLite via CRM
        if getattr(self.sessions, "persist_db", False):
            try:
                crm.get_or_create_customer(
                    phone=session.phone_number,
                    name=session.customer_name,
                    language=session.language,
                )
                crm.append_message(
                    phone=session.phone_number,
                    role="user",
                    text=message_text,
                    media_info=media_info,
                    stage=session.lead_status,
                    source="whatsapp_inbound",
                )
                crm.append_message(
                    phone=session.phone_number,
                    role="model",
                    text=response_text,
                    stage=session.lead_status,
                    source=source,
                    latency_ms=latency_ms,
                )
                crm.update_customer(
                    phone=session.phone_number,
                    name=session.customer_name,
                    language=session.language,
                    locality=session.locality,
                    lead_status=session.lead_status,
                    project_type=session.project_type,
                    dimensions=session.dimensions,
                    preferred_materials=session.preferred_materials,
                    consultation_mode=session.consultation_mode,
                    budget=session.customer_budget,
                )

                # Persist appointment if requested or confirmed
                if session.appointment_status in ("requested", "confirmed"):
                    addr = None
                    for n in session.notes:
                        if n.startswith("address:"):
                            addr = n[8:].strip()
                    appointment_engine.create_or_request_visit(
                        phone=session.phone_number,
                        slot_time=session.appointment_slot or "Saturday at 11:30 AM",
                        address=addr or session.site_address,
                        project_scope=session.project_type,
                    )
            except Exception as err:
                logger.error(f"Error syncing CRM persistence: {err}")

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
carpenter_agent = CarpenterAgent(SessionStore(persist_db=True))
