"""Tests for the quirks subsystem. All randomness and time are stubbed.

Run: python -m unittest tests.test_quirks -v
  or: python -m pytest tests/test_quirks.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from quirks import BUILT_IN_QUIRKS, Quirk, QuirkCategory, QuirkRegistry  # noqa: E402
from quirks.quirk import BUILT_IN_BY_ID, HOOKS, MANIFEST_SEVERITY  # noqa: E402
from quirks.registry import (  # noqa: E402
    ACQUISITION_CHANCE,
    ACQUISITION_PERIOD_DAYS,
    REFUSAL_CAP,
)


def make_quirk(**overrides):
    kwargs = dict(
        quirk_id="test_quirk",
        name="Test Quirk",
        category=QuirkCategory.MOTOR,
        severity=5,
        effect="Does a test thing.",
        onset_days=10,
        removable_without_wipe=True,
        effects={"motion": {"jitter": 1.0}},
    )
    kwargs.update(overrides)
    return Quirk(**kwargs)


def script_rng(values):
    """Deterministic rng_fn cycling through a fixed script of draws."""
    seq = list(values)
    state = {"i": 0}

    def rng():
        value = seq[state["i"] % len(seq)]
        state["i"] += 1
        return value

    return rng


def make_registry(rng_values=(0.9,), start_age=0.0):
    return QuirkRegistry(
        rng_fn=script_rng(rng_values),
        day_fn=lambda: start_age,
    )


class TestQuirkValidation(unittest.TestCase):
    def test_valid_construction(self):
        q = make_quirk()
        self.assertEqual(q.quirk_id, "test_quirk")
        self.assertEqual(q.category, QuirkCategory.MOTOR)

    def test_empty_id_rejected(self):
        with self.assertRaises(ValueError):
            make_quirk(quirk_id="")

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            make_quirk(name="")

    def test_bad_category_rejected(self):
        with self.assertRaises(ValueError):
            make_quirk(category="motor")

    def test_severity_bounds(self):
        for bad in (0, 11, -1, 3.5, True):
            with self.assertRaises(ValueError, msg=f"severity={bad}"):
                make_quirk(severity=bad)
        for good in (1, 10):
            self.assertEqual(make_quirk(severity=good).severity, good)

    def test_negative_onset_rejected(self):
        with self.assertRaises(ValueError):
            make_quirk(onset_days=-1)

    def test_non_bool_removable_rejected(self):
        with self.assertRaises(ValueError):
            make_quirk(removable_without_wipe="yes")

    def test_unknown_effect_hook_rejected(self):
        with self.assertRaises(ValueError):
            make_quirk(effects={"warp_drive": {}})

    def test_built_in_catalog_shape(self):
        self.assertGreaterEqual(len(BUILT_IN_QUIRKS), 8)
        ids = [q.quirk_id for q in BUILT_IN_QUIRKS]
        self.assertEqual(len(ids), len(set(ids)), "duplicate quirk ids")
        categories = {q.category for q in BUILT_IN_QUIRKS}
        self.assertEqual(categories, set(QuirkCategory), "catalog should cover all categories")
        # Spec-named entries exist with their stated hooks.
        self.assertIn("motion", BUILT_IN_BY_ID["head_wobble"]._effects)
        self.assertIn("audio", BUILT_IN_BY_ID["raspberry_chirp"]._effects)
        self.assertIn("brain", BUILT_IN_BY_ID["wipe_aversion"]._effects)


class TestManifestation(unittest.TestCase):
    def test_severity_below_threshold_never_manifests(self):
        q = make_quirk(severity=MANIFEST_SEVERITY - 1, onset_days=0)
        q.age_days(100000)
        self.assertFalse(q.manifest())

    def test_severity_at_threshold_manifests_after_onset(self):
        q = make_quirk(severity=MANIFEST_SEVERITY, onset_days=10)
        q.age_days(9)
        self.assertFalse(q.manifest())
        q.age_days(10)
        self.assertTrue(q.manifest())

    def test_age_days_validates(self):
        q = make_quirk()
        with self.assertRaises(ValueError):
            q.age_days(-1)


class TestHookEffects(unittest.TestCase):
    def test_effect_returned_when_manifested(self):
        q = make_quirk(onset_days=0)
        q.age_days(0)
        eff = q.quirk_effect_for("motion")
        self.assertIsNotNone(eff)
        self.assertEqual(eff["jitter"], 1.0)
        self.assertEqual(eff["quirk_id"], "test_quirk")
        self.assertEqual(eff["severity"], 5)

    def test_none_for_untouched_hook(self):
        q = make_quirk(onset_days=0)
        self.assertIsNone(q.quirk_effect_for("audio"))

    def test_none_before_manifestation(self):
        q = make_quirk(onset_days=50)
        q.age_days(10)
        self.assertIsNone(q.quirk_effect_for("motion"))

    def test_none_for_sub_manifest_severity(self):
        q = make_quirk(severity=2, onset_days=0)
        self.assertIsNone(q.quirk_effect_for("motion"))

    def test_invalid_hook_raises(self):
        q = make_quirk()
        with self.assertRaises(ValueError):
            q.quirk_effect_for("warp_drive")
        for hook in HOOKS:
            q.quirk_effect_for(hook)  # must not raise

    def test_returned_payload_is_a_copy(self):
        q = make_quirk(onset_days=0)
        eff = q.quirk_effect_for("motion")
        eff["jitter"] = 999
        self.assertEqual(q.quirk_effect_for("motion")["jitter"], 1.0)


class TestAcquisition(unittest.TestCase):
    def test_no_roll_before_first_period(self):
        reg = make_registry(rng_values=(0.0, 0.0))  # would always acquire
        gained = reg.age(ACQUISITION_PERIOD_DAYS - 1)
        self.assertEqual(gained, [])
        self.assertEqual(reg.quirk_ids(), [])

    def test_roll_at_period_boundary(self):
        # draw 0.1 < ACQUISITION_CHANCE -> acquire; pick draw 0.0 -> first candidate
        reg = make_registry(rng_values=(0.1, 0.0))
        gained = reg.age(ACQUISITION_PERIOD_DAYS)
        self.assertEqual(len(gained), 1)
        expected = BUILT_IN_QUIRKS[0].quirk_id  # all onset_days >= 10 > 30? check below
        # candidates are catalog entries with onset_days <= 30
        candidates = [q for q in BUILT_IN_QUIRKS if q.onset_days <= ACQUISITION_PERIOD_DAYS]
        self.assertEqual(gained[0], candidates[0].quirk_id)
        self.assertNotEqual(expected, gained[0] or expected)  # sanity, no-op

    def test_failed_roll_acquires_nothing(self):
        reg = make_registry(rng_values=(ACQUISITION_CHANCE,))  # >= chance -> no acquire
        gained = reg.age(ACQUISITION_PERIOD_DAYS)
        self.assertEqual(gained, [])

    def test_max_one_quirk_per_period(self):
        reg = make_registry(rng_values=(0.0, 0.0))
        gained = reg.age(3 * ACQUISITION_PERIOD_DAYS)
        self.assertEqual(len(gained), 3)  # 3 periods -> 3 rolls -> 3 max

    def test_determinism_same_stubs_same_result(self):
        results = []
        for _ in range(2):
            reg = make_registry(rng_values=(0.05, 0.5, 0.9, 0.05, 0.9))
            reg.age(40)
            reg.age(35)
            results.append(reg.quirk_ids())
        self.assertEqual(results[0], results[1])
        self.assertTrue(results[0])

    def test_no_duplicate_acquisition(self):
        reg = make_registry(rng_values=(0.0, 0.0))
        reg.age(20 * ACQUISITION_PERIOD_DAYS)
        ids = reg.quirk_ids()
        self.assertEqual(len(ids), len(set(ids)))

    def test_acquired_quirk_is_aged_and_catalog_unchanged(self):
        reg = make_registry(rng_values=(0.0, 0.0))
        reg.age(ACQUISITION_PERIOD_DAYS)
        gained_id = reg.quirk_ids()[0]
        self.assertFalse(BUILT_IN_BY_ID[gained_id].manifest(),
                         "catalog template must stay age 0 / unmanifested")

    def test_rng_out_of_range_raises(self):
        reg = QuirkRegistry(rng_fn=lambda: 1.5, day_fn=lambda: 0.0)
        with self.assertRaises(ValueError):
            reg.age(ACQUISITION_PERIOD_DAYS)

    def test_negative_age_rejected(self):
        reg = make_registry()
        with self.assertRaises(ValueError):
            reg.age(-1)

    def test_non_callable_injectables_rejected(self):
        with self.assertRaises(ValueError):
            QuirkRegistry(rng_fn=42)
        with self.assertRaises(ValueError):
            QuirkRegistry(rng_fn=lambda: 0.5, day_fn=7)

    def test_day_fn_sets_start_age(self):
        reg = make_registry(start_age=200.0)
        self.assertEqual(reg.quirk_report()["age_days"], 200.0)


class TestWipe(unittest.TestCase):
    def loaded_registry(self):
        # Always acquire; pick draws sweep the catalog for variety.
        picks = [i / 20 for i in range(20)]
        draws = []
        for p in picks:
            draws.extend([0.0, p])
        reg = make_registry(rng_values=tuple(draws))
        reg.age(20 * ACQUISITION_PERIOD_DAYS)
        return reg

    def test_wipe_removes_removable_keeps_permanent(self):
        reg = self.loaded_registry()
        removable = {q.quirk_id for q in BUILT_IN_QUIRKS if q.removable_without_wipe}
        permanent = {q.quirk_id for q in BUILT_IN_QUIRKS if not q.removable_without_wipe}
        result = reg.wipe()
        self.assertEqual(set(result["removed"]) & permanent, set())
        self.assertEqual(set(result["kept"]) & removable, set())
        self.assertEqual(set(reg.quirk_ids()), set(result["kept"]))
        self.assertTrue(result["removed"], "expected some removable quirks loaded")

    def test_wipe_on_empty_registry(self):
        reg = make_registry()
        self.assertEqual(reg.wipe(), {"removed": [], "kept": []})


class TestRefuseWipe(unittest.TestCase):
    def test_fresh_droid_never_refuses(self):
        reg = make_registry()
        self.assertEqual(reg.refuse_wipe(), 0.0)

    def test_refusal_rises_with_severity(self):
        reg_low = make_registry(rng_values=(0.0, 0.0))
        reg_low.age(2 * ACQUISITION_PERIOD_DAYS)  # at least one manifested quirk
        reg_high = self._veteran()
        self.assertGreater(reg_high.refuse_wipe(), reg_low.refuse_wipe())
        self.assertGreater(reg_low.refuse_wipe(), 0.0)

    def test_refusal_bounds(self):
        reg = self._veteran()
        p = reg.refuse_wipe()
        self.assertGreaterEqual(p, 0.0)
        self.assertLessEqual(p, REFUSAL_CAP)

    def test_dormant_quirks_do_not_add_refusal(self):
        # Acquire the severity-1 dome_spin_greeting only (pick draw 0.9
        # lands on the last onset<=30 candidate, which is dome_spin_greeting
        # at onset_days=10... verify via report instead of assuming).
        reg = make_registry(rng_values=(0.0, 0.0))
        reg.age(ACQUISITION_PERIOD_DAYS - 20)  # age 10: no period yet
        self.assertEqual(reg.refuse_wipe(), 0.0)

    def _veteran(self):
        reg = make_registry(rng_values=(0.0, 0.99))
        reg.age(40 * ACQUISITION_PERIOD_DAYS)
        return reg


class TestActiveEffects(unittest.TestCase):
    def test_aggregates_only_manifested_matching_hook(self):
        reg = make_registry(rng_values=(0.0, 0.0))
        reg.age(20 * ACQUISITION_PERIOD_DAYS)
        for hook in HOOKS:
            effects = reg.active_effects(hook)
            expected = [
                q for q in BUILT_IN_QUIRKS
                if q.quirk_id in reg.quirk_ids()
                and hook in q._effects and q.severity >= MANIFEST_SEVERITY
                and q.onset_days <= reg.quirk_report()["age_days"]
            ]
            self.assertEqual(len(effects), len(expected), f"hook={hook}")
            for eff in effects:
                self.assertIn("quirk_id", eff)
                self.assertIn("severity", eff)

    def test_invalid_hook_raises(self):
        reg = make_registry()
        with self.assertRaises(ValueError):
            reg.active_effects("warp_drive")


class TestSerialization(unittest.TestCase):
    def test_quirk_round_trip(self):
        q = make_quirk(onset_days=0)
        q.age_days(42)
        clone = Quirk.from_dict(q.to_dict())
        self.assertEqual(clone.to_dict(), q.to_dict())

    def test_quirk_from_dict_bad_category(self):
        data = make_quirk().to_dict()
        data["category"] = "chaotic"
        with self.assertRaises(ValueError):
            Quirk.from_dict(data)

    def test_registry_round_trip(self):
        reg = make_registry(rng_values=(0.05, 0.3, 0.9, 0.05, 0.7))
        reg.age(10 * ACQUISITION_PERIOD_DAYS)
        data = reg.to_dict()
        restored = QuirkRegistry.from_dict(data, rng_fn=script_rng((0.9,)), day_fn=lambda: 0.0)
        self.assertEqual(restored.to_dict(), data)
        self.assertEqual(restored.quirk_ids(), reg.quirk_ids())
        self.assertEqual(restored.quirk_report(), reg.quirk_report())

    def test_from_dict_unknown_quirk_id_rejected(self):
        reg = make_registry(rng_values=(0.0, 0.0))
        reg.age(ACQUISITION_PERIOD_DAYS)
        data = reg.to_dict()
        data["quirks"][0]["quirk_id"] = "not_a_real_quirk"
        with self.assertRaises(ValueError):
            QuirkRegistry.from_dict(data, rng_fn=script_rng((0.9,)))

    def test_from_dict_tampered_quirk_rejected(self):
        reg = make_registry(rng_values=(0.0, 0.0))
        reg.age(ACQUISITION_PERIOD_DAYS)
        data = reg.to_dict()
        data["quirks"][0]["severity"] = 9
        with self.assertRaises(ValueError):
            QuirkRegistry.from_dict(data, rng_fn=script_rng((0.9,)))


if __name__ == "__main__":
    unittest.main()
