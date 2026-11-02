"""Dedicated Furniture Consultation Flows for AI Master Carpenter Assistant.

Provides deep, domain-authentic consultation flows for:
1. Fitted Wardrobes (Hinged vs Sliding, Marine Ply, 1mm Laminate vs PU)
2. Modular Kitchens (IS 710 BWP, Soft-Close Tandem Boxes, Acrylic vs Laminate)
3. Custom Wooden Sofas (3-Seater, 5-Seater 3+1+1, L-Shape Sectional, 40D Foam)
4. Solid Wood Dining Tables (4-Seater, 6-Seater, 8-Seater, Solid Teak/Sheesham)
5. Architectural Doors & Windows (CP Teak Chaukhat, Toughened Glass, Mosquito Mesh)
6. Custom Storage Beds (King/Queen, Hydraulic Lift vs Platform Drawers)

Voiced by Master Artisan Rajesh Sharma with authentic Gujarati/Hindi/English nuances.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("carpenter.flows")


class WardrobeFlow:
    """Specialized consultation flow for bespoke fitted wardrobes."""

    @staticmethod
    def get_advice(lang: str = "en") -> str:
        if lang == "gu":
            return (
                "વોર્ડરોબ માટે અમે અંદર અને બહાર 18mm IS 710 વોટરપ્રૂફ મરીન પ્લાય જ વાપરીએ છીએ, જેથી ચોમાસામાં પણ ભેજ કે ઉધઈની કોઈ ચિંતા ન રહે. "
                "શટર માટે બે ઉત્તમ વિકલ્પો છે: ક્લાસિક હિન્જ્ડ શટર (હેટીચ સોફ્ટ-ક્લોઝ સાથે) અથવા સ્પેસ-સેવિંગ સ્લાઇડિંગ સિસ્ટમ. "
                "અંદરની ડિઝાઇનમાં હેંગિંગ સ્પેસ, ડીપ ડ્રોઅર્સ અને સેફ લોકર બધું જ તમારા રૂમની ઊંચાઈ મુજબ કસ્ટમાઇઝ કરી આપીએ છીએ."
            )
        elif lang == "hi":
            return (
                "वार्डरोब के लिए हम 18mm IS 710 वाटरप्रूफ मरीन प्लाईवुड इस्तेमाल करते हैं, ताकि सालों-साल सीलन या दीमक की कोई फिक्र न रहे। "
                "दरवाजों में दो बेहतरीन विकल्प हैं: क्लासिक हिंज्ड शटर (हेटिच सॉफ्ट-क्लोज़ कब्जों के साथ) या जगह बचाने वाले स्मूद स्लाइडिंग शटर। "
                "अंदर की दराजें, हैंगिंग एरिया और लॉकर हम आपकी रोजमर्रा की जरूरत के हिसाब से पूरी तरह कस्टमाइज करते हैं।"
            )
        return (
            "For wardrobes, we use genuine 18mm IS 710 waterproof marine ply for both the carcass and shelves, completely eliminating termite or moisture warping risks. "
            "You can choose between classic hinged shutters with German soft-close hinges or smooth sliding systems for compact bedrooms. "
            "Internal layouts include full-length hanging zones, deep felt-lined drawers, and loft organizers built seamlessly up to your ceiling."
        )


class KitchenFlow:
    """Specialized consultation flow for modular kitchens."""

    @staticmethod
    def get_advice(lang: str = "en") -> str:
        if lang == "gu":
            return (
                "રસોઈ ઘરનો સૌથી મહત્વનો ભાગ છે. એટલે જ અમે કિચન કારકસમાં ફક્ત 100% IS 710 BWP (બોઈલિંગ વોટરપ્રૂફ) મરીન પ્લાય વાપરીએ છીએ—કોઈ પણ MDF કે પાર્ટિકલ બોર્ડ નહીં, જે પાણીથી ફૂલી જાય. "
                "બધા ડ્રોઅરમાં 45kg વજન ક્ષમતા વાળા હેટીચ ટેન્ડમ બોક્સ અને સોફ્ટ-ક્લોઝિંગ આવે છે. "
                "શટર ફિનિશમાં 1mm મેટ એન્ટી-સ્ક્રેચ લેમિનેટ અથવા સીમલેસ હાઈ-ગ્લોસ એક્રેલિક ઉપલબ્ધ છે."
            )
        elif lang == "hi":
            return (
                "रसोई घर की सबसे महत्वपूर्ण जगह है। हम किचन का पूरा ढांचा केवल 100% IS 710 BWP वाटरप्रूफ मरीन प्लाई से बनाते हैं—MDF या पार्टिकल बोर्ड बिल्कुल नहीं लगाते, जो पानी से फूल जाते हैं। "
                "दराजों में 45 किलो वजन झेलने वाले जर्मन हेटिच टैंडम बॉक्स और सॉफ्ट-क्लोज़ चैनल दिए जाते हैं। "
                "ऊपर के शटर के लिए 1mm एंटी-स्क्रैच लैमिनेट या सीमलेस हाई-ग्लॉस ऐक्रेलिक दोनों विकल्प उपलब्ध हैं।"
            )
        return (
            "A kitchen needs uncompromising moisture and heat resistance. That's why we build every carcass strictly with 100% IS 710 BWP Marine Plywood—never commercial ply or MDF which bloat around sinks and gas stoves. "
            "All drawers feature heavy-duty German soft-close tandem boxes rated for 45kg loads, paired with high-gloss acrylic or 1mm anti-scratch matte laminates."
        )


class SofaFlow:
    """Specialized consultation flow for handcrafted wooden sofas."""

    @staticmethod
    def get_advice(dim_str: Optional[str] = None, lang: str = "en") -> str:
        dim = (dim_str or "").lower()
        if lang == "gu":
            return (
                "સોફામાં સૌથી મહત્વનું લાકડાની સીઝનિંગ અને મજબૂત જોડાઈ છે. અમે ઓરિજિનલ સાગવાન અથવા શીશમ લાકડામાં પરંપરાગત ખીલા-સાલ (mortise & tenon) સાંધા બનાવીએ છીએ, જેથી સોફા 25 વર્ષ સુધી અડગ રહે. "
                "બેઠક માટે અમે 40D હાઈ-ડેન્સિટી પ્રીમિયમ ફોમ વાપરીએ છીએ, જે વર્ષો સુધી દબાતી નથી, સાથે ડાઘ-પ્રતિરોધક વોશેબલ ફેબ્રિક કવર્સ આપીએ છીએ."
            )
        elif lang == "hi":
            return (
                "सोफा सेट की असली ताकत उसकी लकड़ी और मजबूत जोड़ाई में होती है। हम असली सीजन्ड सागवान या शीशम की लकड़ी पर पारंपरिक 'साल-छेनी' (mortise & tenon) जोड़ बनाते हैं, जिससे फ्रेम कभी ढीला नहीं पड़ता। "
                "बैठने के कुशन में हम 40D हाई-डेंसिटी प्रीमियम फोम और आसानी से धुलने वाले स्टेन-रेसिस्टेंट फैब्रिक कवर्स इस्तेमाल करते हैं।"
            )
        return (
            "Fine wooden sofas depend on seasoned hardwood frames and precision joinery. We craft each frame from solid Central Province Teak or dense Sheesham using interlocking mortise & tenon joinery—no weak screws or staples. "
            "Cushions are built with 40D high-resilience foam that retains bounce for over a decade, paired with stain-resistant washable upholstery."
        )


class DiningFlow:
    """Specialized consultation flow for solid wood dining sets."""

    @staticmethod
    def get_advice(lang: str = "en") -> str:
        if lang == "gu":
            return (
                "ડાઇનિંગ ટેબલ એ પરિવારના ભેગા થવાની જગ્યા છે. અમે 1.5-ઇંચ જાડી સોલિડ સાગવાન કે શીશમ લાકડાની ટોપ સ્લેબ બનાવીએ છીએ, જેના પર કુદરતી વુડ-ગ્રેઇન દેખાય છે. "
                "હીટ અને પાણીથી સુરક્ષા માટે 4-કોટ પ્રીમિયમ PU પોલિશ કરવામાં આવે છે. ખુરશીઓ સંપૂર્ણ સાગવાનમાં એર્ગોનોમિક કવર્ડ બેક સાથે આવે છે."
            )
        elif lang == "hi":
            return (
                "डाइनिंग टेबल परिवार के साथ बैठने की खास जगह होती है। हम 1.5 इंच मोटी सॉलिड सागवान या शीशम की लकड़ी का टॉप स्लैब तैयार करते हैं, जिस पर प्राकृतिक लकड़ी की खूबसूरत धारियां दिखाई देती हैं। "
                "गर्म बर्तनों और पानी से सुरक्षा के लिए इस पर 4-कोट इटैलियन PU पॉलिश की जाती है। कुर्सियां आरामदायक और मजबूत सॉलिड लकड़ी से बनी होती हैं।"
            )
        return (
            "Our dining tables are handcrafted from 1.5-inch thick solid slabs of natural CP Teak or Sheesham timber, finished with a 4-coat heat-and-water resistant Italian PU protective lacquer. "
            "Matching chairs feature ergonomically contoured backrests and high-density cushioned seats built to last generations."
        )


class WindowsAndDoorsFlow:
    """Specialized consultation flow for architectural windows and main doors."""

    @staticmethod
    def get_advice(lang: str = "en") -> str:
        if lang == "gu":
            return (
                "બારી-બારણાં ઘરની શોભા અને સુરક્ષા બંને છે. અમે બારીઓમાં ઓરિજિનલ સાગવાન લાકડાની જાડી ચોખટ, 5mm સેન્ટ-ગોબેન ટફન્ડ ગ્લાસ અને SS-304 સ્ટેનલેસ સ્ટીલ મચ્છરદાની શટર બનાવીએ છીએ. "
                "મેઈન ડોરમાં 35mm જાડી સોલિડ સાગવાન લાકડાની કોતરણી અથવા મોર્ડન ફ્લુટેડ ડિઝાઇન સાથે ગોદરેજ મલ્ટી-લોક પ્રોવિઝન આપીએ છીએ."
            )
        elif lang == "hi":
            return (
                "खिड़कियां और मुख्य दरवाजे घर की मजबूती और खूबसूरती दोनों तय करते हैं। खिड़कियों में हम भारी सागवान की चौखट, 5mm टफन्ड ग्लास और SS-304 स्टील मच्छर जाली का पल्ला बनाते हैं। "
                "मेन डोर में 35mm मोटी सॉलिड सागवान की लकड़ी पर नक्काशी या मॉडर्न फ्लूटेड डिजाइन और गोदरेज मल्टी-लॉक की व्यवस्था देते हैं।"
            )
        return (
            "We craft architectural windows with seasoned CP Teak outer frames (chaukhats), dual-shutter configurations featuring 5mm toughened Saint-Gobain glass, and heavy-gauge SS-304 stainless steel insect mesh. "
            "Main entrance doors are crafted from 35mm thick solid Teak with precision CNC carving or fluted patterns and multi-point deadbolt provisions."
        )


class BedFlow:
    """Specialized consultation flow for custom storage beds."""

    @staticmethod
    def get_advice(lang: str = "en") -> str:
        if lang == "gu":
            return (
                "બેડમાં મજબૂત બેઝ અને સરળ સ્ટોરેજ હોવું અનિવાર્ય છે. અમે 18mm વોટરપ્રૂફ મરીન પ્લાય બેઝ સાથે હેવી-ડ્યુટી હાઇડ્રોલિક ગેસ-સ્પ્રીંગ લિફ્ટ આપીએ છીએ જેથી ગાદલું સરળતાથી એક હાથે ઊંચકી શકાય. "
                "જો તમારું બજેટ ઓછું હોય, તો હાઇડ્રોલિકના બદલે નીચે સ્મૂધ-ગ્લાઇડિંગ સ્ટોરેજ ડ્રોઅર્સ (દરાજ) બનાવી શકાય, જેનાથી ₹13,000 ની સીધી બચત થાય છે."
            )
        elif lang == "hi":
            return (
                "बेड में मजबूत आधार और आसान स्टोरेज सबसे अहम है। हम 18mm वाटरप्रूफ मरीन प्लाई बेस के साथ जर्मन गैस-स्प्रिंग हाइड्रोलिक लिफ्ट देते हैं, जिससे गद्दा एक हाथ से आसानी से उठ जाता है। "
                "अगर बजट सीमित हो, तो हाइड्रोलिक लिफ्ट के बदले नीचे स्मूद-ग्लाइड स्टोरेज दराजें (ड्रॉअर) बनाई जा सकती हैं, जिससे पूरी मजबूती के साथ ₹13,000 की सीधी बचत होती है।"
            )
        return (
            "Our custom storage beds feature a reinforced 18mm IS 710 marine ply sub-frame and German gas-spring hydraulic lift struts that allow effortless, single-handed lifting of heavy mattresses. "
            "For cost-conscious clients, we can value-engineer the design with smooth-glide underbed storage drawers instead of hydraulic struts, saving ₹13,000 with zero compromise on sleep comfort."
        )


class FurnitureFlowRegistry:
    """Central registry routing customer inquiries to dedicated furniture flows."""

    FLOWS = {
        "wardrobe": WardrobeFlow,
        "kitchen": KitchenFlow,
        "sofa": SofaFlow,
        "dining": DiningFlow,
        "window": WindowsAndDoorsFlow,
        "door": WindowsAndDoorsFlow,
        "bed": BedFlow,
    }

    @classmethod
    def get_flow_advice(cls, project_type: Optional[str], lang: str = "en", dim_str: Optional[str] = None) -> Optional[str]:
        """Dispatch to domain-specific craftsman guidance."""
        p_type = (project_type or "").lower()
        if any(k in p_type for k in ["wardrobe", "cupboard", "almirah", "કબાટ", "अलमारी"]):
            return WardrobeFlow.get_advice(lang)
        elif any(k in p_type for k in ["kitchen", "રસોઈ", "रसोई"]):
            return KitchenFlow.get_advice(lang)
        elif any(k in p_type for k in ["sofa", "couch", "સોફા", "सोफा"]):
            return SofaFlow.get_advice(dim_str, lang)
        elif any(k in p_type for k in ["dining", "ડાઇનિંગ", "डाइनिंग", "table"]):
            return DiningFlow.get_advice(lang)
        elif any(k in p_type for k in ["window", "khidki", "बारी", "બારી", "door", "દરવાજો", "दरवाजा"]):
            return WindowsAndDoorsFlow.get_advice(lang)
        elif any(k in p_type for k in ["bed", "palang", "પલંગ", "पलंग"]):
            return BedFlow.get_advice(lang)
        return None
