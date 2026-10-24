"""Bond engine — how much R1-A1 trusts, prioritizes, and protects each operator.

A loyal astromech is not born loyal; the bond is earned interaction by
interaction and lost through neglect. BondEngine keeps a 0..100 bond
score per operator id. Interactions add points; days of silence erode
the score linearly until it reaches the level below. The level, not
the raw score, drives behavior:

    WARY        — a stranger; minimal priority, no protective reflex
    ACQUAINTED  — a familiar face
    TRUSTED     — requests get a bump; threats trigger an alert
    LOYAL       — strong priority, alert on moderate threats
    DEVOTED     — maximum priority; alert on even minor threats

Decay uses an injected time_fn (POSIX seconds) so neglect tests can
fast-forward months without sleeping. Scores never decay below zero
and never exceed the cap; a DEVOTED operator who vanishes for a year
slides back down the ladder one level at a time, which is exactly how
it should feel.

Learning annotation: we decay the *score* and derive the *level* from
thresholds rather than decaying levels directly, so upgrades and
downgrades are symmetric and hysteresis-free — a level boundary is
just "score crossed a line", easy to reason about and easy to test.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Callable

SCORE_CAP = 100.0
DEFAULT_DECAY_PER_DAY = 1.0
SECONDS_PER_DAY = 86400.0

# Score thresholds: effective score >= threshold -> level.
LEVEL_THRESHOLDS = (
    (80.0, "DEVOTED"),
    (60.0, "LOYAL"),
    (40.0, "TRUSTED"),
    (20.0, "ACQUAINTED"),
    (0.0, "WARY"),
)

# Minimum threat_level that triggers a protective escalation, per level.
# Deeper bond -> the unit acts on weaker evidence of danger.
ALERT_THRESHOLDS = {"TRUSTED": 0.6, "LOYAL": 0.4, "DEVOTED": 0.25}

GREETINGS = {
    "WARY": "*cautious warble* ...state your business.",
    "ACQUAINTED": "*friendly chirp* Oh, hello again.",
    "TRUSTED": "*bright trill* Good to see you. How can I help?",
    "LOYAL": "*joyful whistle* There you are! Ready when you are.",
    "DEVOTED": "*ecstatic beeping cascade* You're back! I've missed you.",
}


class BondLevel(IntEnum):
    """Ordered trust levels; IntEnum so levels compare directly."""

    WARY = 0
    ACQUAINTED = 1
    TRUSTED = 2
    LOYAL = 3
    DEVOTED = 4

    @classmethod
    def from_score(cls, score: float) -> "BondLevel":
        """Map an effective bond score to its level via LEVEL_THRESHOLDS."""
        for threshold, name in LEVEL_THRESHOLDS:
            if score >= threshold:
                return cls[name]
        return cls.WARY  # unreachable; kept as a defensive floor


class BondEngine:
    """Per-operator bond scores with neglect decay and bond-driven behavior."""

    def __init__(
        self,
        time_fn: Callable[[], float] | None = None,
        decay_per_day: float = DEFAULT_DECAY_PER_DAY,
    ):
        if time_fn is not None and not callable(time_fn):
            raise ValueError("time_fn must be callable: time_fn() -> POSIX seconds")
        if decay_per_day < 0:
            raise ValueError("decay_per_day must be >= 0")
        import time as _time

        self._time: Callable[[], float] = time_fn or _time.time
        self._decay_per_day = float(decay_per_day)
        # operator_id -> {"score": float, "last_interaction": float | None}
        self._bonds: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Score bookkeeping
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_operator_id(operator_id) -> str:
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ValueError("operator_id must be a non-empty string")
        return operator_id

    def _entry(self, operator_id: str) -> dict:
        return self._bonds.setdefault(
            operator_id, {"score": 0.0, "last_interaction": None}
        )

    def record_interaction(self, operator_id: str, points: float = 2.0) -> float:
        """Add bond points for an operator and stamp the interaction time.

        Pending neglect decay is folded into the stored score *before*
        the new points land, so one interaction after a long silence
        resumes from the decayed value instead of silently erasing
        weeks of neglect. Returns the new stored score, capped at
        SCORE_CAP.
        """
        operator_id = self._validate_operator_id(operator_id)
        if points <= 0:
            raise ValueError("points must be positive")
        entry = self._entry(operator_id)
        entry["score"] = min(SCORE_CAP, self.score(operator_id) + float(points))
        entry["last_interaction"] = float(self._time())
        return entry["score"]

    def days_since_interaction(self, operator_id: str) -> float | None:
        """Days since the last interaction, or None if never interacted."""
        operator_id = self._validate_operator_id(operator_id)
        last = self._entry(operator_id)["last_interaction"]
        if last is None:
            return None
        elapsed = float(self._time()) - last
        return max(0.0, elapsed / SECONDS_PER_DAY)

    def score(self, operator_id: str) -> float:
        """Effective bond score: stored score minus neglect decay, floored at 0."""
        operator_id = self._validate_operator_id(operator_id)
        entry = self._entry(operator_id)
        days = self.days_since_interaction(operator_id)
        if days is None:
            return 0.0
        return max(0.0, entry["score"] - self._decay_per_day * days)

    def bond_level(self, operator_id: str) -> BondLevel:
        """Current bond level after decay; unknown operators are WARY."""
        return BondLevel.from_score(self.score(operator_id))

    # ------------------------------------------------------------------
    # Bond-driven behavior
    # ------------------------------------------------------------------
    def request_priority(self, operator_id: str, base_priority: float) -> float:
        """Loyalty-adjusted priority for an operator's request.

        Higher numbers win scheduling; the bond level (0..4) is added
        on top of the base priority, so a DEVOTED operator's routine
        request can outrank a stranger's routine request — but a
        stranger's genuine emergency (high base) still wins.
        """
        if not isinstance(base_priority, (int, float)) or isinstance(
            base_priority, bool
        ):
            raise ValueError("base_priority must be a number")
        return float(base_priority) + float(self.bond_level(operator_id))

    def protective_alert(self, operator_id: str, threat_level: float) -> dict:
        """Assess a threat to an operator and decide whether to escalate.

        threat_level is 0.0..1.0. Only TRUSTED-and-above operators get
        a protective reflex, and the deeper the bond the weaker the
        evidence needed (ALERT_THRESHOLDS). Always returns a dict;
        ``escalate`` is the field callers must check.
        """
        operator_id = self._validate_operator_id(operator_id)
        if not isinstance(threat_level, (int, float)) or isinstance(
            threat_level, bool
        ):
            raise ValueError("threat_level must be a number")
        threat_level = float(threat_level)
        if not 0.0 <= threat_level <= 1.0:
            raise ValueError("threat_level must be in [0.0, 1.0]")

        level = self.bond_level(operator_id)
        threshold = ALERT_THRESHOLDS.get(level.name)
        escalate = threshold is not None and threat_level >= threshold
        result = {
            "operator_id": operator_id,
            "bond_level": level.name,
            "threat_level": threat_level,
            "escalate": escalate,
            "priority": None,
            "message": "No action required.",
        }
        if escalate:
            result["priority"] = "critical" if threat_level >= 0.8 else "high"
            result["message"] = (
                f"*alarmed shriek* Threat to {operator_id} detected — "
                f"interposing and calling for help!"
            )
        return result

    def greeting(self, operator_id: str) -> str:
        """Bond-appropriate greeting flavor text for an operator."""
        self._validate_operator_id(operator_id)
        return GREETINGS[self.bond_level(operator_id).name]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "decay_per_day": self._decay_per_day,
            "bonds": {
                oid: dict(entry) for oid, entry in self._bonds.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, time_fn=None) -> "BondEngine":
        """Restore an engine from to_dict(); time_fn is re-injected, never stored."""
        if not isinstance(data, dict) or "bonds" not in data:
            raise ValueError("engine data must be a dict with a 'bonds' key")
        engine = cls(time_fn=time_fn, decay_per_day=data.get("decay_per_day", DEFAULT_DECAY_PER_DAY))
        for oid, entry in data["bonds"].items():
            engine._bonds[oid] = {
                "score": float(entry["score"]),
                "last_interaction": entry["last_interaction"],
            }
        return engine
