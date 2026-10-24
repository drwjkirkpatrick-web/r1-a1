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
        lookahead = self._lookahead_m(meters, fusion.grid)
        if not fusion.grid.raycast_clear(0.0, lookahead):
            # one detour attempt each way, then give up politely.
            # Each attempt is relative to the ORIGINAL heading: rotate by
            # the delta from the current detour angle so the second
            # attempt actually probes the opposite side instead of
            # landing back on the (known-blocked) original ray.
            # Extra decay per attempt: from the robot's new heading the
            # stale ego-centric cells are less trustworthy, so fade them
            # faster before re-checking the ray.
            detour_deg = 0.0
            for sign in (+1, -1):
                target_deg = sign * DETOUR_DEG
                self._drive.rotate(target_deg - detour_deg)
                detour_deg = target_deg
                for _ in range(4):  # 0.9^4 ≈ 0.66 → 0.9 confidence → ~0.34
                    fusion.grid.decay()
                state = fusion.refresh()
                advice = self._policy.advise(state["nearest_m"], state["cliff"])
                if (not advice["must_stop"]
                        and fusion.grid.raycast_clear(0.0, lookahead)):
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
        hold ``distance_m`` standoff. The advance passes through the same
        safety gate as ``refined_forward``: proximity/cliff policy first,
        then an occupancy raycast along the heading — following a human
        must not drive blind toward a staircase or wall. Returns
        {'tracking': bool, 'moved': bool, ...}.
        """
        pos = fusion.mmwave.track(target_id)
        if pos is None:
            drive.stop()
            return {"tracking": False, "moved": False,
                    "reason": "target lost"}

        tx, ty = pos
        bearing = math.degrees(math.atan2(ty, tx))
        dist = math.hypot(tx, ty)

        if abs(bearing) > 5.0:
            drive.rotate(bearing)

        state = fusion.refresh()
        advice = self._policy.advise(state["nearest_m"], state["cliff"])
        if advice["must_stop"]:
            drive.stop()
            return {"tracking": True, "moved": False, "distance_m": dist,
                    "bearing_deg": bearing, "reason": advice["reason"]}

        moved = False
        gap = dist - distance_m
        if gap > 0.1:
            lookahead = self._lookahead_m(gap, fusion.grid)
            if fusion.grid.raycast_clear(0.0, lookahead):
                # gentle pursuit speed, further scaled by the policy
                drive.forward(gap, 0.4 * advice["max_speed_factor"])
                moved = True
            else:
                drive.stop()  # pursuit path blocked — hold, report
                return {"tracking": True, "moved": False,
                        "distance_m": dist, "bearing_deg": bearing,
                        "reason": "pursuit path blocked"}
        elif gap < -0.2:
            drive.stop()  # too close — hold position

        return {"tracking": True, "moved": moved, "distance_m": dist,
                "bearing_deg": bearing}

    # -- internals --------------------------------------------------------

    @staticmethod
    def _lookahead_m(meters: float, grid) -> float:
        """Clamp the raycast look-ahead to inside the grid's known bubble.

        The grid spans ``cells * cell_m`` metres across with the robot at
        its center, and cells outside that radius report as blocked
        ("unknown = blocked"). Raycasting the full command length would
        therefore refuse any command that reaches past the grid edge —
        including one landing exactly on it. Clamp the look-ahead half a
        cell inside the last known ring: a longer command is checked as
        far as the sensors can see and proceeds on that evidence.
        """
        limit = grid.cells * grid.cell_m / 2.0 - grid.cell_m / 2.0
        return min(max(0.5, meters), limit)
