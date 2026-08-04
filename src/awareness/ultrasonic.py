"""Ultrasonic ring — 4× HC-SR04P under the skirt at 45°/135°/225°/315°.

mmWave is great at finding *moving humans* but nearly blind to a chair
leg; cheap ultrasonic rangers fill that gap for mid-range static
obstacles. Each sensor: MCU pulses a trigger pin, times the echo pin,
converts to meters — that timing lives on the MCU; here we just inject:

    echo_fn(sensor_index) -> distance in meters (float)

Teaching note: HC-SR04 range ≈ 2 cm–4 m, beam ≈ ±15°, so four sensors
at 90° spacing leave coverage gaps — the fusion layer cross-checks with
mmWave before declaring a sector clear.
"""

from __future__ import annotations

import math

SENSOR_HEADINGS_DEG = (45.0, 135.0, 225.0, 315.0)
MAX_RANGE_M = 4.0  # beyond this an HC-SR04 reading is noise


class UltrasonicRing:
    def __init__(self, echo_fn, headings_deg=SENSOR_HEADINGS_DEG):
        if not callable(echo_fn):
            raise ValueError("echo_fn must be callable: echo_fn(index) -> meters")
        if len(headings_deg) != 4:
            raise ValueError("exactly 4 sensors required")
        self._echo = echo_fn
        self._headings = tuple(headings_deg)

    def distances(self) -> list[float]:
        """Latest distance from each sensor, clamped to sane range."""
        out = []
        for i in range(len(self._headings)):
            d = max(0.02, min(MAX_RANGE_M, float(self._echo(i))))
            out.append(d)
        return out

    def nearest(self) -> tuple[float, float]:
        """(distance_m, heading_deg) of the closest reading."""
        dists = self.distances()
        idx = min(range(len(dists)), key=dists.__getitem__)
        return dists[idx], self._headings[idx]

    def sector_clear(self, heading_deg: float, min_m: float) -> bool:
        """True when the sensor nearest to ``heading_deg`` reads ≥ min_m."""
        if min_m <= 0:
            raise ValueError("min_m must be positive")
        dists = self.distances()
        # nearest sensor by angular distance
        best = min(
            range(len(self._headings)),
            key=lambda i: abs((self._headings[i] - heading_deg + 180) % 360 - 180),
        )
        return dists[best] >= min_m
