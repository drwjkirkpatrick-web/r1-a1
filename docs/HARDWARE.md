# R1-A1 Hardware Architecture

Full hardware layout for a self-contained, LLM-driven R2-D2-class astromech.
Design target: fits inside a standard 1:1 astromech body (approx. 46 cm
diameter body shell, ~108 cm tall with dome), total mass budget ~50 kg.

---

## 1. Compute Bay ("The Brain")

Two-board architecture: a heavy LLM host plus a real-time microcontroller.

### Option A — x86/Ubuntu host (recommended for software flexibility)
- **Board:** Minisforum/Beelink-class mini PC, AMD Ryzen AI Max+ 395
  ("Strix Halo"), 128 GB unified LPDDR5X, ~256 GB/s
- **Why:** 128 GB unified memory runs 70B-class models (Q4) entirely in
  GPU-addressable RAM; x86 Ubuntu 24.04 gives us Ollama, llama.cpp, ROS 2
  Jazzy, and standard tooling with no ARM porting pain.
- **Size:** ~205 × 203 × 70 mm — fits across the body on a mid-deck shelf.
- **Power:** 19 V DC barrel, 40–140 W. Driven from the internal DC/DC
  converter (see §4).

### Option B — Apple host (max tokens/sec per watt)
- **Board:** Mac mini M4 Pro, 64 GB unified (273 GB/s)
- **Why:** Silent, tiny (127 × 127 × 50 mm), ~155 W PSU internal (AC only —
  needs inverter, see §4), MLX backend is the fastest per-watt on 8–32B
  models.
- **Trade-off:** AC-only input means an inverter stage; ROS 2 on macOS is
  second-class. Use only if inference quality matters more than robotics
  middleware.

### Option B-Ultra — Mac Studio M3 Ultra (maximum model capacity)
- **Board:** Mac Studio M3 Ultra, 512 GB unified LPDDR5X, 819 GB/s
  bandwidth
- **Why:** 512 GB unified memory — the only board that can hold a
  full-precision 70B-class model or even a 405B model in 4-bit entirely in
  GPU-addressable RAM. MLX backend delivers best-in-class tokens/sec per
  watt for large models. 28-core Neural Engine, 80-core GPU.
- **Size:** 197 × 197 × 77 mm (larger than Mac mini, but still fits the
  mid-deck shelf — may need a slightly wider shelf plate).
- **Power:** 373 W max (AC only — requires inverter stage, see §4).
  Typical LLM inference load: 120–250 W depending on model size.
- **Trade-offs:** AC-only input (same inverter requirement as Mac mini
  option). ROS 2 on macOS is second-class — but with 512 GB of RAM, the
  brain can run the largest open-weights models locally without any
  quantization compromise, which may outweigh ROS 2 concerns for a
  conversational astromech. MLX server exposes an Ollama-compatible API
  at `localhost:8080` — set `host_type: mac_ultra` in `config/r1a1.yaml`.
- **Config:** When `host_type: mac_ultra` is set, the brain automatically
  uses the MLX backend, `localhost:8080` base URL, and recommends
  `llama-3.3-70b-instruct-4bit` as the primary model with
  `llama-3.2-3b-instruct` as fallback.

### Option C — NVIDIA host (CUDA-native)
- **Board:** Jetson AGX Orin 64 GB dev kit (or AGX Thor if budget allows)
- **Why:** Full CUDA + TensorRT-LLM, Jetson AI Lab containers, 15–60 W.
  64 GB fits 8–20B models comfortably, 70B Q4 barely.
- **Trade-off:** 205 GB/s bandwidth is the lowest of the three; ARM
  ecosystem. Choose this if we want NVIDIA's Isaac/ros2 bridge.

**Decision:** Default build = **Option A (Strix Halo, Ubuntu)**. For
operators who need the largest possible models, **Option B-Ultra (Mac
Studio M3 Ultra)** is the recommended upgrade — 512 GB unified memory
unlocks 70B+ models at full precision. The code in `src/brain/` is
host-agnostic — it talks to a local OpenAI/Ollama-compatible endpoint, so
any of the four options works by changing `host_type` in
`config/r1a1.yaml`.

### Real-time companion MCU
- **Board:** Teensy 4.1 (or Raspberry Pi RP2350 for budget)
- **Role:** servo PWM, motor controller heartbeat, e-stop interlock,
  sensor polling (IMU, bump switches, thermal probes). Never trust the
  LLM host with hard real-time safety.
- **Link to host:** USB CDC serial, 115200 baud, framed JSON-lines protocol
  (`src/interconnect/`).

