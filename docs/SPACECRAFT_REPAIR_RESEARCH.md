# Spacecraft Repair Research Dossier

Real, documented spacecraft failure/repair events, researched to drive concrete additions
to the R1-A1 repair registry (`src/repair/registry.py`). Every event below includes the
failure mode and root cause, the actual repair procedure (ground or in-flight), the tools
used, and a mapping to the registry's subsystem categories:

`propulsion`, `life_support`, `power`, `avionics`, `hull`, `payload`,
`thermal_protection`, `navigation`, `communications`

---

## 1. Apollo 13 (April 1970) — cryogenic O2 tank explosion, LM lifeboat

### Failure modes and causes
- **O2 Tank 2 explosion (life_support / power / propulsion).** Oxygen Tank 2 in the
  Service Module (built by Beech Aircraft for North American Rockwell) contained two
  thermostatic switches rated for the CM's 28 V DC, but 1965 revised specs called for
  65 V for faster tank pressurization during KSC ground testing — the switches Beech
  used were never re-rated. The tank had also been dropped (~5 cm) during handling at
  NAR and had a damaged fill/drain line, so after a Countdown Demonstration Test it
  could not be drained normally; ground crews boiled the oxygen off with the tank's
  internal heaters at 65 V for ~8 hours. This welded the thermostatic switch contacts
  shut and damaged the Teflon insulation on the fan-motor wiring. In flight, a routine
  cryo stir (requested by EECOM Sy Liebergot to fix a misreading pressure sensor)
  shorted the damaged insulation and ignited it, exploding Tank 2; the blast also
  damaged Tank 1's plumbing, venting both SM oxygen tanks to space.
  Source: https://en.wikipedia.org/wiki/Apollo_13 (Investigation and response);
  https://www.nasa.gov/missions/apollo/apollo-13-mission-details/
- **Cascading loss.** Without O2, the SM fuel cells (which also produce drinking/cooling
  water) died: SM propulsion, power, and life support were lost. The CM had to be shut
  down to preserve its batteries for reentry; the crew moved into the LM *Aquarius* as
  a lifeboat. The LM was designed for 2 men / 45 hours on the surface; it had to support
  3 men for ~4 days. Source: https://en.wikipedia.org/wiki/Apollo_13

### Repairs / workarounds and tools
1. **CO2 scrubber adaptation — the "mailbox" (life_support).** The LM's round lithium
   hydroxide (LiOH) canisters could not support 3 crew for the return; the CM had plenty
   of LiOH canisters but they were square cartridges incompatible with the LM's round
   receptacles. Ground engineers devised an adapter built entirely from on-board
   materials: plastic covers ripped from procedure manuals, duct tape, a suit hose, and
   other cabin items, to force LM suit-loop air through a CM LiOH cartridge. CAPCOM
   Joseph Kerwin read the construction procedure up over ~1 hour; Swigert and Haise
   built it; CO2 levels began dropping immediately.
   Tools/materials: duct tape, procedure-manual plastic covers, LM EVA suit hose,
   cardboard, sock. Sources: https://en.wikipedia.org/wiki/Apollo_13 ;
   https://www.nasa.gov/image-article/apollo-13-lunar-module-mail-box/
2. **Power-down / power-up procedures (power / avionics).** The CM was powered down to
   near-zero load; LM power consumption was cut to the lowest possible level (the LM ran
   on silver-zinc batteries that, unlike fuel cells, produce no water — both electricity
   and cooling water became critical). Crew water ration was 200 mL/person/day; cabin
   temperature fell to ~3 °C. Ground teams (EECOM John Aaron and others) wrote and
   simulator-validated a compressed CM reactivation/power-up checklist from scratch so
   the cold, shorted-out CM could be powered up on battery reserves alone for reentry.
   Source: https://en.wikipedia.org/wiki/Apollo_13
3. **Propulsion workarounds.** The SM engine could not be trusted; the LM descent engine
   was used for the free-return burn and mid-course corrections. Alignment for the burns
   was done manually using the LM's alignment optical telescope and the Sun/Earth as
   references after the CM guidance platform was shut down.
   Source: https://en.wikipedia.org/wiki/Apollo_13

