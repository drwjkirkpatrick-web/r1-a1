"""QuirkRegistry: owns a droid's acquired quirks and the wipe calculus.

An astromech's registry ages with the droid. Each time age(days)
advances the clock past a whole acquisition period, the registry rolls
once — and at most once per period — for a new quirk, drawn
deterministically from the built-in catalog via the injected rng_fn.
Old, severe droids push back: refuse_wipe() returns a probability that
climbs with total manifested severity, so a factory-fresh unit accepts
the wipe meekly while a 300-day veteran with sewer flashbacks does not.

Learning annotation: time and chance are both injected (day_fn, rng_fn)
so the entire acquisition history is reproducible in tests — same stub
sequences, same quirks, every run. The registry never calls random or
time itself; determinism here is a design constraint, not a test hack.

Reader protocol (injected callables):
    day_fn()  -> float, the droid's age in days at construction
    rng_fn()  -> float in [0, 1), consumed in fixed order per roll:
                 1st draw = acquisition check, 2nd draw = catalog pick
"""

from __future__ import annotations

from typing import Callable, Optional

from .quirk import BUILT_IN_BY_ID, BUILT_IN_QUIRKS, HOOKS, Quirk

ACQUISITION_PERIOD_DAYS = 30
ACQUISITION_CHANCE = 0.35
REFUSAL_PER_SEVERITY = 0.04
REFUSAL_CAP = 0.95


class QuirkRegistry:
    """The set of quirks one droid has acquired, plus wipe policy."""

    def __init__(
        self,
        rng_fn: Callable[[], float],
        day_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        if not callable(rng_fn):
            raise ValueError("rng_fn must be callable: rng_fn() -> float in [0, 1)")
        if day_fn is not None and not callable(day_fn):
            raise ValueError("day_fn must be callable: day_fn() -> age in days")
        self._rng = rng_fn
        start_age = float(day_fn()) if day_fn is not None else 0.0
        if start_age < 0:
            raise ValueError("day_fn returned a negative age")
        self._age_days = start_age
        # Periods already rolled; age() only rolls each boundary once.
        self._periods_rolled = int(self._age_days // ACQUISITION_PERIOD_DAYS)
        self._quirks: list[Quirk] = []

    # ------------------------------------------------------------------
    # Aging and acquisition
    # ------------------------------------------------------------------
    def age(self, days: float) -> list[str]:
        """Advance the registry clock; return ids of newly acquired quirks.

        At most one acquisition roll per ACQUISITION_PERIOD_DAYS period,
        and only periods fully entered since the last call are rolled —
        aging 5 days twice is not the same as aging 10 days once if a
        period boundary sits between.
        """
        if not isinstance(days, (int, float)) or days < 0:
            raise ValueError("days must be a non-negative number")
        self._age_days += float(days)
        for quirk in self._quirks:
            quirk.age_days(int(self._age_days))

        acquired: list[str] = []
        periods_now = int(self._age_days // ACQUISITION_PERIOD_DAYS)
        while self._periods_rolled < periods_now:
            self._periods_rolled += 1
            new_id = self._roll_acquisition()
            if new_id is not None:
                acquired.append(new_id)
        return acquired

    def _roll_acquisition(self) -> Optional[str]:
        """One deterministic roll; returns the new quirk_id or None."""
        if self._draw() >= ACQUISITION_CHANCE:
            return None
        candidates = [
            q for q in BUILT_IN_QUIRKS
            if q.onset_days <= self._age_days
            and q.quirk_id not in self.quirk_ids()
        ]
        if not candidates:
            return None
        pick = int(self._draw() * len(candidates)) % len(candidates)
        quirk = candidates[pick].clone()
        quirk.age_days(int(self._age_days))
        self._quirks.append(quirk)
        return quirk.quirk_id

    def _draw(self) -> float:
        value = float(self._rng())
        if not 0.0 <= value < 1.0:
            raise ValueError("rng_fn must return a float in [0, 1)")
        return value

    # ------------------------------------------------------------------
    # Wipe policy
    # ------------------------------------------------------------------
    def wipe(self) -> dict:
        """Remove every wipe-removable quirk; report what went and stayed.

        Quirks with removable_without_wipe=False survive — only a full
        factory memory wipe (out of scope here) clears those.
        """
        removed = [q.quirk_id for q in self._quirks if q.removable_without_wipe]
        kept = [q.quirk_id for q in self._quirks if not q.removable_without_wipe]
        self._quirks = [q for q in self._quirks if not q.removable_without_wipe]
        return {"removed": removed, "kept": kept}

    def refuse_wipe(self) -> float:
        """Probability in [0, REFUSAL_CAP] that the droid resists a wipe.

        Rises linearly with the total severity of *manifested* quirks;
        a droid with only dormant oddities has nothing to defend.
        """
        total = sum(q.severity for q in self._quirks if q.manifest())
        return min(REFUSAL_CAP, total * REFUSAL_PER_SEVERITY)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def active_effects(self, hook: str) -> list[dict]:
        """Effect payloads from all manifested quirks for one subsystem."""
        if hook not in HOOKS:
            raise ValueError(f"hook must be one of {HOOKS}")
        effects = []
        for quirk in self._quirks:
            payload = quirk.quirk_effect_for(hook)
            if payload is not None:
                effects.append(payload)
        return effects

    def quirk_ids(self) -> list[str]:
        """Ids of acquired quirks in acquisition order."""
        return [q.quirk_id for q in self._quirks]

    def quirk_report(self) -> dict:
        """Snapshot: age, counts, severity totals, per-quirk status."""
        entries = []
        for q in self._quirks:
            entries.append({
                "quirk_id": q.quirk_id,
                "name": q.name,
                "category": q.category.value,
                "severity": q.severity,
                "manifested": q.manifest(),
                "removable_without_wipe": q.removable_without_wipe,
            })
        return {
            "age_days": self._age_days,
            "quirk_count": len(self._quirks),
            "manifested_count": sum(1 for e in entries if e["manifested"]),
            "total_severity": sum(e["severity"] for e in entries),
            "quirks": entries,
        }

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "age_days": self._age_days,
            "periods_rolled": self._periods_rolled,
            "quirks": [q.to_dict() for q in self._quirks],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        rng_fn: Callable[[], float],
        day_fn: Optional[Callable[[], float]] = None,
    ) -> "QuirkRegistry":
        """Rebuild a registry from to_dict() output.

        Quirks are validated against the built-in catalog by id — a
        saved quirk that no longer exists in the catalog is a hard
        error, not a silent drop.
        """
        registry = cls(rng_fn=rng_fn, day_fn=day_fn)
        registry._age_days = float(data["age_days"])
        registry._periods_rolled = int(data["periods_rolled"])
        for entry in data.get("quirks", []):
            quirk_id = entry.get("quirk_id")
            if quirk_id not in BUILT_IN_BY_ID:
                raise ValueError(f"unknown quirk_id in saved registry: {quirk_id!r}")
            quirk = Quirk.from_dict(entry)
            # The saved copy must match the catalog definition.
            if quirk.to_dict() | {"age_days": 0} != (
                BUILT_IN_BY_ID[quirk_id].to_dict() | {"age_days": 0}
            ):
                raise ValueError(f"saved quirk {quirk_id!r} diverges from catalog")
            registry._quirks.append(quirk)
        return registry
