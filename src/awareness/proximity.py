"""Proximity policy — how fast may we drive given what's around us.

Three zones around the robot:

    stop     < 0.3 m   →  0.0  (never drive into it)
    slow     < 1.0 m   →  0.3
    caution  < 2.0 m   →  0.6
    clear   ≥ 2.0 m    →  1.0

A cliff reading overrides everything: must_stop regardless of distance.
The policy only *advises* — motion/refine.py enforces it against Drive.
"""

from __future__ import annotations

STOP_M = 0.3
SLOW_M = 1.0
CAUTION_M = 2.0


class ProximityPolicy:
    def __init__(self, stop_m: float = STOP_M, slow_m: float = SLOW_M,
                 caution_m: float = CAUTION_M):
        if not 0 < stop_m < slow_m < caution_m:
            raise ValueError("need 0 < stop_m < slow_m < caution_m")
        self.stop_m = stop_m
        self.slow_m = slow_m
        self.caution_m = caution_m

    def speed_factor(self, distance_m: float) -> float:
        d = float(distance_m)
        if d < self.stop_m:
            return 0.0
        if d < self.slow_m:
            return 0.3
        if d < self.caution_m:
            return 0.6
        return 1.0

    def advise(self, nearest_obstacle_m: float, cliff: bool) -> dict:
        factor = self.speed_factor(nearest_obstacle_m)
        if cliff:
            return {
                "max_speed_factor": 0.0,
                "must_stop": True,
                "reason": "cliff detected",
            }
        if factor == 0.0:
            reason = f"obstacle at {nearest_obstacle_m:.2f} m (stop zone)"
        elif factor < 1.0:
            reason = f"obstacle at {nearest_obstacle_m:.2f} m (slow zone)"
        else:
            reason = "clear"
        return {
            "max_speed_factor": factor,
            "must_stop": factor == 0.0,
            "reason": reason,
        }
