"""Spacecraft registry: subsystems, ship types, and a built-in catalog.

This module defines the static knowledge base for the R1-A1 repair framework.
Everything here is pure data plus thin lookup helpers — no I/O, no hardware.
The diagnostic and repair engines in :mod:`repair.diagnostics` consume these
objects to produce actionable reports and procedures.

The built-in catalog contains real spacecraft with real subsystems,
failure modes, and repair procedures. Additional spacecraft types can be
registered at any time via :meth:`SpacecraftRegistry.register`.

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

#: Canonical subsystem categories for real spacecraft.  Stored as a
#: ``frozenset`` so the set is immutable and safe to expose at module scope.
SUBSYSTEM_CATEGORIES: frozenset[str] = frozenset(
    {
        "propulsion",
        "life_support",
        "power",
        "avionics",
        "hull",
        "payload",
        "thermal_protection",
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
        Human-readable subsystem identifier, e.g. ``"Draco thrusters"``.
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
        ``"manual verification required"`` checks.

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
        Spacecraft name / model, e.g. ``"Crew Dragon"``.  Used as the
        registry key.
    manufacturer:
        Producing organisation or company.
    classification:
        Role descriptor — ``"crewed capsule"``, ``"orbiter"``,
        ``"cargo vessel"``, etc.
    length_m:
        Physical length in metres.
    crew_capacity:
        Maximum crew complement (including any robotic systems).
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
# The catalog is built once at import time.  Each spacecraft gets a realistic
# set of subsystems with failure modes and repair steps based on publicly
# documented real-world systems.  This is a knowledge base, not a simulation
# — values are authored from public technical documentation, not generated.


def _build_catalog() -> SpacecraftRegistry:
    """Construct and populate the default :class:`SpacecraftRegistry`.

    Kept as a function (not a module-level literal) so the catalog is rebuilt
    fresh every time it is called — handy for tests that want an untouched
    copy.  The module-level :data:`SPACECRAFT_CATALOG` calls this once.
    """
    registry = SpacecraftRegistry()

    # --- SpaceX Crew Dragon ------------------------------------------------
    dragon = SpacecraftType(
        name="Crew Dragon",
        manufacturer="SpaceX",
        classification="crewed capsule",
        length_m=8.1,
        crew_capacity=7,
        subsystems=[
            Subsystem(
                name="Draco thrusters",
                category="propulsion",
                failure_modes=[
                    "Thruster chamber erosion",
                    "Valve seal degradation",
                    "Propellant line blockage",
                ],
                repair_steps=[
                    "Depressurise propulsion system and safe propellant lines",
                    "Remove affected Draco thruster assembly from service panel",
                    "Replace thruster chamber and valve seals",
                    "Repressurise and run static fire test on test stand",
                ],
                diagnostic_checks=[
                    "Verify rated thrust on test stand",
                    "Check propellant line pressure and flow rate",
                    "Inspect thruster chamber for erosion with borescope",
                ],
            ),
            Subsystem(
                name="ECLSS (life support)",
                category="life_support",
                failure_modes=[
                    "CO2 scrubber cartridge saturation",
                    "Cabin fan motor failure",
                    "Atmosphere pressure sensor drift",
                ],
                repair_steps=[
                    "Switch to backup ECLSS loop",
                    "Replace CO2 scrubber cartridges",
                    "Replace cabin fan motor assembly",
                    "Calibrate atmosphere pressure sensors",
                    "Restore primary loop and verify atmospheric composition",
                ],
                diagnostic_checks=[
                    "Verify O2/CO2 levels within habitable range",
                    "Confirm cabin pressure at 101.3 kPa",
                    "Test backup loop switchover within 30 s",
                ],
            ),
            Subsystem(
                name="Solar arrays",
                category="power",
                failure_modes=[
                    "Photovoltaic cell degradation",
                    "Deployment mechanism jam",
                    "Power bus regulator fault",
                ],
                repair_steps=[
                    "Isolate affected array from power bus",
                    "Inspect deployment hinge actuator",
                    "Replace degraded cell segments or regulator",
                    "Reconnect to bus and verify power output under load",
                ],
                diagnostic_checks=[
                    "Measure per-array power output under load",
                    "Verify deployment mechanism full travel",
                    "Check bus voltage regulation within tolerance",
                ],
            ),
            Subsystem(
                name="Flight computers",
                category="avionics",
                failure_modes=[
                    "IMU calibration drift",
                    "GPS receiver lock failure",
                    "Fault-tolerant computer disagreement",
                ],
                repair_steps=[
                    "Enter safe mode and ground flight computer",
                    "Recalibrate IMU against known reference",
                    "Cycle GPS receiver and verify satellite lock",
                    "Resynchronise triple-redundant computer voting",
                ],
                diagnostic_checks=[
                    "Confirm IMU drift within 0.01 deg/hr",
                    "Verify GPS lock on minimum 4 satellites",
                    "Check computer voting agreement within 1 cycle",
                ],
            ),
            Subsystem(
                name="Heat shield (PICA-X)",
                category="thermal_protection",
                failure_modes=[
                    "Tile erosion beyond reuse limit",
                    "Gap filler displacement",
                    "Bond-line delamination",
                ],
                repair_steps=[
                    "Inspect all heat shield tiles with thermal imaging",
                    "Replace tiles exceeding erosion threshold",
                    "Rebond displaced gap fillers",
                    "Perform bond-line ultrasonic test",
                ],
                diagnostic_checks=[
                    "Scan heat shield for erosion and delamination",
                    "Verify tile-to-tile gap tolerances",
                    "Check bond-line integrity with ultrasonic probe",
                ],
            ),
            Subsystem(
                name="Star tracker",
                category="navigation",
                failure_modes=[
                    "Star catalog corruption",
                    "Optical sensor contamination",
                    "Lost-star lock during slew",
                ],
                repair_steps=[
                    "Reload star catalog from backup",
                    "Clean optical sensor aperture",
                    "Run star identification calibration sequence",
                ],
                diagnostic_checks=[
                    "Verify star lock on minimum 3 catalog stars",
                    "Check optical aperture for contamination",
                ],
            ),
            Subsystem(
                name="Comms system",
                category="communications",
                failure_modes=[
                    "S-band antenna feed fault",
                    "Transponder frequency drift",
                    "Telemetry packet loss",
                ],
                repair_steps=[
                    "Switch to backup transponder",
                    "Reseat antenna feed connection",
                    "Recalibrate transponder frequency",
                    "Verify telemetry link with ground station",
                ],
                diagnostic_checks=[
                    "Confirm S-band downlink signal strength",
                    "Verify telemetry packet integrity at ground station",
                ],
            ),
        ],
    )

    # --- Soyuz MS ----------------------------------------------------------
    soyuz = SpacecraftType(
        name="Soyuz MS",
        manufacturer="RSC Energia",
        classification="crewed capsule",
        length_m=7.2,
        crew_capacity=3,
        subsystems=[
            Subsystem(
                name="KTDU propulsion",
                category="propulsion",
                failure_modes=[
                    "Combustion chamber deposit buildup",
                    "Fuel pump pressure loss",
                    "Thruster nozzle erosion",
                ],
                repair_steps=[
                    "Drain propellant tanks and safe propulsion system",
                    "Remove KTDU main engine access covers",
                    "Clean combustion chamber and inspect nozzle",
                    "Replace fuel pump if pressure below spec",
                    "Reassemble and perform static hot-fire test",
                ],
                diagnostic_checks=[
                    "Verify rated thrust on test stand",
                    "Check fuel pump discharge pressure",
                    "Inspect nozzle for erosion or deposits",
                ],
            ),
            Subsystem(
                name="Life support system",
                category="life_support",
                failure_modes=[
                    "KO2 cartridge depletion",
                    "Cabin humidity control fault",
                    "Pressure equalisation valve stuck",
                ],
                repair_steps=[
                    "Switch to reserve oxygen supply",
                    "Replace KO2 chemical cartridges",
                    "Service humidity control condensate pump",
                    "Inspect and lubricate pressure equalisation valve",
                ],
                diagnostic_checks=[
                    "Verify O2 partial pressure within range",
                    "Check cabin humidity below 60%",
                    "Test pressure equalisation valve travel",
                ],
            ),
            Subsystem(
                name="Solar panels",
                category="power",
                failure_modes=[
                    "Panel hinge freeze",
                    "Battery charge regulator failure",
                    "Cell string open circuit",
                ],
                repair_steps=[
                    "Isolate affected panel from bus",
                    "Free and lubricate hinge mechanism",
                    "Replace charge regulator module",
                    "Verify panel deployment and power output",
                ],
                diagnostic_checks=[
                    "Measure per-panel power output",
                    "Verify battery charge regulator output voltage",
                    "Check hinge actuator current draw",
                ],
            ),
            Subsystem(
                name="Descent module avionics",
                category="avionics",
                failure_modes=[
                    "Descent computer boot failure",
                    "Radar altimeter calibration drift",
                    "Landing radar signal loss",
                ],
                repair_steps=[
                    "Power cycle descent computer from backup bus",
                    "Recalibrate radar altimeter against surveyed range",
                    "Inspect landing radar antenna connections",
                ],
                diagnostic_checks=[
                    "Confirm descent computer boots within 5 s",
                    "Verify radar altimeter accuracy within 1 m at 100 m",
                ],
            ),
            Subsystem(
                name="Descent module heat shield",
                category="thermal_protection",
                failure_modes=[
                    "Ablative material erosion",
                    "Heat shield separation bolt fault",
                    "Backshell tile damage",
                ],
                repair_steps=[
                    "Post-landing: remove descent module for refurbishment",
                    "Strip and replace ablative heat shield layer",
                    "Inspect backshell tiles for damage",
                    "Replace heat shield separation bolt assemblies",
                ],
                diagnostic_checks=[
                    "Verify ablative layer thickness meets reuse spec",
                    "Test heat shield separation bolt firing circuit",
                ],
            ),
            Subsystem(
                name="Parachute system",
                category="payload",
                failure_modes=[
                    "Pilot chute deployment failure",
                    "Main canopy reefing line fraying",
                    "Reefing cutter malfunction",
                ],
                repair_steps=[
                    "Remove parachute pack from descent module",
                    "Inspect pilot chute deployment mechanism",
                    "Replace reefing line and cutter assembly",
                    "Repack parachute per flight procedures",
                ],
                diagnostic_checks=[
                    "Verify pilot chute deployment sequence",
                    "Inspect reefing line for fraying",
                    "Test reefing cutter firing circuit",
                ],
            ),
        ],
    )

    # --- NASA Space Shuttle ------------------------------------------------
    shuttle = SpacecraftType(
        name="Space Shuttle",
        manufacturer="Rockwell International / NASA",
        classification="orbiter",
        length_m=37.2,
        crew_capacity=7,
        subsystems=[
            Subsystem(
                name="SSME main engines",
                category="propulsion",
                failure_modes=[
                    "Turbopump bearing wear",
                    "Combustion chamber liner cracking",
                    "Hydrogen leak at injector interface",
                ],
                repair_steps=[
                    "Drain propellant feed lines and safe SSME",
                    "Remove engine from orbiter aft bay",
                    "Inspect turbopump bearings and replace if worn",
                    "Boroscope combustion chamber liner for cracks",
                    "Pressure-test injector interface seals",
                    "Reinstall and perform static hot-fire at Stennis",
                ],
                diagnostic_checks=[
                    "Verify turbopump RPM and vibration profile",
                    "Check for hydrogen leaks at injector interface",
                    "Confirm rated thrust and specific impulse",
                ],
            ),
            Subsystem(
                name="ECLSS",
                category="life_support",
                failure_modes=[
                    "Cabin pressure control assembly fault",
                    "Condensate water separator jam",
                    "CO2 removal bed saturation",
                ],
                repair_steps=[
                    "Switch to backup pressure control assembly",
                    "Service condensate water separator pump",
                    "Replace CO2 removal bed sorbent",
                    "Verify atmospheric composition and pressure",
                ],
                diagnostic_checks=[
                    "Verify cabin pressure at 101.3 kPa",
                    "Check condensate separator flow",
                    "Confirm CO2 partial pressure below 3 mmHg",
                ],
            ),
            Subsystem(
                name="Fuel cells",
                category="power",
                failure_modes=[
                    "Fuel cell stack degradation",
                    "Reactant valve leak",
                    "Coolant pump cavitation",
                ],
                repair_steps=[
                    "Isolate fuel cell from power bus",
                    "Replace fuel cell stack assembly",
                    "Service reactant valves and coolant pump",
                    "Reconnect and verify power output under load",
                ],
                diagnostic_checks=[
                    "Measure fuel cell output voltage and current",
                    "Check reactant valve seal integrity",
                    "Verify coolant pump discharge pressure",
                ],
            ),
            Subsystem(
                name="RCS thrusters",
                category="propulsion",
                failure_modes=[
                    "Thruster valve stuck open",
                    "Helium pressurisation leak",
                    "Nozzle chamber burn-through",
                ],
                repair_steps=[
                    "Isolate RCS pod propellant supply",
                    "Replace affected thruster valve assembly",
                    "Test helium pressurisation system for leaks",
                    "Inspect nozzle for burn-through damage",
                    "Repressurise and run RCS hot-fire test",
                ],
                diagnostic_checks=[
                    "Verify thruster valve open/close response time",
                    "Check helium pressurisation pressure",
                    "Inspect nozzle for erosion or burn-through",
                ],
            ),
            Subsystem(
                name="TPS tiles (RSI)",
                category="thermal_protection",
                failure_modes=[
                    "Tile gap filler protrusion",
                    "Tile surface coating spalling",
                    "Bond-line void detection",
                ],
                repair_steps=[
                    "Survey all TPS tiles with laser scanner",
                    "Replace tiles with coating spalling exceeding limits",
                    "Rebond or replace protruding gap fillers",
                    "Perform bond-line NDE on suspect tiles",
                ],
                diagnostic_checks=[
                    "Scan tile surface for spalling and erosion",
                    "Verify tile-to-tile gap dimensions",
                    "Check bond-line integrity with thermography",
                ],
            ),
            Subsystem(
                name="Payload bay doors",
                category="payload",
                failure_modes=[
                    "Door latch mechanism jam",
                    "Radiator deployment actuator fault",
                    "Door hinge bearing wear",
                ],
                repair_steps=[
                    "Manually secure payload bay door latches",
                    "Inspect and service latch drive mechanism",
                    "Replace radiator deployment actuator",
                    "Lubricate door hinge bearings",
                    "Verify door open/close cycle and radiator deployment",
                ],
                diagnostic_checks=[
                    "Confirm door latches secure within 30 s",
                    "Test radiator deployment full travel",
                    "Check hinge bearing play",
                ],
            ),
            Subsystem(
                name="Star trackers",
                category="navigation",
                failure_modes=[
                    "Star tracker optical contamination",
                    "Shutter mechanism failure",
                    "Star catalog mismatch",
                ],
                repair_steps=[
                    "Clean star tracker optical aperture",
                    "Replace shutter mechanism assembly",
                    "Reload updated star catalog",
                    "Run star identification calibration",
                ],
                diagnostic_checks=[
                    "Verify star lock on minimum 3 catalog stars",
                    "Test shutter cycle timing",
                ],
            ),
            Subsystem(
                name="S-band comms",
                category="communications",
                failure_modes=[
                    "S-band antenna gimbal jam",
                    "Transponder phase lock loss",
                    "Telemetry encoder fault",
                ],
                repair_steps=[
                    "Switch to backup S-band transponder",
                    "Service antenna gimbal mechanism",
                    "Replace telemetry encoder module",
                    "Verify S-band link with TDRS ground relay",
                ],
                diagnostic_checks=[
                    "Confirm S-band signal strength via TDRS",
                    "Verify telemetry data integrity at ground station",
                    "Test antenna gimbal full travel",
                ],
            ),
        ],
    )

    registry.register(dragon)
    registry.register(soyuz)
    registry.register(shuttle)
    return registry


#: A pre-populated registry containing real spacecraft.  Tests and callers
#: can use this directly, or call :func:`_build_catalog` for a fresh copy.
SPACECRAFT_CATALOG: SpacecraftRegistry = _build_catalog()