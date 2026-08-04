"""Movement refinement — awareness-aware driving on top of Drive.

Wraps the raw ``Drive`` (which happily drives into walls if told to)
with the fused sensor picture:

* speed scaling from the proximity policy (slow near obstacles)
* hard pre-stop when the policy says must_stop (cliff / stop zone)
* one ±30° detour attempt when the occupancy raycast is blocked
* mmWave pursuit step for "follow that person"

Teaching note: this is deliberately a *reflex* layer, not a planner.
One look-ahead ray, one detour attempt, then stop and report. Anything
smarter belongs in a path planner upstream, not in the safety loop.
"""

from __future__ import annotations

import math

try:  # works both as src.motion.refine and (tests) top-level motion.refine
    from ..awareness.proximity import ProximityPolicy
except ImportError:  # pragma: no cover - layout-dependent fallback
    from awareness.proximity import ProximityPolicy

DETOUR_DEG = 30.0


class MovementRefiner:
    def __init__(self, drive, policy: ProximityPolicy | None = None):
        for method in ("forward", "rotate", "stop"):
            if not callable(getattr(drive, method, None)):
                raise ValueError(f"drive must expose {method}()")
        self._drive = drive
        self._policy = policy or ProximityPolicy()

    def refined_forward(self, meters: float, speed: float, fusion) -> dict:
        """Drive forward under the proximity policy.

        Returns a report: {'moved': bool, 'speed_used': float,
        'detoured': bool, 'reason': str}.
        """
        state = fusion.refresh()
        advice = self._policy.advise(state["nearest_m"], state["cliff"])

        if advice["must_stop"]:
            self._drive.stop()
            return {"moved": False, "speed_used": 0.0,
                    "detoured": False, "reason": advice["reason"]}

        detoured = False
        if not fusion.grid.raycast_clear(0.0, max(0.5, meters)):
            # one detour attempt each way, then give up politely.
            # Extra decay per attempt: from the robot's new heading the
            # stale ego-centric cells are less trustworthy, so fade them
            # faster before re-checking the ray.
            for sign in (+1, -1):
                self._drive.rotate(sign * DETOUR_DEG)
                for _ in range(4):  # 0.9^4 ≈ 0.66 → 0.9 confidence → ~0.34
                    fusion.grid.decay()
                state = fusion.refresh()
                advice = self._policy.advise(state["nearest_m"], state["cliff"])
                if (not advice["must_stop"]
                        and fusion.grid.raycast_clear(0.0, max(0.5, meters))):
                    detoured = True
                    break
            else:
                self._drive.stop()
                return {"moved": False, "speed_used": 0.0, "detoured": False,
                        "reason": "path blocked, no detour found"}

        speed_used = speed * advice["max_speed_factor"]
        self._drive.forward(meters, speed_used)
        return {"moved": True, "speed_used": speed_used,
                "detoured": detoured, "reason": advice["reason"]}

    def follow_target(self, fusion, drive, target_id: int,
                      distance_m: float = 1.0) -> dict:
        """One pursuit control step toward an mmWave-tracked target.

        Steers toward the target's smoothed position, advancing only to
        hold ``distance_m`` standoff. Returns {'tracking': bool, ...}.
        """
        pos = fusion.mmwave.track(target_id)
        if pos is None:
            drive.stop()
            return {"tracking": False, "reason": "target lost"}

        tx, ty = pos
        bearing = math.degrees(math.atan2(ty, tx))
        dist = math.hypot(tx, ty)

        if abs(bearing) > 5.0:
            drive.rotate(bearing)
        gap = dist - distance_m
        if gap > 0.1:
            drive.forward(gap, 0.4)  # gentle pursuit speed
        elif gap < -0.2:
            drive.stop()  # too close — hold position

        return {"tracking": True, "distance_m": dist,
                "bearing_deg": bearing}
