"""Hazard assessment — what is wrong, how bad is it, can we fix it ourselves?

The safety layer sits *above* the sensor loops (cliff, thermal, power).
Those modules report measurements; this module turns measurements into
graded hazards with an escalation level the rest of the robot can act
on. A hazard is a value object: it carries no behaviour that touches
hardware, only judgement.

Severity is an integer 1-10 assigned by whatever detected the hazard
(sensor fusion, thermal policy, the operator). Escalation compresses
that into four response bands so downstream code switches on a small,
stable set of levels instead of re-deriving thresholds everywhere:

    severity 1-3   -> level 1  WATCH      log it, keep driving
    severity 4-6   -> level 2  WARN       tell the operator
    severity 7-8   -> level 3  ALERT      stop moving, raise the alarm
    severity 9-10  -> level 4  EMERGENCY  full response set unlocked

Learning annotation
-------------------
1. **Levels, not raw numbers, drive response.** A 4-band escalation
   ladder is the standard industrial pattern (advisory / warning /
   critical / emergency). Callers ask "what level?" and get a stable
   contract even if the severity thresholds are retuned later.

2. **``auto_resolvable`` is a policy hint, not a capability proof.**
   An OBSTRUCTION can usually be cleared by backing up and rerouting;
   a THERMAL_RUNAWAY cannot — the cell keeps cooking no matter what
   the software does. The response planner uses this to decide whether
   "handle it ourselves" is even on the menu before calling for help.

3. **Injected clock for ``first_seen``.** How long a hazard has been
   active matters (a 200 ms smoke blip is not a fire), and injected
   time keeps duration logic deterministic under test.

4. **Hysteresis lives in the controller, not here.** Hazard is a
   snapshot; the *history* of a hazard (peak severity, acknowledged,
   cleared) is response-bookkeeping and belongs to SafetyController.
"""

from __future__ import annotations

import time
from enum import Enum
from numbers import Real
from typing import Callable, Optional


class HazardType(str, Enum):
    """The catalogue of things that can go badly wrong on a 38 kg droid.

    String-valued so hazards serialise to readable JSON without a
    custom encoder.
    """

    FIRE = "fire"
    SMOKE = "smoke"
    THERMAL_RUNAWAY = "thermal_runaway"
    TIP_OVER = "tip_over"
    COLLISION_IMMINENT = "collision_imminent"
    BATTERY_CRITICAL = "battery_critical"
    OBSTRUCTION = "obstruction"


#: Hazard types the droid can plausibly resolve without a human:
#: stop driving / back up / reroute. Everything else needs the operator.
AUTO_RESOLVABLE = frozenset(
    {HazardType.OBSTRUCTION, HazardType.COLLISION_IMMINENT}
)

#: Escalation level names, indexed by level (0 unused so level N -> [N]).
ESCALATION_LEVELS = ("none", "watch", "warn", "alert", "emergency")

#: Minimum severity (inclusive) for each escalation band boundary.
_WATCH_MAX = 3
_WARN_MAX = 6
_ALERT_MAX = 8


def _validate_severity(value) -> float:
    """Coerce + validate a severity; raises ValueError when invalid."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("severity must be a number in [1, 10]")
    sev = float(value)
    if not 1.0 <= sev <= 10.0:
        raise ValueError(f"severity out of range [1, 10]: {value!r}")
    return sev


class Hazard:
    """One detected hazard: type, severity 1-10, source, first-seen time.

    Parameters
    ----------
    hazard_type:
        ``HazardType`` member or its string value (``"fire"`` etc.).
    severity:
        Number in [1, 10]. 1 = cosmetic, 10 = imminent loss of the droid.
    source:
        Human-readable origin, e.g. ``"thermal.bay"`` or ``"mmwave[1]"``.
    hazard_id:
        Stable identity for bookkeeping. Defaults to ``type:source`` so
        re-detections of the same condition update one registry entry.
    time_fn:
        Clock callable, injected for deterministic tests.
    """

    def __init__(
        self,
        hazard_type,
        severity,
        source: str,
        hazard_id: Optional[str] = None,
        time_fn: Callable[[], float] = time.time,
    ) -> None:
        try:
            self.hazard_type = HazardType(hazard_type)
        except ValueError:
            raise ValueError(f"unknown hazard type: {hazard_type!r}") from None
        sev = _validate_severity(severity)
        self.severity = int(sev) if sev.is_integer() else sev
        if not isinstance(source, str) or not source:
            raise ValueError("source must be a non-empty description string")
        if not callable(time_fn):
            raise ValueError("time_fn must be callable: time_fn() -> float")
        self.source = source
        self.hazard_id = hazard_id or f"{self.hazard_type.value}:{source}"
        self.first_seen: float = float(time_fn())

    def escalation(self) -> int:
        """Escalation level 1-4 (watch / warn / alert / emergency)."""
        if self.severity <= _WATCH_MAX:
            return 1
        if self.severity <= _WARN_MAX:
            return 2
        if self.severity <= _ALERT_MAX:
            return 3
        return 4

    def escalation_name(self) -> str:
        """Human name of the current escalation level."""
        return ESCALATION_LEVELS[self.escalation()]

    def auto_resolvable(self) -> bool:
        """True when the droid can plausibly clear this without a human.

        Obstructions and imminent collisions yield to stop/back-up/
        reroute. Fire, smoke, thermal runaway, tip-over, and a dying
        battery all require operator intervention.
        """
        return self.hazard_type in AUTO_RESOLVABLE

    def set_severity(self, severity) -> None:
        """Update severity in place (same validation as construction).

        Used by the response controller when a tracked hazard is
        re-evaluated with a fresh reading.
        """
        sev = _validate_severity(severity)
        self.severity = int(sev) if sev.is_integer() else sev

    def to_dict(self) -> dict:
        """Plain-data snapshot for serialisation."""
        return {
            "hazard_id": self.hazard_id,
            "hazard_type": self.hazard_type.value,
            "severity": self.severity,
            "source": self.source,
            "first_seen": self.first_seen,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Hazard":
        """Rebuild a Hazard from ``to_dict()`` output.

        ``first_seen`` is restored after construction (the clock would
        otherwise stamp 'now').
        """
        hz = cls(
            hazard_type=data["hazard_type"],
            severity=data["severity"],
            source=data["source"],
            hazard_id=data.get("hazard_id"),
        )
        hz.first_seen = float(data["first_seen"])
        return hz

    def __repr__(self) -> str:  # debugging aid only
        return (
            f"Hazard({self.hazard_type.value!r}, severity={self.severity}, "
            f"source={self.source!r})"
        )
