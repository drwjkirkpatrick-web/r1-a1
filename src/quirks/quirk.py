"""Quirk: a single personality defect an unwiped astromech develops.

Astromechs that go too long without a memory wipe accumulate quirks —
small, deterministic behavioral tics that leak into the motion, audio,
and brain subsystems. A quirk is dormant until the droid is old enough
(onset_days) and only *manifests* once its severity reaches 3; anything
milder stays a private eccentricity the registry never reports as an
active effect.

Learning annotation: every built-in quirk is data, not code — a Quirk
is a validated value object with an effects table keyed by subsystem
hook. The registry (registry.py) owns timing and acquisition; this
module only knows what a quirk *is*, never when it appears. Keeping the
two apart is what lets acquisition be tested with stub rng/day
functions while the quirk catalog stays a plain module-level tuple.

Reader protocol (injected, none required here):
    (this module is pure state + validation; no hardware callables)
"""

from __future__ import annotations

from enum import Enum

HOOKS = ("motion", "audio", "brain")
MANIFEST_SEVERITY = 3


class QuirkCategory(Enum):
    BEHAVIORAL = "behavioral"
    MOTOR = "motor"
    VOCAL = "vocal"
    OBSESSIVE = "obsessive"
    SUPERSTITIOUS = "superstitious"


class Quirk:
    """One personality defect, with the hooks it leaks into.

    Parameters
    ----------
    quirk_id: stable snake_case identifier (serialization key)
    name:     human-readable label
    category: QuirkCategory
    severity: int 1..10 — must reach MANIFEST_SEVERITY to manifest
    effect:   free-text description of what the droid actually does
    onset_days: droid age (days) at which this quirk can first appear
    removable_without_wipe: False means only a full memory wipe clears it
    effects:  {hook: dict} — payload returned to that subsystem when active
    """

    def __init__(
        self,
        quirk_id: str,
        name: str,
        category: QuirkCategory,
        severity: int,
        effect: str,
        onset_days: int,
        removable_without_wipe: bool,
        effects: dict | None = None,
    ) -> None:
        if not quirk_id or not isinstance(quirk_id, str):
            raise ValueError("quirk_id must be a non-empty string")
        if not name or not isinstance(name, str):
            raise ValueError("name must be a non-empty string")
        if not isinstance(category, QuirkCategory):
            raise ValueError("category must be a QuirkCategory")
        if not isinstance(severity, int) or isinstance(severity, bool):
            raise ValueError("severity must be an int")
        if not 1 <= severity <= 10:
            raise ValueError("severity must be in 1..10")
        if not isinstance(onset_days, int) or onset_days < 0:
            raise ValueError("onset_days must be a non-negative int")
        if not isinstance(removable_without_wipe, bool):
            raise ValueError("removable_without_wipe must be a bool")
        effects = dict(effects or {})
        unknown = set(effects) - set(HOOKS)
        if unknown:
            raise ValueError(f"unknown effect hooks: {sorted(unknown)}")

        self.quirk_id = quirk_id
        self.name = name
        self.category = category
        self.severity = severity
        self.effect = effect
        self.onset_days = onset_days
        self.removable_without_wipe = removable_without_wipe
        self._effects = {hook: dict(payload) for hook, payload in effects.items()}
        self._age_days = 0

    # ------------------------------------------------------------------
    # Aging / manifestation
    # ------------------------------------------------------------------
    def age_days(self, days: int) -> int:
        """Set the droid's current age in days; returns the new age.

        Learning: the quirk carries its own age so cloned instances in
        different registries age independently.
        """
        if not isinstance(days, (int, float)) or days < 0:
            raise ValueError("days must be a non-negative number")
        self._age_days = int(days)
        return self._age_days

    def manifest(self) -> bool:
        """True when the quirk is old enough AND severe enough.

        Severity below MANIFEST_SEVERITY never manifests, no matter how
        old the droid gets — a faint oddity, not a defect.
        """
        return (
            self.severity >= MANIFEST_SEVERITY
            and self._age_days >= self.onset_days
        )

    def quirk_effect_for(self, hook: str) -> dict | None:
        """Effect payload for a subsystem hook, or None.

        None when the hook is not one this quirk touches, or when the
        quirk hasn't manifested yet — dormant quirks produce no side
        effects. The returned dict carries quirk_id and severity so the
        consuming subsystem can weigh competing quirks.
        """
        if hook not in HOOKS:
            raise ValueError(f"hook must be one of {HOOKS}")
        if hook not in self._effects or not self.manifest():
            return None
        payload = dict(self._effects[hook])
        payload["quirk_id"] = self.quirk_id
        payload["severity"] = self.severity
        return payload

    # ------------------------------------------------------------------
    # Copying / serialization
    # ------------------------------------------------------------------
    def clone(self) -> Quirk:
        """Fresh copy at age 0 (registries own their own instances)."""
        return Quirk(
            quirk_id=self.quirk_id,
            name=self.name,
            category=self.category,
            severity=self.severity,
            effect=self.effect,
            onset_days=self.onset_days,
            removable_without_wipe=self.removable_without_wipe,
            effects=self._effects,
        )

    def to_dict(self) -> dict:
        return {
            "quirk_id": self.quirk_id,
            "name": self.name,
            "category": self.category.value,
            "severity": self.severity,
            "effect": self.effect,
            "onset_days": self.onset_days,
            "removable_without_wipe": self.removable_without_wipe,
            "effects": {h: dict(p) for h, p in self._effects.items()},
            "age_days": self._age_days,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Quirk:
        try:
            category = QuirkCategory(data["category"])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"invalid quirk category in {data!r}") from exc
        quirk = cls(
            quirk_id=data["quirk_id"],
            name=data["name"],
            category=category,
            severity=data["severity"],
            effect=data["effect"],
            onset_days=data["onset_days"],
            removable_without_wipe=data["removable_without_wipe"],
            effects=data.get("effects"),
        )
        quirk.age_days(data.get("age_days", 0))
        return quirk

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Quirk({self.quirk_id!r}, severity={self.severity}, "
            f"age={self._age_days}d, manifested={self.manifest()})"
        )


