"""Diagnostic engine and repair procedure runner for the R1-A1 framework.

The diagnostic engine reads the static knowledge base from
:mod:`repair.registry` and produces structured, human-readable assessments of
subsystem health.  The :class:`RepairProcedure` wraps a subsystem's
``repair_steps`` into a runnable, traceable repair job.

All logic here is deterministic and side-effect free (except that
:meth:`RepairProcedure.execute` records a completion status).  The engine is
*not* a live telemetry feed — it is a reasoning layer over authored failure
data.  In a real droid it would be fed by sensor inputs; here it operates on
the stored ``status`` fields so the framework is testable without hardware.

Learning annotation
-------------------
Separating "what do we know" (registry) from "what do we do about it"
(diagnostics) is the Strategy pattern in disguise.  The registry is pure
data; the engine is pure logic that consumes it.  Swapping the registry (e.g.
for one loaded from a file) does not require touching the engine.
"""

from __future__ import annotations

from typing import Optional

from .registry import SpacecraftRegistry, SpacecraftType, Subsystem


# ---------------------------------------------------------------------------
# Diagnostic engine
# ---------------------------------------------------------------------------


class DiagnosticEngine:
    """Runs diagnostic checks against a :class:`SpacecraftRegistry`.

    The engine is stateless beyond its reference to the registry, so a single
    instance can serve any number of diagnostic requests.

    Parameters
    ----------
    registry:
        The :class:`SpacecraftRegistry` to query for spacecraft data.

    Learning annotation
    -------------------
    Dependency injection: the registry is passed in rather than imported as a
    global.  This makes the engine trivially testable — pass a mock registry
    with hand-crafted ships and assert on the output dict.
    """

    def __init__(self, registry: SpacecraftRegistry) -> None:
        self.registry = registry

    # -- public API --------------------------------------------------------

    def diagnose(self, spacecraft_name: str, subsystem_name: str) -> dict:
        """Diagnose a single subsystem on a single spacecraft.

        Parameters
        ----------
        spacecraft_name:
            Registered spacecraft name (case-sensitive).
        subsystem_name:
            Subsystem name on that spacecraft.

        Returns
        -------
        dict
            Keys: ``spacecraft``, ``subsystem``, ``status``, ``checks``,
            ``recommendations``.

            * ``spacecraft`` — the ship name (or ``None`` if not found).
            * ``subsystem`` — the subsystem name (or ``None`` if not found).
            * ``status`` — current subsystem status, or ``"unknown"``.
            * ``checks`` — list of diagnostic check descriptions.
            * ``recommendations`` — list of repair recommendations derived
              from the subsystem's failure modes and repair steps.

        If the spacecraft or subsystem is not found, the returned dict still
        has all five keys so callers can rely on a stable schema.

        Learning annotation
        -------------------
        Returning a fixed-schema dict (always the same keys) is friendlier
        than raising on a missing name — the caller can format the "not found"
        case uniformly.  This is the "null object" idea applied to a dict.
        """
        spacecraft = self.registry.get(spacecraft_name)
        if spacecraft is None:
            return {
                "spacecraft": None,
                "subsystem": None,
                "status": "unknown",
                "checks": [],
                "recommendations": [
                    f"Spacecraft {spacecraft_name!r} not found in registry"
                ],
            }

        subsystem = spacecraft.get_subsystem(subsystem_name)
        if subsystem is None:
            return {
                "spacecraft": spacecraft_name,
                "subsystem": None,
                "status": "unknown",
                "checks": [],
                "recommendations": [
                    f"Subsystem {subsystem_name!r} not found on {spacecraft_name!r}"
                ],
            }

        return {
            "spacecraft": spacecraft_name,
            "subsystem": subsystem_name,
            "status": subsystem.status,
            "checks": list(subsystem.diagnostic_checks),
            "recommendations": self._recommendations(subsystem),
        }

    def run_all_checks(self, spacecraft_name: str) -> dict:
        """Run diagnostics across every subsystem on a spacecraft.

        Returns
        -------
        dict
            Keys: ``spacecraft``, ``overall_status``, ``subsystems``.
            ``subsystems`` is a list of per-subsystem result dicts (same
            shape as :meth:`diagnose` output).  ``overall_status`` is the
            worst status found: ``"critical"`` beats ``"degraded"`` beats
            ``"nominal"``; an unknown ship yields ``"unknown"``.

        Learning annotation
        -------------------
        We compute the overall status with a priority map and ``max()`` with
        a key function — more declarative than a chain of if/elif.  Each
        status string maps to an integer rank; the highest rank wins.
        """
        spacecraft = self.registry.get(spacecraft_name)
        if spacecraft is None:
            return {
                "spacecraft": None,
                "overall_status": "unknown",
                "subsystems": [],
            }

        results = [
            self.diagnose(spacecraft_name, s.name) for s in spacecraft.subsystems
        ]

        status_rank = {"nominal": 0, "degraded": 1, "critical": 2, "unknown": -1}
        overall = "nominal"
        for r in results:
            overall = max(
                overall,
                r["status"],
                key=lambda s: status_rank.get(s, -1),
            )

        return {
            "spacecraft": spacecraft_name,
            "overall_status": overall,
            "subsystems": results,
        }

    def report(self, spacecraft_name: str) -> str:
        """Produce a human-readable diagnostic report for a spacecraft.

        The report lists each subsystem, its status, its diagnostic checks,
        and any recommendations.  Intended for display in a droid terminal or
        repair bay console.

        Learning annotation
        -------------------
        Building a report as a list of lines joined at the end is cheaper
        than repeated string concatenation (``+=``), because strings are
        immutable in Python — each ``+=`` allocates a new string.  Collecting
        in a list and ``"\\n".join(...)`` at the end is the idiomatic fix.
        """
        result = self.run_all_checks(spacecraft_name)
        lines: list[str] = []

        if result["spacecraft"] is None:
            return f"Spacecraft {spacecraft_name!r} not found in registry."

        lines.append(f"=== Diagnostic Report: {spacecraft_name} ===")
        lines.append(f"Overall status: {result['overall_status']}")
        lines.append("")

        for sub in result["subsystems"]:
            sub_name = sub["subsystem"]
            if sub_name is None:
                lines.append(f"  [unknown] {sub['recommendations']}")
                continue
            lines.append(f"  [{sub['status'].upper():8s}] {sub_name}")
            for check in sub["checks"]:
                lines.append(f"      - check: {check}")
            for rec in sub["recommendations"]:
                lines.append(f"      - rec:   {rec}")
            lines.append("")

        return "\n".join(lines)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _recommendations(subsystem: Subsystem) -> list[str]:
        """Derive repair recommendations from a subsystem's authored data.

        If the subsystem is ``nominal`` we still return its preventive
        maintenance checks so the report is never empty.  If it is degraded
        or critical we surface the failure modes and the first repair step
        as the recommended action.

        Learning annotation
        -------------------
        Keeping this a ``@staticmethod`` signals that it does not depend on
        the engine instance — it is a pure function of the subsystem.  That
        makes it easy to unit-test in isolation.
        """
        recs: list[str] = []
        if subsystem.status == "nominal":
            # Preventive: advise running the diagnostic checks regularly.
            if subsystem.diagnostic_checks:
                recs.append(
                    "Subsystem nominal — schedule routine diagnostic cycle."
                )
            else:
                recs.append("Subsystem nominal — no further action required.")
            return recs

        # Degraded or critical: surface known failure modes.
        for mode in subsystem.failure_modes:
            recs.append(f"Possible failure mode: {mode}")
        if subsystem.repair_steps:
            recs.append(
                f"Recommended first step: {subsystem.repair_steps[0]}"
            )
        else:
            recs.append("No repair steps authored for this subsystem.")
        return recs