### Registry mapping
- life_support: "LiOH canister form-factor incompatibility; improvised adapter (mailbox)"
- power: "Fuel-cell loss → full power-down; battery-budget reactivation checklist"
- propulsion: "SM engine safing; backup-engine (LM DPS) burn substitution"

---

## 2. Skylab 2 (May–June 1973) — first in-space station repair

### Failure modes and causes
- **Micrometeorite shield torn off at launch (hull / thermal_protection).** During the
  May 14, 1973 Saturn V launch, aerodynamic forces tore off Skylab's combined
  micrometeorite/thermal shield, which also ripped away solar array wing 1 and left
  debris jamming solar array wing 2. Without the shield the workshop overheated in
  sunlight; rising interior temperatures outgassed toxic materials into the atmosphere
  and threatened film and food stores. Source: https://en.wikipedia.org/wiki/Skylab_2
- **Jammed solar array wing (power).** A metal strap fragment of the lost shield pinned
  the remaining solar array wing against the hull; array could not deploy, leaving the
  station critically underpowered. Source: https://en.wikipedia.org/wiki/Skylab_2 ;
  https://www.nasa.gov/history/skylab-2-first-repair-spacewalk/

### Repairs and tools
1. **Stand-up EVA attempt (failed).** Conrad positioned the CSM next to the jammed wing;
   Weitz stood in the open hatch (Kerwin holding his legs) and tugged at the wing with a
   **10-foot hooked pole**. This failed and burned a large amount of the station's
   nitrogen maneuvering propellant to hold attitude. Source: https://en.wikipedia.org/wiki/Skylab_2
2. **Docking probe field-repair.** The CSM's capture latches failed eight times; the
   crew suited up and **partially disassembled the docking probe** in-flight, after
   which docking succeeded. Source: https://en.wikipedia.org/wiki/Skylab_2
3. **Parasol sunshade (thermal_protection).** The crew deployed a collapsible parasol
   sunshade — designed on the ground by Jack Kinzler ("Mr. Fix It," later awarded the
   NASA Distinguished Service Medal) — **through the small scientific airlock from
   inside**, no EVA needed. Interior temperatures dropped to sustainable levels. Ground
   controllers also purged the workshop atmosphere with pure nitrogen four times before
   refilling with N2/O2. Source: https://en.wikipedia.org/wiki/Skylab_2 ;
   https://www.nasa.gov/history/50-years-ago-skylab-2-the-we-fix-anything-crew/