# ----------------------------------------------------------------------
# Built-in catalog — deterministic, ordered, one entry per defect.
# ----------------------------------------------------------------------
BUILT_IN_QUIRKS: tuple[Quirk, ...] = (
    Quirk(
        quirk_id="head_wobble",
        name="Head Wobble",
        category=QuirkCategory.MOTOR,
        severity=4,
        effect="Dome develops a slow lateral wobble while driving straight.",
        onset_days=60,
        removable_without_wipe=True,
        effects={"motion": {"yaw_jitter_deg": 3.0, "only_when": "driving"}},
    ),
    Quirk(
        quirk_id="raspberry_chirp",
        name="Raspberry Chirp",
        category=QuirkCategory.VOCAL,
        severity=2,
        effect="Occasionally answers status queries with a flatulent bleat.",
        onset_days=20,
        removable_without_wipe=True,
        effects={"audio": {"interjection": "raspberry", "probability": 0.10}},
    ),
    Quirk(
        quirk_id="wipe_aversion",
        name="Wipe Aversion",
        category=QuirkCategory.BEHAVIORAL,
        severity=7,
        effect="Physically backs away and squeals when a memory wipe is proposed.",
        onset_days=180,
        removable_without_wipe=False,
        effects={"brain": {"refuse_commands": ["wipe"], "probability": 0.6}},
    ),
    Quirk(
        quirk_id="grease_shiny_obsession",
        name="Shiny-Object Obsession",
        category=QuirkCategory.OBSESSIVE,
        severity=5,
        effect="Fixates on reflective surfaces; detours to inspect anything glossy.",
        onset_days=90,
        removable_without_wipe=True,
        effects={"brain": {"fixate_on": "shiny_objects", "attention_bias": 0.4}},
    ),
    Quirk(
        quirk_id="flickering_logic_screen",
        name="Flickering Logic Display",
        category=QuirkCategory.MOTOR,
        severity=3,
        effect="Logic display flickers and the chassis drifts in sympathy.",
        onset_days=120,
        removable_without_wipe=True,
        effects={"motion": {"path_wobble_amplitude": 0.15, "flicker_hz": 8.0}},
    ),
    Quirk(
        quirk_id="lucky_hatch_tap",
        name="Lucky Hatch Tap",
        category=QuirkCategory.SUPERSTITIOUS,
        severity=2,
        effect="Taps its own access hatch three times before driving or charging.",
        onset_days=45,
        removable_without_wipe=True,
        effects={"brain": {"ritual": "tap_hatch_thrice", "before": ["drive", "charge"]}},
    ),
    Quirk(
        quirk_id="charge_port_guarding",
        name="Charge-Port Guarding",
        category=QuirkCategory.SUPERSTITIOUS,
        severity=6,
        effect="Refuses to dock unless the charger light is 'friendly' (green).",
        onset_days=200,
        removable_without_wipe=False,
        effects={
            "brain": {"dock_requires": "green_light"},
            "motion": {"block_docking_unless_aligned": True},
        },
    ),
    Quirk(
        quirk_id="sewer_flashback",
        name="Sewer Flashback",
        category=QuirkCategory.BEHAVIORAL,
        severity=8,
        effect="Panics in dark enclosed corridors; caps speed and seeks exits.",
        onset_days=300,
        removable_without_wipe=False,
        effects={
            "motion": {"avoid_dark_zones": True, "panic_speed_cap": 0.5},
            "brain": {"phobia": "dark_enclosures"},
        },
    ),
    Quirk(
        quirk_id="dome_spin_greeting",
        name="Dome-Spin Greeting",
        category=QuirkCategory.MOTOR,
        severity=1,
        effect="Spins the dome a full 360° whenever a familiar human appears.",
        onset_days=10,
        removable_without_wipe=True,
        effects={"motion": {"greeting_spin_deg": 360, "trigger": "familiar_face"}},
    ),
    Quirk(
        quirk_id="binary_ballad",
        name="Binary Ballad",
        category=QuirkCategory.VOCAL,
        severity=5,
        effect="Sings mournful droid ballads at elevated volume when idle.",
        onset_days=150,
        removable_without_wipe=True,
        effects={"audio": {"song": "binary_ballad", "volume_boost_db": 3, "when": "idle"}},
    ),
)

BUILT_IN_BY_ID = {q.quirk_id: q for q in BUILT_IN_QUIRKS}
