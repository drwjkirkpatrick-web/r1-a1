# R1-A1 3D-Printed Parts List

All structural/cosmetic printing is based on the community-standard
**Mr Baddeley R2-D2** file set (the de-facto open design for full-size
printed astromechs). Files are free via the designer's Patreon/Facebook
("Mr Baddeley Printed Droids") and mirrored design indexes below.

**Print settings (whole project):** PETG or ASA, 0.2 mm layer, 3 walls,
25 % gyroid infill, 5 top/bottom layers. Body/dome parts at 0.28 mm
draft quality acceptable — they get bodyworked and painted.

**Printer requirement:** 250×250×250 mm minimum (Bambu A1/P1S, Prusa
MK4 class). All files are segmented to fit. See:
https://www.printed-droid.com/kb/choosing-a-3d-printer-for-astromech-droids/

**Total print estimate:** ~177 individual pieces, ~8–10 kg filament,
~600–800 print hours.

---

## Design Sources (links)

| Source | Link | What it has |
|---|---|---|
| Mr Baddeley designs index | https://www.thingiverse.com/mrbaddeley/designs | Free dome, skirt, and detail STLs |
| Mr Baddeley Patreon (full set, free tier) | https://www.patreon.com/mrbaddeley | Complete R2-D2 v2 body/leg/foot files |
| Printed Droid KB (terminology + print guide) | https://www.printed-droid.com/kb/r2-d2-terminology/ | Official part names used below |
| R2-D2 print guide v1.2.9 (PDF) | https://www.scribd.com/document/982964411/ | Part-by-part print settings |
| Astromech.net (R2 Builders Club) | https://astromech.net/ | Aluminum dome/frame parts runs, electronics |

---

## Dome (10 parts)
1. Outer dome — main shell *(Baddeley "Droid Dome v2", or aluminum spun dome from astromech.net parts run)*
2. Inner dome — structural liner
3. Dome ring — bearing interface to body
4. Dome ring gear — GT2 240T internal ring (dome rotation)
5. Front logic surround — frame for the 5" round "wink" LCD
6. Rear logic surround
7. PSI (Processor State Indicator) ×2 — red/blue lenses
8. Eye bezel + lens mount — houses IMX477 camera + RGB "wink" LED
9. Holo-projector bezels ×3 (front/top/side) — main front unit houses real P6X projector
10. Radar eye lens

## Body / Skins (22 parts)
11. Body shell segments ×4–6 (depends on printer volume)
12. Front skin panel (door behind which compute bay slides)
13. Rear skin panel with vent cutouts (exhaust grilles)
14. Utility arm doors ×2 (front intake vents hidden here)
15. Front logic display panel (body-level)
16. Coin slots / vertical vents ×2
17. Power coupling detail
18. Octagon port + door
19. Data port + door (real USB-C service port behind it)
20. Charge bay door (rear, hides charge socket + e-stop)
21. Body top ring (dome bearing seat)
22. Body bottom ring (frame rail seat)

## Frame (14 parts) — *printed option; aluminum frame preferred for final build*
23. Top ring plate (compute bay ceiling + dome bearing)
24. Mid-deck plate (compute shelf for the Strix Halo mini PC)
25. Bottom ring plate (battery tray ceiling)
26. Vertical frame rails ×4 (2020 aluminum T-slot replaces these in metal build)
27. Motor mount brackets ×2 (drive motors in feet)
28. Battery tray — 24 V LiFePO4 cradle with strap slots
29. Compute bay fan shrouds ×2 (80 mm ducting)
30. Projector mount cradle (in dome, aimed through front holo lens)

## Legs (12 parts — Baddeley "v2 legs", 6 per side)
31. Leg main strut L/R
32. Leg shoulder L/R (attaches to body via shoulder hub)
33. Leg ankle L/R
34. Leg detail covers L/R
35. Ankle detail/cylinder L/R
36. Shoulder hubs L/R + center shoulder hub (for 2-3-2 center leg)

## Feet (18 parts — 9 per foot + center)
37. Main footshell L/R
38. Foot side plate L/R
39. Half-moon details ×4
40. Foot details/treads ×6
41. Battery box detail shells L/R (cosmetic; real battery is in body)
42. Center foot shell + wheel well (retractable)

## Center Leg / 2-3-2 System (6 parts)
43. Center leg strut
44. Center ankle
45. Center foot shell
46. Linear actuator mounting yoke
47. Center wheel/motor mount
48. Center shoulder pivot

## Internal Custom Parts (R1-A1 specific — we design these ourselves)
49. `compute_sled.stl` — sliding tray for mini PC on 350 mm drawer slides
50. `mcu_mount.stl` — Teensy 4.1 + breakout board tray
51. `power_board_mount.stl` — buck converter / fuse block plate
52. `eye_gimbal.stl` — camera micro-pan mount (SG90 servo, ±30°)
53. `mic_array_mount.stl` — ReSpeaker mount behind front vents
54. `speaker_baffle.stl` — sealed 0.5 L enclosure for 4Ω driver
55. `hdmi_splitter_bracket.stl`, `cable_combs.stl`, `wire_clips_2020.stl`
56. `thermal_probe_clips.stl` — DS18B20 mounts for compute/motor bays
57. `vision_node_tray.stl` — Jetson Orin Nano mount on dome inner ring,
    with CSI ribbon channel to the eye bezel
58. `mmwave_brackets.stl` ×3 — LD2450 radar pods at skirt FL/FR/rear
59. `ultrasonic_pods.stl` ×4 — HC-SR04P under-skirt mounts at 45° spacing
60. `cliff_sensor_clips.stl` ×3 — VL53L1X downward mounts at skirt edge

## Skirt (bottom body) (5 parts)
61. Skirt segments ×4 + front skirt access flap (Baddeley "R2D2 Skirt ver 2"
    on Thingiverse)

---

## Aluminum / Metal Chassis Specification

For the final metal chassis (recommended over the all-printed frame):

- **Frame:** JAG frame pattern — 2× 3 mm 5052-H32 aluminum ring plates
  (top/bottom, 430 mm OD), 8× 2020 T-slot extrusion verticals (400 mm),
  joined with corner brackets; dome bearing bolted to top ring.
  *Source pattern: astromech.net frame forum runs, or cut locally from
  the published JAG DXF files (free to club members).*
- **Dome (premium option):** 500 mm spun aluminum dome, 1.6 mm 3003-H14,
  two-piece (inner/outer) — via astromech.net parts runs (~$300–400).
- **Legs (upgrade):** CNC 6061 leg struts available from club machinists;
  printed legs are fine at our weight class.
- **Fasteners:** M5 × 10 button-head + T-nuts throughout; dome ring M4.
- **Finish:** skins painted (Ford Olympic Blue / Wimbledon White),
  aluminum parts clear-anodized.

**Weight budget check:** frame ~4 kg, printed skins ~9 kg, batteries
~11 kg, motors ~6 kg, compute ~1.5 kg, misc ~6 kg → **~38 kg all-in**,
within the 50 kg design limit and driveable by the 2× 250 W motors.