4. **Freed solar array EVA (power).** Two weeks later Conrad and Kerwin did a full EVA
   (rehearsed in MSFC's Neutral Buoyancy Simulator): they cut the restraining strap with
   a **cable cutter tool on a long pole**, attached a line, and physically pulled the
   wing free — the sudden deployment flung both men off the hull (caught by tethers).
   Freed array restored the station's power budget.
   Source: https://en.wikipedia.org/wiki/Skylab_2 ; https://www.nasa.gov/history/skylab-2-first-repair-spacewalk/

### Registry mapping
- thermal_protection: "Shield loss → deploy replacement sunshade through airlock"
- power: "Array deployment jam → EVA strap cut + manual deploy; NBS rehearsal first"
- hull: "Debris-induced structural interference with deployables"
- propulsion/avionics (CSM): "Docking capture-latch failure → in-flight probe disassembly"

---

## 3. Hubble Servicing Mission 1 — STS-61 (December 1993)

### Failure modes and causes
- **Spherical aberration of the 2.4 m primary mirror (payload).** The mirror's outer
  edge was ground 2 µm too flat (a null-corrector metrology error), scattering light
  into a fuzzy halo. The mirror itself could not be replaced in orbit.
  Source: https://esahubble.org/about/history/servicing_mission_1/
- **Gyroscope failures (navigation).** Rate Sensor Units (RSUs) containing HST's
  pointing gyros were failing, degrading pointing control.
  Source: https://en.wikipedia.org/wiki/STS-61
- **Solar array wobble (power).** The ESA-built 12 m solar arrays flexed/wobbled ~16
  times per day at day/night terminator crossings, jittering the telescope; one array
  was observed bent 90° on approach. Sources: https://en.wikipedia.org/wiki/STS-61 ;
  https://esahubble.org/about/history/servicing_mission_1/

### Repairs and tools (5 EVAs, then a record)
1. **COSTAR (Corrective Optics Space Telescope Axial Replacement).** Removed the High
   Speed Photometer axial instrument and installed COSTAR: five pairs of small
   corrective mirrors deployed on arms in front of the Faint Object Camera, Faint
   Object Spectrograph, and GHRS, restoring focus for those instruments. Opened the
   aft-shroud doors during a night pass to minimize thermal change and outgassing
   contamination of optics. Sources: https://esahubble.org/about/history/servicing_mission_1/ ;
   https://en.wikipedia.org/wiki/STS-61
2. **WFPC2 swap.** Replaced the Wide Field/Planetary Camera with WFPC2, which carried
   **built-in corrective optics** (realigned internal relay mirror) plus improved CCDs;
   guide studs installed to ease the 280 kg camera changeout.
   Source: https://esahubble.org/about/history/servicing_mission_1/
3. **Gyro/electronics replacement (navigation/avionics).** Hoffman replaced RSU-2
   (Gyros 2-3, 2-4) and RSU-3 (Gyros 3-5, 3-6), then Electrical Control Units ECU-3 and
   ECU-1. Source: https://en.wikipedia.org/wiki/STS-61
4. **Solar arrays + SADE.** Both ESA arrays replaced with rigid redesigned arrays;
   Solar Array Drive Electronics replaced; one bent array that would not retract was
   jettisoned. Flight-computer coprocessor and GHRS redundancy kit installed.
   Sources: https://esahubble.org/about/history/servicing_mission_1/ ; https://en.wikipedia.org/wiki/STS-61

### Registry mapping
- payload: "Optics aberration → corrective-optics instrument swap (COSTAR/WFPC2)"
- navigation: "RSU gyro module replacement (ORU changeout)"
- power: "Array wobble → rigid array + drive electronics replacement"

---

## 4. Hubble Servicing Mission 4 — STS-125 (May 2009)

### Failure modes and causes
- **ACS failure (payload).** Advanced Camera for Surveys failed June 2006 (electrical),
  partially recovered, failed again 2007 with an electrical short; its Wide Field
  Channel was dead. Not designed for on-orbit servicing.
  Source: https://en.wikipedia.org/wiki/STS-125
- **STIS failure (payload).** Space Telescope Imaging Spectrograph failed 2004 from a
  blown power supply (Side-2 low-voltage power supply). Also never designed for EVA
  servicing. Source: https://en.wikipedia.org/wiki/STS-125

### Repairs and tools (first-ever board-level instrument surgery on orbit)
1. **ACS board-level repair (EVA 3).** With custom tools, astronauts removed an access
   panel, **replaced the camera's four circuit boards**, and installed a new power
   supply. ACS passed aliveness tests. Source: https://en.wikipedia.org/wiki/STS-125
2. **STIS power-supply board repair (EVA 4).** Required removing a cover plate held by
   **>100 screws** using a purpose-built **fastener-capture plate** that trapped screws
   and washers so none floated free. A handrail blocking the plate had a **stripped
   bolt**; after multiple failed removal attempts, ground controllers told Massimino to
   pull it off by brute force. The low-voltage power-supply board was then replaced.
   Source: https://en.wikipedia.org/wiki/STS-125
3. **WFC3 install (EVA 1).** WFPC2 (installed 1993) removed and Wide Field Camera 3
   installed. Removal bolts had seized after 15+ years in orbit and needed more torque
   than expected; a **contingency torque limiter** was fetched from the airlock so
   Feustel could apply higher torque without over-stressing the fittings.
   Source: https://en.wikipedia.org/wiki/STS-125
4. Also replaced: COSTAR removed (its corrective function now built into every
   instrument) and Cosmic Origins Spectrograph installed; all six gyros, batteries, and
   a Fine Guidance Sensor swapped; soft-capture mechanism fitted for future deorbit.
   Sources: https://en.wikipedia.org/wiki/STS-125 ;
   https://science.nasa.gov/mission/hubble/observatory/missions-to-hubble/servicing-mission-4/

### Registry mapping
- payload: "Instrument power-supply failure → board-level replacement with
  fastener-capture tooling; seized fasteners → contingency torque limiter;
  stripped bolt → brute-force removal under ground direction"
- power: "Battery module changeout"
- navigation: "All-gyro and FGS replacement"

---

## 5. Space Shuttle STS-114 (July–August 2005) — Return to Flight, first in-flight TPS repair

### Failure modes and causes
- **Protruding gap fillers (thermal_protection).** Two gap fillers between belly TPS
  tiles protruded up to ~2.5 cm; wind-tunnel testing showed protrusions that large
  could trip boundary-layer turbulence during reentry, causing local overheating —
  the same class of concern raised by the Columbia (STS-107) loss.
  Sources: https://en.wikipedia.org/wiki/STS-114 ; https://www.nasa.gov/mission/sts-114/
- **Failed ISS CMG-1 (navigation, station payload delivery).** ISS Control Moment
  Gyroscope 1 had failed in 2002; STS-114 carried the replacement up on the Lightweight
  Multi-purpose experiment support structure Carrier (LMC) together with a TPS Repair
  Box. Source: https://en.wikipedia.org/wiki/STS-114

### Repairs and tools
1. **TPS repair demonstration (EVA 1).** In the payload bay, Noguchi and Robinson ran
   Detailed Test Objective 848: application of **NOAX (Non-Oxide Adhesive
   eXperimental)** crack-repair material and **emittance wash** on sample RCC/tile
   coupons in the TPS Repair Box to validate techniques post-Columbia.
   Sources: https://www.spacefacts.de/mission/english/sts-114.htm ;
   https://ntrs.nasa.gov/api/citations/20070020343/downloads/20070020343.pdf
2. **CMG replacement (EVA 2).** Swapped the failed ISS CMG for the new unit from the
   LMC. Source: https://en.wikipedia.org/wiki/STS-114
3. **Gap filler removal (EVA 3) — first repair on the exterior of a spacecraft in
   flight.** Robinson rode the ISS Canadarm2 (positioned under Discovery's belly — an
   unprecedented arm operation near the orbiter's fragile tiles) and simply **pulled
   both protruding gap fillers out with gloved fingers**; planned contingencies
   (forceps, hacksaw) were not needed. A wrinkled thermal blanket near the commander's
   window was later cleared for entry by wind-tunnel analysis.
   Sources: https://en.wikipedia.org/wiki/STS-114 ; https://www.nasa.gov/mission/sts-114/

### Registry mapping
- thermal_protection: "Gap filler protrusion → EVA manual extraction from robot arm;
  TPS repair kit (NOAX, emittance wash) validated"
- navigation (ISS payload): "CMG ORU swap via EVA"

---

## 6. International Space Station — recurring maintenance events

### 6a. CMG failures (navigation)
- **Failure mode:** bearing/rotor failures in the four 600 lb Control Moment Gyroscopes
  in the Z1 truss segment (e.g., CMG-1 failed June 2002). Station attitude control
  tolerates one failure; a second forces thruster attitude control (propellant cost).
- **Repair:** EVA ORU swap (STS-114 EVA-2, 2005, delivered on the LMC); the failed unit
  is returned to Earth for teardown. NASA published formal "lessons learned" on CMG
  life, vibration, and lubrication.
  Sources: https://en.wikipedia.org/wiki/STS-114 ;
  https://ntrs.nasa.gov/api/citations/20100021932/downloads/20100021932.pdf

### 6b. Torn P6 solar array, STS-120/Expedition 16 (October–November 2007)
- **Failure mode (power):** on 30 Oct 2007, redeploying the relocated P6 4B solar array
  wing, a guidewire/snag tore the blanket (~76% deployed, two tears). Deployment was
  halted with the wing structurally unsafe.
  Source: https://en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station
- **Repair (3 Nov 2007):** Scott Parazynski, assisted by Doug Wheelock, rode the
  Shuttle's **OBSS inspection boom** (itself footed on the station's Canadarm2 — the
  first such use, reaching farther than the station arm alone) to the damage site and
  installed five improvised **"cufflink" sutures** (wire-and-strap assemblies built
  on board) to bridge the tear, then completed deployment. Regarded as exceptionally
  hazardous: shock risk from live photovoltaic arrays, unprecedented OBSS use, no
  shuttle rescue possible. Source: https://en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station ;
  https://www.spacefacts.de/mission/english/sts-120.htm

### 6c. Ammonia cooling-loop failures (thermal_protection-adjacent; registry: life_support/power chain)
- **2010 Loop A pump module failure (31 Jul 2010).** The external ammonia cooling loop's
  pump module failed; two of four CMGs and other subsystems were shut down to cut heat
  load. Three EVAs required: EVA 1 (7 Aug) aborted mid-task by an **ammonia leak at one
  of four fluid quick-disconnects**; EVA 2 (11 Aug) removed the failed pump; EVA 3
  restored Loop A. Failed pump returned on STS-135 for root-cause analysis.
  Source: https://en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station ;
  https://ntrs.nasa.gov/api/citations/20150004079/downloads/20150004079.pdf
- **2013 external ammonia leak (9 May 2013).** Crew saw white flakes streaming from the
  P6 truss; external cameras confirmed an ammonia coolant leak. Two days later a
  contingency EVA (Cassidy/Marshburn) replaced the suspect pump module with a spare —
  leak stopped. Source: https://en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station
- **2009 S1-3 radiator panel damage.** Micrometeoroid-damaged radiator panel with
  potential to leak ammonia from the External Thermal Control System; managed by
  monitoring/isolation planning. Source: https://en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station

### Registry mapping
- navigation: "CMG bearing failure → EVA ORU swap; return-for-analysis loop"
- power: "Array tear → improvised cufflink sutures from OBSS boom; live-circuit EVA precautions"
- life_support/thermal: "Ammonia QD leak → EVA pump-module changeout; load-shed
  (CMG shutdown) as interim thermal mitigation"

---

## 7. Salyut 7 rescue — Soyuz T-13 (June 1985)

### Failure modes and causes
- **Total station death (power → avionics → life_support cascade).** In February 1985 a
  sensor failed in Salyut 7's solar-array pointing system; the arrays stopped tracking
  the Sun, the batteries (8 total) drained and two were destroyed, and a telemetry
  radio fault prevented TsUP (ground control) from seeing the problem. The station went
  silent, froze (frost on interior walls), and tumbled slowly with arrays pointed
  randomly. Source: http://www.astronautix.com/s/soyuzt-13eo-4-a.html

### Repairs and tools (Dzhanibekov/Savinykh)
1. **Rendezvous with an uncontrolled target.** No radar docking possible; crew flew
   manual approach, did a fly-around inspection, and used a **hand-held laser
   rangefinder** to judge distance — the first docking with an inactive station.
   They confirmed via the docking-collar electrical connectors that the station bus
   was dead, and sampled station air through the hatch before entering (cold but
   breathable). Source: http://www.astronautix.com/s/soyuzt-13eo-4-a.html
2. **Cold-soak reactivation procedure.** Wearing winter clothing in the frosted
   station: used Soyuz T-13's thrusters to slew the station so the arrays faced the
   Sun and recharged the surviving batteries; relied on Soyuz's air-regeneration
   system until the station's was revived; turned on air heaters (10 Jun); reactivated
   attitude control (13 Jun) — enabling a Progress resupply; **delayed wall heaters
   until all frost evaporated** to keep meltwater out of equipment; normal humidity only
   by end of July; water tanks thawed by end of June; frozen water heater destroyed —
   fluids warmed with a television light. Source: http://www.astronautix.com/s/soyuzt-13eo-4-a.html
3. **Parts pipeline + EVA.** Progress 24 (Jun 23–Jul 15) delivered propellant, solar
   array extensions, a new water heater, three new batteries, and ~40 kg of parts;
   on 2 Aug the crew did a ~5 h EVA in new semi-rigid suits to install the third pair
   of solar array add-ons. Source: http://www.astronautix.com/s/soyuzt-13eo-4-a.html

### Registry mapping
- power: "Sun-pointing sensor failure → battery deep-discharge; manual re-point with
  docked vehicle thrusters; staged recharge; battery replacement via resupply"
- life_support: "Cold-soak moisture management: heaters only after frost sublimates"
- communications: "Telemetry fault masking cascading failure → inspection-before-entry protocol"

---

## 8. Mir — Progress M-34 collision with Spektr (25 June 1997)

### Failure modes and causes
- **Hull puncture + depressurization (hull).** During a manual TORU docking test,
  Progress M-34 collided with Spektr, puncturing its hull (near the base of a solar
  array) and damaging one array. The module depressurized.
  Source: https://www.pbs.org/wgbh/nova/mir/spektr.html/
- **Power loss cascade (power).** Sealing off Spektr saved the station's atmosphere but
  severed the cables carrying power from Spektr's four arrays (~half the station's
  electricity). Source: https://www.pbs.org/wgbh/nova/mir/spektr.html/

