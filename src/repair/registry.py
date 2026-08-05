"""Spacecraft registry: subsystems, ship types, and a built-in catalog.

This module defines the static knowledge base for the R1-A1 repair framework.
Everything here is pure data plus thin lookup helpers — no I/O, no hardware.
The diagnostic and repair engines in :mod:`repair.diagnostics` consume these
objects to produce actionable reports and procedures.

Design notes (learning annotations)
----------------------------------
* ``from __future__ import annotations`` makes every type hint a *string* at
  runtime, so forward references (e.g. a method returning its own class) cost
  nothing and never raise ``NameError``.
* Mutable default arguments are a classic Python footgun: ``subsystems=None``
  followed by ``or []`` inside ``__init__`` avoids sharing one list across all
  instances.  Each spacecraft gets its own subsystem list.
* ``SUBSYSTEM_CATEGORIES`` is a frozenset (immutable) so it can safely serve as
  a module-level constant; callers cannot accidentally mutate it.
"""

from __future__ import annotations

from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Canonical subsystem categories.  Stored as a ``frozenset`` so the set is
#: immutable and safe to expose at module scope — nobody can append to it and
#: silently broaden what ``search_by_category`` accepts.
SUBSYSTEM_CATEGORIES: frozenset[str] = frozenset(
    {
        "propulsion",
        "life_support",
        "power",
        "avionics",
        "hull",
        "weapons",
        "shielding",
        "navigation",
        "communications",
    }
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class Subsystem:
    """A single repairable subsystem of a spacecraft.

    Parameters
    ----------
    name:
        Human-readable subsystem identifier, e.g. ``"S-foil servos"``.
    category:
        One of :data:`SUBSYSTEM_CATEGORIES`.  Validated on construction so
        typos are caught early rather than silently breaking category search.
    status:
        Current condition.  Free-form string, but the diagnostic engine
        recognises ``"nominal"``, ``"degraded"``, and ``"critical"``.
    failure_modes:
        Known ways this subsystem can fail.  Each entry is a short string; the
        diagnostic engine surfaces these when a check fails.
    repair_steps:
        Ordered list of step descriptions to restore the subsystem.  The
        :class:`~repair.diagnostics.RepairProcedure` factory reads these.
    diagnostic_checks:
        Ordered checks performed during diagnosis.  Each entry maps to a
        callable or a descriptive string; the engine treats strings as
        "manual verification required" checks.

    Learning annotation
    -------------------
    ``None`` defaults plus ``or [...]`` inside the body is the idiomatic way to
    give each instance its *own* container.  Using ``failure_modes=[]`` as a
    default parameter would share one list across every Subsystem ever
    created — a subtle but classic bug.
    """

    def __init__(
        self,
        name: str,
        category: str,
        status: str = "nominal",
        failure_modes: Optional[list[str]] = None,
        repair_steps: Optional[list[str]] = None,
        diagnostic_checks: Optional[list[str]] = None,
    ) -> None:
        if category not in SUBSYSTEM_CATEGORIES:
            raise ValueError(
                f"Unknown subsystem category {category!r}. "
                f"Valid categories: {sorted(SUBSYSTEM_CATEGORIES)}"
            )
        self.name = name
        self.category = category
        self.status = status
        # ``or []`` — if caller passes None or an empty list we start fresh.
        self.failure_modes: list[str] = list(failure_modes or [])
        self.repair_steps: list[str] = list(repair_steps or [])
        self.diagnostic_checks: list[str] = list(diagnostic_checks or [])

    def __repr__(self) -> str:
        return (
            f"Subsystem(name={self.name!r}, category={self.category!r}, "
            f"status={self.status!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Subsystem):
            return NotImplemented
        return (
            self.name == other.name
            and self.category == other.category
            and self.status == other.status
        )

    def __hash__(self) -> int:
        return hash((self.name, self.category))


class SpacecraftType:
    """A spacecraft model with its subsystem inventory.

    Parameters
    ----------
    name:
        Ship name / model, e.g. ``"X-Wing"``.  Used as the registry key.
    manufacturer:
        Producing company.
    classification:
        Role descriptor — ``"starfighter"``, ``"light freighter"``, etc.
    length_m:
        Physical length in metres.
    crew_capacity:
        Maximum crew complement (including astromech droids if applicable).
    subsystems:
        Optional list of :class:`Subsystem` objects.  When ``None`` an empty
        list is created.  Subsystems are also indexed by name for O(1) lookup.

    Learning annotation
    -------------------
    We build *two* data structures from the one input list: ``subsystems``
    (ordered, for iteration) and ``_by_name`` (a dict, for fast lookup by
    subsystem name).  This is a common pattern — keep the iteration-friendly
    list and a derived index side by side.
    """

    def __init__(
        self,
        name: str,
        manufacturer: str,
        classification: str,
        length_m: float,
        crew_capacity: int,
        subsystems: Optional[list[Subsystem]] = None,
    ) -> None:
        self.name = name
        self.manufacturer = manufacturer
        self.classification = classification
        self.length_m = length_m
        self.crew_capacity = crew_capacity
        self.subsystems: list[Subsystem] = list(subsystems or [])
        # Derived index for O(1) name lookup.
        self._by_name: dict[str, Subsystem] = {
            s.name: s for s in self.subsystems
        }

    def get_subsystem(self, name: str) -> Optional[Subsystem]:
        """Return the subsystem with ``name`` or ``None`` if absent."""
        return self._by_name.get(name)

    def subsystems_by_category(self, category: str) -> list[Subsystem]:
        """Return all subsystems matching ``category``."""
        return [s for s in self.subsystems if s.category == category]

    def __repr__(self) -> str:
        return (
            f"SpacecraftType(name={self.name!r}, "
            f"manufacturer={self.manufacturer!r}, "
            f"classification={self.classification!r})"
        )


class SpacecraftRegistry:
    """In-memory registry of known spacecraft and their subsystems.

    The registry is a simple ``dict`` keyed by spacecraft name.  It supports
    registration, lookup, listing, and category-based search.  A pre-populated
    instance is available as :data:`SPACECRAFT_CATALOG`.

    Learning annotation
    -------------------
    We deliberately keep this class free of any global state.  An instance is
    just a dict wrapper.  This makes it trivial to test: create a registry,
    register a mock ship, assert on it, throw it away.  No singleton, no
    module-level mutable state to reset between tests.
    """

    def __init__(self) -> None:
        self._spacecraft: dict[str, SpacecraftType] = {}

    def register(self, spacecraft: SpacecraftType) -> None:
        """Add or replace a spacecraft entry keyed by ``spacecraft.name``."""
        self._spacecraft[spacecraft.name] = spacecraft

    def get(self, name: str) -> Optional[SpacecraftType]:
        """Return the :class:`SpacecraftType` for ``name`` or ``None``."""
        return self._spacecraft.get(name)

    def list_spacecraft(self) -> list[str]:
        """Return a sorted list of registered spacecraft names."""
        return sorted(self._spacecraft.keys())

    def all_spacecraft(self) -> list[SpacecraftType]:
        """Return all registered :class:`SpacecraftType` objects (insertion order)."""
        return list(self._spacecraft.values())

    def search_by_category(self, category: str) -> list[SpacecraftType]:
        """Return every spacecraft that has at least one subsystem of ``category``.

        Learning annotation
        -------------------
        ``any(...)`` short-circuits: as soon as one matching subsystem is found
        we stop scanning that ship's subsystems.  Cheap and readable.
        """
        return [
            ship
            for ship in self._spacecraft.values()
            if any(s.category == category for s in ship.subsystems)
        ]

    def __len__(self) -> int:
        return len(self._spacecraft)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._spacecraft

    def __repr__(self) -> str:
        return f"SpacecraftRegistry(count={len(self._spacecraft)})"


# ---------------------------------------------------------------------------
# Built-in catalog
# ---------------------------------------------------------------------------
# The catalog is built once at import time.  Each ship gets a realistic set of
# subsystems with failure modes and repair steps so the diagnostic engine has
# real data to chew on.  This is a knowledge base, not a simulation — values
# are authored, not generated.


def _build_catalog() -> SpacecraftRegistry:
    """Construct and populate the default :class:`SpacecraftRegistry`.

    Kept as a function (not a module-level literal) so the catalog is rebuilt
    fresh every time it is called — handy for tests that want an untouched
    copy.  The module-level :data:`SPACECRAFT_CATALOG` calls this once.
    """
    registry = SpacecraftRegistry()

    # --- X-Wing (T-65B) -----------------------------------------------------
    xwing = SpacecraftType(
        name="X-Wing",
        manufacturer="Incom",
        classification="starfighter",
        length_m=12.5,
        crew_capacity=1,
        subsystems=[
            Subsystem(
                name="S-foil servos",
                category="hull",
                failure_modes=[
                    "Servo motor burnout",
                    "Actuator linkage shear",
                    "Position sensor drift",
                ],
                repair_steps=[
                    "Power down and lock S-foils in closed position",
                    "Remove dorsal access panel above servo bay",
                    "Disconnect power coupling to affected servo",
                    "Extract servo motor assembly",
                    "Replace motor and recalibrate position sensor",
                    "Reconnect power and run deployment cycle test",
                ],
                diagnostic_checks=[
                    "Verify S-foil deployment cycle completes within 3 s",
                    "Check servo current draw under load",
                    "Inspect actuator linkage for wear",
                ],
            ),
            Subsystem(
                name="Targeting computer",
                category="avionics",
                failure_modes=[
                    "Sensor fusion lag",
                    "Range-finder calibration loss",
                    "Targeting reticle freeze",
                ],
                repair_steps=[
                    "Cycle targeting computer power",
                    "Re-calibrate against known reference at 500 m",
                    "Flush targeting cache and reload firmware",
                ],
                diagnostic_checks=[
                    "Confirm target lock acquisition within 2 s",
                    "Verify range accuracy ±5 m at 1000 m",
                ],
            ),
            Subsystem(
                name="Astromech socket",
                category="avionics",
                failure_modes=[
                    "Data bus connector corrosion",
                    "Droid retention clamp jam",
                    "Power feed short",
                ],
                repair_steps=[
                    "Disconnect socket power",
                    "Clean connector contacts with ioniser brush",
                    "Replace retention clamp spring if jammed",
                    "Restore power and seat astromech for handshake test",
                ],
                diagnostic_checks=[
                    "Verify astromech handshake within 1 s of seating",
                    "Check connector pin continuity",
                ],
            ),
            Subsystem(
                name="Proton torpedo launcher",
                category="weapons",
                failure_modes=[
                    "Loading rail misalignment",
                    "Firing circuit fault",
                    "Torpedo arming sequence failure",
                ],
                repair_steps=[
                    "Safe the launcher and remove torpedo magazine",
                    "Inspect loading rail alignment with bore-scope",
                    "Replace firing circuit relay",
                    "Reinstall magazine and run dry-fire sequence",
                ],
                diagnostic_checks=[
                    "Verify magazine seats and locks",
                    "Run dry-fire arming sequence without torpedo",
                ],
            ),
            Subsystem(
                name="T-65B ion engine",
                category="propulsion",
                failure_modes=[
                    "Ionisation chamber fouling",
                    "Thrust vector nozzle erosion",
                    "Coolant loop leak",
                ],
                repair_steps=[
                    "Vent engine and allow cool-down",
                    "Remove ionisation chamber access cover",
                    "Clean chamber electrodes and replace coolant seals",
                    "Inspect thrust vector nozzle for erosion",
                    "Reassemble and perform static thrust test",
                ],
                diagnostic_checks=[
                    "Verify rated thrust at full throttle",
                    "Check coolant loop pressure",
                    "Inspect exhaust signature for ionisation stability",
                ],
            ),
        ],
    )

    # --- TIE Fighter -------------------------------------------------------
    tie = SpacecraftType(
        name="TIE Fighter",
        manufacturer="Sienar",
        classification="starfighter",
        length_m=6.4,
        crew_capacity=1,
        subsystems=[
            Subsystem(
                name="Twin ion engine",
                category="propulsion",
                failure_modes=[
                    "Ion stream imbalance",
                    "Engine pod overheating",
                    "Throttle linkage binding",
                ],
                repair_steps=[
                    "Shut down reactor and ground engine pod",
                    "Balance ion stream injectors",
                    "Replace overheated pod cooling fin array",
                    "Lubricate throttle linkage",
                    "Run throttle sweep and verify thrust symmetry",
                ],
                diagnostic_checks=[
                    "Confirm symmetric thrust from both pods",
                    "Monitor pod temperature under sustained throttle",
                ],
            ),
            Subsystem(
                name="Targeting computer",
                category="avionics",
                failure_modes=[
                    "Display blanking",
                    "Tracking grid misalignment",
                ],
                repair_steps=[
                    "Reseat targeting computer card in avionics bay",
                    "Realign tracking grid to boresight",
                ],
                diagnostic_checks=[
                    "Verify display powers on within 2 s",
                    "Check tracking grid alignment against boresight",
                ],
            ),
            Subsystem(
                name="Hull plating",
                category="hull",
                failure_modes=[
                    "Panel micro-fracture",
                    "Solar-collector panel mount stress",
                    "Radiator fin warping",
                ],
                repair_steps=[
                    "Survey all hull panels with magna-scanner",
                    "Replace any panel with micro-fracture exceeding 20 %",
                    "Re-torque collector panel mounts to spec",
                ],
                diagnostic_checks=[
                    "Scan hull for fractures",
                    "Verify panel mount torque values",
                ],
            ),
            Subsystem(
                name="Solar panels",
                category="power",
                failure_modes=[
                    "Photovoltaic cell degradation",
                    "Panel hinge actuator failure",
                    "Power conduit short",
                ],
                repair_steps=[
                    "Isolate affected panel from power bus",
                    "Replace degraded photovoltaic cell array",
                    "Test hinge actuator and conduit continuity",
                    "Reconnect to bus and verify power output",
                ],
                diagnostic_checks=[
                    "Measure per-panel power output under load",
                    "Verify hinge actuator full travel",
                ],
            ),
        ],
    )

    # --- Millennium Falcon -------------------------------------------------
    falcon = SpacecraftType(
        name="Millennium Falcon",
        manufacturer="Corellian Engineering",
        classification="light freighter",
        length_m=26.7,
        crew_capacity=6,
        subsystems=[
            Subsystem(
                name="Hyperdrive",
                category="propulsion",
                failure_modes=[
                    "Coaxium injector clog",
                    "Motivator burnout",
                    "Navigation coordinate dump failure",
                ],
                repair_steps=[
                    "Drop out of hyperspace safely and power down drive",
                    "Vent coaxium lines and replace injector",
                    "Inspect motivator; replace if winding resistance out of spec",
                    "Recharge hyperdrive and run calibration jump",
                ],
                diagnostic_checks=[
                    "Verify motivator winding resistance",
                    "Test coordinate upload to nav buffer",
                    "Confirm clean micro-jump to known beacon",
                ],
            ),
            Subsystem(
                name="Sublight engines",
                category="propulsion",
                failure_modes=[
                    "Sublight manifold breach",
                    "Thrust bearing wear",
                    "Fuel line blockage",
                ],
                repair_steps=[
                    "Secure engine and isolate fuel supply",
                    "Replace manifold gaskets",
                    "Inspect thrust bearings; repack or replace",
                    "Clear fuel line and test sublight ignition",
                ],
                diagnostic_checks=[
                    "Monitor manifold pressure during ignition",
                    "Check thrust bearing play",
                ],
            ),
            Subsystem(
                name="Shield generator",
                category="shielding",
                failure_modes=[
                    "Projector coil overheating",
                    "Shield matrix desynchronisation",
                    "Capacitor bank failure",
                ],
                repair_steps=[
                    "Power down shield generator",
                    "Replace overheated projector coil",
                    "Resynchronise shield matrix using astromech interface",
                    "Test capacitor bank charge/discharge cycle",
                ],
                diagnostic_checks=[
                    "Verify shield coverage overlay on hull plot",
                    "Monitor projector coil temperature under load",
                ],
            ),
            Subsystem(
                name="Hull",
                category="hull",
                failure_modes=[
                    "Hull breach (micro)",
                    "Landing strut failure",
                    "Docking ring seal degradation",
                ],
                repair_steps=[
                    "Depressurise affected section",
                    "Patch micro-breaches with hull sealant",
                    "Replace landing strut hydraulic ram",
                    "Resurface docking ring seal",
                ],
                diagnostic_checks=[
                    "Pressure-test all hull sections",
                    "Verify landing strut deployment and lock",
                ],
            ),
            Subsystem(
                name="Quad laser cannons",
                category="weapons",
                failure_modes=[
                    "Barrel alignment drift",
                    "Firing servo jam",
                    "Cooling jacket leak",
                ],
                repair_steps=[
                    "Safe cannons and isolate power",
                    "Realign barrels using boresight tool",
                    "Clear firing servo jam and lubricate",
                    "Repair cooling jacket leak",
                    "Dry-fire test all four barrels",
                ],
                diagnostic_checks=[
                    "Verify barrel alignment within 0.1 mrad",
                    "Confirm cooling jacket pressure",
                ],
            ),
            Subsystem(
                name="Life support",
                category="life_support",
                failure_modes=[
                    "Atmosphere scrubber saturation",
                    "Thermal regulation unit fault",
                    "CO2 filter failure",
                ],
                repair_steps=[
                    "Switch to backup life support",
                    "Replace atmosphere scrubber cartridges",
                    "Repair thermal regulation unit",
                    "Replace CO2 filters and restore primary system",
                ],
                diagnostic_checks=[
                    "Verify O2/CO2 levels within habitable range",
                    "Confirm thermal regulation across all decks",
                ],
            ),
            Subsystem(
                name="Nav computer",
                category="navigation",
                failure_modes=[
                    "Coordinate database corruption",
                    "Astrogation buffer overflow",
                    "Nav beacon receiver fault",
                ],
                repair_steps=[
                    "Halt hyperspace navigation",
                    "Restore coordinate database from backup",
                    "Flush and rebuild astrogation buffer",
                    "Test nav beacon receiver lock",
                ],
                diagnostic_checks=[
                    "Verify coordinate database integrity checksum",
                    "Confirm astrogation buffer free space",
                ],
            ),
        ],
    )

    registry.register(xwing)
    registry.register(tie)
    registry.register(falcon)
    return registry


#: A pre-populated registry containing the example ships.  Tests and callers
#: can use this directly, or call :func:`_build_catalog` for a fresh copy.
SPACECRAFT_CATALOG: SpacecraftRegistry = _build_catalog()