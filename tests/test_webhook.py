"""Comprehensive unit and integration tests for AI Carpenter Assistant.

Tests:
1. Message Deduplication (preventing double-replies)
2. Carpenter AI Agent Brain (Persona, Multi-turn context, Scope extraction)
3. Outbound WhatsApp Web bridge (wa.me deep links)
"""
import hashlib
import hmac
import json
import unittest

from app.agent import CarpenterAgent, SessionStore
from app.config import Config
from app.web import Deduplicator, verify_hmac_signature
from app.whatsapp import WhatsAppChannel


class TestDeduplication(unittest.TestCase):
    """Test thread-safe message deduplication logic."""

    def test_deduplicator_prevents_duplicate_processing(self):
        dedup = Deduplicator(ttl_seconds=60.0)
        msg_id = "wamid.HBgL123456789"

        # First delivery: should not be marked as duplicate
        self.assertFalse(dedup.is_duplicate(msg_id))

        # Immediate second delivery (Meta webhook retry): should be flagged as duplicate
        self.assertTrue(dedup.is_duplicate(msg_id))

        # Different message ID: should not be duplicate
        self.assertFalse(dedup.is_duplicate("wamid.HBgL987654321"))


class TestCarpenterAgent(unittest.TestCase):
    """Test Master Carpenter AI Persona, metadata extraction, and multi-turn context."""

    def setUp(self):
        self.store = SessionStore()
        self.agent = CarpenterAgent(session_store=self.store)

    def test_first_turn_greeting_and_options(self):
        res = self.agent.process_message(
            sender_phone="9876543210",
            message_text="Hello, I am interested in custom furniture.",
            customer_name="Priya Sharma",
        )
        self.assertEqual(res["recipient_id"], "9876543210")
        reply = res["response_text"]
        self.assertIn("Rajesh Sharma", reply)
        self.assertIn("Heritage Woodworks", reply)
        # Verify WhatsApp mobile formatting (e.g. bold asterisks and emojis)
        self.assertIn("*", reply)

    def test_modular_kitchen_extraction_and_dimensions(self):
        self.agent.process_message(
            sender_phone="9876543210",
            message_text="We need an L-shaped modular kitchen around 10x8 ft in BWP marine ply with acrylic shutters.",
            customer_name="Priya Sharma",
        )
        session = self.store.get("9876543210")
        self.assertIsNotNone(session)
        self.assertEqual(session.project_type, "Modular Kitchen")
        self.assertIn("10x8", session.dimensions.lower())
        self.assertIn("IS 710 Marine Plywood (BWP)", session.preferred_materials)
        self.assertIn("High-Gloss Acrylic Finish", session.preferred_materials)

    def test_teak_dining_table_extraction(self):
        self.agent.process_message(
            sender_phone="9811122233",
            message_text="Looking for an 8-seater solid Teak wood dining table with PU polish.",
            customer_name="Vikram",
        )
        session = self.store.get("9811122233")
        self.assertIsNotNone(session)
        self.assertEqual(session.project_type, "Solid Wood Dining Table")
        self.assertIn("First-Grade Teak (Sagwan)", session.preferred_materials)
        self.assertIn("Polyurethane (PU) Polish", session.preferred_materials)

    def test_measurement_appointment_booking(self):
        res = self.agent.process_message(
            sender_phone="9811122233",
            message_text="Can you visit our apartment this Saturday morning for laser measurements?",
            customer_name="Vikram",
        )
        session = self.store.get("9811122233")
        self.assertEqual(session.appointment_status, "confirmed")
        self.assertIn("Saturday", session.appointment_slot)
        # Master carpenter reply should mention booking
        self.assertTrue(any(w in res["response_text"].lower() for w in ["booking", "confirmed", "visit"]))

    def test_yes_after_scheduling_offer(self):
        """Test that saying 'yes' after the agent suggests a measurement visit schedules slots without asking for dimensions again."""
        phone = "9822233344"
        # 1. Customer provides kitchen dimensions
        res1 = self.agent.process_message(
            sender_phone=phone,
            message_text="We need an L-shaped modular kitchen around 10x8 ft in BWP marine ply.",
        )
        self.assertIn("Budget Guide", res1["response_text"])
        self.assertIn("Timeline", res1["response_text"])
        self.assertIn("15-minute measurement visit", res1["response_text"])

        # 2. Customer simply says "yes" to schedule
        res2 = self.agent.process_message(
            sender_phone=phone,
            message_text="yes",
        )
        session = self.store.get(phone)
        # Verify it DOES NOT ask for dimensions again
        self.assertNotIn("What are the rough wall or room dimensions", res2["response_text"])
        self.assertIn("Saturday at 11:30 AM", res2["response_text"])
        self.assertIn("Sunday at 4:00 PM", res2["response_text"])

        # 3. Customer picks Saturday slot
        res3 = self.agent.process_message(
            sender_phone=phone,
            message_text="Saturday at 11:30 AM, Flat 402 Green Glen",
        )
        self.assertIn("Booking confirmed", res3["response_text"])

        # 4. Customer says "ok thank you" -> Must NOT re-ask for booking slots!
        res4 = self.agent.process_message(
            sender_phone=phone,
            message_text="ok thank you",
        )
        self.assertNotIn("Which slot suits you best", res4["response_text"])
        self.assertNotIn("We currently have slots open", res4["response_text"])
        self.assertIn("welcome", res4["response_text"].lower())

    def test_sechudel_meeting_typo(self):
        """Test that typing 'sechudel meeting' requests visit without asking for dimensions in loop."""
        phone = "9833344455"
        res = self.agent.process_message(
            sender_phone=phone,
            message_text="sechudel meeting",
        )
        self.assertNotIn("What are the rough wall or room dimensions", res["response_text"])
        self.assertIn("Saturday", res["response_text"])

    def test_bargaining_low_budget_bed(self):
        """Test master carpenter negotiation when customer budget is too low (e.g. 15,000 for bed)."""
        phone = "9877788899"
        # 1. Customer asks for bed
        self.agent.process_message(phone, "We need a custom storage bed with hydraulic lift.")
        
        # 2. Customer provides low budget
        res2 = self.agent.process_message(phone, "my budget is 15000 Rs.")
        session = self.store.get(phone)
        self.assertEqual(session.customer_budget, 15000)
        reply = res2["response_text"]
        # Must acknowledge budget respectfully
        self.assertIn("15,000", reply)
        # Must offer value-engineering compromise (Platform/Drawer bed at 22,000 - 25,000)
        self.assertTrue("22,000" in reply or "25,000" in reply)
        # Must NOT just repeat the King Hydraulic price as a dimension
        self.assertNotIn("Got your specifications for Custom Storage Bed (your specified scale)", reply)

    def test_bargaining_discount_request(self):
        """Test courtesy discount offer when customer asks for discount."""
        phone = "9877788898"
        self.agent.process_message(phone, "Looking for a modular kitchen.")
        res = self.agent.process_message(phone, "Can you give some discount or best price?")
        self.assertTrue(any(w in res["response_text"].lower() for w in ["discount", "5%", "8%", "harness", "courtesy"]))


