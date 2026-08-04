"""Pose fusion — complementary filter over wheel odometry + BNO085 IMU.

Wheel odometry drifts (slip, carpet, caster wobble); an absolute IMU
heading yaws slowly (gyro bias). A complementary filter takes the
*fast* changes from odometry and the *slow absolute truth* from the IMU:

    heading += odom_dheading                      # fast path
    heading += α · wrap(imu_heading − heading)    # slow correction

with α small (0.02) so the IMU only nudges. Position integrates the
odometry deltas in the fused heading frame.

This is intentionally *not* a Kalman filter — on a differential-drive
robot at walking speed a complementary filter is within a couple of
degrees of one and is 20 lines instead of 200.
"""

from __future__ import annotations

import math


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


class PoseFilter:
    def __init__(self, alpha: float = 0.02):
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        self._alpha = alpha
        self.reset()

    def reset(self) -> None:
        self._x = 0.0
        self._y = 0.0
        self._heading = 0.0  # degrees, 0 = +x (forward at boot)

    def update(
        self,
        odom_dx: float,
        odom_dy: float,
        odom_dheading: float,
        imu_heading_deg: float,
        dt: float,
    ) -> None:
        """Fold one sensor tick into the estimate.

        ``odom_*`` are deltas since last tick (meters, degrees);
        ``imu_heading_deg`` is the IMU's absolute heading; ``dt`` is the
        tick period in seconds (kept for interface completeness / future
        gyro-rate path).
        """
        if dt <= 0:
            raise ValueError("dt must be positive")
        # fast path: odometry deltas
        h = math.radians(self._heading)
        self._x += odom_dx * math.cos(h) - odom_dy * math.sin(h)
        self._y += odom_dx * math.sin(h) + odom_dy * math.cos(h)
        self._heading += odom_dheading
        # slow path: IMU absolute correction
        err = _wrap180(imu_heading_deg - self._heading)
        self._heading += self._alpha * err
        self._heading = _wrap180(self._heading)

    def pose(self) -> tuple[float, float, float]:
        """(x_m, y_m, heading_deg) in the boot-relative map frame."""
        return self._x, self._y, self._heading
