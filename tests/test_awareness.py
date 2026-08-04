"""Tests for the spatial-awareness subsystem (the 8 upgrades).

All hardware is faked — no radar, rangers, or IMU attached.
Run: python3 -m pytest tests/test_awareness.py
"""

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.awareness.mmwave import MMWaveArray, DEFAULT_MOUNTS
from src.awareness.ultrasonic import UltrasonicRing, SENSOR_HEADINGS_DEG
from src.awareness.cliff import CliffSensors
from src.awareness.pose import PoseFilter
from src.awareness.occupancy import OccupancyGrid
from src.awareness.proximity import ProximityPolicy
from src.awareness.fusion import AwarenessFusion
from src.motion.refine import MovementRefiner


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeDrive:
    def __init__(self):
        self.calls = []

    def forward(self, meters, speed):
        self.calls.append(("forward", meters, speed))

    def rotate(self, degrees):
        self.calls.append(("rotate", degrees))

    def stop(self):
        self.calls.append(("stop",))


def make_fusion(mmwave_reader=None, echo_fn=None, cliff_fn=None):
    mm = MMWaveArray(mmwave_reader or (lambda i: []))
    us = UltrasonicRing(echo_fn or (lambda i: 4.0))
    cl = CliffSensors(cliff_fn or (lambda i: 20.0))
    pose = PoseFilter()
    return AwarenessFusion(mm, us, cl, pose)


# ---------------------------------------------------------------------------
# mmwave
# ---------------------------------------------------------------------------

class TestMMWave(unittest.TestCase):
    def test_rejects_noncallable_reader(self):
        with self.assertRaises(ValueError):
            MMWaveArray(reader=None)

    def test_rejects_wrong_mount_count(self):
        with self.assertRaises(ValueError):
            MMWaveArray(lambda i: [], mounts=[(0, 0, 0)])

    def test_scan_transforms_rear_sensor_to_robot_frame(self):
        # rear sensor (index 2) yaw=180°: a target 1 m "ahead" of it
        # is 1 m BEHIND the robot plus the −0.2 m mount offset.
        def reader(i):
            if i == 2:
                return [{"id": 1, "x_m": 1.0, "y_m": 0.0, "speed_mps": 0.5}]
            return []
        targets = MMWaveArray(reader).scan()
        self.assertEqual(len(targets), 1)
        t = targets[0]
        self.assertAlmostEqual(t["x_m"], -1.2, places=6)
        self.assertAlmostEqual(t["y_m"], 0.0, places=6)

    def test_nearest_target_picks_closest(self):
        def reader(i):
            if i == 0:
                return [{"id": 1, "x_m": 2.0, "y_m": 0.0, "speed_mps": 0.0}]
            if i == 1:
                return [{"id": 2, "x_m": 0.5, "y_m": 0.0, "speed_mps": 0.0}]
            return []
        arr = MMWaveArray(reader)
        self.assertEqual(arr.nearest_target()["id"], 2)

    def test_nearest_target_none_when_empty(self):
        self.assertIsNone(MMWaveArray(lambda i: []).nearest_target())

    def test_human_present(self):
        arr = MMWaveArray(lambda i: [{"id": 1, "x_m": 1, "y_m": 0,
                                      "speed_mps": 0}] if i == 0 else [])
        self.assertTrue(arr.human_present())
        self.assertFalse(MMWaveArray(lambda i: []).human_present())

    def test_track_ema_smooths_positions(self):
        samples = iter([
            [{"id": 7, "x_m": 1.0, "y_m": 0.0, "speed_mps": 0.0}],
            [{"id": 7, "x_m": 2.0, "y_m": 0.0, "speed_mps": 0.0}],
        ])
        arr = MMWaveArray(lambda i: next(samples, []) if i == 0 else [],
                          ema_alpha=0.5)
        first = arr.track(7)
        second = arr.track(7)
        # EMA with α=0.5 over (1.0 → 2.0) lands at 1.5 in sensor-x,
        # transformed by the front-left mount (offset 0.18, yaw 30°).
        self.assertLess(first[0], second[0])  # moved forward
        self.assertIsNone(arr.track(99))      # unknown id