### Repairs and tools
1. **Immediate:** crew cut/sealed hatch cable pass-throughs and closed the Spektr
   hatch to isolate the leak; station spun up temporarily and was recovered.
   Source: https://www.pbs.org/wgbh/nova/mir/spektr.html/
2. **Internal spacewalks (IVA in the depressurized module).** In August 1997 Solovyov
   and Vinogradov, in suits, entered the airless Spektr and **reconnected the power
   cables** through a modified hatch plate with hermetic cable penetrations — restoring
   array power while keeping Spektr isolated. An October internal spacewalk connected
   two arrays to a remote sun-tracking control system. Net result: ~70% of
   pre-collision power restored. Source: https://www.pbs.org/wgbh/nova/mir/spektr.html/
3. The hole itself was small and elusive; hull patching efforts were limited — the
   practical repair was **isolation + resource rerouting**, not sealing.
   Source: https://www.pbs.org/wgbh/nova/mir/spektr.html/

### Registry mapping
- hull: "Collision puncture → compartment isolation; hermetic feed-through hatch modification"
- power: "Severed array cabling → IVA cable reconnection in depressurized volume"

---

## 9. Modern contrast cases

### 9a. Boeing Starliner CFT (June–September 2024) — thruster failures, no in-flight repair possible
- **Failure modes (propulsion):** as *Calypso* approached the ISS, five of eight
  aft-facing RCS thrusters failed; 6-DOF control was briefly lost (NASA waived flight
  rules to dock with four recovered). Persistent helium leaks in the service module
  (initially blamed on one defective flange seal, then found systemic) compounded the
  problem. Post-mission investigation (Feb 2026 report) found the thruster failures
  most likely caused by a combination of **oxidizer (NTO) heating in the thruster
  "doghouse"** — partial vaporization creating gas bubbles and restricting flow — and
  **Teflon poppet-seal deformation/swelling** in the oxidizer valves under NTO, heat,
  and pressure. Source: https://en.wikipedia.org/wiki/Boe-CFT
