# R1-A1 MCU Firmware

Teensy 4.1 real-time companion firmware. The LLM host thinks; this board
moves, senses, and enforces safety. Motion power never depends on the host.

## Build & Upload

**Option A — Teensyduino (Arduino IDE)**
1. Install Arduino IDE 2.x + [Teensyduino](https://www.pjrc.com/teensy/teensyduino.html)
2. Board: **Teensy 4.1**, USB Type: **Serial**, CPU Speed: 600 MHz
3. Open `r1a1_mcu.ino`, Verify, Upload

**Option B — arduino-cli**
```bash
arduino-cli core install teensy:avr
arduino-cli compile --fqbn teensy:avr:teensy41:usb=serial,speed=600 firmware/
arduino-cli upload  --fqbn teensy:avr:teensy41 -p /dev/ttyACM0 firmware/
```

Compiles with **zero external libraries**. Optional sensor drivers are
guarded by `#define` at the top of the sketch (`HAS_BNO085`,
`HAS_DS18B20`, `HAS_INA219`) — uncomment as hardware is fitted.

## Pin Map

| Pin | Function | Notes |
|---|---|---|
| 2 | E-stop sense | ACTIVE LOW, interrupt, ISR kills all motion PWM |
| 3/4 | Dome stepper STEP/DIR | via stepper driver |
| 5 | Eye LED PWM | wink illuminator |
| 6/7 | Servo 0/1 | eye shutter, gimbal pan |
| 8–11 | Motor L/R PWM+DIR | Cytron MD30C drivers |
| 14 | Center-leg relay | linear actuator H-bridge |
| 18/19 | UART2 (Serial4) | BNO085 IMU |
| 20/21 | I2C (Wire) | INA219 + VL53L1X cliff mux |
| 22 | OneWire | DS18B20 temp bus (3 probes) |
| 24–27 | Bump switches ×4 | ACTIVE LOW, INPUT_PULLUP |

## Protocol Quick Reference

JSON-lines over USB CDC, one object per line:
`{"cmd": str, "seq": int, "payload": object, "crc": uint32}`

CRC-32 (zlib poly) over `cmd + str(seq) + compact-JSON(payload)` — must
match `src/interconnect/link.py` byte-for-byte.

| Command | Payload | Action |
|---|---|---|
| `heartbeat` | `{}` | reply `{alive, uptime_ms}` (also sent unsolicited every 1 s) |
| `estop_sense` | `{}` | reply `{estopped}` — dead-host fail-safe on the Python side |
| `echo` | any | loopback verbatim (link selftest) |
| `drive.forward` | `{meters, speed}` | both motors, speed 0–1 → PWM |
| `drive.rotate` | `{degrees}` | counter-rotate wheels |
| `drive.stop` | `{}` | immediate stop (soft e-stop path) |
| `dome.rotate` | `{degrees}` | stepper move, ±8 steps/deg (TODO calibrate) |
| `leg.deploy` / `leg.retract` | `{}` | center-leg relay |
| `pwm` | `{channel, duty}` | channel 1 = eye LED |
| `servo` | `{channel, position_deg}` | ch 2 = shutter, ch 3 = gimbal |
| `sensors.read` | `{}` | temps + bump states |

**Safety invariants**
- E-stop ISR forces motor/dome/leg outputs LOW in hardware time
- E-stop transitions are pushed as `estop_event` frames, not polled
- Bad CRC → `error` reply, no actuator touched
- Boot state: all motion outputs off until first valid command
