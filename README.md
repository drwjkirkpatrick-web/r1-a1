# R1-A1

![Version](https://img.shields.io/badge/version-0.5.0-blue)
![Tests](https://img.shields.io/badge/tests-351%20passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.12+-yellow)
![License](https://img.shields.io/badge/license-MIT-green)
![Modules](https://img.shields.io/badge/modules-55-orange)
![Lines](https://img.shields.io/badge/code-12.5K_LoC-informational)
![Brain](https://img.shields.io/badge/brain-Ollama%20%7C%20MLX%20%7C%20CUDA-purple)
![Agent Node](https://img.shields.io/badge/agent%20node-Jetson%20Nano%20(dome)-blue)
![Dashboard](https://img.shields.io/badge/dashboard-:9298-teal)
![Firmware](https://img.shields.io/badge/firmware-Teensy%204.1-darkslategray)
![Build Tiers](https://img.shields.io/badge/build%20tiers-3%20(Economy%20%7C%20Standard%20%7C%20Deluxe)-indigo)
![Astro](https://img.shields.io/badge/astro-nav%20%7C%20solar%20system%20%7C%20star%20catalog-blueviolet)
![Repair](https://img.shields.io/badge/repair-spacecraft%20framework-firebrick)
![Comms](https://img.shields.io/badge/comms-GPS%20%7C%205G%20%7C%20WiFi-yellowgreen)

A self-contained, LLM-driven astromech robot — brain, body, and voice.

R1-A1 is a full-size rolling companion robot built around a local large
language model. It sees through a dome-mounted camera eye, speaks and
chirps through an onboard audio stack, projects images from a periscope
projector, winks with a round front logic screen, drives on two powered
feet (with a retractable center leg for 2-3-2 mode), and keeps itself
cool with a ducted multi-fan thermal system — all orchestrated from an
internal mini PC running Ubuntu, with a hidden Jetson Nano in the dome
running the Hermes agent layer as a networked peer.

## Highlights

- 🧠 **Local brain** — Ollama-hosted LLM (primary 3B model, fallback
  2B model) with conversation memory and meta-prompt routing
- 🛸 **Dome Hermes agent node** — a hidden Jetson Nano 4 GB in the dome
  hosts the Hermes agent layer (remedy personality routing, limbic
  affective state, prompt orchestration) over gigabit slip-ring, so the
  main brain host keeps its RAM and memory bandwidth dedicated to
  inference. Degrades gracefully to local bridges when unreachable
- 🔥 **LLM keep-alive** — warm-model management pings the active model
  on an interval (a cold 70B load costs seconds of speech stall), and
  auto-falls back to the small model when the primary stops answering
- 💾 **Persistent memory** — facts and recent turns survive brain
  restarts via atomic JSON snapshot (`~/.r1a1/memory.json`)
- 🌟 **Astro navigation** — celestial coordinate conversion, solar
  system body tracking (real Keplerian orbits), 50+ star catalog with
  real data, Milky Way structure, and a live data bridge to NASA JPL
  Horizons and SIMBAD
- 🔧 **Spacecraft repair framework** — extensible diagnostic engine
  with a spacecraft registry (Crew Dragon, Soyuz MS, Space Shuttle
  built in), subsystem definitions, failure modes, and repair
  procedures — add any spacecraft type later
- 🍎 **Mac Studio M3 Ultra option** — operators can swap to a 512 GB
  Mac Studio M3 Ultra brain via one config line (`host_type: mac_ultra`),
  unlocking 70B+ models at full precision via the MLX backend
- 🎭 **Remedy personalities** — optional Hermes remedy personality
  overlay (100 remedies) shapes the agent's temperament and voice
- 🧬 **Limbic system** — optional Hermes affective state engine gives
  R1-A1 persistent mood (VAD), neurochemistry, and expression style
  across turns — visible on the dashboard
- 📊 **Dashboard** — live web dashboard (port 9298) showing subsystem
  status, brain model, motion odometry, Hermes node reachability,
  personality, and limbic state in real time, plus a lightweight
  `/api/health` keep-alive endpoint
- 👁 **Single eye** — 12 MP dome camera with face tracking, OCR, and
  vision-LLM captioning, plus an RGB "wink" illuminator
- 🛰 **Vision node** — dedicated Jetson Orin Nano in the head running the
  vision LLM (moondream2 / Qwen2.5-VL) over gigabit slip-ring link, so
  the brain never stalls on camera frames
- 📡 **Spatial awareness** — 9 upgrades: mmWave human tracking (sees in
  the dark), ultrasonic ring, cliff sensors, IMU+odometry pose fusion,
  ego-centric occupancy grid, proximity speed policy, one-call sensor
  fusion, awareness-refined movement with detours + pursuit, and a
  liveness **watchdog** that escalates a silent MCU link or dead
  critical sensor to a soft e-stop
- 🌐 **Optional comms stack** — GPS (u-blox NEO-M9N) for position and
  astro-nav alignment, a 5G cellular hotspot for WAN failover, and an
  onboard WiFi router (`r1a1-ops` AP) — all optional, all degrading
  gracefully when absent
- 🖥 **Wink screen** — 5″ round front logic display for expressions,
  gauges, and scrolling text
- 📽 **Projector** — dome periscope projector with brightness control
  and camera mirroring
- 🛞 **Motion** — closed-loop odometry drive with timestamped pose,
  dome rotation with scan/center expressions, 2-3-2 center leg with
  drive guard, expressive wiggles, soft e-stop in under 100 ms
- ❄️ **Thermal** — five-fan ducted cooling with a 3-tier thermal policy
  (throttle → shutdown → full stop) and host temperature trend tracking
  for predictive throttling
- 🔋 **Power** — LiFePO4 bus with state-of-charge (validated against
  garbage sensor reads), range estimation, and charger-seek policy
- 🔗 **Resilient interconnect** — CRC-checked JSON-lines serial link
  between the brain host and the real-time MCU, with bounded retry on
  transient dropouts and a full selftest
- ⚙️ **Firmware** — complete Teensy 4.1 sketch: interrupt-driven e-stop,
  CRC-validated command dispatch, unsolicited safety telemetry

## Brain host options

| `host_type` | Board | RAM | Backend | Max model |
|---|---|---|---|---|
| `ubuntu_x86` (default) | Strix Halo mini PC | 128 GB | Ollama | 70B Q4 |
| `mac_ultra` | Mac Studio M3 Ultra | 512 GB | MLX | 405B Q4 / 70B FP |
| `jetson` | Jetson AGX Orin 64 GB | 64 GB | Ollama | 20B Q4 |

Set in `config/r1a1.yaml` — the brain code is host-agnostic and talks to
any OpenAI/Ollama-compatible endpoint. The dome Hermes node (Jetson
Nano) and vision node (Jetson Orin Nano) are fixed peripherals
independent of the brain host choice.

## Dome compute

Two small Jetsons ride in the dome alongside the eye:

| Node | Board | Role | API |
|---|---|---|---|
| Vision node | Jetson Orin Nano 8 GB | Vision LLM (moondream2 / Qwen2.5-VL), face detect, OCR | HTTP :8081 |
| **Hermes agent node** | Jetson Nano 4 GB (hidden) | Hermes agent layer: personality, limbic, orchestration | HTTP :9299 |

The Hermes node is the agent's *home* — the main brain host is reserved
for inference. When the node is unreachable the brain falls back to
running the personality and limbic bridges locally.

## Personality & Limbic System (optional)

R1-A1 can optionally adopt a Hermes remedy personality and/or run the
Hermes limbic affective system. Both are disabled by default and
require the corresponding Hermes skill/project to be installed.

### Remedy personalities

```yaml
brain:
  personality:
    enabled: true
    remedy: "bryonia_alba"  # 100 remedies available
```

When enabled, the agent's system prompt is prepended with a
temperament-specific directive. The active remedy emoji appears on the
dashboard. Requires the `remedy_personality_picker` Hermes skill.

### Limbic system

```yaml
brain:
  limbic:
    enabled: true
    profile: "pulsatilla_pratensis"  # 52 temperament profiles
    intensity: 0.6                    # 0.0–0.8
    inject_into_prompt: true
```

When enabled, R1-A1 maintains persistent mood (valence/arousal/dominance),
neurochemistry, drives, and expression style across turns. The dashboard
shows live VAD bars, dominant affect, and allostatic load. Requires the
`limbic-hermes` project at `~/projects/limbic-hermes/`.

## Optional comms stack

```yaml
comms:
  enabled: true
  gps:      { enabled: true }                  # u-blox NEO-M9N
  cellular: { enabled: true, apn: "wholesale" } # 5G failover hotspot
  wifi:     { enabled: true, ssid: "r1a1-ops" } # onboard AP
```

WiFi is the primary uplink; cellular comes up only on WiFi loss (30 s
reconnect cooldown). GPS feeds astro-nav true-north alignment and can
geofence drive behaviors. Everything reports `available=False` when its
hardware isn't wired — the robot runs fully offline without any of it.

## Dashboard

```bash
python -m src.dashboard.server  # starts on 127.0.0.1:9298
```

The dashboard shows:

- Robot name, version, and brain model
- Host type and inference backend
- Motion odometry (x, y, heading, fix age) and e-stop latch
- Hermes agent node reachability and last-contact time
- Thermal and power subsystem status
- Active remedy personality (with emoji) if enabled
- Live limbic state: VAD bars, dominant affect, allostatic load,
  expression warmth — if enabled
- `/api/health` — lightweight liveness endpoint for keep-alive monitors

## Layout

```
src/
  brain/        LLM client, memory (persisted), prompt-routing agent
                + personality.py (remedy bridge)
                + limbic.py (affective state bridge)
                + keepalive.py (warm-model management)
  hermesnode/   dome Hermes agent node client (Jetson Nano peer)
  comms/        GPS, cellular hotspot failover, WiFi router stack
  dashboard/    Flask web dashboard (8 cards + /api/health)
  astro/        celestial navigation, solar system, star catalog,
                Milky Way structure, astronomical data bridge
  repair/       spacecraft repair framework: registry, diagnostics,
                repair procedures (extensible)
  motion/       drive, dome, center leg, expressive gaits + awareness refiner
  awareness/    mmWave, ultrasonic, cliff, pose, occupancy, proximity,
                fusion, watchdog
  eye/          dome camera + wink illuminator
  display/      front logic screen
  projector/    periscope projector
  thermal/      fan/temp monitor, thermal policy, trend tracking
  power/        battery monitor (validated) + range policy
  audio/        speaker/chirps + mic array
  interconnect/ host↔MCU serial link (with retry) + selftest
firmware/       Teensy 4.1 MCU sketch (r1a1_mcu.ino) + pin map
tests/          full pytest suite (hardware-mocked, 351 tests)
docs/
  HARDWARE.md       compute bay, dome nodes, comms, interconnect map, cooling, chassis
  PARTS.md          complete 3D-printed parts list with design links
  EXTERNAL_PARTS.md community designs, blueprints, 3D print files, suppliers
  DELUXE_BUILD.md   deluxe build guide integrating external parts
  BUILD.md          phase-by-phase assembly instructions
  GAP_ANALYSIS.md   astromech knowledge domain gap analysis
  PROMPTS.md        53 acceptance prompts (testable behaviors)
config/
  r1a1.yaml     runtime configuration (brain, keepalive, hermes node,
                comms, watchdog, memory, personality, limbic, dashboard)
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/                      # full suite, hardware auto-mocked
python -m src.cli doctor           # audit every subsystem
python -m src.cli chat             # talk to the brain from the shell
python -m src.interconnect.selftest   # bench link check (needs MCU)
python -m src.dashboard.server         # dashboard on :9298
```

## What's new in 0.5.0

- **Dome Hermes agent node** (`src/hermesnode/`) — hidden Jetson Nano
  peer hosting the agent layer
- **LLM keep-alive** (`src/brain/keepalive.py`) — warm-model pings +
  auto-fallback
- **Subsystem watchdog** (`src/awareness/watchdog.py`) — link/sensor
  liveness supervision with e-stop escalation
- **Comms stack** (`src/comms/`) — optional GPS, cellular failover,
  WiFi router
- **Persistent memory** — facts and turns survive restarts
- **Agent context** — the LLM now sees recent conversation turns
- **Safe LLM calls** — a dead model server returns a spoken fallback
  instead of crashing the voice loop
- **Serial retry** — bounded retry on transient link dropouts
- **Odometry freshness** — timestamped pose for fusion/dashboard
- **Power validation** — NaN/inf sensor reads raise instead of
  silently clamping
- **Thermal trend** — host °C/s rate for predictive throttling
- **Dome scan/center**, **center-leg guards**, **CLI chat + selftest**
- **Dashboard** — motion + Hermes node cards, `/api/health` endpoint

## Docs

- [docs/HARDWARE.md](docs/HARDWARE.md) — full hardware architecture
- [docs/PARTS.md](docs/PARTS.md) — every printed part + metal chassis spec
- [docs/EXTERNAL_PARTS.md](docs/EXTERNAL_PARTS.md) — community designs, blueprints, 3D print files, and parts suppliers
- [docs/DELUXE_BUILD.md](docs/DELUXE_BUILD.md) — deluxe build guide integrating external parts and community resources
- [docs/GAP_ANALYSIS.md](docs/GAP_ANALYSIS.md) — astromech knowledge domain gap analysis
- [docs/BUILD.md](docs/BUILD.md) — build sequence with safety gates
- [docs/PROMPTS.md](docs/PROMPTS.md) — 42 acceptance prompts

## License

MIT
