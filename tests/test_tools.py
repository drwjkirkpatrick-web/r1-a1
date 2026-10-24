"""Tests for the tool bay module. Pure logic, no hardware.

Run: python -m unittest tests.test_tools -v
  or: python -m pytest tests/test_tools.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tools import Tool, ToolBay, ToolType                      # noqa: E402
from tools.bay import RESERVE_CHARGE_PCT, STEP_CHARGE_PCT      # noqa: E402
from tools.tool import (                                       # noqa: E402
    MIN_OPERATIONAL_CONDITION_PCT,
    WEAR_PER_CHARGE,
)


def make_tool(tool_type=ToolType.ARC_WELDER, charge=100.0, condition=100.0,
              weight=2.0, subsystems=("hull", "propulsion")):
    return Tool(
        tool_type=tool_type,
        weight_kg=weight,
        required_subsystems=tuple(subsystems),
        charge_pct=charge,
        condition_pct=condition,
    )


class TestToolValidation(unittest.TestCase):
    def test_valid_construction(self):
        t = make_tool(charge=55.0, condition=70.0)
        self.assertEqual(t.tool_type, ToolType.ARC_WELDER)
        self.assertEqual(t.charge_pct, 55.0)
        self.assertEqual(t.condition_pct, 70.0)
        self.assertEqual(t.weight_kg, 2.0)

    def test_tool_type_accepts_value_string(self):
        t = make_tool(tool_type="scomp_link")
        self.assertEqual(t.tool_type, ToolType.SCOMP_LINK)

    def test_bad_tool_type_raises(self):
        with self.assertRaises(ValueError):
            make_tool(tool_type="lightsaber")
        with self.assertRaises(ValueError):
            make_tool(tool_type=42)

    def test_charge_out_of_range_raises(self):
        for bad in (-0.1, 100.1):
            with self.assertRaises(ValueError, msg=f"charge={bad}"):
                make_tool(charge=bad)

    def test_condition_out_of_range_raises(self):
        for bad in (-1.0, 101.0):
            with self.assertRaises(ValueError, msg=f"condition={bad}"):
                make_tool(condition=bad)

    def test_non_positive_weight_raises(self):
        for bad in (0.0, -3.5):
            with self.assertRaises(ValueError):
                make_tool(weight=bad)

    def test_empty_subsystems_raises(self):
        with self.assertRaises(ValueError):
            make_tool(subsystems=())

    def test_unknown_subsystem_raises(self):
        with self.assertRaises(ValueError):
            make_tool(subsystems=("hull", "hyperdrive_flux"))


class TestToolUseAndCare(unittest.TestCase):
    def test_use_consumes_charge_and_wears_condition(self):
        t = make_tool()
        t.use(10.0)
        self.assertAlmostEqual(t.charge_pct, 90.0)
        self.assertAlmostEqual(t.condition_pct, 100.0 - 10.0 * WEAR_PER_CHARGE)

    def test_use_clamps_at_zero(self):
        t = make_tool(charge=5.0, condition=3.0)
        t.use(50.0)
        self.assertEqual(t.charge_pct, 0.0)
        self.assertEqual(t.condition_pct, 0.0)

    def test_use_rejects_non_positive_amount(self):
        t = make_tool()
        for bad in (0.0, -5.0):
            with self.assertRaises(ValueError):
                t.use(bad)

    def test_recharge_restores_charge_only(self):
        t = make_tool(charge=20.0, condition=60.0)
        t.recharge()
        self.assertEqual(t.charge_pct, 100.0)
        self.assertEqual(t.condition_pct, 60.0)

    def test_maintenance_restores_condition_only(self):
        t = make_tool(charge=20.0, condition=60.0)
        t.maintenance()
        self.assertEqual(t.condition_pct, 100.0)
        self.assertEqual(t.charge_pct, 20.0)

    def test_operational_thresholds(self):
        self.assertFalse(make_tool(charge=0.0).is_operational())
        self.assertFalse(
            make_tool(condition=MIN_OPERATIONAL_CONDITION_PCT).is_operational()
        )
        self.assertTrue(
            make_tool(charge=0.1,
                      condition=MIN_OPERATIONAL_CONDITION_PCT + 0.1).is_operational()
        )

    def test_tool_serialization_round_trip(self):
        t = make_tool(charge=42.5, condition=88.0)
        t2 = Tool.from_dict(t.to_dict())
        self.assertEqual(t2.tool_type, t.tool_type)
        self.assertEqual(t2.charge_pct, t.charge_pct)
        self.assertEqual(t2.condition_pct, t.condition_pct)
        self.assertEqual(t2.weight_kg, t.weight_kg)
        self.assertEqual(t2.required_subsystems, t.required_subsystems)

    def test_tool_from_dict_missing_field_raises(self):
        with self.assertRaises(ValueError):
            Tool.from_dict({"tool_type": "arc_welder"})


class TestToolBayRack(unittest.TestCase):
    def test_bay_rejects_non_positive_weight_limit(self):
        with self.assertRaises(ValueError):
            ToolBay(max_weight_kg=0.0)

    def test_add_and_weight_accounting(self):
        bay = ToolBay(max_weight_kg=10.0)
        bay.add_tool(make_tool(weight=2.5))
        bay.add_tool(make_tool(ToolType.SCOMP_LINK, weight=1.0))
        self.assertAlmostEqual(bay.current_weight_kg(), 3.5)
        self.assertEqual(len(bay.tools()), 2)

    def test_add_rejects_non_tool(self):
        bay = ToolBay(max_weight_kg=10.0)
        with self.assertRaises(ValueError):
            bay.add_tool("not a tool")

    def test_duplicate_tool_type_rejected(self):
        bay = ToolBay(max_weight_kg=10.0)
        bay.add_tool(make_tool(weight=1.0))
        with self.assertRaises(ValueError):
            bay.add_tool(make_tool(weight=1.0))

    def test_weight_limit_enforced(self):
        bay = ToolBay(max_weight_kg=3.0)
        bay.add_tool(make_tool(weight=2.0))
        with self.assertRaises(ValueError):
            bay.add_tool(make_tool(ToolType.FUSION_CUTTER, weight=1.5))
        # exactly at the limit is fine
        bay.add_tool(make_tool(ToolType.FUSION_CUTTER, weight=1.0))
        self.assertAlmostEqual(bay.current_weight_kg(), 3.0)

    def test_remove_tool(self):
        bay = ToolBay(max_weight_kg=10.0)
        bay.add_tool(make_tool())
        removed = bay.remove_tool(ToolType.ARC_WELDER)
        self.assertIsInstance(removed, Tool)
        self.assertEqual(len(bay.tools()), 0)

    def test_remove_accepts_value_string(self):
        bay = ToolBay(max_weight_kg=10.0)
        bay.add_tool(make_tool())
        self.assertEqual(bay.remove_tool("arc_welder").tool_type,
                         ToolType.ARC_WELDER)

    def test_remove_missing_raises(self):
        bay = ToolBay(max_weight_kg=10.0)
        with self.assertRaises(ValueError):
            bay.remove_tool(ToolType.HOLORECORDER)
        with self.assertRaises(ValueError):
            bay.remove_tool("lightsaber")


class TestToolSelection(unittest.TestCase):
    def make_bay(self):
        bay = ToolBay(max_weight_kg=20.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, charge=80.0, condition=90.0))
        bay.add_tool(make_tool(ToolType.FUSION_CUTTER, charge=80.0, condition=95.0))
        bay.add_tool(make_tool(ToolType.SCOMP_LINK, charge=80.0, condition=70.0,
                               subsystems=("avionics",)))
        return bay

    def test_prefers_higher_condition(self):
        bay = self.make_bay()
        pick = bay.select_tool("hull")
        self.assertEqual(pick.tool_type, ToolType.FUSION_CUTTER)

    def test_ties_break_on_charge(self):
        bay = ToolBay(max_weight_kg=20.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, charge=50.0, condition=90.0))
        bay.add_tool(make_tool(ToolType.FUSION_CUTTER, charge=80.0, condition=90.0))
        self.assertEqual(bay.select_tool("hull").tool_type,
                         ToolType.FUSION_CUTTER)

    def test_unknown_subsystem_raises(self):
        bay = self.make_bay()
        with self.assertRaises(ValueError):
            bay.select_tool("hyperdrive_flux")

    def test_no_suitable_tool_returns_none(self):
        bay = self.make_bay()
        self.assertIsNone(bay.select_tool("life_support"))

    def test_worn_tool_skipped(self):
        bay = ToolBay(max_weight_kg=20.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, condition=90.0))
        bay.add_tool(make_tool(ToolType.FUSION_CUTTER,
                               condition=MIN_OPERATIONAL_CONDITION_PCT))
        self.assertEqual(bay.select_tool("hull").tool_type, ToolType.ARC_WELDER)

    def test_urgency_relaxes_charge_threshold(self):
        bay = ToolBay(max_weight_kg=20.0)
        # charge above 0 but below the routine reserve
        bay.add_tool(make_tool(ToolType.ARC_WELDER,
                               charge=RESERVE_CHARGE_PCT - 1.0))
        self.assertIsNone(bay.select_tool("hull", urgency=0.0))
        pick = bay.select_tool("hull", urgency=1.0)
        self.assertEqual(pick.tool_type, ToolType.ARC_WELDER)

    def test_urgency_still_requires_operational(self):
        bay = ToolBay(max_weight_kg=20.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, charge=0.0))
        self.assertIsNone(bay.select_tool("hull", urgency=1.0))

    def test_invalid_urgency_raises(self):
        bay = self.make_bay()
        for bad in (-0.1, 1.1):
            with self.assertRaises(ValueError):
                bay.select_tool("hull", urgency=bad)


class TestServicePlan(unittest.TestCase):
    def test_single_tool_covers_short_plan(self):
        bay = ToolBay(max_weight_kg=20.0)
        welder = make_tool(ToolType.ARC_WELDER, charge=50.0, condition=90.0)
        bay.add_tool(welder)
        plan = bay.service_plan("hull", 3)
        self.assertEqual(plan, [welder] * 3)

    def test_plan_rolls_to_backup_tool(self):
        bay = ToolBay(max_weight_kg=20.0)
        primary = make_tool(ToolType.ARC_WELDER, charge=20.0, condition=95.0)
        backup = make_tool(ToolType.FUSION_CUTTER, charge=60.0, condition=80.0)
        bay.add_tool(primary)
        bay.add_tool(backup)
        # primary covers (20 - 10) / 5 = 2 steps, backup takes the rest
        plan = bay.service_plan("hull", 4)
        self.assertEqual(plan, [primary, primary, backup, backup])

    def test_plan_insufficient_capacity_raises(self):
        bay = ToolBay(max_weight_kg=20.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, charge=15.0))
        with self.assertRaises(ValueError):
            bay.service_plan("hull", 5)

    def test_plan_ignores_worn_or_wrong_tools(self):
        bay = ToolBay(max_weight_kg=20.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, charge=50.0, condition=90.0))
        bay.add_tool(make_tool(ToolType.FUSION_CUTTER, condition=10.0))
        bay.add_tool(make_tool(ToolType.SCOMP_LINK, subsystems=("avionics",)))
        plan = bay.service_plan("hull", 2)
        self.assertTrue(all(t.tool_type is ToolType.ARC_WELDER for t in plan))

    def test_plan_does_not_mutate_tools(self):
        bay = ToolBay(max_weight_kg=20.0)
        welder = make_tool(ToolType.ARC_WELDER, charge=50.0)
        bay.add_tool(welder)
        bay.service_plan("hull", 3)
        self.assertEqual(welder.charge_pct, 50.0)

    def test_invalid_steps_raise(self):
        bay = ToolBay(max_weight_kg=20.0)
        for bad in (0, -2, 1.5):
            with self.assertRaises(ValueError):
                bay.service_plan("hull", bad)


class TestBayReporting(unittest.TestCase):
    def test_bay_status_report(self):
        bay = ToolBay(max_weight_kg=12.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, weight=2.0, charge=0.0))
        bay.add_tool(make_tool(ToolType.SCOMP_LINK, weight=1.0,
                               subsystems=("avionics",)))
        status = bay.bay_status()
        self.assertEqual(status["max_weight_kg"], 12.0)
        self.assertAlmostEqual(status["current_weight_kg"], 3.0)
        self.assertEqual(status["tool_count"], 2)
        self.assertEqual(status["operational_count"], 1)
        self.assertEqual(len(status["tools"]), 2)

    def test_bay_serialization_round_trip(self):
        bay = ToolBay(max_weight_kg=15.0)
        bay.add_tool(make_tool(ToolType.ARC_WELDER, weight=2.0, charge=33.0))
        bay.add_tool(make_tool(ToolType.DIAGNOSTIC_PROBE, weight=0.5,
                               condition=44.0, subsystems=("avionics", "power")))
        clone = ToolBay.from_dict(bay.to_dict())
        self.assertEqual(clone.max_weight_kg, bay.max_weight_kg)
        self.assertEqual(clone.bay_status()["tools"], bay.bay_status()["tools"])

    def test_bay_from_dict_missing_field_raises(self):
        with self.assertRaises(ValueError):
            ToolBay.from_dict({"tools": []})

    def test_bay_from_dict_enforces_weight_limit(self):
        bay = ToolBay(max_weight_kg=2.0)
        bay.add_tool(make_tool(weight=1.5))
        data = bay.to_dict()
        data["max_weight_kg"] = 1.0  # forged payload: tool no longer fits
        with self.assertRaises(ValueError):
            ToolBay.from_dict(data)


if __name__ == "__main__":
    unittest.main()
