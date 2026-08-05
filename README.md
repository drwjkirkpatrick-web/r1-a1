# R1-A1

A self-contained, LLM-driven astromech robot — brain, body, and voice.

R1-A1 is a full-size rolling companion robot built around a local large
language model. It sees through a dome-mounted camera eye, speaks and
chirps through an onboard audio stack, projects images from a periscope
projector, winks with a round front logic screen, drives on two powered
feet (with a retractable center leg for 2-3-2 mode), and keeps itself
cool with a ducted multi-fan thermal system — all orchestrated from an
internal mini PC running Ubuntu.

## Highlights

- 🧠 **Local brain** — Ollama-hosted LLM (primary 3B model, fallback
  2B model) with conversation memory and meta-prompt routing
- 🍎 **Mac Studio M3 Ultra option** — operators can swap to a 512 GB
  Mac Studio M3 Ultra brain via one config line (`host_type: mac_ultra`),
  unlocking 70B+ models at full precision via the MLX backend
- 🎭 **Remedy personalities** — optional Hermes remedy personality
  overlay (100 remedies) shapes the agent's temperament and voice
- 🧬 **Limbic system** — optional Hermes affective state engine gives
  R1-A1 persistent mood (VAD), neurochemistry, and expression style
  across turns — visible on the dashboard
- 📊 **Dashboard** — live web dashboard (port 9298) showing subsystem
  status, brain model, personality, and limbic state in real time
- 👁 **Single eye** — 12 MP dome camera with face tracking, OCR, and
  vision-LLM captioning, plus an RGB "wink" illuminator
- 🛰 **Vision node** — dedicated Jetson Orin Nano in the head running the
  vision LLM (moondream2 / Qwen2.5-VL) over gigabit slip-ring link, so
  the brain never stalls on camera frames
- 📡 **Spatial awareness** — 8 upgrades: mmWave human tracking (sees in
  the dark), ultrasonic ring, cliff sensors, IMU+odometry pose fusion,
  ego-centric occupancy grid, proximity speed policy, one-call sensor
  fusion, and awareness-refined movement with detours + pursuit
- 🖥 **Wink screen** — 5″ round front logic display for expressions,
  gauges, and scrolling text
- 📽 **Projector** — dome periscope projector with brightness control
  and camera mirroring
- 🛞 **Motion** — closed-loop odometry drive, dome rotation, 2-3-2
  center leg, expressive wiggles, soft e-stop in under 100 ms
- ❄️ **Thermal** — five-fan ducted cooling with a 3-tier thermal policy
  (throttle → shutdown → full stop)
- 🔋 **Power** — LiFePO4 bus with state-of-charge, range estimation,
  and charger-seek policy
- 🔗 **Interconnect** — CRC-checked JSON-lines serial link between the
  brain host and the real-time MCU, with a full selftest
- ⚙️ **Firmware** — complete Teensy 4.1 sketch: interrupt-driven e-stop,
  CRC-validated command dispatch, unsolicited safety telemetry

## Brain host options

| `host_type` | Board | RAM | Backend | Max model |
|---|---|---|---|---|
| `ubuntu_x86` (default) | Strix Halo mini PC | 128 GB | Ollama | 70B Q4 |
| `mac_ultra` | Mac Studio M3 Ultra | 512 GB | MLX | 405B Q4 / 70B FP |
| `jetson` | Jetson AGX Orin 64 GB | 64 GB | Ollama | 20B Q4 |

Set in `config/r1a1.yaml` — the brain code is host-agnostic and talks to
any OpenAI/Ollama-compatible endpoint.

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

## Dashboard

```bash
python -m src.dashboard.server  # starts on 127.0.0.1:9298
```

The dashboard shows:

- Robot name, version, and brain model
- Host type and inference backend
- Thermal and power subsystem status
- Active remedy personality (with emoji) if enabled
- Live limbic state: VAD bars, dominant affect, allostatic load,
  expression warmth — if enabled

## Layout

```
src/
  brain/        LLM client, memory, prompt-routing agent
                + personality.py (remedy bridge)
                + limbic.py (affective state bridge)
  dashboard/    Flask web dashboard (subsystem + personality + limbic)
  motion/       drive, dome, center leg, expressive gaits + awareness refiner
  awareness/    mmWave, ultrasonic, cliff, pose, occupancy, proximity, fusion
  eye/          dome camera + wink illuminator
  display/      front logic screen
  projector/    periscope projector
  thermal/      fan/temp monitor + thermal policy
  power/        battery monitor + range policy
  audio/        speaker/chirps + mic array
  interconnect/ host↔MCU serial link + selftest
firmware/       Teensy 4.1 MCU sketch (r1a1_mcu.ino) + pin map
tests/          full pytest suite (hardware-mocked)
docs/
  HARDWARE.md   compute bay, vision node, interconnect map, cooling, chassis
  PARTS.md      complete 3D-printed parts list with design links
  BUILD.md      phase-by-phase assembly instructions
  PROMPTS.md    53 acceptance prompts (testable behaviors)
config/
  r1a1.yaml     runtime configuration (brain, personality, limbic, dashboard)
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/                 # full suite, hardware auto-mocked
python -m src.interconnect.selftest   # bench link check (needs MCU)
python -m src.dashboard.server         # dashboard on :9298
```

## Docs

- [docs/HARDWARE.md](docs/HARDWARE.md) — full hardware architecture
- [docs/PARTS.md](docs/PARTS.md) — every printed part + metal chassis spec
- [docs/EXTERNAL_PARTS.md](docs/EXTERNAL_PARTS.md) — community designs, blueprints, 3D print files, and parts suppliers
- [docs/DELUXE_BUILD.md](docs/DELUXE_BUILD.md) — deluxe build guide integrating external parts and community resources
- [docs/BUILD.md](docs/BUILD.md) — build sequence with safety gates
- [docs/PROMPTS.md](docs/PROMPTS.md) — 42 acceptance prompts

## License

MIT