---

## 2. Sensor & Effector Payload

| Subsystem | Part | Interface |
|---|---|---|
| Primary eye | Arducam IMX477 12.3 MP HQ camera w/ 6 mm CS lens, in dome eye bezel | CSI-2 → USB3 bridge (Arducam USB3 shield) → host USB3 |
| Eye illuminator | 3W RGB LED behind eye lens (status "wink") | PWM via MCU |
| Wink screen (front logic display) | Waveshare 5" round HDMI LCD 1080×1080, in dome front logic surround | HDMI from host + USB touch/power |
| Projector | AAXA P6X pico projector (1100 LED lumens, WXGA, 4h battery) gutted for DC-in, mounted in dome periscope | HDMI from host (split via 1×2 HDMI splitter) |
| Mic array | ReSpeaker USB 4-mic array (far-field, AEC) | USB2 |
| Speaker | 20W 4Ω full-range driver + 25W class-D amp (MAX9744, hardware volume pot) | I2S/analog from USB DAC on host |
| Dome rotation | NEMA-17 stepper + 1:5.18 planetary, 12T GT2 pinion on dome ring gear | Step/dir from MCU |
| Drive motors | 2× 24V 250W geared DC scooter motors + Cytron MD30C drivers, in feet | PWM+dir from MCU |
| Center leg lift (2-3-2 mode) | Linear actuator, 150 mm stroke, 24V | Relay/H-bridge from MCU |
| IMU | BNO085 9-DOF, UART | MCU |
| Thermal | 3× DS18B20 (compute bay, motor bay, vision node heatsink) + host internal sensors | OneWire → MCU; host `sensors` |
| Battery monitor | INA219 on main bus | I2C → MCU |
| mmWave presence | 3× Hi-Link LD2450 24 GHz human-tracking radar (front-left, front-right skirt + rear) | UART → USB-serial hub → host |
| Ultrasonic ring | 4× HC-SR04P at 45°/135°/225°/315° under skirt | GPIO trig/echo → MCU |
| Cliff sensors | 3× VL53L1X ToF pointing down under skirt edge | I2C (addr-muxed) → MCU |
| Vision node | Jetson Orin Nano 8 GB in dome (dedicated vision LLM) | GbE via slip-ring → host |
| Hermes agent node | Jetson Nano 4 GB (hidden, dome inner ring) hosting the Hermes agent layer | GbE via slip-ring → host |
| GPS | u-blox NEO-M9N receiver, USB/UART | USB → host |
| Cellular hotspot | 4G/5G USB modem (Quectel RM520N-GL class), WAN failover | USB → host |
| WiFi router | GL.iNet-class travel router, onboard AP for operator | GbE → host |
| E-stop | Latching red mushroom on rear access panel + soft e-stop on RC link | Hardwired motor-power cut; GPIO to MCU |

---

## 3. Interconnect Map (full wiring plan)

```
                        ┌──────────────────────────────────────────────┐
                        │         LLM HOST (Strix Halo)                │
                        │  Ubuntu 24.04 · Ollama · ROS 2 Jazzy         │
                        └───┬───────┬───────┬──────┬─────┬──────┬──────┘
                 USB3 (eye) │       │ HDMI  │ HDMI │ USB │ USB-C│ GbE
                            │       │ (1×2 splitter) │    │  (PD)│ (slip-ring)
                            ▼       ▼      ▼        ▼    │      ▼
                   ┌────────────┐  ┌─────────┐ ┌────────┐│  ┌─────────────────┐
                   │  IMX477    │  │ 5" LCD  │ │ P6X    ││  │ DOME NODES      │
                   │  dome eye  │  │ wink    │ │ proj.  ││  │ ├ vision (Orin) │
                   └────────────┘  └─────────┘ └────────┘│  │ └ hermes (Nano) │
                                                         │  └─────────────────┘
        ┌────────────────────────────────────────────────┘
        │ USB CDC 115200 (JSON-lines framed)
        ▼
┌────────────────────────────────────────────────────────────────┐
│              REAL-TIME MCU (Teensy 4.1)                        │
│                                                                │
│  PWM ch0-7  ──► dome stepper (step/dir), eye LED, gripper arm │
│  PWM ch8-11 ──► MD30C motor drivers (L/R drive)               │
│  Relay 0    ──► center-leg linear actuator H-bridge           │
│  GPIO       ──► e-stop chain sense, bump switches (front/rear)│
│  UART2      ──► BNO085 IMU                                    │
│  OneWire    ──► 3× DS18B20 temp probes                        │
│  I2C        ──► INA219 bus power monitor                      │
│  ADC        ──► panel voltage dividers (aux battery taps)     │
└────────────────────────────────────────────────────────────────┘
        ▲
        │ 24 V main bus (fused 30 A)
┌───────┴───────────────────────────────────────────────────────┐
│                     POWER DISTRIBUTION                        │
│  2× 24V 20Ah LiFePO4 (series/parallel bus, ~960 Wh)           │
│   ├── 30 A fuse ──► motor bus (MD30C drivers)                 │
│   ├── 15 A buck 24→19 V/180 W ──► LLM host DC-in              │
│   ├── 10 A buck 24→12 V ──► projector, amp, fans, comms       │
│   ├── 5 A buck 24→5 V ──► MCU, LCD logic, mic, dome nodes     │
│   └── charge port (rear panel) ──► 24 V LiFePO4 BMS charger   │
└────────────────────────────────────────────────────────────────┘
                        ▲
        ┌───────────────┼────────────────┐
        │ USB           │ USB            │ GbE
        ▼               ▼                ▼
   ┌─────────┐   ┌────────────┐   ┌──────────┐
   │ u-blox  │   │ Quectel 5G │   │ GL.iNet  │
   │ NEO-M9N │   │ cellular   │   │ WiFi AP  │
   │ GPS     │   │ hotspot    │   │ router   │
   └─────────┘   └────────────┘   └──────────┘
```

