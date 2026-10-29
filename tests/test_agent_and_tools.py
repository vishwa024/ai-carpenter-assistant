"""Unit tests for Carpentry Tools and Autonomous Carpenter Agent."""
from __future__ import annotations

import unittest

from app.agent import carpenter_agent
from app.tools import (
    calculate_material_needs,
    check_inventory_stock,
    get_joinery_specs,
    _parse_dimensions,
)


class TestCarpentryTools(unittest.TestCase):
    """Test the carpentry and woodworking engineering tools."""

    def test_parse_dimensions_feet(self):
        parsed = _parse_dimensions("6x3 ft")
        self.assertEqual(parsed["length_in"], 72.0)
        self.assertEqual(parsed["width_in"], 36.0)
        self.assertEqual(parsed["thickness_in"], 1.5)

    def test_parse_dimensions_inches(self):
        parsed = _parse_dimensions("72x36x1.5 inches")
        self.assertEqual(parsed["length_in"], 72.0)
        self.assertEqual(parsed["width_in"], 36.0)
        self.assertEqual(parsed["thickness_in"], 1.5)

    def test_calculate_material_needs_6x3_teak(self):
        res = calculate_material_needs("6x3 ft", "teak")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["wood_type"], "Teak")
        self.assertEqual(res["square_feet_net"], 18.0)
        # Net board feet: (72 * 36 * 1.5) / 144 = 27.0
        self.assertEqual(res["board_feet_net"], 27.0)
        # 15% cutting allowance: 27.0 * 1.15 = 31.05
        self.assertEqual(res["cutting_waste_allowance"], "15%")
        self.assertEqual(res["board_feet_required"], 31.05)
        self.assertIn("₹", res["estimated_raw_timber_cost_inr"])
        self.assertIn("summary", res)

    def test_calculate_material_needs_sheesham(self):
        res = calculate_material_needs("4x3 ft", "sheesham")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["wood_type"], "Sheesham")
        self.assertEqual(res["square_feet_net"], 12.0)
        self.assertEqual(res["board_feet_net"], 18.0)
        self.assertEqual(res["board_feet_required"], 20.7)

    def test_check_inventory_stock_in_stock(self):
        res = check_inventory_stock("teak")
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["in_stock"])
        self.assertIn("Grade-A Seasoned C.P. Teak", res["matched_item"])
        self.assertIn("Rack A-1", res["warehouse_location"])

    def test_check_inventory_stock_hardware(self):
        res = check_inventory_stock("hinges")
        self.assertEqual(res["status"], "success")
        self.assertTrue(res["in_stock"])
        self.assertIn("Hettich", res["matched_item"])

    def test_check_inventory_stock_unknown(self):
        res = check_inventory_stock("bamboo exotic wood 99")
        self.assertEqual(res["status"], "not_found")
        self.assertFalse(res["in_stock"])
        self.assertGreater(res["lead_time_days"], 0)

    def test_get_joinery_specs_mortise_and_tenon(self):
        specs = get_joinery_specs("mortise and tenon")
        self.assertIn("Traditional Mortise and Tenon", specs)
        self.assertIn("drawbore dowel pins", specs)
        self.assertIn("Waterproof PVA", specs)
        self.assertIn("Clamping & Cure Time", specs)

    def test_get_joinery_specs_dovetail(self):
        specs = get_joinery_specs("dovetail")
        self.assertIn("Dovetail", specs)
        self.assertIn("1:8 slope for hardwoods", specs)

    def test_get_joinery_specs_pocket_hole(self):
        specs = get_joinery_specs("pocket hole")
        self.assertIn("Pocket Hole", specs)
        self.assertIn("15-degree", specs)
        self.assertIn("screws", specs)


class TestAutonomousAgent(unittest.TestCase):
    """Test the autonomous agent loop and observable execution traces."""

    def test_autonomous_execution_loop(self):
        user_task = "Estimate material for a 6x3 ft dining table in teak wood and verify stock"
        res = carpenter_agent.run_agent_loop(user_task)

        self.assertIn("final_response", res)
        self.assertIn("trace", res)
        self.assertGreater(len(res["trace"]), 0)

        # Inspect trace steps
        trace_tools = [step["tool_name"] for step in res["trace"]]
        self.assertIn("calculate_material_needs", trace_tools)
        self.assertIn("check_inventory_stock", trace_tools)

        # Verify each trace step contains required keys
        for step in res["trace"]:
            self.assertIn("step", step)
            self.assertIn("thought", step)
            self.assertIn("tool_name", step)
            self.assertIn("tool_args", step)
            self.assertIn("observation", step)

        # Verify final response contains craftsman details
        response_text = res["final_response"]
        self.assertIn("Heritage Woodworks", response_text)
        self.assertIn("Teak", response_text)
        self.assertIn("board feet", response_text)

    def test_joinery_query_trace(self):
        user_task = "What are the specs and glue guidelines for dovetail joints on drawers?"
        res = carpenter_agent.run_agent_loop(user_task)

        trace_tools = [step["tool_name"] for step in res["trace"]]
        self.assertIn("get_joinery_specs", trace_tools)


if __name__ == "__main__":
    unittest.main()
