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

## Layout

```
src/
  brain/        LLM client, memory, prompt-routing agent
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
tests/          full pytest suite (hardware-mocked, 164 tests)
docs/
  HARDWARE.md   compute bay, vision node, interconnect map, cooling, chassis
  PARTS.md      complete 3D-printed parts list with design links
  BUILD.md      phase-by-phase assembly instructions
  PROMPTS.md    53 acceptance prompts (testable behaviors)
```

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest tests/                 # full suite, hardware auto-mocked
python -m src.interconnect.selftest   # bench link check (needs MCU)
```

## Docs

- [docs/HARDWARE.md](docs/HARDWARE.md) — full hardware architecture
- [docs/PARTS.md](docs/PARTS.md) — every printed part + metal chassis spec
- [docs/BUILD.md](docs/BUILD.md) — build sequence with safety gates
- [docs/PROMPTS.md](docs/PROMPTS.md) — 42 acceptance prompts

## License

MIT