- **Response — no crewed-repair option:** on-orbit troubleshooting (hot-fire of five
  aft thrusters restored 6-DOF for docking) plus a **ground analog test at White
  Sands**: a flight-spare thruster fired through >1,000 pulses replicating
  launch-to-docking, then five undock-to-deorbit sequences. Despite that, NASA judged
  crewed return too risky; Starliner returned **uncrewed** (7 Sep 2024, one more
  thruster failed en route, leaving zero fault tolerance) and the crew returned on
  SpaceX Crew-9 in March 2025. Sources: https://en.wikipedia.org/wiki/Boe-CFT ;
  https://www.nasaspaceflight.com/2024/08/cft-update/
- **Registry mapping:** propulsion: "Thruster doghouse thermal soak + seal swelling →
  ground-replica test campaign; crew-transfer as the ultimate 'repair' when the vehicle
  can't be fixed or trusted."

### 9b. JWST (launched 2021) — deliberately unserviceable
- JWST sits at Sun–Earth L2, 1.5 million km away, and **was not designed for servicing**:
  no grapple fixtures, no replaceable ORUs, no propellant refill interface. Lifetime is
  bounded by instrument/component failures and propellant exhaustion; robotic refueling
  has been studied but is hindered by lack of servicing interfaces and outgassing-
  contamination risk to the optics. Contrast: Hubble's modularity added ~$23M up front
  and was projected to save ~5× that in integration/test alone (Grunsfeld).
  Source: https://ccapp.osu.edu/news/repairing-and-building-future-space-telescopes
