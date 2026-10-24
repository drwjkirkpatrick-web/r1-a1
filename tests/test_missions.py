"""Tests for the missions module (Mission, MissionStatus, MissionQueue).

All logic is pure; clocks are injected. No hardware, no sleeps.

Run: python -m unittest tests.test_missions -v
  or: python -m pytest tests/test_missions.py -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from missions import Mission, MissionStatus, MissionQueue  # noqa: E402

SECONDS_PER_DAY = 86400.0


def make_mission(mid="m1", now=0.0, **kwargs):
    """Mission with a pinned creation clock (epoch seconds).

    ``mid`` is intentionally unannotated: construction-validation tests
    pass non-string garbage on purpose.
    """
    kwargs.setdefault("now_fn", lambda: now)
    return Mission(mid, title=kwargs.pop("title", f"mission {mid}"), **kwargs)


class TestMissionConstruction(unittest.TestCase):
    def test_defaults(self):
        m = make_mission("m1")
        self.assertEqual(m.mission_id, "m1")
        self.assertEqual(m.priority, 5)
        self.assertEqual(m.depends_on, ())
        self.assertEqual(m.steps, [])
        self.assertEqual(m.status, MissionStatus.PENDING)

    def test_empty_mission_id_raises(self):
        for bad in ("", "   ", 123, None):
            with self.assertRaises(ValueError, msg=f"id={bad!r}"):
                make_mission(bad)

    def test_empty_title_raises(self):
        with self.assertRaises(ValueError):
            make_mission("m1", title="")

    def test_priority_bounds(self):
        for bad in (0, 11, -1, 3.5, "5"):
            with self.assertRaises(ValueError, msg=f"priority={bad!r}"):
                make_mission("m1", priority=bad)
        for good in (1, 10):
            self.assertEqual(make_mission("m1", priority=good).priority, good)

    def test_bad_deadline_raises(self):
        with self.assertRaises(ValueError):
            make_mission("m1", deadline_days=0)
        with self.assertRaises(ValueError):
            make_mission("m1", deadline_days=-2)

    def test_duplicate_step_names_raise(self):
        with self.assertRaises(ValueError):
            make_mission("m1", steps=["scan", "scan"])

    def test_duplicate_deps_raise(self):
        with self.assertRaises(ValueError):
            make_mission("m1", depends_on=("a", "a"))


class TestStepsAndProgress(unittest.TestCase):
    def test_progress_empty_is_zero(self):
        self.assertEqual(make_mission("m1").progress_pct, 0.0)

    def test_progress_tracks_done_steps(self):
        m = make_mission("m1", steps=["a", "b", "c", "d"])
        self.assertEqual(m.progress_pct, 0.0)
        m.complete_step("a")
        self.assertEqual(m.progress_pct, 25.0)
        m.complete_step("b")
        m.complete_step("c")
        self.assertEqual(m.progress_pct, 75.0)
        m.complete_step("d")
        self.assertEqual(m.progress_pct, 100.0)

    def test_complete_step_idempotent(self):
        m = make_mission("m1", steps=["a", "b"])
        m.complete_step("a")
        m.complete_step("a")
        self.assertEqual(m.progress_pct, 50.0)

    def test_complete_unknown_step_raises(self):
        m = make_mission("m1", steps=["a"])
        with self.assertRaises(ValueError):
            m.complete_step("nope")


class TestTransitions(unittest.TestCase):
    def test_legal_pending_to_active_to_complete(self):
        m = make_mission("m1")
        m.transition(MissionStatus.ACTIVE)
        self.assertEqual(m.status, MissionStatus.ACTIVE)
        m.transition(MissionStatus.COMPLETE)
        self.assertEqual(m.status, MissionStatus.COMPLETE)

    def test_legal_pending_to_blocked_to_pending(self):
        m = make_mission("m1")
        m.transition(MissionStatus.BLOCKED)
        m.transition(MissionStatus.PENDING)
        self.assertEqual(m.status, MissionStatus.PENDING)

    def test_complete_only_from_active(self):
        m = make_mission("m1")
        with self.assertRaises(ValueError):
            m.transition(MissionStatus.COMPLETE)  # PENDING -> COMPLETE
        m2 = make_mission("m2")
        m2.transition(MissionStatus.BLOCKED)
        with self.assertRaises(ValueError):
            m2.transition(MissionStatus.COMPLETE)  # BLOCKED -> COMPLETE

    def test_terminal_states_are_terminal(self):
        for terminal, path in (
            (MissionStatus.COMPLETE, [MissionStatus.ACTIVE, MissionStatus.COMPLETE]),
            (MissionStatus.FAILED, [MissionStatus.FAILED]),
            (MissionStatus.CANCELLED, [MissionStatus.CANCELLED]),
        ):
            m = make_mission("m1")
            for step in path:
                m.transition(step)
            self.assertEqual(m.status, terminal)
            for target in MissionStatus:
                with self.assertRaises(ValueError, msg=f"{terminal}->{target}"):
                    m.transition(target)

    def test_illegal_active_to_blocked(self):
        m = make_mission("m1")
        m.transition(MissionStatus.ACTIVE)
        with self.assertRaises(ValueError):
            m.transition(MissionStatus.BLOCKED)

    def test_non_enum_target_raises(self):
        with self.assertRaises(ValueError):
            make_mission("m1").transition("active")


class TestBlockingAndDeadlines(unittest.TestCase):
    def test_can_unblock_only_when_blocked_and_deps_done(self):
        m = make_mission("m1", depends_on=("a", "b"))
        self.assertFalse(m.can_unblock({"a", "b"}))  # still PENDING
        m.transition(MissionStatus.BLOCKED)
        self.assertFalse(m.can_unblock({"a"}))
        self.assertTrue(m.can_unblock({"a", "b"}))
        self.assertTrue(m.can_unblock({"a", "b", "extra"}))

    def test_no_deadline_never_overdue(self):
        m = make_mission("m1", now=0.0)
        self.assertFalse(m.is_overdue(lambda: 10**9))

    def test_overdue_after_deadline(self):
        m = make_mission("m1", now=0.0, deadline_days=3)
        self.assertFalse(m.is_overdue(lambda: 3 * SECONDS_PER_DAY))
        self.assertTrue(m.is_overdue(lambda: 3 * SECONDS_PER_DAY + 1))

    def test_finished_missions_never_overdue(self):
        for status_path in (
            [MissionStatus.ACTIVE, MissionStatus.COMPLETE],
            [MissionStatus.FAILED],
            [MissionStatus.CANCELLED],
        ):
            m = make_mission("m1", now=0.0, deadline_days=1)
            for step in status_path:
                m.transition(step)
            self.assertFalse(
                m.is_overdue(lambda: 100 * SECONDS_PER_DAY),
                msg=f"path={status_path}",
            )

    def test_blocked_mission_can_be_overdue(self):
        m = make_mission("m1", now=0.0, deadline_days=1)
        m.transition(MissionStatus.BLOCKED)
        self.assertTrue(m.is_overdue(lambda: 2 * SECONDS_PER_DAY))


class TestQueueBasics(unittest.TestCase):
    def test_add_get_len(self):
        q = MissionQueue()
        m = q.add(make_mission("m1"))
        self.assertIs(q.get("m1"), m)
        self.assertIsNone(q.get("missing"))
        self.assertEqual(len(q), 1)

    def test_duplicate_id_raises(self):
        q = MissionQueue()
        q.add(make_mission("m1"))
        with self.assertRaises(ValueError):
            q.add(make_mission("m1"))

    def test_add_non_mission_raises(self):
        with self.assertRaises(ValueError):
            MissionQueue().add("not a mission")

    def test_cancel(self):
        q = MissionQueue()
        q.add(make_mission("m1"))
        q.cancel("m1")
        self.assertEqual(q.get("m1").status, MissionStatus.CANCELLED)
        with self.assertRaises(ValueError):
            q.cancel("m1")  # already terminal
        with self.assertRaises(ValueError):
            q.cancel("ghost")


class TestQueueScheduling(unittest.TestCase):
    def test_next_mission_highest_priority(self):
        q = MissionQueue()
        q.add(make_mission("low", priority=2))
        q.add(make_mission("high", priority=9))
        q.add(make_mission("mid", priority=5))
        self.assertEqual(q.next_mission().mission_id, "high")

    def test_next_mission_tie_breaks_by_insertion_order(self):
        q = MissionQueue()
        q.add(make_mission("first", priority=7))
        q.add(make_mission("second", priority=7))
        self.assertEqual(q.next_mission().mission_id, "first")

    def test_next_mission_skips_unsatisfied_deps(self):
        q = MissionQueue()
        q.add(make_mission("parent", priority=1))
        q.add(make_mission("child", priority=10, depends_on=("parent",)))
        self.assertEqual(q.next_mission().mission_id, "parent")

    def test_next_mission_empty_when_nothing_eligible(self):
        q = MissionQueue()
        self.assertIsNone(q.next_mission())
        q.add(make_mission("done", priority=9))
        q.get("done").transition(MissionStatus.ACTIVE)
        q.get("done").transition(MissionStatus.COMPLETE)
        self.assertIsNone(q.next_mission())

    def test_next_mission_includes_active_missions(self):
        q = MissionQueue()
        q.add(make_mission("running", priority=3))
        q.get("running").transition(MissionStatus.ACTIVE)
        q.add(make_mission("waiting", priority=3))  # later insertion, same priority
        self.assertEqual(q.next_mission().mission_id, "running")


class TestDependencyChains(unittest.TestCase):
    def build_chain(self):
        """a -> b -> c (each depends on the previous)."""
        q = MissionQueue()
        q.add(make_mission("a", priority=1))
        q.add(make_mission("b", priority=9, depends_on=("a",)))
        q.add(make_mission("c", priority=9, depends_on=("b",)))
        return q

    def test_chain_blocks_until_parent_completes(self):
        q = self.build_chain()
        self.assertEqual(q.next_mission().mission_id, "a")
        self.assertEqual(q.get("b").status, MissionStatus.BLOCKED)
        self.assertEqual(q.get("c").status, MissionStatus.BLOCKED)

        q.get("a").transition(MissionStatus.ACTIVE)
        q.get("a").transition(MissionStatus.COMPLETE)
        q.tick("a")
        self.assertEqual(q.get("b").status, MissionStatus.PENDING)
        self.assertEqual(q.next_mission().mission_id, "b")

        q.get("b").transition(MissionStatus.ACTIVE)
        q.get("b").transition(MissionStatus.COMPLETE)
        q.tick("b")
        self.assertEqual(q.get("c").status, MissionStatus.PENDING)
        self.assertEqual(q.next_mission().mission_id, "c")

    def test_unblock_needs_all_deps(self):
        q = MissionQueue()
        q.add(make_mission("p1"))
        q.add(make_mission("p2"))
        q.add(make_mission("kid", depends_on=("p1", "p2")))
        q.next_mission()  # sweep: kid becomes BLOCKED
        self.assertEqual(q.get("kid").status, MissionStatus.BLOCKED)
        for pid in ("p1", "p2"):
            q.get(pid).transition(MissionStatus.ACTIVE)
        q.get("p1").transition(MissionStatus.COMPLETE)
        q.tick("p1")
        self.assertEqual(q.get("kid").status, MissionStatus.BLOCKED)
        q.get("p2").transition(MissionStatus.COMPLETE)
        q.tick("p2")
        self.assertEqual(q.get("kid").status, MissionStatus.PENDING)

    def test_failure_cascades_through_dependents(self):
        q = MissionQueue()
        q.add(make_mission("root"))
        q.add(make_mission("mid", depends_on=("root",)))
        q.add(make_mission("leaf", depends_on=("mid",)))
        q.next_mission()  # block mid + leaf
        q.get("root").transition(MissionStatus.ACTIVE)
        q.get("root").transition(MissionStatus.FAILED)
        q.tick("root")
        self.assertEqual(q.get("mid").status, MissionStatus.FAILED)
        self.assertEqual(q.get("leaf").status, MissionStatus.FAILED)  # transitive

    def test_sibling_survives_when_other_dep_fails(self):
        q = MissionQueue()
        q.add(make_mission("bad"))
        q.add(make_mission("good"))
        q.add(make_mission("doomed", depends_on=("bad",)))
        q.add(make_mission("fine", depends_on=("good",)))
        q.next_mission()
        q.get("bad").transition(MissionStatus.ACTIVE)
        q.get("bad").transition(MissionStatus.FAILED)
        q.get("good").transition(MissionStatus.ACTIVE)
        q.get("good").transition(MissionStatus.COMPLETE)
        q.tick("good")
        self.assertEqual(q.get("doomed").status, MissionStatus.FAILED)
        self.assertEqual(q.get("fine").status, MissionStatus.PENDING)

    def test_tick_unknown_id_raises(self):
        with self.assertRaises(ValueError):
            MissionQueue().tick("ghost")


class TestProgressReport(unittest.TestCase):
    def test_empty_queue(self):
        rep = MissionQueue().progress_report()
        self.assertEqual(rep["avg_progress"], 0.0)
        self.assertTrue(all(v == 0 for v in rep["counts"].values()))

    def test_counts_and_average(self):
        q = MissionQueue()
        q.add(make_mission("a", steps=["s1", "s2"]))
        q.add(make_mission("b", steps=["s1", "s2"]))
        q.add(make_mission("c"))
        q.get("a").complete_step("s1")            # 50 %
        q.get("b").complete_step("s1")
        q.get("b").complete_step("s2")            # 100 %
        q.get("c").transition(MissionStatus.CANCELLED)
        rep = q.progress_report()
        self.assertEqual(rep["counts"]["pending"], 2)
        self.assertEqual(rep["counts"]["cancelled"], 1)
        self.assertEqual(rep["counts"]["active"], 0)
        self.assertAlmostEqual(rep["avg_progress"], 50.0)  # (50+100+0)/3


class TestSerialization(unittest.TestCase):
    def test_mission_round_trip(self):
        m = make_mission(
            "m1",
            now=123.0,
            priority=8,
            depends_on=("p1", "p2"),
            steps=["scan", "dock"],
            deadline_days=2.5,
        )
        m.complete_step("scan")
        m.transition(MissionStatus.ACTIVE)
        m2 = Mission.from_dict(m.to_dict())
        self.assertEqual(m2.to_dict(), m.to_dict())
        self.assertEqual(m2.status, MissionStatus.ACTIVE)
        self.assertEqual(m2.progress_pct, 50.0)
        self.assertEqual(m2.depends_on, ("p1", "p2"))
        # deadline math survives: created clock was pinned to 123 s
        self.assertTrue(m2.is_overdue(lambda: 123.0 + 3 * SECONDS_PER_DAY))

    def test_queue_round_trip(self):
        q = MissionQueue()
        q.add(make_mission("a", priority=3))
        q.add(make_mission("b", priority=9, depends_on=("a",), steps=["x"]))
        q.get("a").transition(MissionStatus.ACTIVE)
        q.get("a").transition(MissionStatus.COMPLETE)
        q.get("b").complete_step("x")
        q2 = MissionQueue.from_dict(q.to_dict())
        self.assertEqual(q2.to_dict(), q.to_dict())
        self.assertEqual(len(q2), 2)
        self.assertEqual(q2.get("a").status, MissionStatus.COMPLETE)
        # restored queue still schedules correctly
        self.assertEqual(q2.next_mission().mission_id, "b")


if __name__ == "__main__":
    unittest.main()
