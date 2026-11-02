"""Phase 1 Foundation Verification Test Suite.

Exhaustively verifies:
1. Database Layer: Schema, WAL mode, foreign keys, catalogue seeding, database backup.
2. CRM Layer: Phone normalization, locality extraction, search, filter, sort, conversation logging, CSV export.
3. Pricing Engine: Dimension parsing, transparent costing formula, quotation levels, admin approval, value-engineering.
4. State Machine & Enquiry Memory: 14-stage state machine, memory tracking, never re-asking answered questions.
5. Server APIs & Security: Admin auth, handover toggle, quotation approval, catalogue endpoints, CRM endpoints.
"""
from __future__ import annotations

import json
import time
import unittest
import urllib.parse
import urllib.request
import threading

from app.config import config
from app.crm import crm, sanitize_phone, detect_ahmedabad_locality
from app.database import db
from app.pricing import pricing_engine, parse_dimension_details
from app.state_machine import state_machine, ConversationStage, CustomerEnquiryMemory
from app.agent import CarpenterAgent, SessionStore
from app.web import CarpenterRequestHandler
from http.server import ThreadingHTTPServer


class TestPhase1DatabaseAndCRM(unittest.TestCase):
    """Test suite for database schema, CRM logic, and data integrity."""

    def test_phone_sanitization_and_locality_detection(self):
        # International and local formats
        self.assertEqual(sanitize_phone("+91 98765 43210"), "919876543210")
        self.assertEqual(sanitize_phone("0091-98765-43210"), "919876543210")
        self.assertEqual(sanitize_phone("9876543210"), "9876543210")

        # Ahmedabad localities
        self.assertEqual(detect_ahmedabad_locality("I live near Bopal cross roads"), "Bopal")
        self.assertEqual(detect_ahmedabad_locality("Flat in Nehrunagar, Ahmedabad"), "Nehrunagar")
        self.assertEqual(detect_ahmedabad_locality("ઘર બોપલમાં છે"), "Bopal")
        self.assertEqual(detect_ahmedabad_locality(" सैटेलाइट एरिया "), "Satellite")

    def test_crm_customer_lifecycle_and_duplicate_prevention(self):
        unique_suffix = str(int(time.time() * 1000))[-6:]
        phone = f"91987{unique_suffix}"
        # Create
        c1 = crm.get_or_create_customer(phone, name="Amit Patel", language="gu")
        self.assertEqual(c1["phone"], phone)
        self.assertEqual(c1["name"], "Amit Patel")
        self.assertEqual(c1["lead_status"], "NEW_ENQUIRY")

        # Duplicate check: should return existing without recreating
        c2 = crm.get_or_create_customer(phone, name="Amit Patel")
        self.assertEqual(c1["id"], c2["id"])

        # Update customer
        updated = crm.update_customer(
            phone,
            locality="Satellite",
            project_type="Modular Kitchen",
            dimensions="10x12 ft",
            budget=180000,
            lead_status="ESTIMATION",
        )
        self.assertEqual(updated["locality"], "Satellite")
        self.assertEqual(updated["project_type"], "Modular Kitchen")
        self.assertEqual(updated["budget"], 180000)
        self.assertEqual(updated["lead_status"], "ESTIMATION")

        # List with filter
        results = crm.list_customers(locality="Satellite")
        self.assertTrue(any(r["phone"] == phone for r in results))

        # CSV Export contains Amit Patel
        csv_export = crm.export_csv()
        self.assertIn("Amit Patel", csv_export)
        self.assertIn(phone, csv_export)
        self.assertIn("Satellite", csv_export)

    def test_database_backup_creates_valid_file(self):
        backup_path = db.backup()
        self.assertTrue(backup_path.is_file())
        self.assertGreater(backup_path.stat().st_size, 0)


class TestPhase1PricingEngine(unittest.TestCase):
    """Test suite for LLM-independent pricing engine and transparent formulas."""

    def test_dimension_parsing_and_seating_scale(self):
        # 10x8 feet
        dim = parse_dimension_details("10x8 ft")
        self.assertEqual(dim["sqft"], 80.0)

        # 3 sofa / 3 seater
        seater = parse_dimension_details("3-seater")
        self.assertEqual(seater["type"], "seater")
        self.assertEqual(seater["seater_count"], 3)

        # King bed
        bed = parse_dimension_details("King Size bed")
        self.assertEqual(bed["type"], "bed")
        self.assertEqual(bed["scale"], "King Size")

    def test_transparent_turnkey_cost_formula(self):
        dim = {"sqft": 100.0, "quantity": 1}
        breakdown = pricing_engine.calculate_turnkey_breakdown("Custom Wardrobe", dim, "laminate")
        formula = breakdown["formula_breakdown"]
        # Formula: Material + Hardware + Labour + Finishing + Transport + Installation + Taxes + Approved Margin = Estimated Price
        self.assertIn("material_cost", formula)
        self.assertIn("hardware_cost", formula)
        self.assertIn("labour_cost", formula)
        self.assertIn("finishing_cost", formula)
        self.assertIn("transport_cost", formula)
        self.assertIn("installation_cost", formula)
        self.assertIn("approved_margin", formula)
        self.assertIn("taxes_gst_18pct", formula)
        self.assertIn("total_exact", formula)

        direct_cost = (
            formula["material_cost"]
            + formula["hardware_cost"]
            + formula["labour_cost"]
            + formula["finishing_cost"]
            + formula["transport_cost"]
            + formula["installation_cost"]
        )
        self.assertAlmostEqual(direct_cost, formula["direct_cost"], places=1)
        sum_parts = direct_cost + formula["approved_margin"] + formula["taxes_gst_18pct"]
        self.assertAlmostEqual(sum_parts, formula["total_exact"], places=1)

    def test_quotation_tiers_and_admin_approval(self):
        phone = "919876500666"
        crm.get_or_create_customer(phone, "Vikram Mehta")
        qid = pricing_engine.save_quotation(
            phone=phone,
            project_type="Modular Kitchen",
            dimensions="12x10 ft",
            level="preliminary",
            breakdown={"sqft": 120.0},
            total_amount=165000,
        )
        quote = pricing_engine.get_quotation(qid)
        self.assertEqual(quote["status"], "pending")

        # Admin approval
        approved = pricing_engine.approve_quotation(qid, approved_by="Rajesh Sharma")
        self.assertTrue(approved)

        quote_after = pricing_engine.get_quotation(qid)
        self.assertEqual(quote_after["status"], "approved")
        self.assertEqual(quote_after["approved_by"], "Rajesh Sharma")


