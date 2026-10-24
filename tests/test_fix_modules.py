"""Regression tests for code-review findings in the new modules.

Covers:
  F5  safety/response.py  — hazards that drop below their reporting
      threshold must still be tracked so they can clear (hysteresis
      compares against a peak that used to go unrecorded).
  F8  loyalty/bond.py     — neglect decay must be persisted: one
      interaction must not undo all accumulated decay.
  F15 tools/tool.py       — VALID_SUBSYSTEMS must cover every repair
      registry category, including "communications".

Run: python -m pytest tests/test_fix_modules.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loyalty import BondEngine                                # noqa: E402
from loyalty.bond import SECONDS_PER_DAY                      # noqa: E402
from repair.registry import SUBSYSTEM_CATEGORIES              # noqa: E402
from safety import Hazard, HazardType, SafetyController       # noqa: E402
from tools import Tool, ToolBay, ToolType                     # noqa: E402
from tools.tool import VALID_SUBSYSTEMS                       # noqa: E402


def make_hazard(htype=HazardType.SMOKE, severity=5, source="bay",
                hazard_id=None):
    return Hazard(htype, severity, source,
                  hazard_id=hazard_id, time_fn=lambda: 1000.0)


def make_engine(now=1_000_000.0, decay_per_day=1.0):
    """BondEngine on a controllable clock. Returns (engine, advance_days)."""
    clock = {"now": now}

    def advance(days):
        clock["now"] += days * SECONDS_PER_DAY

    engine = BondEngine(time_fn=lambda: clock["now"], decay_per_day=decay_per_day)
    return engine, advance


class TestSafetyThresholdClearRegression(unittest.TestCase):
    """F5: a hazard that subsides below its threshold must still clear."""

    def test_below_threshold_hazard_can_clear(self):
        ctl = SafetyController(thresholds={"smoke": 4})
        hz = make_hazard(HazardType.SMOKE, 9, hazard_id="h1")
        plan = ctl.evaluate([hz])
        self.assertTrue(plan)  # active: peak 9 registered
        # Smoke subsides under the reporting threshold: no plan actions,
        # but the tracked severity must refresh so hysteresis can pass.
        hz.set_severity(2)
        self.assertEqual(ctl.evaluate([hz]), [])
        self.assertTrue(ctl.clear("h1"))
        self.assertNotIn(
            "h1", {h["hazard_id"] for h in ctl.status_report()["active"]}
        )

    def test_below_threshold_evaluation_refreshes_tracked_severity(self):
        ctl = SafetyController(thresholds={"smoke": 4})
        hz = make_hazard(HazardType.SMOKE, 9, hazard_id="h1")
        ctl.evaluate([hz])
        hz.set_severity(2)
        ctl.evaluate([hz])
        entry = {h["hazard_id"]: h for h in ctl.status_report()["active"]}["h1"]
        self.assertEqual(entry["severity"], 2)       # refreshed, not stuck at 9
        self.assertEqual(entry["peak_severity"], 9)  # peak preserved

    def test_hysteresis_still_blocks_clear_near_peak(self):
        # Registering below-threshold hazards must not weaken hysteresis:
        # a drop *within* CLEAR_HYSTERESIS of the peak still refuses.
        ctl = SafetyController(thresholds={"smoke": 4})
        hz = make_hazard(HazardType.SMOKE, 9, hazard_id="h1")
        ctl.evaluate([hz])
        hz.set_severity(8)  # above threshold, within 2 of peak
        ctl.evaluate([hz])
        self.assertFalse(ctl.clear("h1"))
        hz.set_severity(3)  # below threshold AND decisively below peak
        ctl.evaluate([hz])
        self.assertTrue(ctl.clear("h1"))

    def test_never_active_hazard_is_still_tracked(self):
        # A hazard first seen below its threshold registers (severity 1,
        # peak 1) and clears immediately once acknowledged as resolved.
        ctl = SafetyController(thresholds={"smoke": 5})
        hz = make_hazard(HazardType.SMOKE, 2, hazard_id="h1")
        self.assertEqual(ctl.evaluate([hz]), [])
        self.assertIn(
            "h1", {h["hazard_id"] for h in ctl.status_report()["active"]}
        )


class TestBondDecayPersistenceRegression(unittest.TestCase):
    """F8: decay is materialized at interaction time, never erased."""

    def test_interaction_does_not_reset_accumulated_decay(self):
        engine, advance = make_engine()
        engine.record_interaction("luke", points=50.0)
        advance(10)  # 10 days of silence: effective score is 40
        returned = engine.record_interaction("luke", points=2.0)
        # Decay must survive: 50 - 10 + 2 = 42, not the buggy 52.
        self.assertAlmostEqual(returned, 42.0)
        self.assertAlmostEqual(engine.score("luke"), 42.0)

    def test_decay_continues_from_materialized_score(self):
        engine, advance = make_engine()
        engine.record_interaction("luke", points=50.0)
        advance(10)
        engine.record_interaction("luke", points=2.0)  # materializes 42
        advance(5)  # decay resumes from the new stamp: 42 - 5
        self.assertAlmostEqual(engine.score("luke"), 37.0)

    def test_deep_neglect_interaction_climbs_from_floor(self):
        engine, advance = make_engine()
        engine.record_interaction("luke", points=30.0)
        advance(60)  # fully decayed: effective 0
        engine.record_interaction("luke", points=5.0)
        self.assertAlmostEqual(engine.score("luke"), 5.0)

    def test_first_interaction_unaffected(self):
        # No prior stamp -> no decay to fold in; behavior unchanged.
        engine, _ = make_engine()
        self.assertAlmostEqual(engine.record_interaction("luke", points=10.0), 10.0)
        self.assertAlmostEqual(engine.score("luke"), 10.0)


class TestToolsCommunicationsRegression(unittest.TestCase):
    """F15: tools must accept every repair-registry subsystem category."""

    def test_valid_subsystems_matches_registry_categories(self):
        self.assertEqual(set(VALID_SUBSYSTEMS), set(SUBSYSTEM_CATEGORIES))
        self.assertIn("communications", VALID_SUBSYSTEMS)
        self.assertEqual(len(VALID_SUBSYSTEMS), 9)

    def test_communications_tool_constructs(self):
        tool = Tool(
            tool_type=ToolType.SCOMP_LINK,
            weight_kg=1.0,
            required_subsystems=("communications", "avionics"),
        )
        self.assertTrue(tool.services("communications"))

    def test_communications_tool_selection_works(self):
        bay = ToolBay(max_weight_kg=10.0)
        scomp = Tool(
            tool_type=ToolType.SCOMP_LINK,
            weight_kg=1.0,
            required_subsystems=("communications",),
            charge_pct=80.0,
            condition_pct=90.0,
        )
        bay.add_tool(scomp)
        self.assertIs(bay.select_tool("communications"), scomp)
        plan = bay.service_plan("communications", 2)
        self.assertEqual(plan, [scomp, scomp])


if __name__ == "__main__":
    unittest.main()