class TestWhatsAppChannel(unittest.TestCase):
    """Test outbound WhatsApp Web bridge and wa.me deep links."""

    def test_web_url(self):
        channel = WhatsAppChannel()
        self.assertEqual(channel.get_web_url(), "https://web.whatsapp.com")

    def test_chat_deep_link(self):
        channel = WhatsAppChannel()
        self.assertEqual(channel.get_chat_deep_link("9876543210"), "https://wa.me/9876543210")
        self.assertEqual(channel.get_chat_deep_link("+91 98765 43210"), "https://wa.me/919876543210")
        self.assertEqual(channel.get_chat_deep_link("919876543210"), "https://wa.me/919876543210")

    def test_chat_deep_link_with_prefill_text(self):
        """Deep link must URL-encode the pre-filled message text."""
        channel = WhatsAppChannel()
        link = channel.get_chat_deep_link("919876543210", prefill_text="Namaste! Your table is ready.")
        self.assertTrue(link.startswith("https://wa.me/919876543210?text="))
        # Encoded text must not contain raw spaces or '!'
        self.assertNotIn(" ", link)
        self.assertIn("Namaste%21%20Your%20table%20is%20ready.", link)
        # Round-trip the query string back to the original message
        import urllib.parse

        parsed = urllib.parse.urlparse(link)
        self.assertEqual(
            urllib.parse.parse_qs(parsed.query)["text"][0],
            "Namaste! Your table is ready.",
        )

    def test_simulation_dispatch(self):
        channel = WhatsAppChannel()
        res = channel.send_message("9876543210", "Namaste! Your appointment is confirmed.")
        self.assertEqual(res["status"], "whatsapp_web")
        self.assertIn("deep_link", res)
        self.assertEqual(res["deep_link"], "https://wa.me/9876543210")
        self.assertEqual(len(channel.outbound_history), 1)
        record = channel.outbound_history[0]
        self.assertEqual(record["recipient_id"], "9876543210")
        self.assertIn("appointment is confirmed", record["message_text"])
        self.assertEqual(record["channel"], "whatsapp_web")

    def test_gujarati_inquiry_and_reply(self):
        """Test Gujarati language inquiry produces authentic Gujarati response."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500001"
        res = agent.process_message(
            sender_phone=phone,
            message_text="મને ૬ સીટર ડાઇનિંગ ટેબલ બનાવવું છે, સાગવાન લાકડામાં શું ભાવ થશે?",
        )
        # Should detect Gujarati and reply in Gujarati
        self.assertEqual(res["session"]["language"], "gu")
        self.assertIn("બજેટ", res["response_text"])
        self.assertIn("₹38,000", res["response_text"])
        self.assertIn("શનિવારે", res["response_text"])

    def test_hindi_sofa_inquiry_and_reply(self):
        """Test Hindi / Hinglish sofa inquiry produces authentic Hindi response."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500002"
        res = agent.process_message(
            sender_phone=phone,
            message_text="मुझे ३ सीटर सोफा बनवाना है, क्या खर्चा आएगा?",
        )
        self.assertEqual(res["session"]["language"], "hi")
        self.assertIn("बजट", res["response_text"])
        self.assertIn("₹22,000", res["response_text"])
        self.assertIn("शनिवार", res["response_text"])

    def test_no_time_chat_confirmation_english(self):
        """Test customer who has no time for in-person visit gets chat confirmation photo request."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500003"
        # 1. State project
        agent.process_message(phone, "We need a fitted wardrobe for master bedroom.")
        # 2. Customer says they don't have time to visit
        res = agent.process_message(phone, "I don't have time for a visit this weekend, can we confirm in chat?")
        self.assertIn("No problem at all", res["response_text"])
        self.assertIn("Room / Wall Photos", res["response_text"])
        self.assertIn("Approximate Measurements", res["response_text"])
        self.assertIn("Design Reference", res["response_text"])

    def test_no_time_chat_confirmation_gujarati(self):
        """Test Gujarati customer who is busy gets Gujarati chat confirmation photo request."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500004"
        agent.process_message(phone, "કબાટ બનાવવો છે")
        res = agent.process_message(phone, "રૂબરૂ મળવાનો સમય નથી, ચેટમાં કહો")
        self.assertEqual(res["session"]["language"], "gu")
        self.assertIn("ચિંતા કરશો નહીં", res["response_text"])
        self.assertIn("દીવાલના ફોટા", res["response_text"])
        self.assertIn("અંદાજિત માપ", res["response_text"])

    def test_customer_shared_photos_acknowledgment(self):
        """Test customer sharing photos gets craftsman photo review acknowledgment."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500005"
        res = agent.process_message(phone, "I have sent the photos of my bedroom wall and Pinterest design.")
        self.assertIn("sharing the photos", res["response_text"].lower())
        self.assertIn("itemized quotation", res["response_text"].lower())

    def test_window_khidkhi_extraction(self):
        """Test window inquiry 'muje 2 khidkhi banani hai' recognizes 2 windows and asks for dimensions & mesh."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500006"
        res = agent.process_message(phone, "muje 2 khidkhi banani hai", customer_name="Rahul")
        self.assertEqual(res["session"]["project_type"], "Custom Wooden Windows")
        self.assertIn("खिड़की", res["response_text"])
        self.assertIn("सागवान", res["response_text"])
        self.assertIn("4x4", res["response_text"])

    def test_human_conversation_flow_no_repeating_templates(self):
        """Test Parag Patel live conversation simulation: multi-turn distinct human replies with exact math."""
        agent = CarpenterAgent(SessionStore())
        phone = "8589951393939"
        name = "Parag Patel"

        # Turn 1: Cabinet inquiry
        r1 = agent.process_message(phone, "Cabinet", customer_name=name)
        self.assertIn("Parag", r1["response_text"])
        self.assertIn("Custom Storage Cabinet", r1["response_text"])

        # Turn 2: Exact dimensions 10*20feet cabinet
        r2 = agent.process_message(phone, "10*20feet cabinet", customer_name=name)
        self.assertIn("200 sq.ft", r2["response_text"])
        self.assertIn("276,000", r2["response_text"])
        self.assertIn("350,000", r2["response_text"])
        self.assertNotEqual(r1["response_text"], r2["response_text"])

        # Turn 3: Labour & transport inquiry - MUST NOT repeat previous message!
        r3 = agent.process_message(phone, "What would be the total cost including labour and transport", customer_name=name)
        self.assertIn("Labour", r3["response_text"])
        self.assertIn("Transport", r3["response_text"])
        self.assertIn("276,000", r3["response_text"])
        self.assertNotEqual(r2["response_text"], r3["response_text"])

        # Turn 4: Exact quote request
        r4 = agent.process_message(phone, "Share me the exact quote", customer_name=name)
        self.assertIn("official workshop quotation", r4["response_text"].lower())
        self.assertIn("Option A", r4["response_text"])
        self.assertIn("Option B", r4["response_text"])
        self.assertNotEqual(r3["response_text"], r4["response_text"])

        # Turn 5: Material selection - Laminate
        r5 = agent.process_message(phone, "Laminate", customer_name=name)
        self.assertIn("Laminate", r5["response_text"])
        self.assertIn("276,000", r5["response_text"])
        self.assertNotEqual(r4["response_text"], r5["response_text"])

        # Turn 6: Material selection - PU
        r6 = agent.process_message(phone, "PU", customer_name=name)
        self.assertIn("PU", r6["response_text"])
        self.assertIn("350,000", r6["response_text"])
        self.assertNotEqual(r5["response_text"], r6["response_text"])

        # Turn 7: Booking site visit
        r7 = agent.process_message(phone, "Come for visit", customer_name=name)
        self.assertIn("Saturday at 11:30 AM", r7["response_text"])
        self.assertIn("Sunday at 4:00 PM", r7["response_text"])

        # Turn 8: Confirmation with landmark
        r8 = agent.process_message(phone, "Saturday is ok and landmark is sosyo Circle", customer_name=name)
        self.assertIn("Booking confirmed", r8["response_text"])
        self.assertIn("Saturday", r8["response_text"])

    def test_cabinate_typo_in_extended_chat(self):
        """Verify that 'cabinate' typo is recognized in ongoing multi-turn conversations."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500007"
        agent.process_message(phone, "Hello Rajesh ji", customer_name="Priya")
        agent.process_message(phone, "How are you?", customer_name="Priya")
        agent.process_message(phone, "Good to connect", customer_name="Priya")
        res = agent.process_message(phone, "i want to make cabinate", customer_name="Priya")

        # Must recognize Custom Storage Cabinet and NOT fall back to generic question
        self.assertEqual(res["session"]["project_type"], "Custom Storage Cabinet")
        self.assertIn("Custom Storage Cabinet", res["response_text"])
        self.assertIn("1,200", res["response_text"])
        self.assertNotIn("What piece are you looking to create", res["response_text"])

    def test_multi_item_inquiry_single_message(self):
        """Verify that asking for multiple furniture items generates distinct itemized quotes."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500008"
        res = agent.process_message(phone, "i want wardrobe and dining table", customer_name="Priya")

        self.assertIn("Custom Wardrobe", res["response_text"])
        self.assertIn("Solid Wood Dining Table", res["response_text"])
        self.assertIn("95,000", res["response_text"])
        self.assertIn("38,000", res["response_text"])

    def test_visit_acceptance_haa_aa_jaiye_and_no_others_ji(self):
        """Verify that 'Haa aa jaiye' accepts site visit offer, locks Saturday slot, asks for address,
        and never addresses the user as 'others ji' or sends generic sofa quote template."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500099"

        # Turn 1: Customer asks about sofa, with WhatsApp pushName set to 'others'
        r1 = agent.process_message(phone, "sofa banana hai", customer_name="others")
        self.assertNotIn("others ji", r1["response_text"].lower())
        self.assertNotIn("others", r1["response_text"].lower())
        self.assertIn("Custom Wooden Sofa", r1["response_text"])

        # Turn 2: Customer selects PU finish
        r2 = agent.process_message(phone, "PU finish", customer_name="others")
        self.assertNotIn("others ji", r2["response_text"].lower())
        self.assertIn("शनिवार सुबह 11:30 बजे", r2["response_text"])
        self.assertIn("रविवार शाम 4:00 बजे", r2["response_text"])

        # Turn 3: Customer agrees to visit: "Haa aa jaiye"
        r3 = agent.process_message(phone, "Haa aa jaiye", customer_name="others")
        self.assertNotIn("others ji", r3["response_text"].lower())
        self.assertNotIn("others", r3["response_text"].lower())
        # Must confirm Saturday 11:30 AM and ask for complete address & landmark
        self.assertIn("शनिवार सुबह 11:30 बजे", r3["response_text"])
        self.assertIn("पता", r3["response_text"])
        self.assertIn("लैंडमार्क", r3["response_text"])
        # Must NOT repeat the generic budget template or ask for room dimensions again
        self.assertNotIn("अनुमानित बजट गाइड", r3["response_text"])
        self.assertNotIn("कमरे या दीवार का अंदाज़न साइज़ क्या है", r3["response_text"])

        # Turn 4: Customer shares address: "Flat 402, Sosyo Circle"
        r4 = agent.process_message(phone, "Flat 402, Sosyo Circle", customer_name="others")
        self.assertIn("बुकिंग पक्की हो गई", r4["response_text"])
        self.assertIn("Flat 402, Sosyo Circle", r4["response_text"])
        self.assertIn("30 मिनट", r4["response_text"])

        # Turn 5: Customer courtesy close: "Theek hai"
        r5 = agent.process_message(phone, "Theek hai", customer_name="others")
        self.assertIn("धन्यवाद", r5["response_text"])
        self.assertNotIn("अनुमानित बजट गाइड", r5["response_text"])

    def test_sequential_sofa_flow_and_no_duplicate_questions(self):
        """Verify sequential conversational flow: 'I want to make 3 sofa' produces exact 3-seater quote,
        never asks 'What piece are you looking to create', and smoothly books appointment."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500111"

        # Turn 1: Customer states piece and size in English
        r1 = agent.process_message(phone, "I want to make 3 sofa", customer_name="hittu Clg")
        self.assertEqual(r1["session"]["project_type"], "Custom Wooden Sofa")
        self.assertEqual(r1["session"]["dimensions"], "3-Seater")
        self.assertEqual(r1["session"]["language"], "en")
        self.assertIn("Custom Wooden Sofa", r1["response_text"])
        self.assertIn("3-Seater", r1["response_text"])
        self.assertIn("22,000", r1["response_text"])
        self.assertIn("Saturday at 11:30 AM", r1["response_text"])
        self.assertNotIn("What piece are you looking to create", r1["response_text"])
        self.assertNotIn("What piece are you planning to make", r1["response_text"])

        # Turn 2: Customer agrees to visit
        r2 = agent.process_message(phone, "Sure, Saturday 11:30 is good", customer_name="hittu Clg")
        self.assertEqual(r2["session"]["appointment_status"], "requested")
        self.assertIn("Saturday at 11:30 AM", r2["response_text"])
        self.assertIn("address", r2["response_text"].lower())
        self.assertNotIn("What piece are you looking to create", r2["response_text"])

        # Turn 3: Customer provides address
        r3 = agent.process_message(phone, "Flat 402, Royal Residency, Pal Road", customer_name="hittu Clg")
        self.assertEqual(r3["session"]["appointment_status"], "confirmed")
        self.assertIn("Booking confirmed", r3["response_text"])
        self.assertIn("Flat 402", r3["response_text"])
        self.assertIn("30 minutes", r3["response_text"])

    def test_10x10_cabinet_dimension_no_re_ask(self):
        """Verify '10×10' with multiplication symbol calculates 100 sq.ft turnkey quote and never asks for size again."""
        agent = CarpenterAgent(SessionStore())
        phone = "919876500222"

        # Turn 1: Customer asks for Custom Storage Cabinet in Gujarati
        r1 = agent.process_message(phone, "સ્ટોરેજ કેબિનેટ બનાવવી છે")
        self.assertEqual(r1["session"]["project_type"], "Custom Storage Cabinet")
        self.assertIn("Custom Storage Cabinet", r1["response_text"])

        # Turn 2: Customer provides dimensions '10×10' (with Unicode multiplication \u00d7)
        r2 = agent.process_message(phone, "10×10")
        self.assertEqual(r2["session"]["dimensions"], "10x10")
        self.assertIn("100 ચોરસ ફૂટ", r2["response_text"])
        self.assertIn("138,000", r2["response_text"])
        self.assertIn("175,000", r2["response_text"])
        # Crucial check: Must NEVER ask for dimensions again!
        self.assertNotIn("તમારી અંદાજિત રૂમ/દીવાલની સાઈઝ", r2["response_text"])
        self.assertNotIn("બેઠક માપ શું છે", r2["response_text"])


if __name__ == "__main__":
    unittest.main()