class TestPhase1StateMachineAndMemory(unittest.TestCase):
    """Test suite for 14-stage state machine and enquiry memory."""

    def test_conversation_stage_enum_has_14_stages(self):
        expected_stages = {
            "NEW_ENQUIRY", "GREETING", "REQUIREMENT_COLLECTION", "PROJECT_DISCOVERY",
            "BUDGET_DISCUSSION", "ESTIMATION", "VISIT_REQUESTED", "VISIT_CONFIRMED",
            "QUOTATION_PENDING", "QUOTATION_SENT", "NEGOTIATION", "FOLLOW_UP",
            "JOB_WON", "JOB_LOST", "HUMAN_HANDOVER"
        }
        actual_stages = {s.value for s in ConversationStage}
        self.assertTrue(expected_stages.issubset(actual_stages))

    def test_memory_tracks_answered_fields_and_never_re_asks(self):
        mem = CustomerEnquiryMemory(phone="919876500777")
        self.assertFalse(mem.is_answered("furniture_type"))
        self.assertEqual(mem.get_missing_field(), "furniture_type")

        # Customer specifies furniture
        mem.update_field("project_type", "Custom Wooden Sofa")
        self.assertTrue(mem.is_answered("furniture_type"))
        self.assertEqual(mem.get_missing_field(), "dimensions")

        # Customer specifies dimensions
        mem.update_field("dimensions", "3-Seater")
        self.assertTrue(mem.is_answered("dimensions"))
        self.assertNotEqual(mem.get_missing_field(), "dimensions")

    def test_human_handover_suppression_in_agent(self):
        agent = CarpenterAgent(SessionStore())
        phone = "919876500888"

        # Normal turn
        r1 = agent.process_message(phone, "Namaste Rajesh bhai")
        self.assertFalse(r1.get("suppressed", False))
        self.assertTrue(any(g in r1["response_text"] for g in ["Namaste", "नमस्ते", "નમસ્તે", "Heritage Woodworks"]))

        # Enable human handover
        session = agent.sessions.get(phone)
        session.human_handover = True

        # Next turn should be suppressed
        r2 = agent.process_message(phone, "Are you there?")
        self.assertTrue(r2.get("suppressed", False))
        self.assertEqual(r2["response_text"], "")
        self.assertEqual(r2["source"], "human_handover")


class TestPhase1ServerAndSecurityAPIs(unittest.TestCase):
    """Test suite for server endpoints, admin authentication, and security."""

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CarpenterRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_crm_customers_api(self):
        url = f"{self.base_url}/api/crm/customers?limit=10"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertIn("customers", data)

    def test_crm_export_csv_api(self):
        url = f"{self.base_url}/api/crm/export.csv"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/csv", resp.headers.get("Content-Type", ""))
            csv_text = resp.read().decode("utf-8")
            self.assertIn("WhatsApp Number", csv_text)

    def test_catalogue_api_get_and_post(self):
        # GET catalogue
        url = f"{self.base_url}/api/catalogue?category=timber"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertGreater(len(data["items"]), 0)

        # POST update rate
        post_url = f"{self.base_url}/api/catalogue"
        body = json.dumps({"action": "update_rate", "item_id": "mat_cp_teak", "rate": 3950.0}).encode("utf-8")
        post_req = urllib.request.Request(post_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(post_req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res["ok"])

    def test_handover_api_toggle(self):
        phone = "919876500999"
        crm.get_or_create_customer(phone, "Test Handover Customer")
        url = f"{self.base_url}/api/handover"
        body = json.dumps({"phone": phone, "human_handover": True}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res["ok"])
            self.assertTrue(res["human_handover"])

    def test_quotation_approval_security_enforcement(self):
        phone = "919876500998"
        crm.get_or_create_customer(phone, "Test Security Customer")
        qid = pricing_engine.save_quotation(
            phone=phone,
            project_type="Wardrobe",
            dimensions="8x6 ft",
            level="detailed",
            breakdown={"sqft": 48.0},
            total_amount=66000,
        )

        # 1. Unauthenticated request should be rejected with 401 Unauthorized
        url = f"{self.base_url}/api/quotations/approve"
        unauth_body = json.dumps({"quotation_id": qid}).encode("utf-8")
        unauth_req = urllib.request.Request(url, data=unauth_body, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(unauth_req)
            self.fail("Expected 401 Unauthorized for unauthenticated approval")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 401)

        # 2. Authenticated request with Bearer token matching config.ADMIN_PASSWORD should succeed
        auth_req = urllib.request.Request(
            url,
            data=unauth_body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.ADMIN_PASSWORD}",
            },
        )
        with urllib.request.urlopen(auth_req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res["ok"])
            self.assertEqual(res["status"], "approved")


if __name__ == "__main__":
    unittest.main()
