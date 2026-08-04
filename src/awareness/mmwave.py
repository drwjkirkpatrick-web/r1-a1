"""mmWave presence + tracking array — 3× Hi-Link LD2450 24 GHz radar.

The LD2450 reports up to 3 tracked humans per sensor as (x, y, speed)
in the *sensor* frame. We mount three of them (front-left skirt,
front-right skirt, rear) and merge everything into the robot frame so
the rest of the stack never thinks about mounting geometry.

Hardware wiring (docs/HARDWARE.md §2): each LD2450 talks UART; a small
USB-serial hub in the body brings all three to the host. The injected
``reader`` callable abstracts that away:

    reader(sensor_index) -> [{"id": int, "x_m": float, "y_m": float,
                              "speed_mps": float}, ...]

Teaching note — frame transform: each sensor is mounted at (offset_x,
offset_y, yaw). A point in the sensor frame maps to the robot frame by
rotating by the mount yaw then translating by the mount offset:

    x_r = x_s·cos(yaw) − y_s·sin(yaw) + offset_x
    y_r = x_s·sin(yaw) + y_s·cos(yaw) + offset_y
"""

from __future__ import annotations

import math

# (offset_x_m, offset_y_m, yaw_deg) per sensor, robot frame.
# +x forward, +y left. Front-left skirt, front-right skirt, rear.
DEFAULT_MOUNTS = (
    (0.18, 0.15, 30.0),     # front-left, angled outward
    (0.18, -0.15, -30.0),   # front-right, angled outward
    (-0.20, 0.0, 180.0),    # rear, facing backward
)


class MMWaveArray:
    """Merge three LD2450 radars into a robot-frame target picture."""

    def __init__(self, reader, mounts=DEFAULT_MOUNTS, ema_alpha: float = 0.4):
        if not callable(reader):
            raise ValueError("reader must be callable: reader(index) -> targets")
        if len(mounts) != 3:
            raise ValueError("exactly 3 sensor mounts required")
        if not 0.0 < ema_alpha <= 1.0:
            raise ValueError("ema_alpha must be in (0, 1]")
        self._reader = reader
        self._mounts = tuple(mounts)
        self._alpha = ema_alpha
        self._tracks: dict[int, tuple[float, float]] = {}  # EMA state

    # -- scanning ------------------------------------------------------

    def scan(self) -> list[dict]:
        """Poll all sensors; return merged targets in the robot frame."""
        merged: list[dict] = []
        for idx, (ox, oy, yaw_deg) in enumerate(self._mounts):
            yaw = math.radians(yaw_deg)
            cos_y, sin_y = math.cos(yaw), math.sin(yaw)
            for t in self._reader(idx) or []:
                xs, ys = float(t["x_m"]), float(t["y_m"])
                merged.append(
                    {
                        "id": int(t.get("id", 0)),
                        "sensor": idx,
                        "x_m": xs * cos_y - ys * sin_y + ox,
                        "y_m": xs * sin_y + ys * cos_y + oy,
                        "speed_mps": float(t.get("speed_mps", 0.0)),
                    }
                )
        return merged

    def nearest_target(self) -> dict | None:
        """Closest tracked target by radial distance, or None."""
        targets = self.scan()
        if not targets:
            return None
        return min(targets, key=lambda t: math.hypot(t["x_m"], t["y_m"]))

    def human_present(self) -> bool:
        """True when any sensor currently tracks at least one target."""
        return any(self._reader(i) for i in range(len(self._mounts)))

    # -- tracking ------------------------------------------------------

    def track(self, target_id: int) -> tuple[float, float] | None:
        """EMA-smoothed robot-frame position for ``target_id``.

        Each call polls the sensors; when the id is visible its position
        folds into the running average (alpha = new-sample weight).
        Returns None while the id isn't visible.
        """
        for t in self.scan():
            if t["id"] != target_id:
                continue
            prev = self._tracks.get(target_id)
            if prev is None:
                smoothed = (t["x_m"], t["y_m"])
            else:
                a = self._alpha
                smoothed = (
                    a * t["x_m"] + (1 - a) * prev[0],
                    a * t["y_m"] + (1 - a) * prev[1],
                )
            self._tracks[target_id] = smoothed
            return smoothed
        return None