- **Registry mapping:** design-philosophy constraint — encode as a spacecraft attribute
  ("serviceable: false") rather than a subsystem; drives different failure-mode
  handling: redundancy and ground-commanded workarounds (e.g., switching to redundant
  electronics, one-gyro mode) instead of physical repair.

---

## Summary table

| Spacecraft | Event (year) | Subsystem category | Failure | Repair summary | Sources |
|---|---|---|---|---|---|
| Apollo 13 | O2 tank explosion (1970) | life_support | Welded thermostat switch + damaged Teflon wire insulation → tank explosion, fuel cells lost | LM lifeboat; power-down; improvised "mailbox" LiOH adapter from manuals, hose, duct tape; ground-written CM power-up checklist | en.wikipedia.org/wiki/Apollo_13; nasa.gov/image-article/apollo-13-lunar-module-mail-box |
| Apollo 13 | Propulsion workarounds (1970) | propulsion | SM engine untrusted | LM descent-engine burns; manual optical alignment | en.wikipedia.org/wiki/Apollo_13 |
| Skylab 2 | Launch damage (1973) | thermal_protection | Micrometeorite shield torn off at launch | Parasol sunshade deployed through science airlock (Kinzler design); N2 atmosphere purge ×4 | en.wikipedia.org/wiki/Skylab_2; nasa.gov/history/skylab-2-first-repair-spacewalk |
| Skylab 2 | Jammed solar wing (1973) | power | Shield debris strap pinning array wing | EVA: cable-cutter on pole, manual pull free (NBS-rehearsed); earlier stand-up EVA with 10-ft hooked pole failed | en.wikipedia.org/wiki/Skylab_2 |
| Skylab 2 | Docking latch failure (1973) | avionics | Capture latches failed ×8 | In-flight partial disassembly of docking probe | en.wikipedia.org/wiki/Skylab_2 |
| HST / STS-61 | Spherical aberration (1993) | payload | Mirror edge 2 µm too flat (null-corrector error) | COSTAR corrective-mirror package installed in HSP slot; WFPC2 with built-in corrective optics | esahubble.org/about/history/servicing_mission_1; en.wikipedia.org/wiki/STS-61 |
| HST / STS-61 | Gyro failures (1993) | navigation | RSU gyro failures degrading pointing | RSU-2, RSU-3 + ECU-1, ECU-3 ORU swaps on EVA | en.wikipedia.org/wiki/STS-61 |
| HST / STS-61 | Array wobble (1993) | power | Thermal flex wobble 16×/day; one array bent 90° | Both ESA arrays replaced with rigid arrays; SADE replaced; bent array jettisoned | en.wikipedia.org/wiki/STS-61; esahubble.org |
| HST / STS-125 | ACS dead (2009) | payload | Electrical short, not designed for servicing | First board-level orbital repair: 4 circuit boards + new PSU with custom tools | en.wikipedia.org/wiki/STS-125 |
| HST / STS-125 | STIS dead (2009) | payload | Blown LV power supply (2004) | Cover plate (100+ screws) removed with fastener-capture plate; stripped handrail bolt removed by brute force on ground go; PSU board replaced | en.wikipedia.org/wiki/STS-125 |
| HST / STS-125 | WFPC2→WFC3 (2009) | payload | Instrument upgrade; seized bolts after 15 yr | Contingency torque limiter fetched from airlock | en.wikipedia.org/wiki/STS-125 |
| Shuttle / STS-114 | Gap filler protrusion (2005) | thermal_protection | Two gap fillers protruding ~2.5 cm, turbulence/heating risk | EVA-3: Robinson on Canadarm2 pulled fillers out by hand — first in-flight spacecraft exterior repair | en.wikipedia.org/wiki/STS-114; nasa.gov/mission/sts-114 |
| Shuttle / STS-114 | TPS repair demo (2005) | thermal_protection | Post-Columbia need for on-orbit TPS fixes | DTO-848: NOAX crack filler + emittance wash tested on coupons in TPS Repair Box | spacefacts.de/mission/english/sts-114.htm; ntrs.nasa.gov 20070020343 |
| ISS / STS-114 | CMG-1 failure (2002, fixed 2005) | navigation | CMG bearing/rotor failure | EVA ORU swap; failed unit returned for teardown; CMG lessons-learned program | en.wikipedia.org/wiki/STS-114; ntrs.nasa.gov 20100021932 |
| ISS / STS-120 | Torn P6 array (2007) | power | Guidewire snag tore 4B blanket during redeploy | EVA from OBSS-on-Canadarm2: 5 improvised "cufflink" sutures, deployment completed; live-array shock hazard | en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station; spacefacts.de/mission/english/sts-120.htm |
| ISS | Loop A pump failure (2010) | life_support (thermal) | Ammonia pump module failure; 2/4 CMGs shed | 3 EVAs; QD ammonia leak aborted EVA-1; pump swapped; returned on STS-135 for RCA | en.wikipedia.org/wiki/Maintenance_of_the_ISS; ntrs.nasa.gov 20150004079 |
| ISS | Ammonia leak (2013) | life_support (thermal) | Visible ammonia flake leak at P6 truss | Contingency EVA in 2 days; pump module replaced with spare | en.wikipedia.org/wiki/Maintenance_of_the_International_Space_Station |
| Salyut 7 | Station death (1985) | power | Array-pointing sensor failure + telemetry fault → battery deep discharge, freeze, tumble | Manual laser-rangefinder docking; Soyuz thrusters re-point arrays; staged thaw/heat procedure; batteries/parts via Progress; EVA array extensions | astronautix.com/s/soyuzt-13eo-4-a.html |
| Mir | Progress M-34 collision (1997) | hull | Progress punctured Spektr hull, depressurization | Module isolated; modified hatch with hermetic cable feed-throughs; internal spacewalks reconnected array cabling → ~70% power | pbs.org/wgbh/nova/mir/spektr.html |
| Starliner CFT | Thruster failures (2024) | propulsion | NTO heating in doghouse + Teflon poppet-seal swelling → 5/8 aft RCS failed | On-orbit hot-fire; White Sands ground-replica test; returned uncrewed; crew returned on Crew-9 | en.wikipedia.org/wiki/Boe-CFT; nasaspaceflight.com/2024/08/cft-update |
| JWST | Unserviceable design (2021–) | (design attribute) | No servicing interfaces at L2 | Redundancy + ground workarounds only; robotic refueling studied; contrast with HST servicing economics | ccapp.osu.edu/news/repairing-and-building-future-space-telescopes |

