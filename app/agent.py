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

    # Parse rectangular dimensions (e.g. 10*20, 10x20, 10 by 20, 12x9, 4x4)
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|\*|by)\s*(\d+(?:\.\d+)?)", target)
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

    # Seater count
    s_match = re.search(r"(\d+)\s*(?:seater|seat|સીટર|सीटर)", target)
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
    history: List[Dict[str, str]] = field(default_factory=list)  # [{"role": "user"|"model", "text": "..."}]
    project_type: Optional[str] = None
    dimensions: Optional[str] = None
    preferred_materials: List[str] = field(default_factory=list)
    customer_budget: Optional[int] = None
    negotiation_stage: str = "none"  # "none", "bargaining", "compromise_offered", "accepted"
    appointment_status: str = "none"  # "none", "requested", "confirmed"
    appointment_slot: Optional[str] = None
    consultation_mode: str = "in_person"  # "in_person" or "virtual"
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

        # Detect and persist language
        detected_lang = detect_language(user_text)
        if detected_lang in ("gu", "hi"):
            session.language = detected_lang
        elif getattr(session, "language", "en") == "en":
            session.language = detected_lang

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
            re.search(r"(\d+(?:\.\d+)?\s*(?:x|\*|by)\s*\d+)", text_lower)
            or any(k in text_lower for k in ["seater", "સીટર", "सीटर", "king", "queen", "feet", "ft", "inch"])
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

        # Dimensions detection (e.g. 10x8, 10x8 ft, 10*20, 10*20feet, 3 seater, three sofa, 6 seater, 7x3)
        dim_match = re.search(r"(\d+(?:\.\d+)?\s*(?:x|\*|by)\s*\d+(?:\.\d+)?\s*(?:ft|feet|inch|in|m|meter|ફૂટ|ફીટ|फुट|फीट)?)", text_lower)
        if dim_match:
            session.dimensions = dim_match.group(0).strip()
        elif any(k in text_lower for k in ["3 seater", "3-seater", "three sofa", "3 sofa", "3 seater sofa", "૩ સીટર", "३ सीटर", "3 seat"]):
            session.dimensions = "3-Seater"
        elif any(k in text_lower for k in ["5 seater", "5-seater", "૫ સીટર", "५ सीटर", "3+1+1", "3+2"]):
            session.dimensions = "5-Seater (3+1+1)"
        elif any(k in text_lower for k in ["6 seater", "6-seater", "૬ સીટર", "६ सीटर", "6 seat", "six seater"]):
            session.dimensions = "6-Seater (approx 6ft x 3ft)"
        elif any(k in text_lower for k in ["8 seater", "8-seater", "૮ સીટર", "૮-સીટર", "८ सीटर", "8 seat", "eight seater"]):
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
            "મુલાકાત", "માપણી", "માપ", "બુક", "વિઝિટ", "આવો", "આવજો",
            "मुलाकात", "विज़िट", "नाप", "बुक", "आओ", "आ जाइए"
        }
        affirmative_words = {
            "yes", "yeah", "yep", "sure", "ok", "okay", "yup", "done", "please", "pls",
            "confirm", "go ahead", "why not", "sounds good", "perfect",
            "હા", "હાજી", "ચાલશે", "બરાબર", "પાક્કું",
            "हाँ", "हां", "हाँजी", "ठीक है", "चलेगा", "पक्का", "ज़रूर"
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
                if any(k in prev_text for k in ["visit", "schedule", "measurement", "slot", "workshop", "માપણી", "મુલાકાત", "नाप", "विज़िट"]):
                    prev_agent_offered_visit = True
                break

        has_scheduling_word = bool(words.intersection(scheduling_keywords)) or any(
            k in text_lower for k in ["site visit", "laser measurement", "come over", "come to", "ઘરે આવો", "રૂબરૂ મળો", "घर आ जाओ", "नाप लेने आओ"]
        )
        is_affirming_visit = prev_agent_offered_visit and bool(words.intersection(affirmative_words))

        if has_scheduling_word or is_affirming_visit:
            if session.appointment_status == "none":
                session.appointment_status = "requested"

        # Check specific day / time slots
        days_and_slots = [
            ("saturday", "Saturday Slot"),
            ("sunday", "Sunday Slot"),
            ("શનિવાર", "શનિવાર (Saturday Slot)"),
            ("રવિવાર", "રવિવાર (Sunday Slot)"),
            ("शनिवार", "शनिवार (Saturday Slot)"),
            ("रविवार", "रविवार (Sunday Slot)"),
            ("weekend", "Weekend Slot"),
            ("tomorrow", "Tomorrow Slot"),
            ("11:30", "11:30 AM Slot"),
            ("4 pm", "4:00 PM Slot"),
        ]
        for slot_kw, slot_val in days_and_slots:
            if slot_kw in text_lower:
                session.appointment_status = "confirmed"
                session.appointment_slot = slot_val
                break

        # Address / Location detection
        address_markers = [
            "flat", "apt", "apartment", "tower", "road", "street", "sector", "phase", "block",
            "society", "colony", "layout", "nagar", "house", "સોસાયટી", "નગર", "રોડ", "घर", "सोसायटी"
        ]
        if any(marker in text_lower for marker in address_markers) or (len(user_text.split()) > 3 and any(c.isdigit() for c in user_text) and not dim_match):
            session.appointment_status = "confirmed"
            if not session.appointment_slot:
                session.appointment_slot = "આ વીકએન્ડ (This Weekend)" if session.language == "gu" else ("इस वीकेंड (This Weekend)" if session.language == "hi" else "This Weekend")

    def _generate_fallback_response(self, session: CustomerSession, user_text: str) -> str:
        """Intelligent offline Master Carpenter response generator with multi-turn multilingual state."""
        text_lower = user_text.lower()
        words = set(re.findall(r"\b\w+\b", text_lower))
        lang = getattr(session, "language", "en") or "en"

        # Check previous turn context
        prev_agent_msg = ""
        for turn in reversed(session.history[:-1]):
            if turn.get("role") == "model":
                prev_agent_msg = turn.get("text", "").lower()
                break

        scheduling_keywords = {
            "visit", "measurement", "measurements", "appointment", "book", "booking",
            "schedule", "sechudel", "schedul", "skedule", "meeting", "meet", "slot", "slots",
            "મુલાકાત", "માપણી", "માપ", "બુક", "વિઝિટ", "આવો", "આવજો",
            "मुलाकात", "विज़िट", "नाप", "बुक", "आओ", "आ जाइए"
        }
        affirmative_words = {
            "yes", "yeah", "yep", "sure", "ok", "okay", "yup", "done", "please", "pls", "confirm", "go ahead",
            "હા", "હાજી", "ચાલશે", "બરાબર", "પાક્કું",
            "हाँ", "हां", "हाँजी", "ठीक है", "चलेगा", "पक्का", "ज़रूर"
        }
        courtesy_words = {
            "ok", "okay", "thank", "thanks", "thx", "great", "perfect", "good", "bye", "see", "alright", "done",
            "આભાર", "ધન્યવાદ", "ધન્યવાદ જી", "સારું",
            "धन्यवाद", "शुक्रिया", "बहुत अच्छा", "नमस्ते"
        }

        user_is_scheduling = bool(words.intersection(scheduling_keywords)) or any(
            k in text_lower for k in ["site visit", "come over", "come to", "laser measurement", "ઘરે આવો", "घर आ जाओ"]
        )
        user_is_affirming = bool(words.intersection(affirmative_words)) and (
            "visit" in prev_agent_msg or "schedule" in prev_agent_msg or "measurement" in prev_agent_msg or "માપણી" in prev_agent_msg or "विज़िट" in prev_agent_msg or session.appointment_status == "requested"
        )
        has_time_slot = any(w in words for w in ["saturday", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "weekend", "tomorrow", "morning", "evening", "શનિવાર", "રવિવાર", "शनिवार", "रविवार"]) or any(t in text_lower for t in ["11:30", "11 am", "4 pm", "10 am"])
        address_markers = ["flat", "apt", "apartment", "tower", "road", "street", "sector", "phase", "block", "society", "colony", "layout", "nagar", "સોસાયટી", "सोसायटी"]
        has_address = any(marker in text_lower for marker in address_markers)

        # 1. Post-Booking Confirmation Courtesy (only when customer is closing after confirmation)
        is_courtesy_close = (
            (words.intersection(courtesy_words) or "thank you" in text_lower or "thanks" in text_lower or "આભાર" in text_lower or "धन्यवाद" in text_lower)
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

        # 2. Booking confirmed when customer provides a specific day/time slot or address
        if (has_time_slot or has_address) and session.appointment_status in ("requested", "confirmed"):
            session.appointment_status = "confirmed"
            slot_name = session.appointment_slot or "your selected time"
            project_name = session.project_type or "custom woodwork"
            if lang == "gu":
                return (
                    f"બુકિંગ કન્ફર્મ થઈ ગયું! 📅✨\n\n"
                    f"• *સમય*: *{slot_name}*\n"
                    f"• *કામ*: *{project_name}*\n"
                    f"• *અમારી ટીમ લાવશે*: લેસર મેઝરમેન્ટ ટેપ અને લાકડાના અસલી સેમ્પલ્સ (સાગવાન, શીશમ, મરીન પ્લાય, PU પોલિશ).\n\n"
                    f"અમારી માસ્ટર કારીગર ટીમ આવવાના 30 મિનિટ પહેલાં તમને ફોન કરશે. તમને મળવા માટે ઉત્સુક છીએ! 🙏🪵"
                )
            elif lang == "hi":
                return (
                    f"बुकिंग कन्फर्म हो गई! 📅✨\n\n"
                    f"• *समय*: *{slot_name}*\n"
                    f"• *काम*: *{project_name}*\n"
                    f"• *हमारी टीम लाएगी*: लेज़र मेज़रमेंट टेप और लकड़ी के असली सैंपल्स (सागवान, शीशम, मरीन प्लाई, PU पॉलिश)।\n\n"
                    f"हमारी मास्टर कारिगर टीम पहुंचने से 30 मिनट पहले आपको फोन करेगी। आपसे मिलने की प्रतीक्षा रहेगी! 🙏🪵"
                )
            return (
                f"Booking confirmed! 📅✨\n\n"
                f"• *Appointment*: *{slot_name}*\n"
                f"• *Project Scope*: *{project_name}*\n"
                f"• *What we bring*: Laser measurement tape & physical wood samples (Teak, Sheesham, Marine Ply, PU swatches).\n\n"
                f"Our master carpenter team will call you 30 minutes before arrival. Looking forward to meeting you! 🙏🪵"
            )

        # 3. Customer agreed to schedule a visit ("yes", "sure", "schedule meeting")
        if (user_is_scheduling or user_is_affirming) and session.appointment_status != "confirmed":
            session.appointment_status = "requested"
            project_context = f"for your *{session.project_type}*" if session.project_type else ""
            if lang == "gu":
                return (
                    f"બહુ સરસ! 📐 હું આનંદથી તમારી સાઇટ પર {project_context} લેસર ટૂલ્સ અને લાકડાના સેમ્પલ્સ સાથે આવીશ.\n\n"
                    f"અમારી પાસે આ સ્લોટ ખુલ્લા છે:\n"
                    f"• *શનિવારે સવારે 11:30 વાગ્યે*\n"
                    f"• *રવિવારે સાંજે 4:00 વાગ્યે*\n\n"
                    f"તમને કયો સમય અનુકૂળ રહેશે? તમારું સોસાયટી/એપાર્ટમેન્ટનું એડ્રેસ પણ જણાવી દેજો! 🪚✨"
                )
            elif lang == "hi":
                return (
                    f"बहुत बढ़िया! 📐 मैं खुशी से आपके घर {project_context} लेज़र टूल्स और लकड़ी के सैंपल्स के साथ आऊंगा।\n\n"
                    f"हमारे पास ये स्लॉट उपलब्ध हैं:\n"
                    f"• *शनिवार सुबह 11:30 बजे*\n"
                    f"• *रविवार शाम 4:00 बजे*\n\n"
                    f"आपको कौन सा समय ठीक रहेगा? कृपया अपना *अपार्टमेंट/सोसायटी का पता* भी बता दीजिए! 🪚✨"
                )
            return (
                f"Wonderful! 📐 I will gladly visit your site {project_context} with our laser tools and wood samples.\n\n"
                f"We currently have slots open this:\n"
                f"• *Saturday at 11:30 AM*\n"
                f"• *Sunday at 4:00 PM*\n\n"
                f"Which slot suits you best? Also, please share your *apartment address or landmark* so we can lock it in! 🪚✨"
            )

        # Extract caller name for personal addressing
        caller_name = session.customer_name or ""
        first_name = ""
        if caller_name and not caller_name.lower().startswith("client") and caller_name.lower() != "customer":
            clean_n = re.sub(r"[^a-zA-Z\u0900-\u097F\u0A80-\u0AFF]", "", caller_name.split()[0])
            if clean_n and len(clean_n) >= 2:
                first_name = clean_n

        if lang == "gu":
            name_title = f"{first_name}ભાઈ" if first_name else "જી"
        elif lang == "hi":
            name_title = f"{first_name} जी" if first_name else "जी"
        else:
            name_title = f"{first_name} ji" if first_name else "Ji"

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
                    f"હેરિટેજ વુડવર્ક્સ (Heritage Woodworks) માં આપનું સ્વાગત છે. હું *રાજેશ શર્મા* (માસ્ટર કારીગર).\n\n"
                    f"અમે સાગવાન (Teak), શીશમ અને વોટરપ્રૂફ મરીન પ્લાયવુડમાંથી પ્રીમિયમ ફર્નિચર બનાવીએ છીએ:\n\n"
                    f"• *કબાટ / વોર્ડરોબ* (Hinged / Sliding)\n"
                    f"• *મોડ્યુલર કિચન* (IS 710 BWP Marine Ply)\n"
                    f"• *સોલિડ વુડ સોફા સેટ & ડાઇનિંગ ટેબલ*\n"
                    f"• *મુખ્ય દરવાજા & બારીઓ*\n\n"
                    f"તમારે તમારા ઘર માટે શું બનાવવું છે? 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"नमस्ते {name_title}! 🙏\n\n"
                    f"हेरिटेज वुडवर्क्स (Heritage Woodworks) में आपका स्वागत है। मैं *राजेश शर्मा* (मास्टर कारिगर)।\n\n"
                    f"हम सागवान (Teak), शीशम और वाटरप्रूफ मरीन प्लाईवुड से हाथ से बना हुआ मजबूत फर्नीचर तैयार करते हैं:\n\n"
                    f"• *वार्डरोब / अलमारी* (Hinged / Sliding)\n"
                    f"• *मॉड्युलर किचन* (IS 710 BWP Marine Ply)\n"
                    f"• *लकड़ी के सोफा सेट & डाइनिंग टेबल*\n"
                    f"• *मेन डोर & खिड़कियां*\n\n"
                    f"आप अपने घर के लिए क्या बनवाना चाहते हैं? 🪵✨"
                )
            return (
                f"Namaste {name_title}! 🙏\n\n"
                f"Welcome to *Heritage Woodworks*. I am *Rajesh Sharma*, Master Carpenter at *Heritage Woodworks*.\n\n"
                f"We handcraft bespoke wardrobes, modular kitchens, solid Teak/Sheesham dining tables, and architectural woodwork:\n\n"
                f"• *Fitted Wardrobes* (Hinged / Sliding)\n"
                f"• *Modular Kitchens* (IS 710 BWP Marine Ply)\n"
                f"• *Solid Wood Dining Sets* (Teak / Sheesham)\n"
                f"• *Main Doors & Windows*\n\n"
                f"What piece are you planning to make for your home? 🪵✨"
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

        # 5. Customer states a Budget or requests Bargaining / Discount / Negotiation
        has_budget_mention = bool(
            session.customer_budget
            or any(w in words for w in ["budget", "discount", "expensive", "costly", "cheaper", "reduce", "less", "concession", "afford", "બજેટ", "ઓછું", "ઓછા", "બજેટમાં", "बजट", "कम", "कम करो", "डिस्काउंट"])
            or any(k in text_lower for k in ["too high", "too much", "best price", "can you do", "my budget", "within", "max", "ભાવ ઓછો", "भाव कम"])
        )
        if has_budget_mention:
            return generate_bargaining_response(session, session.customer_budget, user_text)

        # 6. Customer provided Dimensions & Requirements -> Approximate Budget, Timeline in Days, then Slot Booking
        has_current_dimension = bool(
            ("x" in text_lower or "*" in text_lower or " by " in text_lower)
            and any(c.isdigit() for c in user_text)
        ) or any(
            w in text_lower for w in ["seater", "સીટર", "सीटर", "king size", "queen size", "feet", "inch"]
        )

        if has_current_dimension:
            dim_info = parse_dimension_details(session.dimensions, text_lower)
            quote = calculate_turnkey_quote(session.project_type, dim_info, lang)
            p_name = session.project_type or "Custom Furniture"
            dim_str = session.dimensions or f"{int(quote.get('sqft', 80))} sq.ft."

            if quote.get("type") == "cabinet_wardrobe":
                if lang == "gu":
                    return (
                        f"તમારી *{p_name}* ({dim_str}, {int(quote['sqft'])} ચોરસ ફૂટ) ની વિગત મળી ગઈ, {name_title}! 📏\n\n"
                        f"• *વિકલ્પ A (1mm લેમિનેટ + જર્મન સોફ્ટ-ક્લોઝ)*: *₹{quote['total_lam']:,}* (આશરે ₹{quote['rate_lam']}/ચોરસ ફૂટ)\n"
                        f"• *વિકલ્પ B (પ્રીમિયમ 4-કોટ PU પોલિશ)*: *₹{quote['total_pu']:,}* (આશરે ₹{quote['rate_pu']}/ચોરસ ફૂટ)\n"
                        f"• *બનાવવાનો સમય*: *{quote['timeline']}*\n"
                        f"• *કારીગરી*: 18mm IS 710 BWP વોટરપ્રૂફ મરીન પ્લાય અને હેટીચ સોફ્ટ-ક્લોઝ ફિટિંગ્સ.\n\n"
                        f"શું તમારે લેબર અને ટ્રાન્સપોર્ટ સહિતનો વિગતવાર હિસાબ જોવો છે, કે પછી આ *શનિવારે સવારે 11:30 વાગ્યે* કે *રવિવારે સાંજે 4:00 વાગ્યે* ફ્રી માપણી વિઝિટ ગોઠવીએ? 📐🪵\n\n"
                        f"*(ખાસ: જો રૂબરૂ મળવાનો સમય ન હોય, તો તમે અહીં ચેટમાં રૂમ/દીવાલના ફોટા મોકલીને પણ ફાઇનલ કરી શકો છો! 📸)*"
                    )
                elif lang == "hi":
                    return (
                        f"आपकी *{p_name}* ({dim_str}, {int(quote['sqft'])} स्क्वायर फीट) की जानकारी मिल गई, {name_title}! 📏\n\n"
                        f"• *विकल्प A (1mm लैमिनेट + जर्मन सॉफ्ट-क्लोज़)*: *₹{quote['total_lam']:,}* (लगभग ₹{quote['rate_lam']}/स्क्वायर फीट)\n"
                        f"• *विकल्प B (प्रीमियम 4-कोट PU पॉलिश)*: *₹{quote['total_pu']:,}* (लगभग ₹{quote['rate_pu']}/स्क्वायर फीट)\n"
                        f"• *तैयार होने का समय*: *{quote['timeline']}*\n"
                        f"• *कारीगरी*: 18mm IS 710 BWP वाटरप्रूफ मरीन प्लाई और हेटिच जर्मन फिटिंग्स।\n\n"
                        f"क्या आप लेबर और ट्रांसपोर्ट सहित पूरा हिसाब देखना चाहेंगे, या फिर इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* फ्री लेज़र नाप विज़िट रख लें? 📐🪵\n\n"
                        f"*(सुझाव: अगर विज़िट का समय न हो, तो आप यहीं चैट पर कमरे की फोटो और नाप भेजकर तुरंत ऑनलाइन फाइनल कर सकते हैं! 📸)*"
                    )
                return (
                    f"Got your specifications for *{p_name}* ({dim_str}, {int(quote['sqft'])} sq.ft.), {name_title}! 📏\n\n"
                    f"• *Option A (1mm Anti-Scratch Laminate + Hettich Fittings)*: *₹{quote['total_lam']:,}* (around ₹{quote['rate_lam']}/sq.ft)\n"
                    f"• *Option B (Premium 4-Coat PU Polish)*: *₹{quote['total_pu']:,}* (around ₹{quote['rate_pu']}/sq.ft)\n"
                    f"• *Completion Timeline*: *{quote['timeline']}*\n"
                    f"• *Craftsmanship*: 18mm IS 710 BWP Waterproof Marine Ply with German soft-close fittings.\n\n"
                    f"Would you like an itemized breakdown including labour & transport, or shall we book a free 15-minute measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM*? 📐🪵\n\n"
                    f"*(Tip: If you're busy or don't have time for a visit, you can simply send photos of your room & wall measurements here in chat for an instant online quote! 📸)*"
                )
            else:
                price_est, timeline_est = get_price_and_timeline_estimate(session.project_type, session.dimensions, lang)
                if lang == "gu":
                    return (
                        f"તમારી *{p_name}* ({dim_str}) ની વિગત મળી ગઈ, {name_title}! 📏\n\n"
                        f"• *અંદાજિત બજેટ*: {price_est}\n"
                        f"• *બનાવવાનો સમય*: *{timeline_est}*\n"
                        f"• *કારીગરી*: પ્રીમિયમ સીઝન્ડ લાકડું / IS 710 મરીન પ્લાય અને જર્મન સોફ્ટ-ક્લોઝ ફિટિંગ્સ.\n\n"
                        f"સચોટ માપ લેવા માટે, શું અમે આ *શનિવારે સવારે 11:30 વાગ્યે* અથવા *રવિવારે સાંજે 4:00 વાગ્યે* ફ્રી લેસર માપણી વિઝિટ રાખી શકીએ? 📐🪵"
                    )
                elif lang == "hi":
                    return (
                        f"आपकी *{p_name}* ({dim_str}) की जानकारी मिल गई, {name_title}! 📏\n\n"
                        f"• *अनुमानित बजट*: {price_est}\n"
                        f"• *तैयार होने का समय*: *{timeline_est}*\n"
                        f"• *कारीगरी*: प्रीमियम सीजन्ड लकड़ी / IS 710 मरीन प्लाई और जर्मन सॉफ्ट-क्लोज़ फिटिंग्स।\n\n"
                        f"सटीक नाप लेने के लिए, क्या हम इस *शनिवार सुबह 11:30 बजे* या *रविवार शाम 4:00 बजे* आपके घर पर फ्री लेज़र मेज़रमेंट विज़िट रख लें? 📐🪵"
                    )
                return (
                    f"Got your specifications for *{p_name}* ({dim_str}), {name_title}! 📏\n\n"
                    f"• *Approximate Budget Guide*: {price_est}\n"
                    f"• *Completion Timeline*: *{timeline_est}*\n"
                    f"• *Craftsmanship*: Premium seasoned timber / IS 710 marine ply with soft-close German fittings.\n\n"
                    f"To verify exact site measurements, shall we book a free 15-minute measurement visit this *Saturday at 11:30 AM* or *Sunday at 4:00 PM*? 📐🪵"
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
            if lang == "gu":
                return (
                    f"નમસ્તે {name_title}! 🙏 બારી (Wooden Windows) માટે ખૂબ સરસ!\n\n"
                    f"અમે સીઝન્ડ સીપી સાગવાન (Teak Wood) માં વેધરપ્રૂફ ચોખટ, 5mm ગ્લાસ અને એસએસ મચ્છર જાળી શટર સાથે ટકાઉ બારીઓ બનાવીએ છીએ.\n\n"
                    f"તમારી બારીઓનું અંદાજિત માપ શું છે (જેમ કે 4x4 ફૂટ કે 5x4 ફૂટ)? 📐\n"
                    f"અને શું તમારે મચ્છર જાળી વાળો પલ્લો પણ સાથે બનાવવો છે? 🪵✨"
                )
            elif lang == "hi":
                return (
                    f"नमस्ते {name_title}! 🙏 खिड़की (Wooden Windows) के लिए बहुत बढ़िया!\n\n"
                    f"हम सीजन्ड सीपी सागवान (Teak Wood) या शीशम में वेदरप्रूफ चौखट, 5mm टफन्ड ग्लास और स्टेनलेस स्टील (SS-304) मच्छर जाली वाले पल्लों के साथ मजबूत खिड़कियां बनाते हैं।\n\n"
                    f"आपकी खिड़कियों का अंदाज़न साइज़ क्या है (जैसे 4x4 फीट या 5x4 फीट)? 📐\n"
                    f"और क्या आपको जाली वाला पल्ला भी साथ में चाहिए? 🪵✨"
                )
            return (
                f"Namaste {name_title}! 🙏 Great to hear regarding your custom wooden windows!\n\n"
                f"We craft window frames and sashes in seasoned CP Teak (Sagwan) with 5mm toughened glass and stainless steel (SS-304) insect mesh shutters.\n\n"
                f"What are the approximate dimensions of your windows (e.g., 4x4 ft or 5x4 ft)? 📐\n"
                f"And would you also like the mosquito mesh shutter included? 🪵✨"
            )

        # 7. Customer mentioned what they want to make (without dimensions yet) -> Budget range, Timeline, Ask for Size
        if session.project_type and not session.dimensions:
            p_name = session.project_type
            price_est, timeline_est = get_price_and_timeline_estimate(p_name, None, lang)
            if lang == "gu":
                return (
                    f"અમે તમારી *{p_name}* ઉત્તમ કારીગરીથી બનાવી આપીશું, {name_title}! 🪵\n\n"
                    f"• *અંદાજિત બજેટ માર્ગદર્શિકા*: {price_est}\n"
                    f"• *અંદાજિત સમય*: *{timeline_est}*\n\n"
                    f"સચોટ ભાવ આપવા માટે:\n"
                    f"1. તમારી અંદાજિત રૂમ/દીવાલની સાઈઝ અથવા બેઠક માપ શું છે? 📐\n"
                    f"2. તમારી પસંદગીનું ફિનિશ કયું છે (ઓરિજિનલ સાગવાન/શીશમ, કે મરીન પ્લાય સાથે લેમિનેટ/PU)?\n\n"
                    f"અથવા જો રૂબરૂ મળવાનો સમય ન હોય, તો તમે અહીં ચેટમાં રૂમ/જગ્યાના ફોટા મોકલીને પણ ઓનલાઈન ક્વોટ મેળવી શકો છો! 📸🪚"
                )
            elif lang == "hi":
                return (
                    f"हम आपकी *{p_name}* बहुत बढ़िया कारीगरी से बनाएंगे, {name_title}! 🪵\n\n"
                    f"• *अनुमानित बजट गाइड*: {price_est}\n"
                    f"• *अनुमानित समय*: *{timeline_est}*\n\n"
                    f"सही कीमत तय करने के लिए:\n"
                    f"1. कमरे या दीवार का अंदाज़न साइज़ या सीटिंग साइज़ क्या है? 📐\n"
                    f"2. आपका पसंदीदा फिनिश कौन सा है (सागवान, शीशम, या मरीन प्लाई के साथ लैमिनेट/PU)?\n\n"
                    f"या अगर आपके पास विज़िट का समय न हो, तो आप यहीं चैट पर कमरे की फोटो भेजकर तुरंत ऑनलाइन एस्टिमेट ले सकते हैं! 📸🪚"
                )
            return (
                f"We would love to handcraft your *{p_name}*, {name_title}! 🪵\n\n"
                f"• *Approximate Budget Range*: {price_est}\n"
                f"• *Estimated Timeline*: *{timeline_est}*\n\n"
                f"To help us estimate the exact price:\n"
                f"1. What are your approximate room / wall dimensions or seating size? 📐\n"
                f"2. Do you have a preferred finish in mind (Solid Teak, Sheesham, or Marine Ply with Laminate/PU)?\n\n"
                f"Alternatively, if you're busy or don't have time for a visit, you can also share room photos right here in chat for an instant online quote! 📸🪚"
            )
        # 8. Material inquiry
        if any(w in text_lower for w in ["teak", "sheesham", "ply", "laminate", "material", "wood", "difference", "લાકડું", "સાગવાન", "લાકડા", "लकड़ी", "सागवान"]):
            if lang == "gu":
                return (
                    f"ઉત્તમ સવાલ, {name_title}! સાચું લાકડું પસંદ કરવું એ જ સારા ફર્નિચરનું રહસ્ય છે:\n\n"
                    f"• *સાગવાન (Teak)*: કુદરતી તેલ વાળું લાકડું, 100% ઊધઈ-પ્રૂફ, આજીવન ચાલતા ફર્નિચર અને દરવાજા માટે શ્રેષ્ઠ.\n"
                    f"• *શીશમ (Rosewood)*: વજનદાર, મજબૂત અને ડ્યુઅલ-ટોન કુદરતી રેસા વાળું. ડાઇનિંગ ટેબલ અને સોફા માટે શ્રેષ્ઠ.\n"
                    f"• *IS 710 BWP મરીન પ્લાય*: વોટરપ્રૂફ, કિચન અને કબાટ માટે શ્રેષ્ઠ, 1mm મેટ/એક્રેલિક ફિનિશ સાથે.\n\n"
                    f"તમે કેવો લૂક પસંદ કરો છો — કુદરતી લાકડાનો કે મોર્ડન મેટ કલર? 🪵"
                )
            elif lang == "hi":
                return (
                    f"बहुत अच्छा सवाल, {name_title}! सही लकड़ी चुनना ही मजबूत फर्नीचर का राज़ है:\n\n"
                    f"• *सागवान (Teak)*: प्राकृतिक तेल से भरपूर, 100% दीमक-रोधी, हमेशा चलने वाले फर्नीचर और दरवाजों के लिए सर्वश्रेष्ठ।\n"
                    f"• *शीशम (Rosewood)*: भारी, मजबूत और शानदार प्राकृतिक रेशों वाला। डाइनिंग और सोफा के लिए उत्तम।\n"
                    f"• *IS 710 BWP मरीन प्लाई*: वाटरप्रूफ, किचन और वार्डरोब के लिए बेस्ट, 1mm मैट/PU फिनिश के साथ।\n\n"
                    f"आप किस तरह का फिनिश पसंद करेंगे — नेचुरल वुड ग्रेन या मॉडर्न मैट? 🪵"
                )
            return (
                f"Excellent question, {name_title}! Choosing the right timber is 80% of fine woodworking:\n\n"
                f"• *Teak (Sagwan)*: High natural oil content, 100% termite proof, ideal for lifetime pieces and doors.\n"
                f"• *Sheesham*: Hard, dense, with striking dual-tone grain. Perfect for dining sets & sturdy beds.\n"
                f"• *IS 710 BWP Marine Ply*: Waterproof, best for kitchens & wardrobes, paired with *1mm Matte/PU finish*.\n\n"
                f"Do you have a specific finish in mind, like warm natural grains or modern matte solid colors? 🪵"
            )

        # 9. General project advice
        if lang == "gu":
            return (
                f"નમસ્તે {name_title}! 🙏 હેરિટેજ વુડવર્ક્સમાં આપનું સ્વાગત છે.\n\n"
                f"અમે સીઝન્ડ સાગવાન લાકડું અને IS 710 વોટરપ્રૂફ મરીન પ્લાય સાથે જર્મન ફિટિંગ્સ વાપરીએ છીએ. દરેક ફર્નિચર 12 થી 18 કામકાજના દિવસોમાં તૈયાર થાય છે.\n\n"
                f"તમારે તમારા ઘર માટે કયું ફર્નિચર બનાવવું છે, અને અંદાજિત માપ શું છે? 📐"
            )
        elif lang == "hi":
            return (
                f"नमस्ते {name_title}! 🙏 हेरिटेज वुडवर्क्स में आपका स्वागत है।\n\n"
                f"हम सीजन्ड सागवान लकड़ी और IS 710 वाटरप्रूफ मरीन प्लाई के साथ जर्मन फिटिंग्स इस्तेमाल करते हैं। हर फर्नीचर 12 से 18 कार्य दिवसों में मजबूती से तैयार होता है।\n\n"
                f"आप अपने घर के लिए क्या बनवाना चाहते हैं, और अंदाज़न साइज़ क्या है? 📐"
            )
        return (
            f"Thank you for reaching out to Heritage Woodworks, {name_title}! 🪵\n\n"
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

        # Real-time Master Carpenter Engine (Executes in <5ms to guarantee 3-4s WhatsApp replies with typing presence)
        response_text = self._generate_fallback_response(session, message_text)
        source = "master_carpenter_engine"

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
