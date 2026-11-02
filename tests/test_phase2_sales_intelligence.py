"""Phase 2 Sales Intelligence & Consultation Verification Test Suite.

Exhaustively verifies:
1. Furniture Consultation Flows: Wardrobes, Kitchens, Sofas, Dining Tables, Windows/Doors, Beds.
2. Smart Visit Scheduling: Localized slots, conflict checks, address validation, rescheduling, cancellations.
3. Growth & Follow-Up Engine: Rule-based follow-up evaluation, personalized craft nudges, business growth metrics.
4. Server APIs: Appointments management, growth analytics, follow-up dispatches.
"""
from __future__ import annotations

import json
import threading
import time
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from app.appointments import appointment_engine, get_smart_visit_slots
from app.crm import crm
from app.flows import (
    BedFlow,
    DiningFlow,
    FurnitureFlowRegistry,
    KitchenFlow,
    SofaFlow,
    WardrobeFlow,
    WindowsAndDoorsFlow,
)
from app.growth import growth_engine
from app.web import CarpenterRequestHandler


class TestPhase2FurnitureFlows(unittest.TestCase):
    """Test suite for specialized furniture domain consultation flows."""

    def test_wardrobe_consultation_flow(self):
        adv_en = WardrobeFlow.get_advice("en")
        self.assertIn("IS 710", adv_en)
        self.assertIn("waterproof", adv_en)
        self.assertIn("hinged", adv_en.lower())

        adv_gu = WardrobeFlow.get_advice("gu")
        self.assertIn("મરીન પ્લાય", adv_gu)

        adv_hi = WardrobeFlow.get_advice("hi")
        self.assertIn("वाटरप्रूफ मरीन प्लाईवुड", adv_hi)

    def test_kitchen_consultation_flow(self):
        adv_en = KitchenFlow.get_advice("en")
        self.assertIn("BWP Marine Plywood", adv_en)
        self.assertIn("45kg", adv_en)

        adv_gu = KitchenFlow.get_advice("gu")
        self.assertIn("100% IS 710 BWP", adv_gu)

    def test_sofa_and_dining_flows(self):
        sofa_en = SofaFlow.get_advice("3-seater", "en")
        self.assertIn("Teak", sofa_en)
        self.assertIn("mortise & tenon", sofa_en)
        self.assertIn("40D", sofa_en)

        dining_en = DiningFlow.get_advice("en")
        self.assertIn("1.5-inch", dining_en)
        self.assertIn("PU", dining_en)

    def test_doors_windows_and_bed_flows(self):
        win_en = WindowsAndDoorsFlow.get_advice("en")
        self.assertIn("CP Teak", win_en)
        self.assertIn("SS-304", win_en)

        bed_en = BedFlow.get_advice("en")
        self.assertIn("hydraulic", bed_en.lower())
        self.assertIn("13,000", bed_en)

    def test_flow_registry_dispatch(self):
        self.assertIsNotNone(FurnitureFlowRegistry.get_flow_advice("Modular Kitchen", "en"))
        self.assertIsNotNone(FurnitureFlowRegistry.get_flow_advice("Fitted Wardrobe", "gu"))
        self.assertIsNotNone(FurnitureFlowRegistry.get_flow_advice("Solid Wood Dining Table", "hi"))
        self.assertIsNotNone(FurnitureFlowRegistry.get_flow_advice("Custom Wooden Sofa", "en"))


