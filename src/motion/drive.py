"""Differential-drive base control for R1-A1.

Wraps the SerialLink to the MCU. Tracks a dead-reckoned odometry
estimate (x, y in meters, heading in degrees) so behavior can be
verified without hardware.
"""

import math
import time


class EstopTimeoutError(RuntimeError):
    """Soft e-stop failed to get its stop command out within budget."""


class Drive:
    """Two-motor scooter drive (Cytron MD30C drivers, PWM+dir from MCU).

    Commands:
      drive.forward  {meters, speed}
      drive.rotate   {degrees}
      drive.stop     {}

    Soft e-stop budget: the stop command must be handed to the link
    within ESTOP_BUDGET_S seconds, per docs/PROMPTS.md #12.
    """

    ESTOP_BUDGET_S = 0.100  # 100 ms

    def __init__(self, link, clock=time.perf_counter):
        """
        Args:
            link: SerialLink-like object with send(cmd, payload).
            clock: monotonic clock callable (injectable for tests).
        """
        self.link = link
        self._clock = clock
        self._x = 0.0
        self._y = 0.0
        self._heading_deg = 0.0
        # Learning: timestamp every pose update so downstream consumers
        # (fusion, logging, dashboard) can tell a fresh odometry fix
        # from a stale one after a long stop.
        self._last_update_s = clock()
        self.estop_latched = False

    # -- motion -----------------------------------------------------------

    def forward(self, meters, speed):
        """Drive forward `meters` at `speed` (m/s, 0.0-1.0 normalized).

        Raises RuntimeError while the soft e-stop is latched.
        """
        self._check_latched()
        if speed <= 0:
            raise ValueError("speed must be positive")
        self.link.send("drive.forward", {"meters": float(meters),
                                         "speed": float(speed)})
        rad = math.radians(self._heading_deg)
        self._x += meters * math.cos(rad)
        self._y += meters * math.sin(rad)
        self._last_update_s = self._clock()

    def rotate(self, degrees):
        """Rotate in place. Positive = counterclockwise (left)."""
        self._check_latched()
        self.link.send("drive.rotate", {"degrees": float(degrees)})
        self._heading_deg = (self._heading_deg + degrees) % 360.0
        self._last_update_s = self._clock()

    def stop(self):
        """Normal stop. Always allowed, even when e-stop is latched."""
        self.link.send("drive.stop", {})

    # -- safety -----------------------------------------------------------

    def estop_soft(self):
        """Soft emergency stop.

        Sends drive.stop and verifies the send completed within the
        100 ms budget. Latches estop_latched regardless of outcome;
        motion commands are refused until the latch is cleared.

        Raises EstopTimeoutError if the budget was exceeded (the stop
        was still sent — the flag and exception report the lateness).
        """
        t0 = self._clock()
        self.link.send("drive.stop", {})
        elapsed = self._clock() - t0
        self.estop_latched = True
        if elapsed > self.ESTOP_BUDGET_S:
            raise EstopTimeoutError(
                f"soft e-stop send took {elapsed * 1000:.1f} ms "
                f"(budget {self.ESTOP_BUDGET_S * 1000:.0f} ms)")

    def clear_estop(self):
        """Release the soft e-stop latch (operator action)."""
        self.estop_latched = False

    # -- telemetry --------------------------------------------------------

    def odometry_read(self):
        """Return dead-reckoned pose estimate: (x, y, heading_deg)."""
        return (self._x, self._y, self._heading_deg)

    def odometry_age_s(self) -> float:
        """Seconds since the last pose update (freshness of the fix)."""
        return self._clock() - self._last_update_s

    def odometry(self) -> dict:
        """Pose plus freshness metadata as a dict (dashboard/fusion use)."""
        return {
            "x": self._x,
            "y": self._y,
            "heading_deg": self._heading_deg,
            "age_s": self.odometry_age_s(),
        }

    # -- internals --------------------------------------------------------

    def _check_latched(self):
        if self.estop_latched:
            raise RuntimeError(
                "soft e-stop latched; call clear_estop() before motion")
