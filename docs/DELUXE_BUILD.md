# R1-A1 Deluxe Build Guide

The complete end-to-end build path for R1-A1, integrating the project's
own hardware design (`docs/HARDWARE.md`), printed parts list
(`docs/PARTS.md`), and acceptance suite (`docs/PROMPTS.md`) with the
best community resources, suppliers, and 3D-printable file sets
catalogued in `docs/EXTERNAL_PARTS.md`.

This guide assumes you have read `docs/HARDWARE.md` for the overall
architecture and `docs/PARTS.md` for the part inventory. Each step
below cross-references both, plus external links where applicable.

**Estimated timeline:** 6–12 months part-time. The critical path is
3D print time (~700 hours) and long-lead part orders (dome, motors,
batteries, compute host). Start those first.

---

## Phase 0 — Preparation & Procurement (Week 0)

### 0.1 Join the community

1. **Register on [astromech.net](https://astromech.net/)** (free). This
   unlocks parts runs, blueprint downloads, and the forum knowledge base.
   Many vendors will not sell you parts without a valid forum user ID.
2. **Browse [Droidbuilders UK](https://droidbuilders.uk/)** for build
   showcases and UK supplier links.
3. **Bookmark [Printed Droid](https://www.printed-droid.com/)** — the
   knowledge base for 3D-printed droids, with wiring diagrams, print
   guides, and FAQs.

### 0.2 Download plans and reference materials

4. **Download the Dave Everett styrene plans** from the
   [astromech.net downloads section](https://astromech.net/forums/downloads.php).
   These are the canonical dimensional drawings — every measurement in
   R1-A1 traces back to them.
5. **Download the R2-D2 Terminology Guide v1.2** from
   [printed-droid.com/files](https://www.printed-droid.com/files/).
   This defines the official part names used across all builders and
   in this project's `docs/PARTS.md`.
6. **Download the Mr Baddeley v2 file set** from his
   [Patreon (free tier)](https://www.patreon.com/mrbaddeley/posts/r2d2-version-2-8318848).
   This is R1-A1's primary 3D-printable design source — dome, body,
   legs, feet, skirt, and all cosmetic detail parts.
7. **Download the Printed Droid Print Guide v1.2 and FAQ v1.3** from
   [printed-droid.com/files](https://www.printed-droid.com/files/).
   These cover filament choices, print settings, hardware compatibility,
   and electronics wiring.
8. **Download the Filament Guide by Christina Cato** from the same page
   for recommended filaments, colors, and quantities.

### 0.3 Choose your build tier

R1-A1 supports three build tiers. Pick one now — it determines what you
order and what you print.

| Tier | Dome | Frame | Skins | Legs/Feet | Best for |
|---|---|---|---|---|---|
| **Economy** (all-printed) | Baddeley printed dome | Baddeley printed frame | PETG printed | Baddeley printed | Budget builds, prototyping, indoor use |
| **Standard** (hybrid) | Spun aluminum (astromech.net parts run) | JAG aluminum frame (DXF cut locally) | PETG printed, painted | Baddeley printed | Recommended balance of cost and durability |
| **Deluxe** (premium) | Darren Murrer hydro-formed aluminum (Granite Earth) | Frank's pre-cut aluminum frame | Aluminum skins (Rebelscum) | CNC 6061 leg struts (club machinist) | Screen-accurate, long-lasting, outdoor events |

### 0.4 Order long-lead items

These have the longest shipping times — order them in Week 0.

**Compute & electronics (all tiers):**
| Item | Source | Notes |
|---|---|---|
| LLM host mini PC (Strix Halo) | Minisforum / Beelink | See `docs/HARDWARE.md` §1 Option A |
| Teensy 4.1 | [PJRC](https://www.pjrc.com/store/teensy41.html) | Real-time MCU |
| BNO085 IMU | Adafruit / Pimoroni | 9-DOF, UART |
| IMX477 camera + USB3 shield | Arducam | Dome eye |
| 5" round HDMI LCD (1080×1080) | Waveshare | Wink screen |
| AAXA P6X projector | AAXA | Dome periscope |
| ReSpeaker USB 4-mic array | Seeed Studio | Far-field audio |
| 20W 4Ω speaker + MAX9744 amp | Adafruit | Audio output |
| Cytron MD30C motor drivers ×2 | Cytron | Drive motor controllers |
| 24V 250W geared DC motors ×2 | Electric scooter parts | Drive |
| NEMA-17 stepper + planetary gearbox | StepperOnline | Dome rotation |
| Linear actuator 150 mm stroke 24V | Firgelli / generic | Center leg lift |
| DS18B20 temp probes ×3 | Adafruit / generic | Thermal monitoring |
| INA219 current sensor | Adafruit | Battery monitor |
| Hi-Link LD2450 mmWave radar ×3 | Hi-Link / AliExpress | Spatial awareness |
| HC-SR04P ultrasonic ×4 | Generic | Proximity ring |
| VL53L1X ToF sensors ×3 | Adafruit / Pimoroni | Cliff detection |
| Jetson Orin Nano 8 GB | NVIDIA / distributors | Vision node |
| LiFePO4 batteries 2× 24V 20Ah | Battery suppliers | ~960 Wh main bus |
| Noctua NF-A8 80mm fans ×4 | Noctua | Cooling |
| Rockler lazy susan bearing #12451 | [Amazon](https://amzn.to/2UD6xlc) | Dome rotation bearing |
| Press-fit studs (50 pcs) | [McMaster-Carr](https://www.mcmaster.com/catalog/125/3286) | Dome hardware |
| 12-circuit slip-ring (dome) | eBay / AliExpress | Dome-to-body wiring |
| 1000BASE-T slip-ring capsule | Electronics supplier | Vision node GbE |

**Tier-specific structural parts:**

| Tier | Item | Source |
|---|---|---|
| Standard / Deluxe | Spun aluminum dome or hydro-formed dome | [Granite Earth](http://www.graniteearth.com/ProductDetails.asp?ProductCode=ALUMINUM-DOME-SET) or astromech.net parts runs |
| Standard | JAG frame DXF → local waterjet shop | astromech.net frame forum (free to members) |
| Deluxe | Frank's pre-cut frame + legs + feet | http://r2d2.media-conversions.net/ (contact "mediaconvert" on astromech.net) |
| Deluxe | Aluminum skins | [Rebelscum/Philip Wise](http://www.rebelscum.com/estore/products.asp?cat=182) |
| Deluxe | CNC aluminum radar eye bezel | [Granite Earth](https://www.graniteearth.com/ProductDetails.asp?ProductCode=PAY-RadarEye-CSR-R2-Builders) |
| Deluxe | Aluminum holo-projectors ×3 | [Bob Considine — astromech.net](https://astromech.net/forums/showthread.php?24378) |
| Standard / Deluxe | M5 × 10 button-head + T-nuts (fasteners) | McMaster-Carr / local hardware |

### 0.5 Order filament

| Tier | Filament | Qty | Notes |
|---|---|---|---|
| Economy | PETG (white + blue) | 10 kg | Structural + skins |
| Economy | ASA (black, silver) | 2 kg | External skins, UV-stable |
| Standard | PETG (white + blue) | 8 kg | Skins, details, custom internals |
| Standard | PETG (natural) | 2 kg | Internal brackets, shrouds |
| Deluxe | PETG (natural) | 4 kg | Internal parts only — skins are aluminum |

Reference the [Filament Guide by Christina Cato](https://www.printed-droid.com/files/)
for exact color codes and brand recommendations matching the Baddeley set.

### 0.6 Calibrate the 3D printer

9. Print a calibration cube and verify dimensional accuracy (±0.1 mm on
   a 20 mm cube). Calibrate flow rate, first-layer height, and bed
   leveling.
10. **Printer requirement:** 250×250×250 mm minimum build volume
    (Bambu A1/P1S, Prusa MK4 class). All Baddeley files are segmented
    to fit. See the
    [Printed Droid printer guide](https://www.printed-droid.com/kb/choosing-a-3d-printer-for-astromech-droids/).

**Print settings (whole project):** PETG or ASA, 0.2 mm layer, 3 walls,
25% gyroid infill, 5 top/bottom layers. Body/dome parts at 0.28 mm
draft quality acceptable — they get bodyworked and painted.

---

## Phase 1 — 3D Printing (Weeks 1–10, ~700 print hours)

Print in this order so assembly can start while later parts are still
printing. Follow the
[Mr Baddeley Print Guide v1.2](https://www.printed-droid.com/files/)
for per-part settings. Reference
[Kevin Rye's 8-part build series](https://kevinrye.net/index_files/3d_printed_r2d2_p1.php)
for practical tips and photos at each stage.

### 1.1 Frame set (Weeks 1–2)

11. Print frame plates (top ring, mid-deck, bottom ring) and vertical
    rails. *(Economy tier only — Standard/Deluxe use metal frame.)*
12. Print motor mount brackets ×2 and battery tray.
13. Print compute bay fan shrouds ×2.
14. Print `compute_sled.stl`, `mcu_mount.stl`, `power_board_mount.stl`
    — R1-A1 custom internal parts (see `docs/PARTS.md` §Internal).
15. Deburr, tap M5/M4 holes, test-fit each subassembly as it completes.

### 1.2 Feet and legs (Weeks 3–4)

16. Print foot shells L/R, foot side plates, half-moon details ×4,
    foot details/treads ×6. *(Deluxe tier: skip — CNC aluminum legs/feet
    from Frank's.)*
17. Print leg main struts L/R, shoulders L/R, ankles L/R, detail
    covers L/R, ankle details L/R.
18. Print shoulder hubs L/R + center shoulder hub (for 2-3-2).
19. Print center leg strut, center ankle, center foot shell, linear
    actuator mounting yoke, center wheel/motor mount, center shoulder
    pivot — the complete 2-3-2 system (6 parts).

### 1.3 Body shell and skirt (Weeks 5–7)

20. Print body shell segments ×4–6 (depends on printer volume).
21. Print front skin panel, rear skin panel with vent cutouts.
22. Print utility arm doors ×2, front logic display panel.
23. Print coin slots / vertical vents ×2, power coupling detail.
24. Print octagon port + door, data port + door, charge bay door.
25. Print body top ring (dome bearing seat), body bottom ring.
26. Print skirt segments ×4 + front skirt access flap (Baddeley
    "R2D2 Skirt ver 2" on [Thingiverse](https://www.thingiverse.com/mrbaddeley/designs)).

### 1.4 Dome (Weeks 8–9)

27. **Economy tier:** Print outer dome, inner dome, dome ring, dome
    ring gear (GT2 240T internal ring).
    **Standard/Deluxe:** Skip printed dome — use aluminum dome from
    your supplier. Still print: dome ring gear, front logic surround,
    rear logic surround, PSI lenses ×2, eye bezel + lens mount,
    holo-projector bezels ×3, radar eye lens.
28. Print all dome cosmetic details per the Baddeley print guide.

### 1.5 Cosmetic details (Week 9–10)

29. Print remaining detail parts: utility arms, data port trim,
    charge bay trim, any optional Baddeley accessories.
30. Print R1-A1 custom sensor mounts: `eye_gimbal.stl`,
    `mic_array_mount.stl`, `speaker_baffle.stl`,
    `hdmi_splitter_bracket.stl`, `cable_combs.stl`, `wire_clips_2020.stl`,
    `thermal_probe_clips.stl`, `vision_node_tray.stl`,
    `mmwave_brackets.stl` ×3, `ultrasonic_pods.stl` ×4,
    `cliff_sensor_clips.stl` ×3.
31. Final deburr and dry-fit everything. Label and bag parts by
    subassembly.

---

## Phase 2 — Chassis & Drivetrain (Weeks 6–8, parallel with printing)

### 2.1 Frame assembly

32. **Economy:** Assemble printed frame: ring plates + vertical rails,
    square and level on a flat surface.
    **Standard:** Cut JAG frame from DXF at a local waterjet/CNC shop.
    Assemble 3 mm 5052-H32 ring plates + 2020 T-slot verticals
    (400 mm) with corner brackets. See `docs/PARTS.md` §Aluminum.
    **Deluxe:** Assemble Frank's pre-cut aluminum frame per his
    instructions. Contact "mediaconvert" on astromech.net for guidance.

### 2.2 Drivetrain

33. Mount drive motors in feet; fit feet to legs; legs to shoulder hubs.
34. Wire motor power: batteries → 30 A fuse → e-stop loop → MD30C
    drivers. **Verify e-stop cuts all motor power with a bench test
    BEFORE wheels touch ground.** This is **Safety Gate A.**
35. Bench-run each motor via MCU test firmware (`firmware/motor_test.ino`
    pattern): spin up, spin down, direction check, current draw note.
36. Install center leg + linear actuator; test 2-3-2 transition on blocks.
    Verify the center wheel lifts the droid cleanly and retracts fully.

### 2.3 Dome rotation

37. Install the Rockler lazy susan bearing (#12451) between the body
    top ring and dome ring. Verify smooth rotation with no binding.
38. Mount the NEMA-17 stepper with planetary gearbox. Fit the 12T GT2
    pinion to the dome ring gear. Verify full 360° rotation under MCU
    control.
39. Route the 12-circuit slip-ring through the dome center. Verify all
    circuits pass continuity before assembly closes up. Reference the
    [Printed Droid slip-ring pinouts](https://www.printed-droid.com/files/)
    for wiring.

---

## Phase 3 — Power Distribution (Week 9)

40. Mount the power distribution board: buck converters (24→19 V,
    24→12 V, 24→5 V), fuse block, charge port, INA219 monitor.
    Use the `power_board_mount.stl` bracket.
41. Wire buses per the interconnect map in `docs/HARDWARE.md` §3:
    - 30 A fuse → motor bus (MD30C drivers)
    - 15 A buck 24→19 V → LLM host DC-in
    - 10 A buck 24→12 V → projector, amp, fans
    - 5 A buck 24→5 V → MCU, LCD logic, mic, USB hub
    - Charge port → 24 V LiFePO4 BMS charger
42. **Star-ground everything** at the power board. Verify ground
    continuity (< 0.1 Ω) from any chassis point to battery negative.
43. Power-up sequence test: 24 V bus → each rail no-load → each rail
    loaded. Record rail voltages; anything off by >5% gets fixed now.
44. **Mac Studio M3 Ultra note:** if using `host_type: mac_ultra`, the
    host requires AC power (373 W max). Install a pure-sine-wave inverter
    (≥500 W) on the 24 V bus → AC output. Verify inverter output is
    clean under load before connecting the Mac. See `docs/HARDWARE.md`
    §1 Option B-Ultra.

---

## Phase 4 — Compute Bay (Week 10)

### 4.1 Brain host

45. Assemble the compute sled on 350 mm drawer slides. Mount the LLM
    host (Strix Halo mini PC or Mac Studio M3 Ultra) on the sled.
    Route 19 V DC (Strix Halo) or AC (Mac Ultra via inverter) from its
    respective rail.
46. Install host OS:
    - **ubuntu_x86:** Ubuntu 24.04 LTS → Ollama → ROS 2 Jazzy →
      Python 3.12 venv with `requirements.txt` from this repo.
    - **mac_ultra:** macOS → MLX server (`mlx-lm` / `mlx-vlm`) →
      Python 3.12 venv. Set `host_type: mac_ultra` in
      `config/r1a1.yaml`.
    - **jetson:** Ubuntu 22.04 (JetPack) → Ollama or TensorRT-LLM →
      ROS 2 Jazzy → Python venv.
47. Verify Ollama (or MLX server) responds at the configured
    `base_url`. Load the primary and fallback models:
    - ubuntu_x86: `qwen2.5:3b` + `gemma2:2b`
    - mac_ultra: `llama-3.3-70b-instruct-4bit` + `llama-3.2-3b-instruct`
    - jetson: `qwen2.5:7b` + `qwen2.5:3b`

### 4.2 Real-time MCU

48. Flash the Teensy 4.1 with `firmware/r1a1_mcu.ino`. Mount it on the
    `mcu_mount.stl` tray. Connect USB CDC to the host.
49. Run `python -m src.interconnect.selftest` — verifies serial
    framing, heartbeat, e-stop sense line, and loopback telemetry.
    This is **Safety Gate B.**

### 4.3 Vision node

50. Mount the Jetson Orin Nano on the `vision_node_tray.stl` inside the
    dome. Route the CSI-2 ribbon to the IMX477 camera through the eye
    bezel. Route GbE through the slip-ring capsule to the host.
51. Flash the vision node with moondream2 + Qwen2.5-VL-3B via
    llama.cpp / jetson-containers. Verify the HTTP API responds at
    `:8081/caption` and `:8081/detect`.
52. Clip a DS18B20 probe to the vision node heatsink — this reports
    into the thermal policy as zone `vision_c`.

---

## Phase 5 — Sensors & Effectors (Weeks 11–12)

### 5.1 Dome assembly

53. Mount the IMX477 camera in the eye bezel with the `eye_gimbal.stl`
    micro-pan mount (SG90 servo, ±30°). Install the 3W RGB wink LED
    behind the eye lens.
54. Install the 5" round HDMI LCD in the front logic surround. Route
    HDMI from the host through the 1×2 HDMI splitter.
55. Mount the AAXA P6X projector in its cradle inside the dome,
    aimed through the front holo-projector lens. Route HDMI from the
    splitter. Gut the P6X battery and wire DC-in from the 12 V rail.
56. Install the 60 mm dome fan behind the projector vent.
57. **Deluxe tier:** Install the aluminum holo-projectors from
    [Bob Considine](https://astromech.net/forums/showthread.php?24378)
    in place of the printed bezels. Install the CNC aluminum radar eye
    bezel from [Granite Earth](https://www.graniteearth.com/ProductDetails.asp?ProductCode=PAY-RadarEye-CSR-R2-Builders).

### 5.2 Body sensors and audio

58. Mount the ReSpeaker 4-mic array behind the front vents on the
    `mic_array_mount.stl`.
59. Mount the 20W speaker in the `speaker_baffle.stl` sealed enclosure
    behind the front logic panel. Wire to the MAX9744 amp.
60. Install bump switches (front/rear). Wire to MCU GPIO.
61. Install DS18B20 thermal probes: one in the compute bay, one in
    the motor bay, one on the vision node heatsink. Use
    `thermal_probe_clips.stl` mounts. Wire OneWire → MCU.

### 5.3 Spatial awareness

62. Mount 3× LD2450 mmWave radar pods on `mmwave_brackets.stl` at
    skirt front-left, front-right, and rear. Wire UART → USB-serial
    hub → host.
63. Mount 4× HC-SR04P ultrasonic sensors on `ultrasonic_pods.stl`
    at 45°/135°/225°/315° under the skirt. Wire GPIO trig/echo → MCU.
64. Mount 3× VL53L1X ToF cliff sensors on `cliff_sensor_clips.stl`
    pointing down under the skirt edge. Wire I2C (address-muxed) → MCU.
65. Mount the BNO085 IMU. Wire UART → MCU.

### 5.4 Cooling

66. Install 2× Noctua NF-A8 intake fans at the compute bay front
    (behind utility arm doors) and 2× exhaust fans at the rear panel
    vents. Use the printed `compute_bay_shroud.stl` ducts.
67. Install the 200×150×3 mm copper heat spreader plate, thermal-pad
    coupled to the chassis rail behind the host.
68. **Smoke-pencil test:** verify intake at utility doors, exhaust at
    rear panel. The airflow path must move air deliberately through
    the compute bay, not short-circuit.

### 5.5 Cable management

69. Install cable combs every 150 mm on the verticals. Leave service
    loops at the dome joint. Use `wire_clips_2020.stl` on T-slot rails.
70. Route the HDMI splitter, USB hub, and all signal cables per the
    interconnect map in `docs/HARDWARE.md` §3.

---

## Phase 6 — Software Bring-Up (Weeks 12–14)

### 6.1 Test suite

71. `pytest tests/` on the host — the full suite (195 tests) must
    pass. Hardware tests auto-skip when devices are absent.
72. `r1a1 doctor` — CLI hardware audit. Every subsystem should report
    green:
    - interconnect, brain, thermal, power — core modules
    - personality — remedy bridge (100 remedies if skill installed)
    - limbic — affective state engine (if limbic-hermes installed)
    - dashboard — Flask availability check

### 6.2 Services

73. Enable systemd services (or launchd on macOS):
    `systemctl enable r1a1-brain r1a1-motion r1a1-thermal`
74. Start the dashboard: `r1a1 dashboard` — verify it serves at
    `http://127.0.0.1:9298` and shows live subsystem status.

### 6.3 Optional personality & limbic

75. **Remedy personality** (optional): Enable in `config/r1a1.yaml`:
    ```yaml
    brain:
      personality:
        enabled: true
        remedy: "bryonia_alba"
    ```
    Verify the remedy emoji appears on the dashboard. Requires the
    `remedy_personality_picker` Hermes skill installed at
    `~/.hermes/skills/remedy_personality_picker/`.
76. **Limbic system** (optional): Enable in `config/r1a1.yaml`:
    ```yaml
    brain:
      limbic:
        enabled: true
        profile: "pulsatilla_pratensis"
        intensity: 0.6
        inject_into_prompt: true
    ```
    Verify the VAD bars, dominant affect, and allostatic load appear
    on the dashboard. Requires the `limbic-hermes` project at
    `~/projects/limbic-hermes/`.

### 6.4 Calibration

77. Calibrate motor deadband (minimum PWM that produces motion).
78. Calibrate dome stepper steps/degree (verify 360° = N steps).
79. Calibrate IMU orientation (mount offset → correct frame).
80. Calibrate mic array DOA (direction of arrival at known positions).
81. Calibrate projector keystone (adjust image to fill the holo lens).
82. **Thermal shutdown trip test** with a heat gun: verify the thermal
    policy triggers at 75 °C (throttle), 85 °C (shutdown), 50 °C
    (battery stop). This is **Safety Gate C.**

### 6.5 Acceptance suite

83. Run the 42-prompt acceptance suite from `docs/PROMPTS.md`. Every
    prompt must pass before first public roll. This is **Safety Gate D.**

---

## Phase 7 — Bodywork & Finish (Weeks 14+)

### 7.1 Surface preparation

84. Fill any gaps in printed skins with model putty or Bondo. Sand
    smooth. Prime with a high-build automotive primer.
85. **Deluxe tier:** aluminum skins need minimal prep — degrease,
    scuff-sand, prime with self-etching primer.

### 7.2 Paint

86. Paint skins: white base (Wimbledon White or equivalent), blue
    panels (Ford Olympic Blue or equivalent). Apply 2–3 coats with
    light sanding between.
87. Weather lightly — a subtle scuff on the lower skirt and feet sells
    the "lived-in" look without looking damaged.
88. Clear-coat everything (matte or satin for body, gloss for dome).
89. **Aluminum parts:** clear anodize (dome, frame, detail parts).
    This is a professional process — send parts to an anodizing shop.

### 7.3 Decals and detail

90. Apply decals: dome logic display graphics, body panel labels,
    caution stripes. Source from astromech.net decal runs or print
    your own on vinyl.
91. Install all final cosmetic details: utility arms, data port
    covers, charge bay door, coin slot inserts.
92. Final assembly: bolt skins to frame, install dome, connect all
    slip-ring cables, verify everything still works after bodywork.

### 7.4 First roll

93. Place R1-A1 on a smooth, flat surface. Power on. Run `r1a1 doctor`
    one final time. Verify the dashboard shows all green.
94. **First outdoor roll.** 🎉

---

## Safety Gates Summary

| Gate | Phase | What | Why |
|---|---|---|---|
| **A** | 2 | E-stop loop proven on the bench | Mobility power must be killable instantly |
| **B** | 4 | Interconnect selftest green | MCU ↔ host serial link is the nervous system |
| **C** | 6 | Thermal shutdown trip tested with heat gun | Fire prevention — batteries + compute in a sealed tube |
| **D** | 6 | All 42 acceptance prompts pass | Behavioral correctness before public operation |

**Never skip a gate.** If a gate fails, stop and fix it before
proceeding to the next phase.

---

## Build Tier Comparison

| Aspect | Economy | Standard | Deluxe |
|---|---|---|---|
| **Dome** | Printed PETG, sanded + painted silver | Spun aluminum (~$300–400) | Hydro-formed aluminum, CNC cut (~$490) |
| **Frame** | Printed PETG | JAG aluminum DXF (cut locally) | Frank's pre-cut aluminum |
| **Skins** | Printed PETG, painted | Printed PETG, painted | Aluminum (pre-cut) |
| **Legs/Feet** | Printed PETG | Printed PETG | CNC 6061 aluminum |
| **Holo-projectors** | Printed | Printed | Aluminum (Bob Considine) |
| **Radar eye** | Printed | Printed | CNC aluminum (Granite Earth) |
| **Filament needed** | ~12 kg | ~10 kg | ~4 kg (internals only) |
| **Print time** | ~700 hrs | ~500 hrs | ~200 hrs |
| **Total cost (est.)** | ~$1,500–2,500 | ~$3,000–4,500 | ~$5,000–8,000+ |
| **Weight** | ~38 kg | ~40 kg | ~42 kg |
| **Best for** | Prototyping, indoor | Events, general use | Screen-accurate, long-term |

Costs are rough estimates for structural/cosmetic parts only.
Electronics, compute, and batteries are the same across all tiers and
add ~$2,000–4,000 depending on compute host choice.

---

## External Resource Quick Reference

All links below are catalogued with full descriptions in
`docs/EXTERNAL_PARTS.md`.

| Need | Go to |
|---|---|
| Community help, parts runs | [astromech.net](https://astromech.net/) |
| 3D print files (full set) | [Mr Baddeley Patreon](https://www.patreon.com/mrbaddeley) (free) |
| 3D print files (alt) | [MakerWorld life-size R2](https://makerworld.com/en/models/1372214-life-size-star-wars-r2d2-3d-model) |
| Print settings & FAQ | [Printed Droid files](https://www.printed-droid.com/files/) |
| Wiring diagrams | [Printed Droid files](https://www.printed-droid.com/files/) |
| Blueprints (dimensions) | [astromech.net downloads](https://astromech.net/forums/downloads.php) |
| Aluminum dome | [Granite Earth](http://www.graniteearth.com/ProductDetails.asp?ProductCode=ALUMINUM-DOME-SET) |
| Aluminum frame | astromech.net JAG frame forum or [Frank's](http://r2d2.media-conversions.net/) |
| Aluminum skins | [Rebelscum](http://www.rebelscum.com/estore/products.asp?cat=182) |
| Aluminum holo-projectors | [astromech.net — Bob Considine](https://astromech.net/forums/showthread.php?24378) |
| Dome bearing | [Rockler #12451](https://amzn.to/2UD6xlc) |
| Press-fit studs | [McMaster-Carr](https://www.mcmaster.com/catalog/125/3286) |
| Build walkthrough (video) | [I Like To Make Stuff](https://iliketomakestuff.com/making-r2-d2-part-1/) |
| Build walkthrough (photo) | [Kevin Rye](https://kevinrye.net/index_files/3d_printed_r2d2_p1.php) |
| Parts reference | [renev.biz](https://renev.biz/category/droids/lifesize-droids/r2-droid-parts/) |