# ---------------------------------------------------------------------------
# Repair procedure
# ---------------------------------------------------------------------------


class RepairProcedure:
    """A concrete, runnable repair job for a single subsystem.

    Wraps the ordered repair steps, required tools, estimated time, and a
    difficulty rating.  :meth:`execute` walks the steps and returns a result
    dict — it does not perform real repairs, but it models the workflow so a
    droid UI or test harness can trace progress.

    Parameters
    ----------
    spacecraft_name:
        The ship being repaired.
    subsystem_name:
        The subsystem being repaired.
    steps:
        Ordered list of human-readable repair steps.
    tools_required:
        Tools needed to perform the repair (e.g. ``["magna-scanner", "hydrospanner"]``).
    estimated_time_min:
        Estimated repair time in minutes.
    difficulty:
        Difficulty rating — ``"easy"``, ``"moderate"``, or ``"hard"``.
        Free-form but the UI may colour-code these.

    Learning annotation
    -------------------
    :meth:`execute` records completion state on the instance.  This is the
    one place this module carries mutable instance state — and it is clearly
    scoped to a single job, so it is safe.  Avoiding global state is the
    rule; per-job state is fine.
    """

    def __init__(
        self,
        spacecraft_name: str,
        subsystem_name: str,
        steps: list[str],
        tools_required: list[str],
        estimated_time_min: int,
        difficulty: str,
    ) -> None:
        self.spacecraft_name = spacecraft_name
        self.subsystem_name = subsystem_name
        self.steps: list[str] = list(steps)
        self.tools_required: list[str] = list(tools_required)
        self.estimated_time_min: int = estimated_time_min
        self.difficulty: str = difficulty
        # Job state — set by execute().
        self.completed: bool = False
        self.completed_steps: list[str] = []

    def execute(self) -> dict:
        """Walk the repair steps and return a result dict.

        Returns
        -------
        dict
            Keys: ``spacecraft``, ``subsystem``, ``steps_total``,
            ``steps_completed``, ``completed`` (bool), ``tools_required``,
            ``estimated_time_min``, ``difficulty``.

        In a live droid each step would trigger hardware actions; here we
        record them as completed for traceability.

        Learning annotation
        -------------------
        We iterate with ``enumerate(..., start=1)`` so step numbers are
        human-friendly (1-based).  The list copy on the instance
        (``completed_steps``) is a log, not the source of truth for the
        steps — ``self.steps`` is.
        """
        for idx, step in enumerate(self.steps, start=1):
            # In a real implementation each step would dispatch to hardware.
            # Here we simply log completion.
            self.completed_steps.append(f"Step {idx}/{len(self.steps)}: {step}")

        self.completed = True
        return {
            "spacecraft": self.spacecraft_name,
            "subsystem": self.subsystem_name,
            "steps_total": len(self.steps),
            "steps_completed": len(self.completed_steps),
            "completed": self.completed,
            "tools_required": list(self.tools_required),
            "estimated_time_min": self.estimated_time_min,
            "difficulty": self.difficulty,
        }

    @classmethod
    def from_subsystem(
        cls, spacecraft: SpacecraftType, subsystem: Subsystem
    ) -> "RepairProcedure":
        """Build a :class:`RepairProcedure` from a :class:`SpacecraftType` + :class:`Subsystem`.

        Derives ``steps`` and ``tools_required`` from the subsystem's authored
        repair data.  ``estimated_time_min`` scales with the number of steps
        (5 min per step as a heuristic).  ``difficulty`` is inferred from the
        subsystem category: weapons and propulsion default to ``"hard"``,
        hull and shielding to ``"moderate"``, everything else ``"easy"``.

        Learning annotation
        -------------------
        A ``@classmethod`` that constructs the object from *other* domain
        objects (not from raw string args) is an Alternative Constructor —
        the classic use of classmethods in Python.  ``cls`` (not the class
        name) is used so subclasses get the right type back.
        """
        _HARD_CATEGORIES = {"weapons", "propulsion"}
        _MODERATE_CATEGORIES = {"hull", "shielding", "life_support"}

        if subsystem.category in _HARD_CATEGORIES:
            difficulty = "hard"
        elif subsystem.category in _MODERATE_CATEGORIES:
            difficulty = "moderate"
        else:
            difficulty = "easy"

        return cls(
            spacecraft_name=spacecraft.name,
            subsystem_name=subsystem.name,
            steps=list(subsystem.repair_steps),
            tools_required=_tools_for_category(subsystem.category),
            estimated_time_min=max(5, len(subsystem.repair_steps) * 5),
            difficulty=difficulty,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Default tool sets per category.  A module-level constant so it is defined
#: once and reused; a dict of lists is fine because we always copy the list
#: when handing it to a RepairProcedure.
_TOOLSETS: dict[str, list[str]] = {
    "propulsion": ["hydrospanner", "plasma torch", "coolant tester"],
    "life_support": ["atmosphere sampler", "filter wrench", "thermal probe"],
    "power": ["multitool", "circuit tester", "insulated gloves"],
    "avionics": ["data probe", "soldering iron", "diagnostic datapad"],
    "hull": ["magna-scanner", "hull sealant applicator", "riveter"],
    "weapons": ["boresight tool", "firing servo wrench", "bore-scope"],
    "shielding": ["shield resonator calibrator", "multitool"],
    "navigation": ["astrogation datapad", "data probe"],
    "communications": ["comms analyzer", "soldering iron"],
}


def _tools_for_category(category: str) -> list[str]:
    """Return the default tool list for ``category`` (empty list if unknown).

    Learning annotation
    -------------------
    ``dict.get(key, default)`` is cleaner than an if/else and never raises
    ``KeyError`` — perfect for optional lookup with a sensible fallback.
    """
    return list(_TOOLSETS.get(category, []))