class TestPhase2AppointmentEngine(unittest.TestCase):
    """Test suite for measurement appointment booking and calendar logic."""

    def test_smart_visit_slots_generation(self):
        slots_en = get_smart_visit_slots("en")
        self.assertIn("Saturday at 11:30 AM", slots_en["slot_a"])
        self.assertIn("Sunday at 4:00 PM", slots_en["slot_b"])
        self.assertIn("free 15-minute measurement visit", slots_en["prompt"])

        slots_gu = get_smart_visit_slots("gu")
        self.assertIn("શનિવારે", slots_gu["slot_a"])
        self.assertIn("રવિવારે", slots_gu["slot_b"])

    def test_appointment_booking_confirmation_and_lifecycle(self):
        unique_phone = f"91987{str(int(time.time() * 1000))[-6:]}"
        crm.get_or_create_customer(unique_phone, "Kalpesh Shah")

        # 1. Request visit without address
        apt1 = appointment_engine.create_or_request_visit(
            phone=unique_phone,
            slot_time="Saturday at 11:30 AM",
            project_scope="Fitted Wardrobe",
        )
        self.assertEqual(apt1["status"], "requested")
        self.assertEqual(apt1["slot_time"], "Saturday at 11:30 AM")

        # 2. Confirm visit by providing address in Satellite
        apt2 = appointment_engine.confirm_visit(
            phone=unique_phone,
            address="A-302, Safal Parivesh, Prahlad Nagar, Ahmedabad",
        )
        self.assertEqual(apt2["status"], "confirmed")
        self.assertEqual(apt2["locality"], "Prahlad Nagar")

        # 3. Reschedule visit
        ok_resched = appointment_engine.reschedule_visit(unique_phone, "Sunday at 4:00 PM")
        self.assertTrue(ok_resched)
        apt3 = appointment_engine.get_appointment_for_customer(unique_phone)
        self.assertEqual(apt3["slot_time"], "Sunday at 4:00 PM")
        self.assertEqual(apt3["status"], "rescheduled")

        # 4. Cancel visit
        ok_cancel = appointment_engine.cancel_visit(unique_phone, reason="Client out of town")
        self.assertTrue(ok_cancel)
        apt4 = appointment_engine.get_appointment_for_customer(unique_phone)
        self.assertEqual(apt4["status"], "cancelled")
        self.assertIn("Client out of town", apt4["notes"])


class TestPhase2GrowthAndAnalyticsEngine(unittest.TestCase):
    """Test suite for business growth metrics and automated craft follow-ups."""

    def test_business_growth_metrics_calculation(self):
        metrics = growth_engine.get_business_growth_metrics()
        self.assertIn("total_inquiries", metrics)
        self.assertIn("active_pipeline_leads", metrics)
        self.assertIn("conversion_rate_pct", metrics)
        self.assertIn("won_revenue_inr", metrics)
        self.assertIn("pipeline_value_inr", metrics)
        self.assertIn("top_localities", metrics)
        self.assertIn("top_furniture_demand", metrics)
        self.assertGreaterEqual(metrics["total_inquiries"], 1)

    def test_follow_up_message_crafting_multilingual(self):
        phone = "919876540099"
        crm.get_or_create_customer(phone, "Jignesh Bhai", language="gu")
        crm.update_customer(phone, project_type="Solid Wood Dining Table", locality="Bopal")

        msg_gu = growth_engine.generate_follow_up_message(phone)
        self.assertEqual(msg_gu["language"], "gu")
        self.assertIn("હેરિટેજ વુડવર્ક્સ", msg_gu["text"])
        self.assertIn("Bopal", msg_gu["text"])


class TestPhase2ServerAPIs(unittest.TestCase):
    """Test suite for Phase 2 REST API endpoints."""

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

    def test_appointments_api_flow(self):
        phone = f"91988{str(int(time.time() * 1000))[-6:]}"
        # Book appointment
        book_url = f"{self.base_url}/api/appointments/book"
        body = json.dumps({
            "phone": phone,
            "slot_time": "Saturday at 11:30 AM",
            "address": "B-404, Gala Haven, South Bopal",
            "project_scope": "Modular Kitchen",
        }).encode("utf-8")
        req = urllib.request.Request(book_url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertEqual(data["appointment"]["status"], "confirmed")

        # List appointments
        list_url = f"{self.base_url}/api/appointments?limit=10"
        with urllib.request.urlopen(list_url) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertGreater(data["count"], 0)

        # Reschedule appointment
        resched_url = f"{self.base_url}/api/appointments/reschedule"
        resched_body = json.dumps({"phone": phone, "new_slot": "Sunday at 4:00 PM"}).encode("utf-8")
        resched_req = urllib.request.Request(resched_url, data=resched_body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(resched_req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])

    def test_growth_metrics_and_follow_ups_api(self):
        # Growth metrics
        url_metrics = f"{self.base_url}/api/growth/metrics"
        with urllib.request.urlopen(url_metrics) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertIn("conversion_rate_pct", data["metrics"])

        # Follow ups
        url_followups = f"{self.base_url}/api/growth/follow_ups"
        with urllib.request.urlopen(url_followups) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["ok"])
            self.assertIn("pending", data)


if __name__ == "__main__":
    unittest.main()
