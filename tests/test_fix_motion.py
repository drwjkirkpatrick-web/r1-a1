"""Regression tests for the motion-safety findings in docs/CODE_REVIEW.md.

Covers:
  F6  — MovementRefiner detour loop must probe BOTH sides of the
        original heading, not re-test the (blocked) original ray.
  F7  — a forward command reaching the occupancy-grid extent (≥ 2.0 m)
        must not be refused just because the ray leaves the known bubble.
  F17 — Drive.estop_soft must latch locally even when link.send raises.
  F28 — follow_target must pass through the same proximity/cliff/raycast
        safety gate as refined_forward.

All hardware is faked — no radar, rangers, IMU, or serial link attached.
Run: python3 -m pytest tests/test_fix_motion.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.awareness.mmwave import MMWaveArray
from src.awareness.ultrasonic import UltrasonicRing
from src.awareness.cliff import CliffSensors
from src.awareness.pose import PoseFilter
from src.awareness.fusion import AwarenessFusion
from src.motion.drive import Drive, EstopTimeoutError
from src.motion.refine import MovementRefiner, DETOUR_DEG


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

    def net_rotation(self):
        return sum(c[1] for c in self.calls if c[0] == "rotate")


def make_fusion(mmwave_reader=None, echo_fn=None, cliff_fn=None):
    mm = MMWaveArray(mmwave_reader or (lambda i: []))
    us = UltrasonicRing(echo_fn or (lambda i: 4.0))
    cl = CliffSensors(cliff_fn or (lambda i: 20.0))
    pose = PoseFilter()
    return AwarenessFusion(mm, us, cl, pose)


IDENTITY_MOUNTS = [(0.0, 0.0, 0.0)] * 3  # sensor frame == robot frame


# ---------------------------------------------------------------------------
# F6 — detour loop probes both sides
# ---------------------------------------------------------------------------

class StubGrid:
    """Ego-grid stand-in: an obstacle dead ahead in the WORLD frame.

    ``heading_deg`` tracks the robot's accumulated rotation; the forward
    ray reads clear only once the robot has turned at least 20° to the
    RIGHT (negative). Both the original heading and a +30° (left) detour
    stay blocked, so a successful detour proves the −30° side was truly
    probed — under the old code the second attempt rotated −30° from
    +30°, landing back on the blocked original heading.
    """

    cells = 40
    cell_m = 0.1

    def __init__(self):
        self.heading_deg = 0.0

    def raycast_clear(self, heading_deg, max_m):
        return self.heading_deg <= -20.0

    def decay(self):
        pass


class StubFusion:
    def __init__(self, grid):
        self.grid = grid

    def refresh(self):
        return {"nearest_m": 9.9, "cliff": False}


class TestDetourProbesOppositeSide(unittest.TestCase):
    def test_detour_deviates_from_blocked_heading(self):
        grid = StubGrid()

        class RotDrive(FakeDrive):
            def rotate(self, degrees):
                super().rotate(degrees)
                grid.heading_deg += degrees

        drive = RotDrive()
        refiner = MovementRefiner(drive)
        result = refiner.refined_forward(1.0, 0.5, StubFusion(grid))

        self.assertTrue(result["moved"])
        self.assertTrue(result["detoured"])
        # the chosen detour actually left the original (blocked) heading
        self.assertAlmostEqual(drive.net_rotation(), -DETOUR_DEG)
        # first attempt +30°, second attempt the −60° delta to reach −30°
        rotates = [c[1] for c in drive.calls if c[0] == "rotate"]
        self.assertEqual(rotates, [DETOUR_DEG, -2 * DETOUR_DEG])

    def test_detour_gives_up_when_both_sides_blocked(self):
        class BlockedGrid(StubGrid):
            def raycast_clear(self, heading_deg, max_m):
                return False

        grid = BlockedGrid()

        class RotDrive(FakeDrive):
            def rotate(self, degrees):
                super().rotate(degrees)
                grid.heading_deg += degrees

        drive = RotDrive()
        refiner = MovementRefiner(drive)
        result = refiner.refined_forward(1.0, 0.5, StubFusion(grid))
        self.assertFalse(result["moved"])
        self.assertIn("no detour", result["reason"])
        self.assertNotIn("forward", [c[0] for c in drive.calls])


# ---------------------------------------------------------------------------
# F7 — commands at/past the grid extent are not refused
# ---------------------------------------------------------------------------

class TestGridExtentBoundary(unittest.TestCase):
    def test_forward_exactly_at_grid_extent_moves(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        # empty grid, clear sensors: 2.0 m == the 40×0.1 m grid radius
        result = refiner.refined_forward(2.0, 0.5, make_fusion())
        self.assertTrue(result["moved"])
        self.assertIn(("forward", 2.0, 0.5), drive.calls)

    def test_forward_beyond_grid_extent_moves(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        result = refiner.refined_forward(3.5, 0.5, make_fusion())
        self.assertTrue(result["moved"])
        self.assertIn(("forward", 3.5, 0.5), drive.calls)

    def test_lookahead_clamped_inside_bubble(self):
        fusion = make_fusion()
        limit = MovementRefiner._lookahead_m(3.5, fusion.grid)
        radius = fusion.grid.cells * fusion.grid.cell_m / 2.0
        self.assertLess(limit, radius)
        # short commands keep the old 0.5 m minimum look-ahead
        self.assertEqual(MovementRefiner._lookahead_m(0.1, fusion.grid), 0.5)


# ---------------------------------------------------------------------------
# F17 — estop_soft latches even when the link is down
# ---------------------------------------------------------------------------

class DeadLink:
    def __init__(self):
        self.calls = []

    def send(self, cmd, payload):
        self.calls.append((cmd, payload))
        raise OSError("serial port vanished")


class TestEstopLatchesOnLinkFailure(unittest.TestCase):
    def test_estop_latches_when_send_raises(self):
        drive = Drive(DeadLink())
        with self.assertRaises(EstopTimeoutError):
            drive.estop_soft()
        self.assertTrue(drive.estop_latched)

    def test_motion_refused_after_failed_estop(self):
        drive = Drive(DeadLink())
        with self.assertRaises(EstopTimeoutError):
            drive.estop_soft()
        with self.assertRaises(RuntimeError):
            drive.forward(1.0, 0.5)
        with self.assertRaises(RuntimeError):
            drive.rotate(90)

    def test_link_failure_chained_and_send_attempted(self):
        link = DeadLink()
        drive = Drive(link)
        with self.assertRaises(EstopTimeoutError) as ctx:
            drive.estop_soft()
        self.assertIsInstance(ctx.exception.__cause__, OSError)
        self.assertEqual(link.calls, [("drive.stop", {})])  # still tried


# ---------------------------------------------------------------------------
# F28 — follow_target obeys the proximity/cliff safety gate
# ---------------------------------------------------------------------------

class TestFollowTargetSafetyGate(unittest.TestCase):
    def _fusion(self, echo=4.0, cliff=20.0):
        def reader(i):
            if i == 0:
                return [{"id": 3, "x_m": 2.0, "y_m": 0.0, "speed_mps": 0.0}]
            return []
        mm = MMWaveArray(reader, mounts=IDENTITY_MOUNTS)
        return AwarenessFusion(mm, UltrasonicRing(lambda i: echo),
                               CliffSensors(lambda i: cliff), PoseFilter())

    def test_clear_path_advances(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        out = refiner.follow_target(self._fusion(), drive, target_id=3)
        self.assertTrue(out["tracking"])
        self.assertTrue(out["moved"])
        # target at 2.0 m, 1.0 m standoff → advance the 1.0 m gap
        self.assertIn(("forward", 1.0, 0.4), drive.calls)

    def test_stop_zone_blocks_pursuit(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        out = refiner.follow_target(self._fusion(echo=0.1), drive,
                                    target_id=3)
        self.assertTrue(out["tracking"])   # target still visible
        self.assertFalse(out["moved"])
        self.assertIn(("stop",), drive.calls)
        self.assertNotIn("forward", [c[0] for c in drive.calls])

    def test_cliff_blocks_pursuit(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        out = refiner.follow_target(self._fusion(cliff=500.0), drive,
                                    target_id=3)
        self.assertTrue(out["tracking"])
        self.assertFalse(out["moved"])
        self.assertIn("cliff", out["reason"])
        self.assertNotIn("forward", [c[0] for c in drive.calls])

    def test_blocked_ray_holds_position(self):
        drive = FakeDrive()
        refiner = MovementRefiner(drive)
        fusion = self._fusion()
        # wall dead ahead at 0.8 m: past the stop zone but on the ray
        fusion.grid.update_from_ultrasonic([0.8], [0.0])
        out = refiner.follow_target(fusion, drive, target_id=3)
        self.assertTrue(out["tracking"])
        self.assertFalse(out["moved"])
        self.assertEqual(out["reason"], "pursuit path blocked")
        self.assertNotIn("forward", [c[0] for c in drive.calls])


if __name__ == "__main__":
    unittest.main()