# ---------------------------------------------------------------------------
# ultrasonic
# ---------------------------------------------------------------------------

class TestUltrasonic(unittest.TestCase):
    def test_rejects_noncallable(self):
        with self.assertRaises(ValueError):
            UltrasonicRing(echo_fn=None)

    def test_distances_clamped(self):
        ring = UltrasonicRing(lambda i: 99.0)
        self.assertTrue(all(d == 4.0 for d in ring.distances()))

    def test_nearest_returns_heading(self):
        ring = UltrasonicRing(lambda i: 0.5 if i == 2 else 3.0)
        d, hdg = ring.nearest()
        self.assertAlmostEqual(d, 0.5)
        self.assertAlmostEqual(hdg, SENSOR_HEADINGS_DEG[2])

    def test_sector_clear(self):
        ring = UltrasonicRing(lambda i: 2.5 if i == 0 else 0.1)
        self.assertTrue(ring.sector_clear(45.0, 1.0))
        self.assertFalse(ring.sector_clear(135.0, 1.0))
        with self.assertRaises(ValueError):
            ring.sector_clear(0.0, 0.0)


# ---------------------------------------------------------------------------
# cliff
# ---------------------------------------------------------------------------

class TestCliff(unittest.TestCase):
    def test_threshold_boundary(self):
        # exactly at threshold: not a cliff (strictly greater)
        self.assertFalse(CliffSensors(lambda i: 80.0).is_cliff())
        self.assertTrue(CliffSensors(lambda i: 80.1).is_cliff())

    def test_safest_turn_away_from_front_left(self):
        cl = CliffSensors(lambda i: 200.0 if i == 0 else 20.0)
        self.assertTrue(cl.is_cliff())
        self.assertEqual(cl.safest_turn(), "right")

    def test_safest_turn_away_from_front_right(self):
        cl = CliffSensors(lambda i: 200.0 if i == 1 else 20.0)
        self.assertEqual(cl.safest_turn(), "left")

    def test_safest_turn_rear_or_multiple_goes_back(self):
        self.assertEqual(CliffSensors(lambda i: 200.0 if i == 2 else 20.0)
                         .safest_turn(), "back")
        self.assertEqual(CliffSensors(lambda i: 200.0).safest_turn(), "back")

    def test_bad_config(self):
        with self.assertRaises(ValueError):
            CliffSensors(None)
        with self.assertRaises(ValueError):
            CliffSensors(lambda i: 0, threshold_mm=0)


# ---------------------------------------------------------------------------
# pose
# ---------------------------------------------------------------------------

