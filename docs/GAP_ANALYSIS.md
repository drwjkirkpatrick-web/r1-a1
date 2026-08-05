# R1-A1 Gap Analysis: Astromech Knowledge Domains

Comparing canonical astromech droid capabilities (R2-D2's demonstrated
skills across the Star Wars saga) against R1-A1's current module set,
identifying what is built, what is planned, and what this document
proposes to add now.

---

## Legend

| Status | Meaning |
|---|---|
| ✅ Built | Module exists and is tested |
| 🟡 Partial | Some coverage exists but gaps remain |
| 🔴 Gap | No module exists |
| ➕ New | Proposed in this analysis |

---

## 1. Core AI & Communication

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Language model / conversation | Understands speech, responds in droid binary | ✅ Built | `src/brain/` |
| Memory & fact store | Remembers owner preferences, mission data | ✅ Built | `src/brain/memory.py` |
| Personality / temperament | Distinct personality (brave, loyal, stubborn) | ✅ Built | `src/brain/personality.py` |
| Affective state (mood) | Shows fear, joy, determination, grief | ✅ Built | `src/brain/limbic.py` |
| Droid-to-droid communication | Astromech binary (whistles/blips) | 🟡 Partial | `src/audio/` — audio I/O exists, no binary protocol |
| Multi-language translation | Translates droid binary for humans | 🔴 Gap | — |
| Computer slicing / security bypass | Slices into Death Star, Imperial networks | 🔴 Gap | — |
| Encryption / decryption | Reroutes power, unlocks doors | 🔴 Gap | — |

## 2. Sensing & Perception

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Visual sensing (camera eye) | Recognizes people, objects, text | ✅ Built | `src/eye/` |
| Vision-LLM captioning | — (modern addition) | ✅ Built | `src/eye/` + vision node |
| Spatial awareness (local) | Navigates corridors, avoids obstacles | ✅ Built | `src/awareness/` (8 upgrades) |
| Long-range sensor scanning | Scans for life forms, ships at distance | 🔴 Gap | — |
| Hazard detection (radiation) | Detects radiation, toxic atmosphere | 🔴 Gap | — |
| Atmospheric analysis | Samples air composition | 🔴 Gap | — |
| Fire / smoke detection | Detects fires aboard ships | 🔴 Gap | — |
| Life sign detection | Scans for biological activity | 🔴 Gap | — |

## 3. Navigation

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Local navigation (indoor) | Navigates corridors, rooms | ✅ Built | `src/awareness/` + `src/motion/` |
| Odometry / pose fusion | — (modern addition) | ✅ Built | `src/awareness/pose.py` |
| Occupancy grid mapping | — (modern addition) | ✅ Built | `src/awareness/occupancy.py` |
| Celestial navigation (stars) | Uses star positions for orientation | ➕ New | `src/astro/navigation.py` |
| Solar system body tracking | Knows planetary positions | ➕ New | `src/astro/solar_system.py` |
| Star catalog (real data) | Maps the galaxy | ➕ New | `src/astro/star_catalog.py` |
| Milky Way structure | Knows galactic regions, hyperspace lanes | ➕ New | `src/astro/milky_way.py` |
| Astronomical data bridge | Looks up real-time ephemeris, objects | ➕ New | `src/astro/bridge.py` |
| Map storage & retrieval | Stores and replays holographic maps | 🟡 Partial | `src/awareness/occupancy.py` (local only) |

