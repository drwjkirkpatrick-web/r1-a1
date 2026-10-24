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

    # --- Apollo Command/Service Module -------------------------------------
    # Apollo 13 (1970) is the most documented improvised repair in spaceflight:
    # an SM O2 tank exploded 56 hours out, and the LM became a lifeboat while
    # the crew and ground built the CO2 "mailbox" adapter from cabin materials.
    apollo = SpacecraftType(
        name="Apollo CSM/LM",
        manufacturer="North American Rockwell / Grumman (NASA)",
        classification="crewed capsule + lunar module",
        length_m=11.0,
        crew_capacity=3,
        subsystems=[
            Subsystem(
                name="Service Module oxygen tanks",
                category="life_support",
                status="degraded",
                failure_modes=[
                    "O2 tank thermostat switches welded closed by 65 V ground "
                    "test on 28 V-rated switches (Apollo 13 root cause)",
                    "Teflon-insulated wire fire inside tank from damaged "
                    "insulation and inadequate stir-fan operation",
                    "Tank explosion takes out adjacent tank and fuel cells",
                ],
                repair_steps=[
                    "Transfer crew to lunar module as lifeboat; power down "
                    "command module to preserve re-entry batteries",
                    "Build improvised LiOH CO2 scrubber adapter ('mailbox') "
                    "from flight-plan covers, hose, tape, and thermal "
                    "underwear per ground-written procedure",
                    "Cross-cable LM environmental control to sustain cabin "
                    "atmosphere for full crew",
                    "Follow ground-written 2-hour CM power-up checklist for "
                    "re-entry (normally requires months to write)",
                ],
                diagnostic_checks=[
                    "Monitor O2 tank pressure, temperature, and quantity",
                    "Check fuel cell reactant flow after tank anomaly",
                    "Track cabin CO2 partial pressure (Apollo 13 rose to "
                    "dangerous levels before the mailbox was fitted)",
                ],
            ),
            Subsystem(
                name="Service Propulsion System",
                category="propulsion",
                failure_modes=[
                    "SPS engine integrity unknown after SM explosion — "
                    "ground prohibits burn (Apollo 13)",
                    "Helium pressurisation leak in propellant feed",
                    "Injector valve seat leakage (hypergolics ignite on "
                    "contact — no ignition system needed but leaks are fatal)",
                ],
                repair_steps=[
                    "Do not fire suspect engine; use LM descent engine for "
                    "all burns (Apollo 13 free-return burn + midcourse "
                    "corrections)",
                    "Perform manual optical alignment burn check — crew "
                    "aligned LM by keeping Earth in the window when the "
                    "computer attitude could not be trusted",
                    "Jettison service module before re-entry after visual "
                    "inspection of the damage",
                ],
                diagnostic_checks=[
                    "Review telemetry for unexplained thrust or pressure "
                    "decay before authorising any burn",
                    "Pressure-test propellant and helium feed lines",
                ],
            ),
            Subsystem(
                name="Command Module heat shield",
                category="thermal_protection",
                failure_modes=[
                    "Ablative shield integrity unknown after SM explosion "
                    "debris",
                    "Cracked ablator seams from thermal cycling",
                ],
                repair_steps=[
                    "Visual inspection of SM after jettison (crew photographed "
                    "the Apollo 13 damage, including the missing panel)",
                    "Ground inspection of recovered shield: section and "
                    "measure ablation depth against prediction",
                    "Refurbish: strip and re-apply ablative material on "
                    "salvageable structure",
                ],
                diagnostic_checks=[
                    "Photographic survey of shield surface after any "
                    "anomalous event",
                    "Ultrasonic bond check of ablator seams",
                ],
            ),
            Subsystem(
                name="Entry guidance and batteries",
                category="navigation",
                status="degraded",
                failure_modes=[
                    "IMU platform drift after days powered down (lifeboat "
                    "operation)",
                    "Re-entry batteries depleted by emergency load profile",
                ],
                repair_steps=[
                    "Transfer LM guidance state to CM platform during "
                    "power-up (Apollo 13: only a few hours were available, "
                    "so the transfer was done by manual angle readout)",
                    "Shed all non-essential loads days before re-entry; "
                    "power up only the minimum entry stack",
                    "Run the compressed 2-hour power-up checklist written "
                    "and simulator-validated by the ground team",
                ],
                diagnostic_checks=[
                    "Verify platform alignment against star sightings",
                    "Confirm battery voltage under simulated entry load",
                ],
            ),
        ],
    )

    # --- Skylab --------------------------------------------------------------
    # Skylab 2 (1973) was NASA's first space-station rescue: launched with its
    # micrometeorite shield torn off, it was saved by a parasol sunshade and an
    # EVA that freed a pinned solar wing.
    skylab = SpacecraftType(
        name="Skylab",
        manufacturer="NASA (McDonnell Douglas)",
        classification="orbital workshop",
        length_m=25.1,
        crew_capacity=3,
        subsystems=[
            Subsystem(
                name="Micrometeorite shield / thermal control",
                category="thermal_protection",
                status="critical",
                failure_modes=[
                    "Shield torn off 63 s after launch by aerodynamic forces "
                    "(Skylab 1) — workshop skin temperatures climb to "
                    "uninhabitable levels",
                    "Replacement parasol must deploy through the science "
                    "airlock without further damage",
                ],
                repair_steps=[
                    "Deploy parasol sunshade: push folded 10 m sunshade "
                    "through the science airlock on extendable rods and let "
                    "it unfold over the exposed skin (Kinzler design, built "
                    "in 10 days)",
                    "Purge workshop atmosphere with nitrogen four times to "
                    "vent heat and any material outgassing before crew "
                    "occupies",
                    "Evaluate permanent replacement: external 'twin-pole' "
                    "shade installed on a later EVA by Skylab 3 crew",
                ],
                diagnostic_checks=[
                    "Track internal skin and atmosphere temperatures after "
                    "shield loss",
                    "Verify parasol coverage of exposed hull section",
                ],
            ),
            Subsystem(
                name="Main solar array wing",
                category="power",
                status="critical",
                failure_modes=[
                    "Array wing pinned closed by a strap of shield debris — "
                    "station at half power (Skylab 1)",
                    "Stand-up EVA with 10 ft hooked pole fails to free it",
                ],
                repair_steps=[
                    "EVA along the array boom to the wing hinge with cable "
                    "cutter on a pole",
                    "Cut the debris strap; crew pulls the wing free by hand "
                    "against the deployment spring (procedure rehearsed in "
                    "the NBS neutral-buoyancy tank)",
                    "Verify full deployment and power output",
                ],
                diagnostic_checks=[
                    "Inspect wing hinge line with TV cameras before EVA",
                    "Measure array current after freeing",
                ],
            ),
            Subsystem(
                name="Docking probe capture latches",
                category="avionics",
                failure_modes=[
                    "Capture latches fail to engage at docking (Skylab 2: "
                    "eight failed capture attempts)",
                ],
                repair_steps=[
                    "Partially disassemble the docking probe in flight to "
                    "release the latch mechanism",
                    "Reattempt capture with manual probe alignment",
                    "Post-flight: redesign latch preload for ground "
                    "maintenance procedures",
                ],
                diagnostic_checks=[
                    "Confirm latch engagement telemetry on capture attempt",
                    "Inspect probe head alignment before approach",
                ],
            ),
            Subsystem(
                name="Apollo Telescope Mount",
                category="payload",
                failure_modes=[
                    "ATM solar-wing loss during launch accident",
                    "Film canister thermal exposure without thermal shield",
                ],
                repair_steps=[
                    "Retrieve and replace ATM film canisters on EVA per "
                    "planned schedule",
                    "Repoint ATM cluster to reduce thermal load after shield "
                    "loss",
                ],
                diagnostic_checks=[
                    "Monitor ATM temperature profile after parasol deploy",
                    "Verify canister cassette latches before EVA retrieval",
                ],
            ),
        ],
    )

    # --- Hubble Space Telescope ----------------------------------------------
    # HST is the canonical serviceable spacecraft: five Shuttle servicing
    # missions, including corrective optics (STS-61) and the first board-level
    # electronic repairs in orbit (STS-125).
    hubble = SpacecraftType(
        name="Hubble Space Telescope",
        manufacturer="NASA / ESA (Lockheed, Perkin-Elmer optics)",
        classification="orbital observatory",
        length_m=13.2,
        crew_capacity=0,
        subsystems=[
            Subsystem(
                name="Primary mirror / corrective optics",
                category="payload",
                failure_modes=[
                    "Spherical aberration: mirror edge ground 2 µm too flat "
                    "(null-corrector assembly error) — images unfixable in "
                    "software alone",
                ],
                repair_steps=[
                    "Install COSTAR corrective-mirror package in the High "
                    "Speed Photometer slot — deployable mirrors re-shape "
                    "light for the affected instruments (STS-61)",
                    "Install WFPC2 with corrective optics figured directly "
                    "into its relay mirrors",
                    "Verify wavefront error with on-orbit star images before "
                    "releasing science operations",
                ],
                diagnostic_checks=[
                    "Star-image wavefront analysis on orbit",
                    "Verify COSTAR arm deployment to optical prescription",
                ],
            ),
            Subsystem(
                name="Rate sensor unit gyros",
                category="navigation",
                failure_modes=[
                    "Gyro failures degrade fine pointing (HST carries 6, "
                    "needs 3) — RSU-2 and RSU-3 failed by 1993",
                    "Electronics control unit faults take gyros offline",
                ],
                repair_steps=[
                    "EVA swap of failed RSUs and ECUs as orbital replacement "
                    "units (STS-61: RSU-2, RSU-3, ECU-1, ECU-3 replaced)",
                    "Re-run gyro calibration and fine-guidance handover",
                    "Post-2009: run 3-gyro / 1-gyro degraded modes to extend "
                    "life without servicing",
                ],
                diagnostic_checks=[
                    "Monitor gyro noise and bias drift in telemetry",
                    "Verify pointing lock after ORU swap",
                ],
            ),
            Subsystem(
                name="Solar arrays",
                category="power",
                failure_modes=[
                    "Original ESA arrays flex in day/night thermal cycles — "
                    "wobble 16 times/day shakes the telescope off target",
                    "One array bent 90° and cannot retract (STS-61)",
                ],
                repair_steps=[
                    "Jettison the bent array from the RMS end effector",
                    "Install rigid second-generation arrays and new Solar "
                    "Array Drive Electronics (STS-61)",
                    "Later missions: swap to third-generation arrays with "
                    "higher output (STS-109)",
                ],
                diagnostic_checks=[
                    "Track jitter in fine-guidance data correlated to orbit "
                    "day/night",
                    "Verify array drive current after replacement",
                ],
            ),
            Subsystem(
                name="Science instrument electronics (ACS/STIS)",
                category="payload",
                status="degraded",
                failure_modes=[
                    "ACS electrical short (2007) — instrument not designed "
                    "for on-orbit board replacement",
                    "STIS low-voltage power supply blown (2004) — cover "
                    "plate held by 100+ non-captive screws",
                ],
                repair_steps=[
                    "STS-125 board-level surgery: remove cover plates with "
                    "custom fastener-capture plate; replace 4 ACS circuit "
                    "boards and install new power supply",
                    "For STIS: remove stripped handrail bolt by brute force "
                    "only after ground authorises; replace LVPS board",
                    "Fetch contingency torque limiter from airlock for "
                    "15-year-seized instrument bolts",
                    "Power-on self-test and on-orbit checkout before "
                    "release from the Shuttle payload bay",
                ],
                diagnostic_checks=[
                    "Instrument POST after board replacement",
                    "Verify thermal straps and harness dress before closeout",
                ],
            ),
        ],
    )

    # --- International Space Station -----------------------------------------
    # The ISS is repaired continuously: CMG swaps, a torn solar array sutured
    # by hand, and emergency ammonia-loop EVAs.
    iss = SpacecraftType(
        name="International Space Station",
        manufacturer="NASA / Roscosmos / ESA / JAXA / CSA",
        classification="modular space station",
        length_m=73.0,
        crew_capacity=7,
        subsystems=[
            Subsystem(
                name="P6 solar array",
                category="power",
                status="degraded",
                failure_modes=[
                    "Guidewire snag tears 4B blanket during redeploy (STS-120, "
                    "2007) — array cannot be fully deployed",
                    "Live array voltage makes direct contact a shock hazard",
                ],
                repair_steps=[
                    "EVA on OBSS at Canadarm2 end to reach the tear 25 m "
                    "from the truss",
                    "Install 5 improvised 'cufflink' sutures built onboard "
                    "from wire and insulation; guide deployment past the "
                    "sutures",
                    "Complete deployment to full span; confirm power output",
                    "Maintain standoff rules: live arrays stay electrically "
                    "isolated from crew tools",
                ],
                diagnostic_checks=[
                    "Video survey of blanket and hinge line before EVA",
                    "Monitor array output and tension during redeploy",
                ],
            ),
            Subsystem(
                name="External ammonia cooling loops",
                category="life_support",
                status="degraded",
                failure_modes=[
                    "Loop A pump module failure (2010) — half the cooling "
                    "capacity lost, 2 of 4 CMGs shed",
                    "Visible ammonia flake leak at P6 truss (2013)",
                ],
                repair_steps=[
                    "Contingency EVA (2013: assembled in 2 days) to swap the "
                    "pump module with an on-orbit spare",
                    "Expect QD ammonia leakage — 2010 EVA-1 aborted when a "
                    "quick-disconnect leaked; depressurise lines first",
                    "Repressurise loop, run activation, verify loop "
                    "temperatures",
                    "Return failed module on a visiting vehicle for root-"
                    "cause analysis (2010 pump flew home on STS-135)",
                ],
                diagnostic_checks=[
                    "Track loop outlet temperatures and pump current",
                    "Visual/telemetry watch for ammonia flakes at the truss",
                ],
            ),
            Subsystem(
                name="Control Moment Gyroscopes",
                category="navigation",
                failure_modes=[
                    "CMG bearing/rotor failure — attitude control margin "
                    "lost (CMG-1 failed 2002)",
                ],
                repair_steps=[
                    "EVA orbital-replacement-unit swap of the failed CMG "
                    "(performed on STS-114, 2005)",
                    "Spin up replacement, verify momentum desaturation "
                    "behaviour",
                    "Return failed CMG for teardown; feed findings into the "
                    "CMG lessons-learned program",
                ],
                diagnostic_checks=[
                    "Monitor bearing temperatures and wheel spin current",
                    "Track desaturation burn frequency as wear indicator",
                ],
            ),
            Subsystem(
                name="USOS life support (ECLSS)",
                category="life_support",
                failure_modes=[
                    "Carbon Dioxide Removal Assembly desiccant bed fault",
                    "Water Recovery System urine processor distillation "
                    "failure",
                ],
                repair_steps=[
                    "Swap CDRA bed orbital replacement unit; reactivate and "
                    "verify CO2 draw-down",
                    "Service urine processor: flush lines, replace filter/"
                    "distillation components on orbit",
                ],
                diagnostic_checks=[
                    "Verify cabin CO2 partial pressure trend",
                    "Check water recovery percentage (target 90%+)",
                ],
            ),
        ],
    )

    # --- Mir -----------------------------------------------------------------
    # The 1997 Progress M-34 collision punctured the Spektr module; the crew
    # isolated it and reconnected its solar arrays through a modified hatch.
    mir = SpacecraftType(
        name="Mir",
        manufacturer="RSC Energia (Soviet Union / Russia)",
        classification="modular space station",
        length_m=19.0,
        crew_capacity=3,
        subsystems=[
            Subsystem(
                name="Spektr module hull",
                category="hull",
                status="critical",
                failure_modes=[
                    "Progress M-34 collision punctures Spektr solar array and "
                    "hull (1997) — module depressurises within minutes",
                    "Debris field risk from the uncontrolled Progress after "
                    "impact",
                ],
                repair_steps=[
                    "Isolate the breached module: crew cuts and seals cables "
                    "through the hatch, then closes it as the pressure drops",
                    "Fit a modified hatch with hermetic cable feed-throughs "
                    "so Spektr's surviving arrays can be re-connected from "
                    "inside (internal spacewalks into the evacuated module)",
                    "Re-route ~70% of lost power via the re-connected array "
                    "cabling",
                    "Document leak location attempts; accept permanent "
                    "module isolation when sealing is impractical",
                ],
                diagnostic_checks=[
                    "Listen/ultrasonic survey for the leak point",
                    "Track station pressure decay rate to size the breach",
                ],
            ),
            Subsystem(
                name="Solar array power network",
                category="power",
                status="degraded",
                failure_modes=[
                    "Spektr array loss removes a major share of station power "
                    "after the collision",
                    "Cabling passes through the sealed hatch — feed-through "
                    "connectors are single points of failure",
                ],
                repair_steps=[
                    "Internal spacewalk into depressurised Spektr to route "
                    "array cables through the modified hatch",
                    "Load-shed non-critical systems during the power "
                    "shortfall",
                    "Progressively restore loads as re-connected arrays come "
                    "online",
                ],
                diagnostic_checks=[
                    "Measure per-array contribution after reconnection",
                    "Verify feed-through connector integrity at the hatch",
                ],
            ),
            Subsystem(
                name="Kurs automated docking",
                category="avionics",
                failure_modes=[
                    "Kurs rendezvous system failures force manual docking — "
                    "the 1997 collision occurred during a manual TORU "
                    "test approach",
                ],
                repair_steps=[
                    "Fall back to manual TORU control from the station with "
                    "TV camera guidance",
                    "Restrict manual test approaches to safety-approved "
                    "profiles after the collision",
                    "Post-flight: service Kurs antenna and logic units on "
                    "the ground",
                ],
                diagnostic_checks=[
                    "Compare Kurs range/range-rate against ground radar "
                    "during approach",
                    "Verify TORU video and control links before undocking "
                    "any Progress",
                ],
            ),
            Subsystem(
                name="Elektron oxygen generation",
                category="life_support",
                failure_modes=[
                    "Elektron electrolysis unit faults — Mir crews repeatedly "
                    "serviced valves and pumps over the station's life",
                ],
                repair_steps=[
                    "Switch to backup Elektron channel or solid-fuel oxygen "
                    "generators",
                    "Service the failed unit in orbit: clean valves, replace "
                    "pump and electrolyte filters",
                    "Progress resupply of water and cartridges as consumable "
                    "backstop",
                ],
                diagnostic_checks=[
                    "Monitor Elektron current and O2 production rate",
                    "Track cabin O2 partial pressure across the service",
                ],
            ),
        ],
    )

    registry.register(dragon)
    registry.register(soyuz)
    registry.register(shuttle)
    registry.register(apollo)
    registry.register(skylab)
    registry.register(hubble)
    registry.register(iss)
    registry.register(mir)
    return registry


#: A pre-populated registry containing real spacecraft.  Tests and callers
#: can use this directly, or call :func:`_build_catalog` for a fresh copy.
SPACECRAFT_CATALOG: SpacecraftRegistry = _build_catalog()