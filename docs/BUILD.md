# R1-A1 Master Build Instructions

Complete assembly sequence, in dependency order. Estimated total build time:
6–12 months part-time (dominated by print time and bodywork).

---

## Phase 0 — Workshop Prep (Week 0)
1. Calibrate the 3D printer (flow, first layer, dimensional accuracy cube).
2. Order filament: 10 kg PETG (white/blue) + 2 kg ASA for external skins.
3. Order long-lead items: LiFePO4 batteries, motors, Cytron MD30C drivers,
   mini PC, Teensy 4.1, BNO085, IMX477 + USB3 shield, 5" round HDMI LCD,
   P6X projector, ReSpeaker mic, Noctua fans, aluminum stock.
4. Download the full Mr Baddeley file set (see docs/PARTS.md sources).
5. Print the R2-D2 Print Guide (Scribd v1.2.9) as a shop reference.

## Phase 1 — Printing (Weeks 1–10, ~700 print hours)
6. Print in this order so assembly can start early:
   a. Frame set (top/mid/bottom plates, rails, motor mounts, battery tray)
   b. Feet and legs (needed for static rolling tests)
   c. Body shell segments + skirt
   d. Dome (outer, inner, ring, ring gear)
   e. Cosmetic details (arms, doors, coin slots, ports)
   f. R1-A1 custom internal parts (`compute_sled`, `mcu_mount`,
      `power_board_mount`, `eye_gimbal`, `speaker_baffle`, shrouds)
7. Deburr, tap M5/M4 holes, test-fit each subassembly as it completes.

## Phase 2 — Chassis & Drivetrain (Weeks 6–8, parallel with printing)
8. Assemble frame: ring plates + 2020 verticals, square and level.
9. Mount drive motors in feet; fit feet to legs; legs to shoulder hubs.
10. Wire motor power: batteries → 30 A fuse → e-stop loop → MD30C drivers.
    Verify e-stop cuts all motor power with a bench test BEFORE wheels
    touch ground.
11. Bench-run each motor via MCU test firmware (`firmware/motor_test.ino`
    pattern): spin up, spin down, direction check, current draw note.
12. Install center leg + linear actuator; test 2-3-2 transition on blocks.

## Phase 3 — Power Distribution (Week 9)
13. Mount power board: bucks, fuse block, charge port, INA219 monitor.
14. Wire buses per the interconnect map in docs/HARDWARE.md §3.
15. Star-ground everything at the power board. Verify ground continuity
    (< 0.1 Ω) from any chassis point to battery negative.
16. Power-up sequence test: 24 V bus → each rail no-load → each rail
    loaded. Record rail voltages; anything off by >5 % gets fixed now.

## Phase 4 — Compute Bay (Week 10)
17. Assemble compute sled; mount mini PC; route 19 V from its buck.
18. Install host OS: Ubuntu 24.04 LTS, then Ollama, ROS 2 Jazzy,
    Python 3.12 venv with `requirements.txt` from this repo.
19. Flash Teensy with `firmware/r1a1_mcu.ino`; connect USB CDC to host.
20. Run `python -m src.interconnect.selftest` — verifies serial framing,
    heartbeat, e-stop sense line, and loopback telemetry.

## Phase 5 — Sensors & Effectors (Weeks 11–12)
21. Dome: mount ring gear, stepper, IMX477 eye + wink LED, LCD in front
    logic surround, projector in its cradle. Route HDMI + USB through the
    dome slip-ring (12-circuit capsule) down the frame center.
22. Body: mic array behind front vents, speaker + baffle behind front
    logic panel, bump switches, thermal probes in both bays.
23. Cooling: fans + shrouds; verify intake at utility doors, exhaust at
    rear panel. Smoke-pencil test the airflow path.
24. Cable-manage: cable combs every 150 mm, service loops at dome joint.

## Phase 6 — Software Bring-Up (Weeks 12–14)
25. `pytest tests/` on the host — full suite must pass (hardware tests
    auto-skip when devices are absent).
26. `r1a1 doctor` — CLI hardware audit: every interconnect reports green.
27. Enable services: `systemctl enable r1a1-brain r1a1-motion r1a1-thermal`.
28. Calibrate: motor deadband, dome stepper steps/degree, IMU orientation,
    mic array DOA, projector keystone.
29. Run the 42-prompt acceptance suite from docs/PROMPTS.md — every
    prompt passes before first public roll.

## Phase 7 — Bodywork & Finish (Weeks 14+)
30. Fill/sand skins, prime, paint (white base, blue panels), weather
    lightly, clear-coat. Aluminum parts: clear anodize.
31. Final decals and detail work. First outdoor roll. 🎉

---

## Safety Gates (do not skip)
- **Gate A (Phase 2):** e-stop loop proven on the bench.
- **Gate B (Phase 4):** interconnect selftest green.
- **Gate C (Phase 6):** thermal shutdown trip tested with a heat gun.
- **Gate D (Phase 6):** all 42 acceptance prompts pass.