## 4. Spacecraft Operations

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Ship power interfacing | Plugs into ship power sockets | 🟡 Partial | `src/interconnect/` (MCU link, not ship power) |
| Ship system monitoring | Monitors engine, shield, hull status | 🔴 Gap | — |
| Starship repair (mechanical) | Fixes hyperdrives, deflector shields | ➕ New | `src/repair/framework.py` |
| Starship repair (electronic) | Repairs computer circuits, wiring | ➕ New | `src/repair/framework.py` |
| Diagnostic engine | Runs full system diagnostics | ➕ New | `src/repair/diagnostics.py` |
| Spacecraft knowledge base | Knows ship types, subsystems, parts | ➕ New | `src/repair/registry.py` |
| Hull patching | Applies emergency hull repairs | 🔴 Gap | — |
| Hyperdrive repair | Replaces/calibrates hyperdrive motivators | ➕ Framework | `src/repair/` (extensible) |
| Fire suppression | Extinguishes fires aboard ships | 🔴 Gap | — |
| Life support management | Monitors and repairs life support | ➕ Framework | `src/repair/` (extensible) |

## 5. Physical Capabilities

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Wheeled locomotion | Drives on 2 feet + center leg | ✅ Built | `src/motion/` |
| Dome rotation | 360° dome rotation | ✅ Built | `src/motion/dome.py` |
| 2-3-2 mode | Retractable center leg | ✅ Built | `src/motion/center_leg.py` |
| Expressive gaits | Body language via movement | ✅ Built | `src/motion/express.py` |
| Electric shock defense | Zaps assailants with prod | 🔴 Gap | — |
| Tool deployment | Extends utility arm with tools | 🔴 Gap | — |
| Gripper / manipulator | Picks up and carries objects | 🔴 Gap | — |
| Hover / flight (rocket boosters) | Flies briefly in some episodes | 🔴 Gap | (out of scope) |

## 6. Output & Display

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Hologram projection | Projects holographic maps/messages | ✅ Built | `src/projector/` |
| Front logic display | Shows expressions, gauges | ✅ Built | `src/display/` |
| Audio output (chirps/speech) | Communicates with beeps, whistles | ✅ Built | `src/audio/speaker.py` |
| Audio input (microphone) | Hears speech, sounds | ✅ Built | `src/audio/mic.py` |
| Dashboard / monitoring UI | — (modern addition) | ✅ Built | `src/dashboard/` |

## 7. Power & Thermal Management

| Capability | R2-D2 demonstrates | R1-A1 status | Module |
|---|---|---|---|
| Battery monitoring | Knows own power level | ✅ Built | `src/power/` |
| Charger seeking | Finds charging stations | ✅ Built | `src/power/` |
| Thermal management | Operates in extreme temperatures | ✅ Built | `src/thermal/` |
| External power socket | Plugs into ship power systems | 🔴 Gap | — |
| Power distribution routing | Reroutes power between systems | 🔴 Gap | — |

---

## Summary: What This Phase Adds

From the gaps above, this phase implements two new knowledge packages:

### 1. `src/astro/` — Astro Navigation

Covers gaps in celestial navigation, solar system body tracking, star
catalogs, Milky Way structure, and a real-data bridge. Provides the
foundation an astromech needs for orientation, star mapping, and
astronomical lookups. Uses real astronomical data (orbital elements,
star coordinates, magnitudes) and bridges to live APIs (NASA JPL
Horizons, SIMBAD) for precision queries.

### 2. `src/repair/` — Spacecraft Repair Framework

Covers gaps in starship repair, diagnostics, and spacecraft knowledge.
Provides an extensible framework where specific spacecraft types and
their subsystems can be registered over time. Each spacecraft type
defines its subsystems (propulsion, life support, power, avionics,
hull, weapons), known failure modes, diagnostic procedures, and
repair steps. The LLM can query this knowledge base to assist with
repair scenarios.

### Future phases (not in this build)

| Module | Priority | Description |
|---|---|---|
| `src/security/` | Medium | Computer slicing, encryption, network intrusion (simulated) |
| `src/hazard/` | Medium | Radiation, atmospheric, fire/smoke detection |
| `src/medical/` | Low | First aid knowledge, bacta/medpac reference |
| `src/comms/` | Medium | Droid-to-droid binary protocol, long-range comms |
| `src/defense/` | Low | Electric shock defense, non-lethal deterrents |
| `src/manipulator/` | Low | Gripper arm, tool deployment |