**Bus rules**
- All motion power (motors, actuator) is on a hardware e-stop loop that
  does not pass through any computer. The MCU only *senses* the loop.
- The host can be hard-powered down independently (soft-off via MCU
  relay on its DC line) so compute can reboot without touching mobility
  power.
- All high-current grounds star-ground at the power distribution board,
  never through signal cables.

---

## 4. Cooling & Thermal System

Heat budget at full load: host ~140 W + motors ~200 W peak + projector
~60 W ≈ 400 W worst case. The astromech body is a sealed tube — cooling
must move air deliberately.

| Zone | Airflow path | Hardware |
|---|---|---|
| Compute bay (mid-deck) | Intake: filtered vent behind front utility arms. Exhaust: rear panel vents (hidden by rear logic display) | 2× 80 mm Noctua NF-A8 12 V intake, 2× 80 mm exhaust; ducted shrouds (3D printed: `compute_bay_shroud`) |
| Host heatsink | Stock mini-PC vapor chamber retained; add copper heat spreader plate to chassis rail as passive sink | 200×150×3 mm C110 copper plate, thermal-pad coupled |
| Dome | Convection via dome ring gap; eye LED + projector add ~15 W | 1× 60 mm quiet fan behind projector vent |
| Battery bay (lower body) | LiFePO4 needs no active cooling below 45 °C | passive vents at skirt, monitored by MCU |

**Thermal policy (enforced in `src/thermal/`):**
- CPU/GPU > 75 °C → fan curve to 100 %, LLM inference throttled to
  smaller model (fallback model config).
- Any zone > 85 °C → graceful inference shutdown, mobility stays live.
- Battery > 50 °C → full stop, charge-inhibit, audible alert.

---

### Vision Node (dome-mounted, dedicated vision LLM)
- **Board:** Jetson Orin Nano 8 GB dev module (or Orin Nano Super), mounted
  in the dome/head beside the eye assembly
- **Role:** dedicated vision-language inference so the main brain host
  never stalls on camera frames. Runs the vision LLM (moondream2 or
  Qwen2.5-VL-3B GGUF via llama.cpp / jetson-containers), face detection,
  and OCR for the eye.
- **Why separate:** vision inference is bursty and memory-hungry; on the
  shared host it would evict the chat LLM's KV cache and stutter speech.
  A dedicated 8 GB node keeps the eye pipeline at a steady ~5–10 fps
  caption / ~15 fps detect without touching the brain's context.
- **Link to host:** gigabit Ethernet over the dome slip-ring
  (1000BASE-T pair on the slip-ring capsule). Vision node exposes a tiny
  HTTP API (`POST /caption`, `POST /detect`) consumed by `src/eye/camera.py`
  — the `vlm_client` injection point already supports a remote callable.
- **Power:** 5 V/4 A buck from the 12 V rail; ~7–15 W typical, 25 W peak.
- **Thermal:** 60 mm dome fan already specified pulls air across its
  heatsink; DS18B20 probe clipped to the SoC heatsink reports into the
  thermal policy as a fourth zone (`vision_c`).
