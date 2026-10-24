"""Tests for the safety subsystem (hazard assessment + response). No hardware.

Run: python -m unittest tests.test_safety -v
  or: python -m pytest tests/test_safety.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from safety import Hazard, HazardType, SafetyController          # noqa: E402
from safety.response import CLEAR_HYSTERESIS                     # noqa: E402


def make_hazard(htype=HazardType.OBSTRUCTION, severity=5, source="test",
                hazard_id=None, first_seen=1000.0):
    return Hazard(htype, severity, source,
                  hazard_id=hazard_id, time_fn=lambda: first_seen)


class TestHazardConstruction(unittest.TestCase):
    def test_severity_bounds_validated(self):
        for bad in (0, -1, 11, 100):
            with self.assertRaises(ValueError, msg=f"severity={bad}"):
                make_hazard(severity=bad)
        for good in (1, 5, 10):
            self.assertEqual(make_hazard(severity=good).severity, good)

    def test_severity_rejects_non_numeric(self):
        for bad in ("5", None, True, [5]):
            with self.assertRaises(ValueError, msg=f"severity={bad!r}"):
                make_hazard(severity=bad)

    def test_unknown_hazard_type_raises(self):
        with self.assertRaises(ValueError):
            make_hazard(htype="alien_contact")

    def test_string_type_coerced_to_enum(self):
        self.assertIs(make_hazard(htype="fire").hazard_type, HazardType.FIRE)

    def test_source_must_be_non_empty(self):
        for bad in ("", None, 42):
            with self.assertRaises(ValueError, msg=f"source={bad!r}"):
                make_hazard(source=bad)

    def test_first_seen_uses_injected_clock(self):
        hz = make_hazard(first_seen=4242.5)
        self.assertEqual(hz.first_seen, 4242.5)

    def test_default_hazard_id_is_type_and_source(self):
        hz = make_hazard(HazardType.SMOKE, 6, "bay")
        self.assertEqual(hz.hazard_id, "smoke:bay")


class TestEscalation(unittest.TestCase):
    def test_escalation_thresholds(self):
        cases = {1: 1, 3: 1, 4: 2, 6: 2, 7: 3, 8: 3, 9: 4, 10: 4}
        for severity, level in cases.items():
            hz = make_hazard(severity=severity)
            self.assertEqual(hz.escalation(), level, f"severity={severity}")

    def test_escalation_names(self):
        names = {3: "watch", 5: "warn", 7: "alert", 10: "emergency"}
        for severity, name in names.items():
            self.assertEqual(make_hazard(severity=severity).escalation_name(), name)

    def test_auto_resolvable(self):
        self.assertTrue(make_hazard(HazardType.OBSTRUCTION).auto_resolvable())
        self.assertTrue(make_hazard(HazardType.COLLISION_IMMINENT).auto_resolvable())
        for htype in (HazardType.FIRE, HazardType.SMOKE,
                      HazardType.THERMAL_RUNAWAY, HazardType.TIP_OVER,
                      HazardType.BATTERY_CRITICAL):
            self.assertFalse(make_hazard(htype).auto_resolvable(), htype)


class TestResponsePlan(unittest.TestCase):
    def test_watch_level_produces_no_actions(self):
        ctl = SafetyController()
        plan = ctl.evaluate([make_hazard(severity=2)])
        self.assertEqual(plan, [])

    def test_warn_alerts_operator(self):
        ctl = SafetyController()
        plan = ctl.evaluate([make_hazard(severity=5)])
        self.assertEqual([a["action"] for a in plan], ["alert_operator"])

    def test_alert_stops_drive(self):
        ctl = SafetyController()
        plan = ctl.evaluate([make_hazard(severity=8)])
        self.assertEqual([a["action"] for a in plan],
                         ["alert_operator", "stop_drive"])

    def test_emergency_action_set_gated_at_level_4(self):
        ctl = SafetyController()
        # level 3 fire: no extinguisher, no seal, no distress
        plan3 = ctl.evaluate([make_hazard(HazardType.FIRE, 8, "bay")])
        actions3 = {a["action"] for a in plan3}
        self.assertNotIn("deploy_extinguisher", actions3)
        self.assertNotIn("seal_power", actions3)
        self.assertNotIn("broadcast_distress", actions3)
        # level 4 fire: full set including the bottle
        ctl2 = SafetyController()
        plan4 = ctl2.evaluate([make_hazard(HazardType.FIRE, 9, "bay")])
        actions4 = {a["action"] for a in plan4}
        self.assertEqual(actions4, {"alert_operator", "stop_drive", "seal_power",
                                    "broadcast_distress", "deploy_extinguisher"})

    def test_extinguisher_only_for_incendiary_hazards(self):
        ctl = SafetyController()
        plan = ctl.evaluate([make_hazard(HazardType.TIP_OVER, 10, "imu")])
        self.assertNotIn("deploy_extinguisher", {a["action"] for a in plan})

    def test_plan_ordered_most_urgent_first(self):
        ctl = SafetyController()
        hazards = [
            make_hazard(HazardType.OBSTRUCTION, 5, "sonar", hazard_id="h1"),
            make_hazard(HazardType.FIRE, 9, "bay", hazard_id="h2"),
            make_hazard(HazardType.SMOKE, 7, "bay", hazard_id="h3"),
        ]
        plan = ctl.evaluate(hazards)
        levels = [a["escalation"] for a in plan]
        self.assertEqual(levels, sorted(levels, reverse=True))
        self.assertEqual(plan[0]["hazard_id"], "h2")  # the fire leads

    def test_threshold_config_filters_low_severity(self):
        ctl = SafetyController(thresholds={"smoke": 4})
        plan = ctl.evaluate([make_hazard(HazardType.SMOKE, 3, "bay")])
        self.assertEqual(plan, [])
        plan = ctl.evaluate([make_hazard(HazardType.SMOKE, 4, "bay")])
        self.assertTrue(plan)

    def test_bad_threshold_config_raises(self):
        with self.assertRaises(ValueError):
            SafetyController(thresholds={"smoke": 0})
        with self.assertRaises(ValueError):
            SafetyController(thresholds={"not_a_hazard": 5})


class TestInterlocks(unittest.TestCase):
    def setUp(self):
        self.ctl = SafetyController()

    def test_nominal_all_systems_safe(self):
        self.assertTrue(self.ctl.interlock("drive", []))
        self.assertTrue(self.ctl.interlock("charge", []))
        self.assertTrue(self.ctl.interlock("projector", []))
        self.assertTrue(self.ctl.interlock("welder", []))

    def test_drive_blocked_by_obstruction_at_any_severity(self):
        hz = make_hazard(HazardType.OBSTRUCTION, 2, "sonar")
        self.assertFalse(self.ctl.interlock("drive", [hz]))

    def test_drive_blocked_by_any_level3_hazard(self):
        hz = make_hazard(HazardType.SMOKE, 7, "bay")
        self.assertFalse(self.ctl.interlock("drive", [hz]))

    def test_charge_blocked_by_battery_critical(self):
        hz = make_hazard(HazardType.BATTERY_CRITICAL, 3, "power")
        self.assertFalse(self.ctl.interlock("charge", [hz]))

    def test_charge_ok_with_low_level_non_battery_hazard(self):
        hz = make_hazard(HazardType.OBSTRUCTION, 5, "sonar")
        self.assertTrue(self.ctl.interlock("charge", [hz]))

    def test_projector_blocked_by_thermal_runaway(self):
        hz = make_hazard(HazardType.THERMAL_RUNAWAY, 2, "bay")
        self.assertFalse(self.ctl.interlock("projector", [hz]))

    def test_projector_blocked_at_level_4(self):
        hz = make_hazard(HazardType.OBSTRUCTION, 10, "sonar")
        self.assertFalse(self.ctl.interlock("projector", [hz]))

    def test_welder_blocked_by_smoke_and_tip(self):
        for htype in (HazardType.SMOKE, HazardType.TIP_OVER, HazardType.FIRE):
            hz = make_hazard(htype, 2, "test")
            self.assertFalse(self.ctl.interlock("welder", [hz]), htype)

    def test_below_threshold_hazard_does_not_block(self):
        ctl = SafetyController(thresholds={HazardType.SMOKE: 5})
        hz = make_hazard(HazardType.SMOKE, 4, "bay")
        self.assertTrue(ctl.interlock("welder", [hz]))

    def test_unknown_system_raises(self):
        with self.assertRaises(ValueError):
            self.ctl.interlock("laser_cannon", [])


class TestAcknowledgeClearHysteresis(unittest.TestCase):
    def test_acknowledge_records_bookkeeping(self):
        ctl = SafetyController()
        hz = make_hazard(HazardType.SMOKE, 6, "bay", hazard_id="h1")
        ctl.evaluate([hz])
        ctl.acknowledge("h1")
        self.assertIn("h1", ctl.status_report()["acknowledged"])

    def test_acknowledge_does_not_silence_response(self):
        ctl = SafetyController()
        hz = make_hazard(HazardType.FIRE, 9, "bay", hazard_id="h1")
        ctl.evaluate([hz])
        ctl.acknowledge("h1")
        plan = ctl.evaluate([hz])
        self.assertIn("deploy_extinguisher", {a["action"] for a in plan})

    def test_unknown_ids_raise(self):
        ctl = SafetyController()
        with self.assertRaises(ValueError):
            ctl.acknowledge("nope")
        with self.assertRaises(ValueError):
            ctl.clear("nope")

    def test_hysteresis_blocks_clear_near_peak(self):
        ctl = SafetyController()
        hz = make_hazard(HazardType.SMOKE, 9, "bay", hazard_id="h1")
        ctl.evaluate([hz])
        # drops one point: still within 2 of the peak -> refused
        hz.set_severity(8)
        ctl.evaluate([hz])
        self.assertFalse(ctl.clear("h1"))
        self.assertIn("h1", {h["hazard_id"] for h in ctl.status_report()["active"]})

    def test_hysteresis_allows_clear_after_two_point_drop(self):
        ctl = SafetyController()
        hz = make_hazard(HazardType.SMOKE, 9, "bay", hazard_id="h1")
        ctl.evaluate([hz])
        hz.set_severity(9 - CLEAR_HYSTERESIS)  # exactly peak - 2
        ctl.evaluate([hz])
        self.assertTrue(ctl.clear("h1"))
        self.assertNotIn("h1", {h["hazard_id"] for h in ctl.status_report()["active"]})

    def test_no_flap_on_oscillating_severity(self):
        ctl = SafetyController()
        hz = make_hazard(HazardType.SMOKE, 7, "bay", hazard_id="h1")
        ctl.evaluate([hz])
        # oscillate 6 <-> 7 around the alert/warn boundary; peak stays 7,
        # so every clear attempt is refused — no relay toggling.
        for sev in (6, 7, 6, 7, 6):
            hz.set_severity(sev)
            ctl.evaluate([hz])
            self.assertFalse(ctl.clear("h1"), f"sev={sev}")
        # a decisive fall to 5 (peak 7 - 2) finally clears
        hz.set_severity(5)
        ctl.evaluate([hz])
        self.assertTrue(ctl.clear("h1"))


class TestStatusAndSerialization(unittest.TestCase):
    def test_status_report_counts_and_emergency(self):
        ctl = SafetyController()
        ctl.evaluate([
            make_hazard(HazardType.FIRE, 9, "bay", hazard_id="h1"),
            make_hazard(HazardType.OBSTRUCTION, 5, "sonar", hazard_id="h2"),
        ])
        rep = ctl.status_report()
        self.assertTrue(rep["emergency"])
        self.assertEqual(rep["counts_by_level"][4], 1)
        self.assertEqual(rep["counts_by_level"][2], 1)
        self.assertEqual(rep["active"][0]["hazard_id"], "h1")  # urgent first

    def test_hazard_round_trip(self):
        hz = make_hazard(HazardType.TIP_OVER, 8, "imu", first_seen=123.0)
        hz2 = Hazard.from_dict(hz.to_dict())
        self.assertEqual(hz2.hazard_type, HazardType.TIP_OVER)
        self.assertEqual(hz2.severity, 8)
        self.assertEqual(hz2.source, "imu")
        self.assertEqual(hz2.first_seen, 123.0)
        self.assertEqual(hz2.hazard_id, hz.hazard_id)

    def test_controller_round_trip(self):
        ctl = SafetyController(thresholds={HazardType.SMOKE: 3})
        ctl.evaluate([make_hazard(HazardType.SMOKE, 9, "bay", hazard_id="h1")])
        ctl.acknowledge("h1")
        data = ctl.to_dict()
        ctl2 = SafetyController.from_dict(data)
        self.assertEqual(ctl2.to_dict(), data)
        rep = ctl2.status_report()
        self.assertEqual(rep["active"][0]["peak_severity"], 9)
        self.assertIn("h1", rep["acknowledged"])
        # hysteresis state survives: severity 9 vs peak 9 -> clear refused
        self.assertFalse(ctl2.clear("h1"))


if __name__ == "__main__":
    unittest.main()
