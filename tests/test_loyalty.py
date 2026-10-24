"""Tests for the loyalty subsystem (operator directory + bond engine).

All time is injected; no real clocks, no I/O.

Run: python -m pytest tests/test_loyalty.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loyalty import (                       # noqa: E402
    BondEngine,
    BondLevel,
    OperatorDirectory,
    OperatorProfile,
)
from loyalty.bond import ALERT_THRESHOLDS, GREETINGS, SCORE_CAP, SECONDS_PER_DAY  # noqa: E402
from loyalty.operator import FAMILIARITY_RATE, ROLES  # noqa: E402


def make_engine(now=1_000_000.0, decay_per_day=1.0):
    """BondEngine on a controllable clock. Returns (engine, advance_days)."""
    clock = {"now": now}

    def advance(days):
        clock["now"] += days * SECONDS_PER_DAY

    engine = BondEngine(time_fn=lambda: clock["now"], decay_per_day=decay_per_day)
    return engine, advance


def make_directory():
    d = OperatorDirectory()
    d.add(OperatorProfile("Luke", role="owner", authorization_level=5))
    d.add(OperatorProfile("Wedge", role="pilot", authorization_level=3))
    return d


class TestOperatorProfile(unittest.TestCase):
    def test_defaults(self):
        p = OperatorProfile("Leia")
        self.assertEqual(p.role, "guest")
        self.assertEqual(p.authorization_level, 1)
        self.assertEqual(p.interaction_count, 0)
        self.assertEqual(p.familiarity, 0.0)
        self.assertEqual(p.preferences, {})
        self.assertEqual(p.operator_id, "leia")

    def test_operator_id_slug(self):
        self.assertEqual(OperatorProfile("Anakin Sky").operator_id, "anakin_sky")

    def test_validation_errors(self):
        with self.assertRaises(ValueError):
            OperatorProfile("")
        with self.assertRaises(ValueError):
            OperatorProfile("X", role="sith_lord")
        with self.assertRaises(ValueError):
            OperatorProfile("X", authorization_level=0)
        with self.assertRaises(ValueError):
            OperatorProfile("X", authorization_level=6)
        with self.assertRaises(ValueError):
            OperatorProfile("X", authorization_level=3.5)
        with self.assertRaises(ValueError):
            OperatorProfile("X", authorization_level=True)
        with self.assertRaises(ValueError):
            OperatorProfile("X", interaction_count=-1)
        with self.assertRaises(ValueError):
            OperatorProfile("X", familiarity=1.5)
        with self.assertRaises(ValueError):
            OperatorProfile("X", preferences=["not", "a", "dict"])

    def test_all_documented_roles_accepted(self):
        for role in ROLES:
            self.assertEqual(OperatorProfile("X", role=role).role, role)

    def test_roundtrip(self):
        p = OperatorProfile(
            "Han", role="pilot", authorization_level=4, interaction_count=7,
            first_met=123.0, preferences={"seat": "falcon"},
        )
        p2 = OperatorProfile.from_dict(p.to_dict())
        self.assertEqual(p2.to_dict(), p.to_dict())

    def test_from_dict_rejects_non_dict(self):
        with self.assertRaises(ValueError):
            OperatorProfile.from_dict("nope")


class TestOperatorDirectory(unittest.TestCase):
    def test_add_lookup_classify(self):
        d = make_directory()
        self.assertEqual(d.classify("luke"), "known")
        self.assertEqual(d.classify("jabba"), "unknown")
        self.assertFalse(d.is_known("jabba"))
        self.assertIsNone(d.get("jabba"))
        self.assertEqual(d.get("luke").role, "owner")
        self.assertEqual(d.known_ids(), ["luke", "wedge"])

    def test_duplicate_add_raises(self):
        d = make_directory()
        with self.assertRaises(ValueError):
            d.add(OperatorProfile("Luke"))

    def test_add_rejects_non_profile(self):
        with self.assertRaises(ValueError):
            OperatorDirectory().add({"name": "Luke"})

    def test_record_interaction_unknown_raises(self):
        with self.assertRaises(ValueError):
            make_directory().record_interaction("jabba")

    def test_familiarity_diminishing_returns(self):
        d = make_directory()
        increments = []
        prev = 0.0
        for _ in range(6):
            fam = d.record_interaction("luke")
            increments.append(fam - prev)
            prev = fam
        # monotonically increasing, strictly shrinking increments, bounded < 1
        self.assertTrue(all(inc > 0 for inc in increments))
        self.assertEqual(increments, sorted(increments, reverse=True))
        self.assertLess(prev, 1.0)
        # matches the documented curve
        import math

        self.assertAlmostEqual(prev, 1.0 - math.exp(-FAMILIARITY_RATE * 6))

    def test_roundtrip(self):
        d = make_directory()
        d.record_interaction("luke")
        d2 = OperatorDirectory.from_dict(d.to_dict())
        self.assertEqual(d2.to_dict(), d.to_dict())
        self.assertEqual(d2.get("luke").familiarity, d.get("luke").familiarity)

    def test_from_dict_rejects_bad_data(self):
        with self.assertRaises(ValueError):
            OperatorDirectory.from_dict({"nope": {}})


class TestBondEngine(unittest.TestCase):
    def test_validation_errors(self):
        with self.assertRaises(ValueError):
            BondEngine(time_fn=42)
        with self.assertRaises(ValueError):
            BondEngine(decay_per_day=-1.0)
        engine, _ = make_engine()
        with self.assertRaises(ValueError):
            engine.record_interaction("  ")
        with self.assertRaises(ValueError):
            engine.record_interaction("luke", points=0)
        with self.assertRaises(ValueError):
            engine.request_priority("luke", "high")
        with self.assertRaises(ValueError):
            engine.protective_alert("luke", 1.5)
        with self.assertRaises(ValueError):
            engine.protective_alert("luke", "scary")

    def test_unknown_operator_is_wary(self):
        engine, _ = make_engine()
        self.assertEqual(engine.score("stranger"), 0.0)
        self.assertEqual(engine.bond_level("stranger"), BondLevel.WARY)
        self.assertIsNone(engine.days_since_interaction("stranger"))

    def test_bond_upgrades_through_levels(self):
        engine, _ = make_engine()
        self.assertEqual(engine.bond_level("luke"), BondLevel.WARY)
        engine.record_interaction("luke", points=10)   # 10
        self.assertEqual(engine.bond_level("luke"), BondLevel.WARY)
        engine.record_interaction("luke", points=10)   # 20
        self.assertEqual(engine.bond_level("luke"), BondLevel.ACQUAINTED)
        engine.record_interaction("luke", points=20)   # 40
        self.assertEqual(engine.bond_level("luke"), BondLevel.TRUSTED)
        engine.record_interaction("luke", points=20)   # 60
        self.assertEqual(engine.bond_level("luke"), BondLevel.LOYAL)
        engine.record_interaction("luke", points=20)   # 80
        self.assertEqual(engine.bond_level("luke"), BondLevel.DEVOTED)

    def test_score_capped(self):
        engine, _ = make_engine()
        engine.record_interaction("luke", points=SCORE_CAP + 50)
        self.assertEqual(engine.score("luke"), SCORE_CAP)

    def test_decay_downgrades_with_neglect(self):
        engine, advance = make_engine()
        engine.record_interaction("luke", points=80.0)
        self.assertEqual(engine.bond_level("luke"), BondLevel.DEVOTED)
        advance(15)  # 80 - 15 = 65 -> still LOYAL but DEVOTED lost
        self.assertAlmostEqual(engine.score("luke"), 65.0)
        self.assertEqual(engine.bond_level("luke"), BondLevel.LOYAL)
        advance(30)  # 35 -> ACQUAINTED
        self.assertEqual(engine.bond_level("luke"), BondLevel.ACQUAINTED)
        advance(40)  # floored at 0 -> WARY
        self.assertEqual(engine.score("luke"), 0.0)
        self.assertEqual(engine.bond_level("luke"), BondLevel.WARY)

    def test_interaction_halts_decay(self):
        engine, advance = make_engine()
        engine.record_interaction("luke", points=50.0)
        advance(30)  # 30 days of neglect decay (rate 1.0/day) -> score 20
        engine.record_interaction("luke", points=30.0)
        # Post-F8 semantics: pending decay is FOLDED IN before the points are
        # added, so stored = min(cap, 20 + 30) = 50 and decay restarts from
        # this stamp.  10 more days -> 40.
        advance(10)
        self.assertAlmostEqual(engine.score("luke"), 40.0)

    def test_request_priority_bump(self):
        engine, _ = make_engine()
        base = 5.0
        self.assertEqual(engine.request_priority("stranger", base), base)
        engine.record_interaction("luke", points=80.0)  # DEVOTED = +4
        bumped = engine.request_priority("luke", base)
        self.assertEqual(bumped, base + BondLevel.DEVOTED)
        self.assertGreater(bumped, engine.request_priority("stranger", base))

    def test_protective_alert_escalation(self):
        engine, _ = make_engine()
        engine.record_interaction("luke", points=80.0)  # DEVOTED
        low = engine.protective_alert("luke", ALERT_THRESHOLDS["DEVOTED"] - 0.01)
        self.assertFalse(low["escalate"])
        hit = engine.protective_alert("luke", ALERT_THRESHOLDS["DEVOTED"])
        self.assertTrue(hit["escalate"])
        self.assertEqual(hit["bond_level"], "DEVOTED")
        self.assertEqual(hit["priority"], "high")
        crit = engine.protective_alert("luke", 0.9)
        self.assertEqual(crit["priority"], "critical")

    def test_protective_alert_wary_never_escalates(self):
        engine, _ = make_engine()
        result = engine.protective_alert("stranger", 1.0)
        self.assertFalse(result["escalate"])
        self.assertEqual(result["bond_level"], "WARY")

    def test_greeting_varies_with_bond(self):
        engine, _ = make_engine()
        greetings = set()
        for points in (0, 20, 40, 60, 80):
            if points:
                engine.record_interaction("luke", points=points if points == 20 else 20)
            greetings.add(engine.greeting("luke"))
        self.assertEqual(len(greetings), 5)
        self.assertEqual(engine.greeting("stranger"), GREETINGS["WARY"])
        engine.record_interaction("han", points=80.0)
        self.assertEqual(engine.greeting("han"), GREETINGS["DEVOTED"])

    def test_roundtrip(self):
        engine, advance = make_engine()
        engine.record_interaction("luke", points=50.0)
        advance(5)
        snapshot = engine.to_dict()
        restored = BondEngine.from_dict(snapshot, time_fn=lambda: engine._time())
        self.assertEqual(restored.to_dict(), snapshot)
        self.assertAlmostEqual(restored.score("luke"), engine.score("luke"))
        self.assertEqual(restored.bond_level("luke"), engine.bond_level("luke"))

    def test_from_dict_rejects_bad_data(self):
        with self.assertRaises(ValueError):
            BondEngine.from_dict({"nope": {}})


if __name__ == "__main__":
    unittest.main()
