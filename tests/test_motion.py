"""Tests for the R1-A1 motion subsystem (src/motion/).

All tests run hardware-free against a FakeLink mock that captures
send(cmd, payload) calls.
"""

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from motion import (  # noqa: E402
    CenterLeg,
    Dome,
    DomeToleranceError,
    Drive,
    EstopTimeoutError,
    Express,
)


class FakeLink:
    """SerialLink stand-in: records every send() call."""

    def __init__(self):
        self.calls = []  # list of (cmd, payload)

    def send(self, cmd, payload):
        self.calls.append((cmd, payload))


class FakeClock:
    """Deterministic monotonic clock; each call advances by `step`."""

    def __init__(self, step=0.0):
        self.step = step
        self.now = 0.0

    def __call__(self):
        t = self.now
        self.now += self.step
        return t


class TestDrive(unittest.TestCase):
    def setUp(self):
        self.link = FakeLink()
        self.drive = Drive(self.link)

    def test_forward_sends_correct_command_and_payload(self):
        self.drive.forward(1.0, 0.5)
        self.assertEqual(self.link.calls,
                         [("drive.forward", {"meters": 1.0, "speed": 0.5})])

    def test_forward_rejects_nonpositive_speed(self):
        with self.assertRaises(ValueError):
            self.drive.forward(1.0, 0.0)
        self.assertEqual(self.link.calls, [])

    def test_rotate_sends_degrees(self):
        self.drive.rotate(180)
        self.assertEqual(self.link.calls,
                         [("drive.rotate", {"degrees": 180.0})])

    def test_stop_sends_stop_command(self):
        self.drive.stop()
        self.assertEqual(self.link.calls, [("drive.stop", {})])

    def test_odometry_straight_line(self):
        self.drive.forward(2.0, 0.5)
        x, y, heading = self.drive.odometry_read()
        self.assertAlmostEqual(x, 2.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(heading, 0.0)

    def test_odometry_rotate_then_forward(self):
        self.drive.rotate(90)          # face +y
        self.drive.forward(1.5, 0.5)
        x, y, heading = self.drive.odometry_read()
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 1.5, places=6)
        self.assertAlmostEqual(heading, 90.0)

    def test_odometry_full_turn_returns_to_zero_heading(self):
        self.drive.rotate(360)
        _, _, heading = self.drive.odometry_read()
        self.assertAlmostEqual(heading, 0.0)

    def test_odometry_square_path_returns_home(self):
        for _ in range(4):
            self.drive.forward(1.0, 0.5)
            self.drive.rotate(90)
        x, y, heading = self.drive.odometry_read()
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(y, 0.0, places=6)
        self.assertAlmostEqual(heading, 0.0)

    def test_estop_sends_stop_and_latches(self):
        self.drive.estop_soft()
        self.assertEqual(self.link.calls, [("drive.stop", {})])
        self.assertTrue(self.drive.estop_latched)

    def test_estop_within_budget_passes(self):
        clock = FakeClock(step=0.05)  # 50 ms send latency
        drive = Drive(self.link, clock=clock)
        drive.estop_soft()
        self.assertTrue(drive.estop_latched)

    def test_estop_over_budget_raises_but_still_latches(self):
        clock = FakeClock(step=0.20)  # 200 ms send latency > 100 ms budget
        drive = Drive(self.link, clock=clock)
        with self.assertRaises(EstopTimeoutError):
            drive.estop_soft()
        self.assertEqual(self.link.calls, [("drive.stop", {})])
        self.assertTrue(drive.estop_latched)

    def test_motion_refused_while_latched(self):
        self.drive.estop_soft()
        with self.assertRaises(RuntimeError):
            self.drive.forward(1.0, 0.5)
        with self.assertRaises(RuntimeError):
            self.drive.rotate(90)

    def test_clear_estop_restores_motion(self):
        self.drive.estop_soft()
        self.drive.clear_estop()
        self.assertFalse(self.drive.estop_latched)
        self.drive.forward(1.0, 0.5)
        self.assertIn(("drive.forward", {"meters": 1.0, "speed": 0.5}),
                      self.link.calls)


class TestDome(unittest.TestCase):
    def setUp(self):
        self.link = FakeLink()
        self.dome = Dome(self.link)

    def test_rotate_sends_degrees(self):
        self.dome.rotate_deg(-90)
        self.assertEqual(self.link.calls,
                         [("dome.rotate", {"degrees": -90.0})])

    def test_rotate_tracks_position(self):
        self.dome.rotate_deg(90)
        self.dome.rotate_deg(-30)
        self.assertAlmostEqual(self.dome.position_deg, 60.0)

    def test_rotate_within_tolerance_passes(self):
        self.dome.simulated_encoder_error_deg = 1.5  # within ±2°
        self.dome.rotate_deg(90)
        self.assertAlmostEqual(self.dome.position_deg, 91.5)

    def test_rotate_at_exact_tolerance_boundary_passes(self):
        self.dome.simulated_encoder_error_deg = Dome.TOLERANCE_DEG
        self.dome.rotate_deg(10)

    def test_rotate_beyond_tolerance_raises(self):
        self.dome.simulated_encoder_error_deg = 3.0  # exceeds ±2°
        with self.assertRaises(DomeToleranceError):
            self.dome.rotate_deg(90)

    def test_express_confused_sends_two_wags(self):
        self.dome.express("confused")
        expected = [("dome.rotate", {"degrees": d})
                    for d in (45.0, -45.0, 45.0, -45.0)]
        self.assertEqual(self.link.calls, expected)
        self.assertAlmostEqual(self.dome.position_deg, 0.0)

    def test_express_unknown_raises(self):
        with self.assertRaises(ValueError):
            self.dome.express("furious")
        self.assertEqual(self.link.calls, [])


class TestCenterLeg(unittest.TestCase):
    def setUp(self):
        self.link = FakeLink()
        self.leg = CenterLeg(self.link)

    def test_initially_retracted(self):
        self.assertFalse(self.leg.is_deployed())

    def test_deploy(self):
        self.leg.deploy()
        self.assertEqual(self.link.calls, [("leg.deploy", {})])
        self.assertTrue(self.leg.is_deployed())

    def test_retract(self):
        self.leg.deploy()
        self.leg.retract()
        self.assertEqual(self.link.calls,
                         [("leg.deploy", {}), ("leg.retract", {})])
        self.assertFalse(self.leg.is_deployed())


class TestExpress(unittest.TestCase):
    def setUp(self):
        self.link = FakeLink()
        self.drive = Drive(self.link)
        self.express = Express(self.drive)

    def test_wiggle_alternates_plus_minus_five_degrees(self):
        self.express.wiggle()
        expected = [("drive.rotate", {"degrees": d})
                    for d in (5.0, -5.0, 5.0, -5.0)]
        self.assertEqual(self.link.calls, expected)

    def test_wiggle_returns_to_original_heading(self):
        self.express.wiggle()
        _, _, heading = self.drive.odometry_read()
        self.assertTrue(math.isclose(heading, 0.0, abs_tol=1e-9))

    def test_wiggle_pulse_count(self):
        self.express.wiggle(pulses=2)
        self.assertEqual(len(self.link.calls), 2)

    def test_wiggle_rejects_nonpositive_pulses(self):
        with self.assertRaises(ValueError):
            self.express.wiggle(pulses=0)
        self.assertEqual(self.link.calls, [])


if __name__ == "__main__":
    unittest.main()