- **Failover:** if the vision node is unreachable, `EyeCamera.caption()`
  falls back to the brain host's own (slower) vision model — same API.

| Vision node spec | Value |
|---|---|
| SoC | Jetson Orin Nano 8 GB (102 GB/s, 40 TOPS sparse INT8) |
| Vision model | moondream2 (fast caption) + Qwen2.5-VL-3B (detail/OCR) |
| Camera | IMX477 via CSI-2 direct on the Jetson (bypasses USB3 bridge — shorter path); USB3 bridge version kept as spare |
| API | HTTP :8081 — `/caption`, `/detect`, `/ocr`, `/health` |
| Mount | 3D-printed `vision_node_tray.stl` on dome inner ring, ribbon CSI through eye bezel |

---

### Hermes Agent Node (hidden, dome-mounted agent host)

- **Board:** Jetson Nano 4 GB (the older, smaller Nano — *not* the Orin),
  mounted on the dome inner ring beside the vision node, behind the
  rear logic display so it's invisible from outside.
- **Role:** hosts the **Hermes agent layer** — remedy personality
  routing, limbic affective state, prompt orchestration, and the
  long-running agent loop — as a *networked peer* to the main brain
  host. The brain host keeps its RAM and memory bandwidth dedicated to
  LLM inference; the agent layer's chatter (personality prefix builds,
  limbic prompt wrapping, memory reads) lives on its own board.
- **Why separate:** the Hermes agent loop makes frequent small calls
  (affect updates, memory reads, prefix assembly). On the shared host
  these compete with the LLM's KV cache and CUDA context; on a 4 GB
  Nano the whole agent stack fits comfortably (it calls back to the
  brain host over GbE for actual inference) and the brain host never
  sees the orchestration overhead.
- **API:** HTTP :9299 — `/health`, `/state`, `/prompt`, `/personality`,
  `/limbic`. Consumed by `src/hermesnode/agent_node.py`.
- **Link:** gigabit Ethernet over the dome slip-ring (shares the
  vision node's 1000BASE-T capsule via a 2-port slip-ring switch).
- **Power:** 5 V/3 A buck from the 12 V rail; ~5–10 W typical.
- **Thermal:** shares the dome 60 mm fan airflow; a fifth DS18B20
  probe (`hermes_c`) reports into the thermal policy.
- **Failover:** if the node is unreachable, the brain host runs the
  personality/limbic bridges locally (the bridges already degrade
  gracefully — see `src/brain/personality.py`, `src/brain/limbic.py`).

---

### Comms Stack (optional WAN / positioning add-ons)

Three independent, all-optional modules behind `src/comms/`:

| Module | Part | Role |
|---|---|---|
| GPS | u-blox NEO-M9N | Global position fix for outdoor ops, astro-nav alignment, and geofenced behaviors |
| Cellular hotspot | Quectel RM520N-GL 5G USB modem | WAN failover when the WiFi router's uplink drops — keeps the dashboard + remote ops reachable in the field |
| WiFi router | GL.iNet travel router | Onboard AP (`r1a1-ops`) the operator's phone joins; bridges to venue WiFi or falls back to cellular |

- **Failover policy** (`CommsStack.ensure_wan()`): WiFi is primary;
  cellular is brought up only when WiFi drops, with a 30 s reconnect
  cooldown so a flapping uplink doesn't hammer the modem.
- **GPS** feeds the astro navigation stack (true-north alignment,
  local sidereal time) and can geofence drive behaviors.
- **All optional:** every subsystem reports `available=False` when its
  hardware isn't wired; the robot runs fully offline without them.

| Comms spec | Value |
|---|---|
| GPS | u-blox NEO-M9N, USB/UART, 1.5 m CEP |
| Cellular | Quectel RM520N-GL, 5G sub-6, USB 3.0 |
| WiFi router | GL.iNet AX1800-class, dual-band AP |
| API | `src/comms/stack.py` — `CommsStack.status()` |

---

## 5. Chassis & Structure

- **Internal frame:** JAG-style aluminum frame — 3 mm 5052 aluminum ring
  plates top/bottom, 2020/T-slot verticals, or the printed PETG/ABS
  frame if staying all-print (Mr Baddeley frame set).
- **Skins:** 3D-printed PETG (weatherable) or ASA (UV-stable), body shell
  in 4–6 segments, glued + solvent-welded.
- **Dome:** 3D-printed two-piece dome is fine; aluminum dome (500 mm
  spun) if we want the premium option — source via astromech.net
  parts runs.
- See `docs/PARTS.md` for the complete printed-parts list with links.
