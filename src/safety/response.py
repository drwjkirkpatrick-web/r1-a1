"""Emergency response — turn graded hazards into an ordered action plan.

``hazard.py`` judges what is wrong; this module decides what to *do*
about it, in what order, and which subsystems are allowed to keep
running while it is happening. SafetyController is the decision layer:
pure logic over Hazard objects, no threads, no hardware — the caller
executes the returned plan.

Response ladder (mirrors Hazard.escalation):

    level 1  WATCH      no automatic action (logged upstream)
    level 2  WARN       alert_operator
    level 3  ALERT      alert_operator, stop_drive
    level 4  EMERGENCY  alert_operator, stop_drive, seal_power,
                        broadcast_distress  (+ deploy_extinguisher for
                        fire / smoke / thermal_runaway)

Learning annotation
-------------------
1. **Emergency actions are *gated*, not merely sorted.** Extinguisher
   gas, sealed contactors, and a distress broadcast are one-way or
   disruptive acts. They appear in the plan ONLY when a level-4 hazard
   is present — a severity-8 alert must never fire the bottle.

2. **Interlocks are a deny-list per subsystem.** 'drive', 'charge',
   'projector', and 'welder' each have a rule naming the hazard types
   and escalation levels that make operation unsafe. Welding next to
   smoke or driving while tipped is forbidden even if nothing has
   reached level 4 yet — interlocks answer "may this run *now*?" which
   is a different question from "how do we respond?"

3. **Hysteresis kills alarm flapping.** A hazard hovering at the
   clear/raise boundary (smoke at 7, 6, 7, 6...) must not toggle
   relays every cycle. ``clear()`` only succeeds once severity has
   dropped at least ``CLEAR_HYSTERESIS`` (2) points below the worst
   recorded peak — one decisive crossing instead of many noisy ones.

4. **Acknowledge is bookkeeping, not silence.** ``acknowledge()``
   records that a human has seen the hazard; it changes neither the
   plan nor the interlocks. Safety must not be dismissable by accident.

5. **Peak tracking survives re-evaluation.** ``evaluate()`` updates the
   registry with the latest severity per hazard_id and keeps the
   running peak, so hysteresis always compares against the worst the
   hazard has ever been, not the last sample. Registration happens for
   EVERY evaluated hazard — including ones below their configured
   threshold — so a hazard that peaks and then subsides under the
   reporting threshold still refreshes its tracked severity and can
   clear; threshold filtering gates the *plan*, never the bookkeeping.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .hazard import Hazard, HazardType

#: Severity points a hazard must fall below its peak before clearing.
CLEAR_HYSTERESIS = 2

#: Actions unlocked at each escalation level, in execution order.
_LEVEL_ACTIONS = {
    1: (),
    2: ("alert_operator",),
    3: ("alert_operator", "stop_drive"),
    4: ("alert_operator", "stop_drive", "seal_power", "broadcast_distress"),
}

#: Hazard types that additionally trigger the fire bottle at level 4.
_INCENDIARY = frozenset(
    {HazardType.FIRE, HazardType.SMOKE, HazardType.THERMAL_RUNAWAY}
)

#: Systems that can be interlocked, with the hazard types that always
#: block them plus the minimum escalation level that blocks them.
INTERLOCK_RULES = {
    "drive": {
        "types": frozenset(
            {HazardType.TIP_OVER, HazardType.COLLISION_IMMINENT, HazardType.OBSTRUCTION}
        ),
        "min_level": 3,
    },
    "charge": {
        "types": frozenset(
            {
                HazardType.BATTERY_CRITICAL,
                HazardType.THERMAL_RUNAWAY,
                HazardType.FIRE,
                HazardType.SMOKE,
            }
        ),
        "min_level": 4,
    },
    "projector": {
        "types": frozenset({HazardType.THERMAL_RUNAWAY}),
        "min_level": 4,
    },
    "welder": {
        "types": frozenset(
            {
                HazardType.FIRE,
                HazardType.SMOKE,
                HazardType.THERMAL_RUNAWAY,
                HazardType.TIP_OVER,
            }
        ),
        "min_level": 3,
    },
}


class SafetyController:
    """Decision layer: plans responses, gates interlocks, tracks hazards.

    Parameters
    ----------
    thresholds:
        Optional per-hazard-type minimum severity (1-10) for a hazard to
        count as *active*. Below its threshold a hazard produces no plan
        actions and does not trip ``interlock()`` — e.g. ignore smoke
        below 4 in a dusty workshop — but ``evaluate()`` still tracks it
        so its severity/peak stay current for ``clear()``. Keys may be
        HazardType members or string values.
    """

    def __init__(self, thresholds: Optional[Dict] = None) -> None:
        self._thresholds: Dict[HazardType, int] = {}
        for raw_key, value in (thresholds or {}).items():
            try:
                key = HazardType(raw_key)
            except ValueError:
                raise ValueError(f"unknown hazard type in thresholds: {raw_key!r}") from None
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 10:
                raise ValueError(f"threshold for {key.value} must be an int in [1, 10]")
            self._thresholds[key] = value
        # Registry: hazard_id -> bookkeeping record (see _register()).
        self._registry: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # registry bookkeeping
    # ------------------------------------------------------------------
    def _threshold_for(self, hazard: Hazard) -> int:
        return self._thresholds.get(hazard.hazard_type, 1)

    def _is_active(self, hazard: Hazard) -> bool:
        return hazard.severity >= self._threshold_for(hazard)

    def _register(self, hazard: Hazard) -> None:
        """Insert/refresh a hazard, preserving peak and ack state."""
        entry = self._registry.get(hazard.hazard_id)
        if entry is None:
            self._registry[hazard.hazard_id] = {
                "hazard": hazard,
                "peak": hazard.severity,
                "acknowledged": False,
            }
        else:
            entry["hazard"] = hazard
            entry["peak"] = max(entry["peak"], hazard.severity)

    # ------------------------------------------------------------------
    # response planning
    # ------------------------------------------------------------------
    def evaluate(self, hazards: Iterable[Hazard]) -> List[dict]:
        """Return the ordered response plan for the given hazards.

        Every hazard is registered (refreshing its tracked severity and
        running peak for hysteresis) — even one below its threshold, so
        a subsided hazard can still clear later. Each hazard *above* its
        threshold contributes one action dict per action its escalation
        level unlocks::

            {"action": "stop_drive", "hazard_id": ..., "hazard_type": ...,
             "severity": ..., "escalation": ...}

        The plan is sorted most-urgent-first: escalation descending,
        then severity descending, so the caller can execute head-first.
        Emergency-only actions never appear below level 4.
        """
        plan: List[dict] = []
        for hazard in hazards:
            if not isinstance(hazard, Hazard):
                raise ValueError("evaluate() expects Hazard instances")
            self._register(hazard)
            if not self._is_active(hazard):
                continue
            level = hazard.escalation()
            actions = list(_LEVEL_ACTIONS[level])
            if level == 4 and hazard.hazard_type in _INCENDIARY:
                actions.append("deploy_extinguisher")
            for action in actions:
                plan.append(
                    {
                        "action": action,
                        "hazard_id": hazard.hazard_id,
                        "hazard_type": hazard.hazard_type.value,
                        "severity": hazard.severity,
                        "escalation": level,
                    }
                )
        plan.sort(key=lambda a: (-a["escalation"], -a["severity"], a["action"]))
        return plan

    # ------------------------------------------------------------------
    # interlocks
    # ------------------------------------------------------------------
    def interlock(self, system: str, hazards: Iterable[Hazard]) -> bool:
        """True when ``system`` may operate given the active hazards.

        A system is blocked when any hazard above its threshold either
        matches the system's deny-listed hazard types OR meets the
        system's minimum blocking escalation level. Unknown systems
        raise ValueError — a typo'd system name must fail loudly, never
        silently permit power.
        """
        rule = INTERLOCK_RULES.get(system)
        if rule is None:
            raise ValueError(
                f"unknown system {system!r}; known: {sorted(INTERLOCK_RULES)}"
            )
        for hazard in hazards:
            if not isinstance(hazard, Hazard):
                raise ValueError("interlock() expects Hazard instances")
            if not self._is_active(hazard):
                continue
            if hazard.hazard_type in rule["types"]:
                return False
            if hazard.escalation() >= rule["min_level"]:
                return False
        return True

    # ------------------------------------------------------------------
    # acknowledge / clear
    # ------------------------------------------------------------------
    def acknowledge(self, hazard_id: str) -> None:
        """Record that a human has seen the hazard. Bookkeeping only."""
        entry = self._registry.get(hazard_id)
        if entry is None:
            raise ValueError(f"unknown hazard_id: {hazard_id!r}")
        entry["acknowledged"] = True

    def clear(self, hazard_id: str) -> bool:
        """Attempt to clear a tracked hazard. True when removed.

        Hysteresis: clearing is refused while the hazard's current
        severity is within CLEAR_HYSTERESIS points of its recorded peak
        — the condition must *decisively* improve before we stand down.
        """
        entry = self._registry.get(hazard_id)
        if entry is None:
            raise ValueError(f"unknown hazard_id: {hazard_id!r}")
        if entry["hazard"].severity > entry["peak"] - CLEAR_HYSTERESIS:
            return False
        del self._registry[hazard_id]
        return True

    # ------------------------------------------------------------------
    # reporting / serialisation
    # ------------------------------------------------------------------
    def status_report(self) -> dict:
        """Snapshot of everything the controller is currently tracking."""
        active = [
            {
                **entry["hazard"].to_dict(),
                "escalation": entry["hazard"].escalation(),
                "peak_severity": entry["peak"],
                "acknowledged": entry["acknowledged"],
            }
            for entry in self._registry.values()
        ]
        active.sort(key=lambda h: (-h["escalation"], -h["severity"]))
        by_level = {1: 0, 2: 0, 3: 0, 4: 0}
        for entry in active:
            by_level[entry["escalation"]] += 1
        return {
            "active": active,
            "counts_by_level": by_level,
            "emergency": by_level[4] > 0,
            "acknowledged": [
                hid for hid, e in self._registry.items() if e["acknowledged"]
            ],
        }

    def to_dict(self) -> dict:
        """Serialise thresholds plus the full hazard registry."""
        return {
            "thresholds": {k.value: v for k, v in self._thresholds.items()},
            "registry": [
                {
                    "hazard": entry["hazard"].to_dict(),
                    "peak": entry["peak"],
                    "acknowledged": entry["acknowledged"],
                }
                for entry in self._registry.values()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SafetyController":
        """Rebuild a controller from ``to_dict()`` output."""
        ctl = cls(thresholds=data.get("thresholds"))
        for record in data.get("registry", []):
            hazard = Hazard.from_dict(record["hazard"])
            ctl._registry[hazard.hazard_id] = {
                "hazard": hazard,
                "peak": record["peak"],
                "acknowledged": bool(record["acknowledged"]),
            }
        return ctl