class TestPose(unittest.TestCase):
    def test_straight_line_integration(self):
        pf = PoseFilter()
        for _ in range(10):
            pf.update(0.1, 0.0, 0.0, 0.0, 0.1)
        x, y, h = pf.pose()
        self.assertAlmostEqual(x, 1.0, places=6)
        self.assertAlmostEqual(y, 0.0, places=6)
        self.assertAlmostEqual(h, 0.0, places=6)

    def test_imu_correction_converges(self):
        pf = PoseFilter(alpha=0.5)
        pf.update(0, 0, 0, 90.0, 0.1)   # IMU says 90°, odom says no turn
        _, _, h = pf.pose()
        self.assertAlmostEqual(h, 45.0, places=6)
        pf.update(0, 0, 0, 90.0, 0.1)
        _, _, h2 = pf.pose()
        self.assertAlmostEqual(h2, 67.5, places=6)

    def test_heading_wraps(self):
        pf = PoseFilter(alpha=0.02)
        pf.update(0, 0, 200.0, 200.0, 0.1)
        _, _, h = pf.pose()
        self.assertTrue(-180 <= h <= 180)

    def test_rejects_bad_dt_and_alpha(self):
        with self.assertRaises(ValueError):
            PoseFilter(alpha=1.5)
        with self.assertRaises(ValueError):
            PoseFilter().update(0, 0, 0, 0, 0.0)

    def test_reset(self):
        pf = PoseFilter()
        pf.update(1, 0, 45, 45, 0.1)
        pf.reset()
        self.assertEqual(pf.pose(), (0.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# occupancy
# ---------------------------------------------------------------------------

class TestOccupancy(unittest.TestCase):
    def test_mark_and_query(self):
        g = OccupancyGrid()
        g.update_from_mmwave([{"x_m": 1.0, "y_m": 0.0}])
        self.assertTrue(g.is_cell_blocked(1.0, 0.0))
        self.assertFalse(g.is_cell_blocked(-1.0, 0.0))

    def test_raycast_blocked_by_marked_cell(self):
        g = OccupancyGrid()
        g.update_from_mmwave([{"x_m": 0.5, "y_m": 0.0}])
        self.assertFalse(g.raycast_clear(0.0, 1.0))   # forward blocked
        self.assertTrue(g.raycast_clear(180.0, 1.0))  # reverse clear

    def test_decay_fades_below_threshold(self):
        g = OccupancyGrid()
        g.update_from_mmwave([{"x_m": 1.0, "y_m": 0.0}])
        for _ in range(10):  # 0.9^10 ≈ 0.35 < 0.5 threshold
            g.decay()
        self.assertFalse(g.is_cell_blocked(1.0, 0.0))

    def test_cliff_marks_hard_hazard(self):
        g = OccupancyGrid()
        g.update_from_cliff(["front-left"])
        self.assertFalse(g.raycast_clear(30.0, 0.5))
        g.decay()
        self.assertFalse(g.raycast_clear(30.0, 0.5))  # 1.0*0.9 still ≥ 0.5

    def test_ultrasonic_feed(self):
        g = OccupancyGrid()
        g.update_from_ultrasonic([1.0, 4.0, 4.0, 4.0], SENSOR_HEADINGS_DEG)
        r = math.radians(45.0)
        self.assertTrue(g.is_cell_blocked(math.cos(r), math.sin(r)))

    def test_outside_bubble_is_blocked(self):
        self.assertTrue(OccupancyGrid().is_cell_blocked(99.0, 0.0))

    def test_bad_config(self):
        with self.assertRaises(ValueError):
            OccupancyGrid(cells=7)
        with self.assertRaises(ValueError):
            OccupancyGrid(cell_m=0)


# ---------------------------------------------------------------------------
# proximity
# ---------------------------------------------------------------------------

class TestProximity(unittest.TestCase):
    def test_zone_boundaries(self):
        p = ProximityPolicy()
        self.assertEqual(p.speed_factor(0.29), 0.0)
        self.assertEqual(p.speed_factor(0.5), 0.3)
        self.assertEqual(p.speed_factor(1.5), 0.6)
        self.assertEqual(p.speed_factor(2.5), 1.0)

    def test_cliff_forces_stop(self):
        advice = ProximityPolicy().advise(5.0, cliff=True)
        self.assertTrue(advice["must_stop"])
        self.assertEqual(advice["max_speed_factor"], 0.0)
        self.assertIn("cliff", advice["reason"])

    def test_clear_advice(self):
        advice = ProximityPolicy().advise(5.0, cliff=False)
        self.assertFalse(advice["must_stop"])
        self.assertEqual(advice["reason"], "clear")

    def test_bad_zone_config(self):
        with self.assertRaises(ValueError):
            ProximityPolicy(stop_m=2.0, slow_m=1.0)


# ---------------------------------------------------------------------------
# fusion
# ---------------------------------------------------------------------------

class TestFusion(unittest.TestCase):
    def test_refresh_picture(self):
        fusion = make_fusion(
            mmwave_reader=lambda i: [{"id": 1, "x_m": 1.0, "y_m": 0.0,
                                      "speed_mps": 0.2}] if i == 0 else [],
            echo_fn=lambda i: 1.5,
        )
        state = fusion.refresh()
        self.assertTrue(state["human_present"])
        self.assertLessEqual(state["nearest_m"], 1.5)
        self.assertFalse(state["cliff"])
        self.assertEqual(len(state["pose"]), 3)

    def test_status_report_has_provenance(self):
        fusion = make_fusion()
        fusion.refresh()
        report = fusion.status_report()
        self.assertIn("mmwave", report["sensors"])
        self.assertEqual(report["grid_cells"], 40 * 40)

    def test_missing_sensor_rejected(self):
        with self.assertRaises(ValueError):
            AwarenessFusion(None, UltrasonicRing(lambda i: 1),
                            CliffSensors(lambda i: 1), PoseFilter())


# ---------------------------------------------------------------------------
# motion.refine
# ---------------------------------------------------------------------------

class TestMovementRefiner(unittest.TestCase):
    def test_rejects_drive_without_methods(self):
        with self.assertRaises(ValueError):
            MovementRefiner(drive=object())

    def test_full_speed_when_clear(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        result = refiner.refined_forward(1.0, 0.5, make_fusion())
        self.assertTrue(result["moved"])
        self.assertAlmostEqual(result["speed_used"], 0.5)
        self.assertIn(("forward", 1.0, 0.5), drive.calls)

    def test_slows_in_slow_zone(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        fusion = make_fusion(echo_fn=lambda i: 0.7)
        result = refiner.refined_forward(1.0, 1.0, fusion)
        self.assertAlmostEqual(result["speed_used"], 0.3)

    def test_stops_in_stop_zone(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        fusion = make_fusion(echo_fn=lambda i: 0.1)
        result = refiner.refined_forward(1.0, 0.5, fusion)
        self.assertFalse(result["moved"])
        self.assertIn(("stop",), drive.calls)
        self.assertNotIn("forward", [c[0] for c in drive.calls])

    def test_cliff_forces_stop(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        fusion = make_fusion(cliff_fn=lambda i: 500.0)
        result = refiner.refined_forward(1.0, 0.5, fusion)
        self.assertFalse(result["moved"])
        self.assertIn("cliff", result["reason"])

    def test_detour_attempt_when_raycast_blocked(self):
        # Target dead ahead blocks the ray; after the first rotate the
        # target "walks away" (flag flips), so the detour succeeds.
        state = {"blocked": True}
        class FlagDrive(FakeDrive):
            def rotate(self, degrees):
                super().rotate(degrees)
                state["blocked"] = False  # detour clears the path
        def reader(i):
            if state["blocked"]:
                # 0.4 m dead ahead in the ROBOT frame (identity mounts)
                return [{"id": 1, "x_m": 0.4, "y_m": 0.0, "speed_mps": 0.0}]
            return []
        # identity mounts: sensor frame == robot frame for all 3
        identity = [(0.0, 0.0, 0.0)] * 3
        mm = MMWaveArray(reader, mounts=identity)
        fusion = AwarenessFusion(mm, UltrasonicRing(lambda i: 4.0),
                                 CliffSensors(lambda i: 20.0), PoseFilter())
        drive = FlagDrive()
        refiner = MovementRefiner(drive)
        # stop_m=0.2 keeps 0.4 m out of the must-stop zone
        refiner._policy = ProximityPolicy(stop_m=0.2, slow_m=0.8,
                                          caution_m=1.6)
        result = refiner.refined_forward(0.5, 0.5, fusion)
        self.assertTrue(result["moved"])
        self.assertTrue(result["detoured"])
        self.assertIn(("rotate", 30.0), drive.calls)

    def test_follow_target_steers_toward_bearing(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        fusion = make_fusion(
            mmwave_reader=lambda i: [{"id": 3, "x_m": 2.0, "y_m": 1.0,
                                      "speed_mps": 0.3}] if i == 0 else [])
        out = refiner.follow_target(fusion, drive, target_id=3)
        self.assertTrue(out["tracking"])
        self.assertTrue(any(c[0] == "rotate" and c[1] > 5.0
                            for c in drive.calls))

    def test_follow_lost_target_stops(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        out = refiner.follow_target(make_fusion(), drive, target_id=42)
        self.assertFalse(out["tracking"])
        self.assertIn(("stop",), drive.calls)


if __name__ == "__main__":
    unittest.main()
