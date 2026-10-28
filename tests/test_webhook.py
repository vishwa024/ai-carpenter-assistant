"""Comprehensive unit and integration tests for AI Carpenter Assistant.

Tests:
1. Meta Webhook Handshake Verification (GET /webhook/whatsapp)
2. HMAC SHA-256 Payload Signature Verification
3. Message Deduplication (preventing double-replies)
4. Carpenter AI Agent Brain (Persona, Multi-turn context, Scope extraction)
5. Outbound WhatsApp Channel bridge
"""
import hashlib
import hmac
import json
import unittest

from app.agent import CarpenterAgent, SessionStore
from app.config import Config
from app.web import Deduplicator, verify_hmac_signature
from app.whatsapp import WhatsAppChannel


class TestWebhookSecurityAndHandshake(unittest.TestCase):
    """Test Meta webhook verification and HMAC security layer."""

    def test_hmac_sha256_verification_valid(self):
        """Test valid HMAC SHA-256 payload signature."""
        secret = "super_secret_meta_app_key_123"
        payload = b'{"object": "whatsapp_business_account"}'
        signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        header = f"sha256={signature}"

        self.assertTrue(verify_hmac_signature(payload, header, secret))

    def test_hmac_sha256_verification_tampered(self):
        """Test that tampered payload fails HMAC verification."""
        secret = "super_secret_meta_app_key_123"
        payload = b'{"object": "whatsapp_business_account"}'
        tampered_payload = b'{"object": "whatsapp_business_account", "tampered": true}'
        signature = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        header = f"sha256={signature}"

        self.assertFalse(verify_hmac_signature(tampered_payload, header, secret))

    def test_hmac_sha256_invalid_header_format(self):
        """Test missing prefix or empty header."""
        secret = "secret123"
        payload = b'{}'
        self.assertFalse(verify_hmac_signature(payload, None, secret))
        self.assertFalse(verify_hmac_signature(payload, "invalid_header", secret))


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
    """Test outbound WhatsApp bridge simulation and formatting."""

    def test_simulation_dispatch(self):
        channel = WhatsAppChannel()
        res = channel.send_message("9876543210", "Namaste! Your appointment is confirmed.")
        self.assertEqual(res["status"], "simulated")
        self.assertEqual(len(channel.outbound_history), 1)
        record = channel.outbound_history[0]
        self.assertEqual(record["recipient_id"], "9876543210")
        self.assertIn("appointment is confirmed", record["message_text"])


if __name__ == "__main__":
    unittest.main()
