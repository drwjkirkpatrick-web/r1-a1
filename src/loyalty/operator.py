"""Operator profiles and the directory of people R1-A1 has met.

An astromech that cannot tell its owner from a wandering convention
guest is a menace: it will hand control of a 38 kg robot to anyone who
asks nicely. The OperatorProfile records who someone is (name, role,
authorization level), and the OperatorDirectory remembers everyone the
unit has met, how often, and how well.

Familiarity grows on a diminishing-returns curve: the first few
interactions teach the unit a lot about a person; the five-hundredth
teaches almost nothing new. We model that with a saturating
exponential, familiarity = 1 - exp(-FAMILIARITY_RATE * interactions),
so the score is bounded in [0, 1) and each additional interaction adds
strictly less than the one before.

All state is plain data — no clocks, no I/O — so every behavior is
testable by construction.

Learning annotation: diminishing returns matters because a naive
linear counter would let a chatty guest outrank the owner in a week.
Saturating curves encode "trust accrues fast, then plateaus" — the
same shape as real habituation, and the same shape used by the bond
score decay in bond.py.
"""

from __future__ import annotations

import math

ROLES = ("pilot", "owner", "technician", "guest")
MIN_AUTH_LEVEL = 1
MAX_AUTH_LEVEL = 5
FAMILIARITY_RATE = 0.25  # familiarity = 1 - exp(-RATE * interaction_count)


class OperatorProfile:
    """One person the unit has met: identity, clearance, and history."""

    def __init__(
        self,
        name: str,
        role: str = "guest",
        authorization_level: int = MIN_AUTH_LEVEL,
        interaction_count: int = 0,
        first_met: float = 0.0,
        familiarity: float | None = None,
        preferences: dict | None = None,
    ) -> None:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, got {role!r}")
        if isinstance(authorization_level, bool) or not isinstance(
            authorization_level, int
        ):
            raise ValueError("authorization_level must be an int")
        if not MIN_AUTH_LEVEL <= authorization_level <= MAX_AUTH_LEVEL:
            raise ValueError(
                f"authorization_level must be {MIN_AUTH_LEVEL}..{MAX_AUTH_LEVEL}"
            )
        if isinstance(interaction_count, bool) or not isinstance(
            interaction_count, int
        ):
            raise ValueError("interaction_count must be an int")
        if interaction_count < 0:
            raise ValueError("interaction_count must be >= 0")
        if preferences is None:
            preferences = {}
        if not isinstance(preferences, dict):
            raise ValueError("preferences must be a dict")

        self.name = name.strip()
        self.role = role
        self.authorization_level = authorization_level
        self.interaction_count = interaction_count
        self.first_met = float(first_met)
        if familiarity is None:
            familiarity = self.familiarity_for(interaction_count)
        familiarity = float(familiarity)
        if not 0.0 <= familiarity <= 1.0:
            raise ValueError("familiarity must be in [0.0, 1.0]")
        self.familiarity = familiarity
        self.preferences = dict(preferences)

    @staticmethod
    def familiarity_for(interaction_count: int) -> float:
        """Saturating familiarity curve for a given interaction count."""
        if interaction_count <= 0:
            return 0.0
        return 1.0 - math.exp(-FAMILIARITY_RATE * interaction_count)

    @property
    def operator_id(self) -> str:
        """Stable identifier derived from the name ('Anakin Sky' -> 'anakin_sky')."""
        return "_".join(self.name.lower().split())

    def record_interaction(self) -> float:
        """Count one more interaction and recompute familiarity.

        Returns the new familiarity. Each call nudges the curve; the
        increment shrinks as the count grows (diminishing returns).
        """
        self.interaction_count += 1
        self.familiarity = self.familiarity_for(self.interaction_count)
        return self.familiarity

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "authorization_level": self.authorization_level,
            "interaction_count": self.interaction_count,
            "first_met": self.first_met,
            "familiarity": self.familiarity,
            "preferences": dict(self.preferences),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OperatorProfile":
        if not isinstance(data, dict):
            raise ValueError("profile data must be a dict")
        return cls(
            name=data["name"],
            role=data.get("role", "guest"),
            authorization_level=data.get("authorization_level", MIN_AUTH_LEVEL),
            interaction_count=data.get("interaction_count", 0),
            first_met=data.get("first_met", 0.0),
            familiarity=data.get("familiarity"),
            preferences=data.get("preferences"),
        )

    def __repr__(self) -> str:
        return (
            f"OperatorProfile({self.name!r}, role={self.role!r}, "
            f"auth={self.authorization_level}, "
            f"interactions={self.interaction_count})"
        )


class OperatorDirectory:
    """Registry of every operator the unit has met, keyed by operator_id."""

    def __init__(self) -> None:
        self._operators: dict[str, OperatorProfile] = {}

    def add(self, profile: OperatorProfile) -> str:
        """Register a profile; returns its operator_id.

        Re-adding the same operator_id raises — updating an existing
        operator must go through record_interaction() so history is
        never silently overwritten.
        """
        if not isinstance(profile, OperatorProfile):
            raise ValueError("profile must be an OperatorProfile")
        oid = profile.operator_id
        if oid in self._operators:
            raise ValueError(f"operator already registered: {oid!r}")
        self._operators[oid] = profile
        return oid

    def get(self, operator_id: str) -> OperatorProfile | None:
        """Look up a profile by id, or None if unknown."""
        return self._operators.get(operator_id)

    def is_known(self, operator_id: str) -> bool:
        return operator_id in self._operators

    def classify(self, operator_id: str) -> str:
        """'known' or 'unknown' — the binary every security check wants."""
        return "known" if self.is_known(operator_id) else "unknown"

    def record_interaction(self, operator_id: str) -> float:
        """Record an interaction with a known operator.

        Returns the new familiarity. Raises on unknown ids: silently
        auto-registering strangers would defeat the whole point of the
        known/unknown classification.
        """
        profile = self._operators.get(operator_id)
        if profile is None:
            raise ValueError(f"unknown operator: {operator_id!r}")
        return profile.record_interaction()

    def known_ids(self) -> list[str]:
        return sorted(self._operators)

    def to_dict(self) -> dict:
        return {
            "operators": {
                oid: profile.to_dict() for oid, profile in self._operators.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OperatorDirectory":
        if not isinstance(data, dict) or "operators" not in data:
            raise ValueError("directory data must be a dict with an 'operators' key")
        directory = cls()
        for profile_data in data["operators"].values():
            directory.add(OperatorProfile.from_dict(profile_data))
        return directory
