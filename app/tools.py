"""Modular Carpentry and Woodworking Tools for AI Master Carpenter Agent.

Provides deterministic engineering and material calculation tools:
1. calculate_material_needs: Computes board feet, square footage, 15% cutting waste, and costs.
2. check_inventory_stock: Checks local workshop stock, warehouse locations, and availability.
3. get_joinery_specs: Returns hardware specs, screw gauges, adhesives, and curing guidelines.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional

# Standard Wood Prices in INR per Board Foot (1 board foot = 144 cubic inches = 1ft x 1ft x 1inch)
WOOD_RATES_PER_BOARD_FOOT: Dict[str, float] = {
    "teak": 420.0,            # C.P. / Burma Teak (Sagwan)
    "sagwan": 420.0,
    "burma teak": 520.0,
    "sheesham": 260.0,         # Indian Rosewood
    "rosewood": 260.0,
    "shisham": 260.0,
    "white oak": 320.0,
    "oak": 310.0,
    "red oak": 290.0,
    "walnut": 490.0,
    "mahogany": 340.0,
    "pine": 110.0,             # New Zealand / Radiata Pine
    "pinewood": 110.0,
    "cedar": 220.0,
    "ash": 280.0,
    "maple": 310.0,
    "marine ply": 140.0,       # Plywood board-foot equivalent
    "plywood": 120.0,
    "commercial ply": 90.0,
    "mdf": 75.0,
}

# Simulated Workshop Inventory Catalogue
WORKSHOP_INVENTORY: Dict[str, Dict[str, Any]] = {
    "teak": {
        "item_name": "Grade-A Seasoned C.P. Teak Lumber (2\" x 6\" x 8')",
        "category": "Solid Hardwood",
        "in_stock": True,
        "quantity_available": 185,
        "unit": "board feet",
        "unit_price_inr": 420.0,
        "warehouse_location": "Rack A-1 (Kiln-Dried Timber Yard)",
        "lead_time_days": 0,
        "grade": "FAS (First and Seconds) - Moisture < 10%",
        "notes": "Premium seasoned grain, zero sapwood, ready for immediate cutting and joining.",
    },
    "sheesham": {
        "item_name": "Indian Rosewood / Sheesham Planks (1.5\" x 5\" x 7')",
        "category": "Solid Hardwood",
        "in_stock": True,
        "quantity_available": 120,
        "unit": "board feet",
        "unit_price_inr": 260.0,
        "warehouse_location": "Rack A-3 (Hardwood Bay)",
        "lead_time_days": 0,
        "grade": "Select Seasoned Heartwood",
        "notes": "Rich dual-tone grain, kiln-dried to 9% moisture content.",
    },
    "oak": {
        "item_name": "Imported American White Oak (1.5\" x 6\" x 8')",
        "category": "Solid Hardwood",
        "in_stock": True,
        "quantity_available": 65,
        "unit": "board feet",
        "unit_price_inr": 310.0,
        "warehouse_location": "Rack B-2 (Imported Timber Bay)",
        "lead_time_days": 0,
        "grade": "FAS Quarter-Sawn",
        "notes": "Excellent ray fleck patterns, ideal for high-end dining tables.",
    },
    "pine": {
        "item_name": "Radiata Pine Clear Boards (1\" x 6\" x 8')",
        "category": "Softwood",
        "in_stock": True,
        "quantity_available": 90,
        "unit": "board feet",
        "unit_price_inr": 110.0,
        "warehouse_location": "Rack C-1 (Softwood Bay)",
        "lead_time_days": 0,
        "grade": "Clear Grade (Knot-free)",
        "notes": "Lightweight, easy machining, ideal for drawer interiors and framing.",
    },
    "walnut": {
        "item_name": "American Black Walnut (2\" x 7\" x 8')",
        "category": "Exotic Hardwood",
        "in_stock": False,
        "quantity_available": 0,
        "unit": "board feet",
        "unit_price_inr": 490.0,
        "warehouse_location": "Special Procurement",
        "lead_time_days": 4,
        "grade": "FAS Premium",
        "notes": "Currently reserved on custom order; new batch arriving from port distributor in 4 days.",
    },
    "marine ply": {
        "item_name": "IS 710 Boiling Water Resistant (BWR) Marine Plywood (8' x 4' x 18mm)",
        "category": "Engineered Wood Panels",
        "in_stock": True,
        "quantity_available": 28,
        "unit": "sheets (8x4 ft)",
        "unit_price_inr": 3600.0,
        "warehouse_location": "Sheet Bay S-1 (Ground Floor)",
        "lead_time_days": 0,
        "grade": "Century / Greenply IS 710 Marine Grade",
        "notes": "Calibrated thickness, 100% Gurjan core, 25-year borer and termite warranty.",
    },
    "commercial ply": {
        "item_name": "IS 303 Moisture Resistant (MR) Commercial Plywood (8' x 4' x 18mm)",
        "category": "Engineered Wood Panels",
        "in_stock": True,
        "quantity_available": 35,
        "unit": "sheets (8x4 ft)",
        "unit_price_inr": 2200.0,
        "warehouse_location": "Sheet Bay S-2",
        "lead_time_days": 0,
        "grade": "IS 303 Interior Grade",
        "notes": "Suitable for bedroom wardrobes, TV consoles, and wall panelling.",
    },
    "hinges": {
        "item_name": "Hettich Sensys 110° Soft-Close Concealed Hydraulic Hinges",
        "category": "Hardware & Fittings",
        "in_stock": True,
        "quantity_available": 46,
        "unit": "pairs",
        "unit_price_inr": 480.0,
        "warehouse_location": "Hardware Bin H-4",
        "lead_time_days": 0,
        "grade": "German Engineering - 80,000 Cycle Tested",
        "notes": "Integrated soft-close damping, nickel-plated anti-rust finish.",
    },
    "drawer slides": {
        "item_name": "Hafele Matrix Box / Telescopic Soft-Close Channels (20-inch)",
        "category": "Hardware & Fittings",
        "in_stock": True,
        "quantity_available": 22,
        "unit": "pairs",
        "unit_price_inr": 950.0,
        "warehouse_location": "Hardware Bin H-7",
        "lead_time_days": 0,
        "grade": "Heavy Duty 45kg Load Rating",
        "notes": "Full extension ball-bearing slides with silent soft-close action.",
    },
    "fevicol": {
        "item_name": "Fevicol Marine Waterproof Wood Adhesive (5kg Pack)",
        "category": "Adhesives & Glues",
        "in_stock": True,
        "quantity_available": 14,
        "unit": "buckets (5kg)",
        "unit_price_inr": 1350.0,
        "warehouse_location": "Chemical Locker C-2",
        "lead_time_days": 0,
        "grade": "EN 204 / D3 Waterproof Standard",
        "notes": "7-hour water boiling resistance, rapid 45-minute green strength setting.",
    },
    "pu polish": {
        "item_name": "Asian Paints Acolook 2-Pack Polyurethane (PU) Clear Polish (4L Pack)",
        "category": "Finishing & Coating",
        "in_stock": True,
        "quantity_available": 8,
        "unit": "packs (4L)",
        "unit_price_inr": 3200.0,
        "warehouse_location": "Finishing Room F-1",
        "lead_time_days": 0,
        "grade": "Interior Hard-Wearing Gloss / Matt",
        "notes": "Scratch-resistant, non-yellowing, alcohol and water ring resistant.",
    },
    "screws": {
        "item_name": "Hardened Woodworking Screws #8 x 1-1/4\" & 2\" Coarse Zinc",
        "category": "Fasteners",
        "in_stock": True,
        "quantity_available": 1400,
        "unit": "pieces",
        "unit_price_inr": 2.5,
        "warehouse_location": "Fasteners Cabinet F-3",
        "lead_time_days": 0,
        "grade": "Case-Hardened Carbon Steel with Torx Drive",
        "notes": "Self-tapping, deep-thread design that prevents timber splitting.",
    },
    "dowels": {
        "item_name": "Fluted Beechwood Alignment Dowels (8mm x 40mm)",
        "category": "Joinery Fasteners",
        "in_stock": True,
        "quantity_available": 600,
        "unit": "pieces",
        "unit_price_inr": 4.0,
        "warehouse_location": "Fasteners Cabinet F-2",
        "lead_time_days": 0,
        "grade": "European Kiln-Dried Beechwood",
        "notes": "Spiral glue flutes for maximum PVA glue spread and hydraulic release.",
    },
}

# Joinery Guidelines Database
JOINERY_SPECIFICATIONS: Dict[str, Dict[str, Any]] = {
    "mortise and tenon": {
        "name": "Traditional Mortise and Tenon Joint",
        "application": "Dining tables, workbench legs, solid wood chair frames, structural timber door framing.",
        "proportions": "Tenon thickness = 1/3 of stock thickness (e.g. 1/2\" tenon on 1.5\" timber). Tenon width = 1/2 to 2/3 of rail width. Depth = 2/3 to 3/4 of leg thickness.",
        "hardware_and_fasteners": "No metallic screws needed. Use 3/8\" (10mm) tapered drawbore dowel pins in contrasting hardwood (Oak or Teak) for irreversible mechanical lock.",
        "adhesive_specs": "Type D3/D4 Waterproof PVA Wood Glue (e.g., Fevicol Marine or Titebond III) applied to both mortise walls and tenon cheeks.",
        "clamping_and_curing": "Parallel jaw bar clamps at 80-100 PSI for 60-90 minutes. Full cure time: 24 hours before shaping or applying heavy loads.",
        "master_craftsman_tip": "Cut mortises first, then size tenons to fit. Relieve tenon corners slightly to allow excess glue squeeze-out and prevent hydraulic blowout.",
    },
    "pocket hole": {
        "name": "Kreg-Style Pocket Hole Joinery",
        "application": "Cabinet carcasses, face frames, hidden internal supports, quick modular furniture builds.",
        "proportions": "Drill at 15-degree angle. Position holes 1/2\" from each edge and 6\"-8\" on center along face frames.",
        "hardware_and_fasteners": "#7 or #8 case-hardened coarse-thread Maxi-Loc screws with washer head (1-1/4\" length for 3/4\" stock; 1-1/2\" for 1\" stock; 2-1/2\" for 1.5\" stock).",
        "adhesive_specs": "PVA Wood Glue applied along the butted mating edges before driving screws.",
        "clamping_and_curing": "Hold flush with face-clamp or right-angle clamp while driving screws. Immediate joint strength; clamps can be removed immediately after screw seating.",
        "master_craftsman_tip": "Always drive screws slowly into hardwoods with clutch set to prevent stripping the pocket recess or shearing screw heads.",
    },
    "dovetail": {
        "name": "Through and Half-Blind Dovetail Joinery",
        "application": "High-end solid wood drawers, blanket chests, heirloom casework, jewellery boxes.",
        "proportions": "1:8 slope for hardwoods (Teak, Sheesham, Walnut); 1:6 slope for softwoods (Pine). Pin size: 1/4\" to 3/8\" at narrowest point for refined hand-cut aesthetic.",
        "hardware_and_fasteners": "100% mechanical wooden interlock. Zero metal fasteners required.",
        "adhesive_specs": "PVA Wood Glue or Liquid Hide Glue (LHG) for extended open working time during complex multi-pin assembly.",
        "clamping_and_curing": "Light clamping pressure across pin boards only using wooden cauls for 45 minutes. Full cure: 24 hours before planing flush.",
        "master_craftsman_tip": "Score your baseline deeply with a marking gauge. Scribing lines prevents cross-grain tearout when chiseling the waste between pins and tails.",
    },
    "dowel": {
        "name": "Fluted Hardwood Dowel Joint",
        "application": "Tabletop panel edge-gluing, knock-down furniture frames, cabinet shelf supports.",
        "proportions": "Dowel diameter = 3/8\" to 1/2\" of timber thickness (e.g., 8mm dowel for 18mm board; 10mm dowel for 25mm board). Embed at least 1-1/4\" on each side.",
        "hardware_and_fasteners": "Multi-groove spiral fluted beechwood dowels (8mm x 40mm or 10mm x 50mm).",
        "adhesive_specs": "PVA D3 adhesive injected into both holes and spread along mating edges.",
        "clamping_and_curing": "Pipe or I-beam bar clamps every 10-12 inches for 60 minutes. Full cure: 12-24 hours.",
        "master_craftsman_tip": "Chamfer dowel tips slightly to ease insertion, and ensure drill holes are 2mm deeper than dowel half-length to hold surplus glue.",
    },
    "mitre with spline": {
        "name": "Reinforced 45° Mitre Joint with Hardwood Spline",
        "application": "Picture frames, decorative keepsake boxes, cabinet door borders, plinth fascias.",
        "proportions": "45-degree angle cut. Spline slot routed across exterior corner: 1/8\" (3mm) thick, extending 3/4 through the joint.",
        "hardware_and_fasteners": "Contrasting solid hardwood spline (e.g., dark Teak spline inside a White Oak or Pine frame).",
        "adhesive_specs": "PVA Marine Wood Glue applied to mitre faces and into the spline kerf.",
        "clamping_and_curing": "Corner band/strap clamp with corner pads for 90 minutes. Full cure: 24 hours before trimming spline flush.",
        "master_craftsman_tip": "Cut spline grain oriented across the joint angle, never parallel to the spline length, so it provides maximum cross-grain tensile strength.",
    },
    "lap joint": {
        "name": "Half-Lap / Cross-Lap Joint",
        "application": "Timber framing, workbench stretchers, trellis construction, cabinet door rails.",
        "proportions": "Remove exactly 50% of the thickness on both mating components for a perfectly flush face.",
        "hardware_and_fasteners": "Two #8 x 1-1/2\" countersunk stainless/brass screws, or twin 8mm dowels.",
        "adhesive_specs": "Standard D3 PVA wood glue across the generous lap face.",
        "clamping_and_curing": "Parallel F-clamps for 45 minutes. Full cure: 12 hours.",
        "master_craftsman_tip": "Cut cheeks using a dado blade or multi-kerf table saw pass, then pare dead flat with a wide shoulder chisel.",
    },
}


def _parse_dimensions(dim_str: str) -> Dict[str, float]:
    """Parse dimension string into length (inches), width (inches), and thickness (inches).

    Handles formats like:
    - '6x3 ft' or '6 x 3 ft'
    - '6x3x2.5 ft' or '72x36x1.5 inches'
    - '6ft x 3ft' or '6 ft by 3 ft'
    - '8x4' or '72 x 36'
    """
    clean = dim_str.lower().strip()
    # Normalize 'by' to 'x'
    clean = re.sub(r"\s+by\s+", "x", clean)
    clean = re.sub(r"\s*x\s*", "x", clean)

    is_explicit_feet = "ft" in clean or "feet" in clean or "'" in clean
    is_explicit_inches = "in" in clean or "inch" in clean or '"' in clean

    # Strip everything except numbers, decimal point, and 'x'
    num_str = re.sub(r"[^0-9.xX]", "", clean).strip()
    parts = [p.strip() for p in re.split(r"[xX]", num_str) if p.strip()]

    numbers = []
    for p in parts:
        try:
            numbers.append(float(p))
        except ValueError:
            continue

    if not numbers:
        # Fallback default: 6ft x 3ft table (72 in x 36 in x 1.5 in)
        return {"length_in": 72.0, "width_in": 36.0, "thickness_in": 1.5, "unit_detected": "default (6x3 ft)"}

    # Determine default unit
    if is_explicit_feet:
        unit = "feet"
    elif is_explicit_inches:
        unit = "inches"
    else:
        # If numbers are small (< 15), assume feet. Otherwise inches.
        unit = "feet" if max(numbers[:2]) < 15.0 else "inches"

    if len(numbers) == 1:
        # Square surface (e.g., '4 ft')
        l = numbers[0]
        w = numbers[0]
        t = 1.5 if unit == "feet" else 1.5
    elif len(numbers) == 2:
        l = numbers[0]
        w = numbers[1]
        t = 1.5  # standard 1.5 inch furniture top
    else:
        l = numbers[0]
        w = numbers[1]
        t = numbers[2]

    # Convert to inches
    if unit == "feet":
        l_in = l * 12.0
        w_in = w * 12.0
        # If thickness was part of feet string but < 5, treat thickness as inches
        t_in = t if t < 5.0 else t * 12.0
    else:
        l_in = l
        w_in = w
        t_in = t

    # Ensure length >= width
    if l_in < w_in:
        l_in, w_in = w_in, l_in

    return {
        "length_in": round(l_in, 2),
        "width_in": round(w_in, 2),
        "thickness_in": round(t_in, 2),
        "unit_detected": unit,
    }


def calculate_material_needs(dimensions: str, wood_type: str) -> Dict[str, Any]:
    """Computes board feet, square footage, cutting waste (15%), and estimated costs.

    Args:
        dimensions: Dimensions description, e.g. "6x3 ft", "6x3x1.5", "72x36 inches".
        wood_type: Timber or plywood type, e.g. "teak", "sheesham", "oak", "marine ply".

    Returns:
        Structured dictionary with board feet, square footage, waste, and INR cost estimates.
    """
    parsed = _parse_dimensions(dimensions)
    l_in = parsed["length_in"]
    w_in = parsed["width_in"]
    t_in = parsed["thickness_in"]

    # Calculate net board feet: (L in * W in * T in) / 144
    net_board_feet = (l_in * w_in * t_in) / 144.0

    # Calculate square footage: (L ft * W ft)
    l_ft = l_in / 12.0
    w_ft = w_in / 12.0
    square_feet = l_ft * w_ft

    # 15% Standard Craftsman Waste Allowance (for end-checking, knots, saw kerf & grain matching)
    waste_percentage = 15.0
    waste_multiplier = 1.0 + (waste_percentage / 100.0)
    gross_board_feet = net_board_feet * waste_multiplier
    gross_square_feet = square_feet * waste_multiplier

    # Match wood rate
    wood_clean = wood_type.lower().strip()
    rate = WOOD_RATES_PER_BOARD_FOOT.get("teak", 420.0)
    matched_wood = "Teak (Sagwan)"
    for key, val in WOOD_RATES_PER_BOARD_FOOT.items():
        if key in wood_clean:
            rate = val
            matched_wood = key.title()
            break

    estimated_lumber_cost = gross_board_feet * rate

    # Hardware, adhesive & 4-coat PU polish allowance (~25% of timber or minimum ₹2,500)
    hardware_finish_cost = max(2500.0, estimated_lumber_cost * 0.25)
    total_estimated_budget = estimated_lumber_cost + hardware_finish_cost

    # Estimate standard lumber planks needed (assuming standard 2" x 6" x 8' = 8 bd.ft plank)
    standard_plank_bdft = 8.0
    planks_needed = math.ceil(gross_board_feet / standard_plank_bdft)

    return {
        "status": "success",
        "wood_type": matched_wood,
        "input_dimensions": dimensions,
        "normalized_dimensions": f"{l_ft:.1f} ft x {w_ft:.1f} ft x {t_in:.1f} inch",
        "dimensions_in_inches": {
            "length_in": l_in,
            "width_in": w_in,
            "thickness_in": t_in,
        },
        "square_feet_net": round(square_feet, 2),
        "square_feet_with_waste": round(gross_square_feet, 2),
        "board_feet_net": round(net_board_feet, 2),
        "cutting_waste_allowance": f"{waste_percentage:.0f}%",
        "board_feet_required": round(gross_board_feet, 2),
        "estimated_planks_needed": f"{planks_needed} planks (standard 2\"x6\"x8')",
        "rate_per_board_foot_inr": f"₹{rate:,.0f}",
        "estimated_raw_timber_cost_inr": f"₹{estimated_lumber_cost:,.0f}",
        "estimated_hardware_finish_cost_inr": f"₹{hardware_finish_cost:,.0f}",
        "total_estimated_material_budget_inr": f"₹{total_estimated_budget:,.0f}",
        "summary": (
            f"For {dimensions} in {matched_wood}: Net board feet is {net_board_feet:.1f} bd.ft. "
            f"With 15% cutting allowance, you require {gross_board_feet:.1f} bd.ft (~{planks_needed} standard planks). "
            f"Estimated raw timber cost is ₹{estimated_lumber_cost:,.0f} (@ ₹{rate:.0f}/bd.ft), "
            f"plus ~₹{hardware_finish_cost:,.0f} for adhesive, fasteners & PU finish (Total: ~₹{total_estimated_budget:,.0f})."
        ),
    }


def check_inventory_stock(item_name: str) -> Dict[str, Any]:
    """Checks simulated local stock, quantity available, and workshop bay location.

    Args:
        item_name: Item to check (e.g. 'teak', 'sheesham', 'marine ply', 'hinges', 'fevicol').

    Returns:
        Structured dictionary with in_stock status, quantity, location, and procurement lead time.
    """
    clean_query = item_name.lower().strip()

    # Search catalogue
    best_match: Optional[Dict[str, Any]] = None
    stop_words = {"wood", "lumber", "grade", "item", "stock", "pack", "available", "material", "check", "the", "for", "pieces", "unit"}
    query_tokens = [w for w in re.findall(r"\b[a-zA-Z0-9]+\b", clean_query) if w not in stop_words and len(w) > 2]

    # 1. Exact key substring match
    for key, data in WORKSHOP_INVENTORY.items():
        if key in clean_query:
            best_match = data
            break

    # 2. Token match on distinctive words
    if not best_match and query_tokens:
        for key, data in WORKSHOP_INVENTORY.items():
            if any(tok in key for tok in query_tokens):
                best_match = data
                break

    if best_match:
        return {
            "status": "success",
            "query": item_name,
            "matched_item": best_match["item_name"],
            "category": best_match["category"],
            "in_stock": best_match["in_stock"],
            "quantity_available": f"{best_match['quantity_available']} {best_match['unit']}",
            "unit_price_inr": f"₹{best_match['unit_price_inr']:,.0f} per {best_match['unit'].split()[0]}",
            "warehouse_location": best_match["warehouse_location"],
            "lead_time_days": best_match["lead_time_days"],
            "grade": best_match["grade"],
            "craftsman_notes": best_match["notes"],
            "availability_summary": (
                f"✅ IN STOCK: {best_match['item_name']} ({best_match['quantity_available']} {best_match['unit']} "
                f"available at {best_match['warehouse_location']}). Immediate dispatch/cutting ready."
                if best_match["in_stock"]
                else f"⚠️ OUT OF STOCK: {best_match['item_name']}. {best_match['notes']} (Lead time: {best_match['lead_time_days']} days)."
            ),
        }

    # Not found in local catalogue
    return {
        "status": "not_found",
        "query": item_name,
        "in_stock": False,
        "quantity_available": "0 units",
        "warehouse_location": "External Distributor / Mill",
        "lead_time_days": 3,
        "availability_summary": (
            f"ℹ️ Item '{item_name}' is not currently in local shop inventory. "
            f"Can be procured from our certified timber distributor within 2-3 working days."
        ),
    }


def get_joinery_specs(joint_type: str) -> str:
    """Returns hardware, screw gauge, adhesive specifications, and glue-curing guidelines.

    Args:
        joint_type: Joint method, e.g. 'mortise and tenon', 'pocket hole', 'dovetail', 'dowel', 'mitre'.

    Returns:
        Detailed craftsman engineering and joinery specification string.
    """
    clean = joint_type.lower().strip()

    # Match joinery
    for key, spec in JOINERY_SPECIFICATIONS.items():
        if key in clean or clean in key or any(k in clean for k in key.split()):
            return (
                f"🪚 **JOINERY SPECIFICATION: {spec['name']}**\n\n"
                f"• **Best Application**: {spec['application']}\n"
                f"• **Proportions & Tolerances**: {spec['proportions']}\n"
                f"• **Hardware & Fasteners**: {spec['hardware_and_fasteners']}\n"
                f"• **Adhesive Specs**: {spec['adhesive_specs']}\n"
                f"• **Clamping & Cure Time**: {spec['clamping_and_curing']}\n"
                f"• **Master Craftsman Tip**: {spec['master_craftsman_tip']}"
            )

    # Generic comprehensive joinery guide
    return (
        f"🪚 **MASTER CARPENTER JOINERY RECOMMENDATIONS FOR '{joint_type.title()}'**\n\n"
        f"• **For Load-Bearing Frames (Tables, Beds, Chairs)**: Use *Mortise and Tenon* joints with 1/3 timber thickness tenon and 3/8\" drawbore dowel pins.\n"
        f"• **For Cabinet Carcasses & Face Frames**: Use *Pocket Hole Joinery* with #8 1-1/4\" coarse washer-head screws and PVA glue.\n"
        f"• **For Heirloom Drawers**: Use *Through or Half-Blind Dovetails* (1:8 slope for hardwoods) with PVA or Hide Glue.\n"
        f"• **Adhesive Standard**: Always use EN 204 D3 waterproof PVA adhesive (e.g. Fevicol Marine). Clamp at 80-100 PSI for minimum 60 mins; full cure in 24 hours."
    )