## Cross-cutting lessons for the registry

1. **Improvised-material repairs are first-class procedures**: Apollo 13 mailbox
   (tape/manuals/hose), Skylab parasol, ISS cufflinks — the registry's `repair_steps`
   should support "field-expedient" step types, not just part swaps.
2. **Ground-in-the-loop is part of the procedure**: every case above involved
   ground-devised procedures read up and executed by crew (mailbox, brute-force
   handrail, cufflink build, Starliner hot-fire). A `requires_ground_support` flag
   would be realistic.
3. **Rehearsal media matter**: NBS (Skylab), simulators (Apollo power-up), ground
   replica hardware (Starliner White Sands). Diagnostic confidence can be tied to
   whether a procedure was rehearsed.
4. **Isolation beats repair when sealing is impossible** (Mir/Spektr): model
   "isolate compartment + reroute resources" as a distinct repair strategy.
5. **Load-shedding as mitigation**: Apollo 13 power-down, ISS CMG shedding during the
   2010 cooling failure, Salyut 7 staged heater activation — degraded-mode operating
   states deserve explicit registry representation.
6. **Tooling is the long pole**: fastener-capture plates, contingency torque limiters,
   cable cutters on poles, OBSS-as-platform — several failures were only repairable
   because a purpose-built tool existed; missing tools should gate procedures.
