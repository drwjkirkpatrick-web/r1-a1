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

### Option C — NVIDIA host (CUDA-native)
- **Board:** Jetson AGX Orin 64 GB dev kit (or AGX Thor if budget allows)
- **Why:** Full CUDA + TensorRT-LLM, Jetson AI Lab containers, 15–60 W.
  64 GB fits 8–20B models comfortably, 70B Q4 barely.
- **Trade-off:** 205 GB/s bandwidth is the lowest of the three; ARM
  ecosystem. Choose this if we want NVIDIA's Isaac/ros2 bridge.

**Decision:** Default build = **Option A (Strix Halo, Ubuntu)**. The code
in `src/brain/` is host-agnostic — it talks to a local OpenAI-compatible
endpoint, so any of the three works by changing one config line.

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
| Thermal | 2× DS18B20 (compute bay, motor bay) + host internal sensors | OneWire → MCU; host `sensors` |
| Battery monitor | INA219 on main bus | I2C → MCU |
| E-stop | Latching red mushroom on rear access panel + soft e-stop on RC link | Hardwired motor-power cut; GPIO to MCU |

---

## 3. Interconnect Map (full wiring plan)

```
                        ┌──────────────────────────────────────┐
                        │         LLM HOST (Strix Halo)        │
                        │  Ubuntu 24.04 · Ollama · ROS 2 Jazzy │
                        └───┬───────┬───────┬──────┬─────┬─────┘
                 USB3 (eye) │       │ HDMI  │ HDMI │ USB │ USB-C
                            │       │ (1×2 splitter) │    │  (PD trigger)
                            ▼       ▼      ▼        ▼    │
                   ┌────────────┐  ┌─────────┐ ┌────────┐│
                   │  IMX477    │  │ 5" LCD  │ │ P6X    ││
                   │  dome eye  │  │ wink    │ │ proj.  ││
                   └────────────┘  └─────────┘ └────────┘│
                                                        │
        ┌───────────────────────────────────────────────┘
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
│  OneWire    ──► 2× DS18B20 temp probes                        │
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
│   ├── 10 A buck 24→12 V ──► projector, amp, fans              │
│   ├── 5 A buck 24→5 V ──► MCU, LCD logic, mic, USB hub        │
│   └── charge port (rear panel) ──► 24 V LiFePO4 BMS charger   │
└────────────────────────────────────────────────────────────────┘
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
