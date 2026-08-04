/*
 * R1-A1 MCU firmware — Teensy 4.1 real-time companion
 * =====================================================
 *
 * Role: hard real-time partner to the LLM host. The host thinks; this
 * board moves, senses, and — above all — keeps the robot SAFE. Motion
 * power never depends on the host being alive.
 *
 * Protocol (must match src/interconnect/link.py exactly):
 *   One JSON object per line over USB CDC (Serial), 115200 8N1:
 *       {"cmd": <str>, "seq": <int>, "payload": <object>, "crc": <uint32>}
 *   crc = CRC-32 (zlib poly 0xEDB88320) of the UTF-8 bytes of:
 *       cmd + str(seq) + json.dumps(payload, separators=(",", ":"))
 *   i.e. cmd, decimal seq, then COMPACT JSON of the payload (no spaces),
 *   concatenated as raw text. Replies use the same framing.
 *
 * PIN MAP (docs/HARDWARE.md §2/§3)
 * --------------------------------
 *   0/1   (Serial1)  — spare / RC receiver soft e-stop link
 *   2     ESTOP_SENSE — latching mushroom, ACTIVE LOW, interrupt-driven
 *   3     DOME_STEP  — dome stepper STEP (PWM ch0)
 *   4     DOME_DIR   — dome stepper DIR
 *   5     EYE_LED    — wink illuminator PWM (ch1)
 *   6     SERVO_0    — eye shutter servo (ch2)
 *   7     SERVO_1    — eye gimbal pan servo (ch3)
 *   8     MOTOR_L_PWM— MD30C left  (ch8)
 *   9     MOTOR_L_DIR
 *   10    MOTOR_R_PWM— MD30C right (ch9)
 *   11    MOTOR_R_DIR
 *   14    LEG_RELAY  — center-leg actuator H-bridge relay (ch Relay0)
 *   18/19 (Serial4=UART2) — BNO085 IMU (if HAS_BNO085)
 *   22    ONEWIRE    — DS18B20 temp bus (compute/motor/vision probes)
 *   20/21 (Wire)     — I2C: INA219 bus monitor + VL53L1X cliff mux
 *   24-27 BUMP[0:3]  — bump switches (front L/R, rear L/R), ACTIVE LOW
 *
 * Build: see firmware/README.md. Optional sensor drivers are guarded by
 * #ifdef so the sketch compiles bare-metal with zero libraries.
 */

#include <stdint.h>

// ---------------------------------------------------------------
// Config
// ---------------------------------------------------------------
#define FW_VERSION      "0.2.0"
#define LINE_BUF_SIZE   512
#define HEARTBEAT_MS    1000

// Uncomment when the sensor libraries are installed:
// #define HAS_BNO085
// #define HAS_DS18B20
// #define HAS_INA219

// Pin assignments (see map above)
static const uint8_t PIN_ESTOP      = 2;
static const uint8_t PIN_DOME_STEP  = 3;
static const uint8_t PIN_DOME_DIR   = 4;
static const uint8_t PIN_EYE_LED    = 5;
static const uint8_t PIN_SERVO0     = 6;
static const uint8_t PIN_SERVO1     = 7;
static const uint8_t PIN_ML_PWM     = 8;
static const uint8_t PIN_ML_DIR     = 9;
static const uint8_t PIN_MR_PWM     = 10;
static const uint8_t PIN_MR_DIR     = 11;
static const uint8_t PIN_LEG_RELAY  = 14;
static const uint8_t PIN_ONEWIRE    = 22;
static const uint8_t PIN_BUMP[4]    = {24, 25, 26, 27};

// ---------------------------------------------------------------
// E-stop — the one thing that must always work
// ---------------------------------------------------------------
static volatile bool g_estop = false;

static void kill_motion_outputs() {
  // ISR-safe: direct digital writes only, no malloc, no Serial.
  digitalWriteFast(PIN_ML_PWM, LOW);
  digitalWriteFast(PIN_MR_PWM, LOW);
  digitalWriteFast(PIN_DOME_STEP, LOW);
  digitalWriteFast(PIN_LEG_RELAY, LOW);
}

static void estop_isr() {
  g_estop = (digitalReadFast(PIN_ESTOP) == LOW);  // active low
  if (g_estop) kill_motion_outputs();
}

// ---------------------------------------------------------------
// CRC-32, zlib polynomial — matches zlib.crc32 on the host
// ---------------------------------------------------------------
static uint32_t crc32_update(uint32_t crc, const uint8_t* data, size_t len) {
  crc = ~crc;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int b = 0; b < 8; b++)
      crc = (crc >> 1) ^ (0xEDB88320UL & (uint32_t)(-(int32_t)(crc & 1)));
  }
  return ~crc;
}

// ---------------------------------------------------------------
// Minimal JSON field extraction (flat objects only — our frames are)
// ---------------------------------------------------------------
// Find "key" and copy its string value (without quotes) into out.
static bool json_get_string(const char* line, const char* key,
                            char* out, size_t out_len) {
  char pat[24];
  snprintf(pat, sizeof(pat), "\"%s\":\"", key);
  const char* p = strstr(line, pat);
  if (!p) return false;
  p += strlen(pat);
  const char* end = strchr(p, '"');
  if (!end) return false;
  size_t n = (size_t)(end - p);
  if (n >= out_len) n = out_len - 1;
  memcpy(out, p, n);
  out[n] = '\0';
  return true;
}

// Find "key" and parse its integer value.
static bool json_get_int(const char* line, const char* key, long* out) {
  char pat[24];
  snprintf(pat, sizeof(pat), "\"%s\":", key);
  const char* p = strstr(line, pat);
  if (!p) return false;
  p += strlen(pat);
  *out = strtol(p, nullptr, 10);
  return true;
}

// Find "key" and parse its float value.
static bool json_get_float(const char* line, const char* key, float* out) {
  char pat[24];
  snprintf(pat, sizeof(pat), "\"%s\":", key);
  const char* p = strstr(line, pat);
  if (!p) return false;
  p += strlen(pat);
  *out = strtof(p, nullptr);
  return true;
}

// Extract the raw text of the "payload" value (object or primitive),
// so we can reproduce the host's CRC input byte-for-byte.
static bool json_get_raw_payload(const char* line, char* out, size_t out_len) {
  const char* p = strstr(line, "\"payload\":");
  if (!p) return false;
  p += strlen("\"payload\":");
  // payload ends at the matching close of the value; our frames always
  // follow it with ,"crc": so scan for that terminator.
  const char* end = strstr(p, ",\"crc\":");
  if (!end) return false;
  size_t n = (size_t)(end - p);
  if (n >= out_len) return false;
  memcpy(out, p, n);
  out[n] = '\0';
  return true;
}

// ---------------------------------------------------------------
// Actuators (tuning constants marked TODO — bench-calibrate per build)
// ---------------------------------------------------------------
static void setMotorPWM(int16_t left, int16_t right) {  // -255..255
  if (g_estop) return;  // motion stays dead while latched
  // TODO: verify MD30C sign conventions on the bench (Gate A, BUILD.md)
  digitalWrite(PIN_ML_DIR, left  >= 0 ? HIGH : LOW);
  digitalWrite(PIN_MR_DIR, right >= 0 ? HIGH : LOW);
  analogWrite(PIN_ML_PWM, constrain(abs(left),  0, 255));
  analogWrite(PIN_MR_PWM, constrain(abs(right), 0, 255));
}

static void setServo(uint8_t pin, float deg) {  // 0..180
  // TODO: calibrate µs endpoints per servo (default 500–2500 µs)
  int us = 500 + (int)(constrain(deg, 0.0f, 180.0f) / 180.0f * 2000.0f);
  (void)us;  // wire to Servo library or 50 Hz PWM timer when fitted
  (void)pin;
}

static void domeStep(int32_t steps, bool dir) {  // blocking, small moves
  if (g_estop) return;
  // TODO: steps-per-degree after ring-gear tooth count is measured
  digitalWrite(PIN_DOME_DIR, dir ? HIGH : LOW);
  for (int32_t i = 0; i < steps; i++) {
    digitalWrite(PIN_DOME_STEP, HIGH);
    delayMicroseconds(800);
    digitalWrite(PIN_DOME_STEP, LOW);
    delayMicroseconds(800);
    if (g_estop) return;  // bail mid-move if the loop trips
  }
}

// ---------------------------------------------------------------
// Telemetry
// ---------------------------------------------------------------
static float read_temp_c(uint8_t probe) {
#ifdef HAS_DS18B20
  // TODO: OneWire + DallasTemperature on PIN_ONEWIRE, index by probe
  (void)probe;
  return 0.0f;
#else
  (void)probe;
  return -127.0f;  // DS18B20 error sentinel
#endif
}

// ---------------------------------------------------------------
// Replies
// ---------------------------------------------------------------
static uint32_t g_rx_seq = 0;

static void send_reply(const char* cmd, uint32_t seq, const char* payload_json) {
  // CRC input: cmd + str(seq) + payload (compact), matching the host.
  char seqbuf[12];
  snprintf(seqbuf, sizeof(seqbuf), "%lu", (unsigned long)seq);
  uint32_t crc = 0;
  crc = crc32_update(crc, (const uint8_t*)cmd, strlen(cmd));
  crc = crc32_update(crc, (const uint8_t*)seqbuf, strlen(seqbuf));
  crc = crc32_update(crc, (const uint8_t*)payload_json, strlen(payload_json));

  Serial.print("{\"cmd\":\"");      Serial.print(cmd);
  Serial.print("\",\"seq\":");      Serial.print(seq);
  Serial.print(",\"payload\":");    Serial.print(payload_json);
  Serial.print(",\"crc\":");        Serial.print(crc);
  Serial.print("}");
  Serial.println();
}

// ---------------------------------------------------------------
// Command dispatch
// ---------------------------------------------------------------
static void handle_line(const char* line) {
  char cmd[32];
  long seq = 0, crc = 0;
  char payload_raw[384];

  if (!json_get_string(line, "cmd", cmd, sizeof(cmd))) return;
  if (!json_get_int(line, "seq", &seq)) return;
  if (!json_get_int(line, "crc", &crc)) return;
  if (!json_get_raw_payload(line, payload_raw, sizeof(payload_raw))) return;

  // Validate CRC before touching any actuator.
  char seqbuf[12];
  snprintf(seqbuf, sizeof(seqbuf), "%ld", seq);
  uint32_t expect = 0;
  expect = crc32_update(expect, (const uint8_t*)cmd, strlen(cmd));
  expect = crc32_update(expect, (const uint8_t*)seqbuf, strlen(seqbuf));
  expect = crc32_update(expect, (const uint8_t*)payload_raw, strlen(payload_raw));
  if ((uint32_t)crc != expect) {
    send_reply("error", seq, "{\"reason\":\"crc\"}");
    return;
  }
  g_rx_seq = seq;

  // --- dispatch table -------------------------------------------------
  if (!strcmp(cmd, "heartbeat")) {
    char p[64];
    snprintf(p, sizeof(p), "{\"alive\":true,\"uptime_ms\":%lu}", millis());
    send_reply("heartbeat", seq, p);

  } else if (!strcmp(cmd, "estop_sense")) {
    send_reply("estop_sense", seq,
               g_estop ? "{\"estopped\":true}" : "{\"estopped\":false}");

  } else if (!strcmp(cmd, "echo")) {
    send_reply("echo", seq, payload_raw);  // loopback verbatim

  } else if (!strcmp(cmd, "drive.forward")) {
    float meters = 0, speed = 0;
    json_get_float(payload_raw, "meters", &meters);
    json_get_float(payload_raw, "speed", &speed);
    // TODO: closed-loop odometry drive; open-loop mapping for now
    int16_t pwm = (int16_t)(constrain(speed, 0.0f, 1.0f) * 255.0f);
    setMotorPWM(pwm, pwm);
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "drive.rotate")) {
    float degrees = 0;
    json_get_float(payload_raw, "degrees", &degrees);
    int16_t pwm = 120;  // TODO: gyro-closed rotation
    setMotorPWM(degrees > 0 ? pwm : -pwm, degrees > 0 ? -pwm : pwm);
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "drive.stop")) {
    setMotorPWM(0, 0);
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "dome.rotate")) {
    float degrees = 0;
    json_get_float(payload_raw, "degrees", &degrees);
    // TODO: steps-per-degree constant from measured ring gear
    domeStep((int32_t)(fabs(degrees) * 8.0f), degrees >= 0);
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "leg.deploy") || !strcmp(cmd, "leg.retract")) {
    digitalWrite(PIN_LEG_RELAY, cmd[4] == 'd' ? HIGH : LOW);
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "pwm")) {
    long channel = 0; float duty = 0;
    json_get_int(payload_raw, "channel", &channel);
    json_get_float(payload_raw, "duty", &duty);
    if (channel == 1)  // eye LED
      analogWrite(PIN_EYE_LED, (int)(constrain(duty, 0.0f, 1.0f) * 255.0f));
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "servo")) {
    long channel = 0; float deg = 0;
    json_get_int(payload_raw, "channel", &channel);
    json_get_float(payload_raw, "position_deg", &deg);
    setServo(channel == 2 ? PIN_SERVO0 : PIN_SERVO1, deg);
    send_reply("ack", seq, "{\"ok\":true}");

  } else if (!strcmp(cmd, "sensors.read")) {
    char p[160];
    snprintf(p, sizeof(p),
             "{\"compute_c\":%.1f,\"motor_bay_c\":%.1f,\"vision_c\":%.1f,"
             "\"bumps\":[%d,%d,%d,%d]}",
             read_temp_c(0), read_temp_c(1), read_temp_c(2),
             digitalRead(PIN_BUMP[0]) == LOW, digitalRead(PIN_BUMP[1]) == LOW,
             digitalRead(PIN_BUMP[2]) == LOW, digitalRead(PIN_BUMP[3]) == LOW);
    send_reply("sensors", seq, p);

  } else {
    send_reply("error", seq, "{\"reason\":\"unknown_cmd\"}");
  }
}

// ---------------------------------------------------------------
// Arduino entry points
// ---------------------------------------------------------------
static char g_line[LINE_BUF_SIZE];
static size_t g_line_len = 0;
static uint32_t g_last_beat = 0;

void setup() {
  Serial.begin(115200);  // USB CDC: baud is nominal, host must match name only
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_ML_PWM, OUTPUT); pinMode(PIN_ML_DIR, OUTPUT);
  pinMode(PIN_MR_PWM, OUTPUT); pinMode(PIN_MR_DIR, OUTPUT);
  pinMode(PIN_DOME_STEP, OUTPUT); pinMode(PIN_DOME_DIR, OUTPUT);
  pinMode(PIN_EYE_LED, OUTPUT);
  pinMode(PIN_SERVO0, OUTPUT); pinMode(PIN_SERVO1, OUTPUT);
  pinMode(PIN_LEG_RELAY, OUTPUT);
  for (uint8_t i = 0; i < 4; i++) pinMode(PIN_BUMP[i], INPUT_PULLUP);

  attachInterrupt(digitalPinToInterrupt(PIN_ESTOP), estop_isr, CHANGE);
  kill_motion_outputs();  // boot safe: everything off until commanded
}

void loop() {
  // Non-blocking line reader: accumulate until '\n', dispatch, reset.
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n') {
      g_line[g_line_len] = '\0';
      if (g_line_len > 0) handle_line(g_line);
      g_line_len = 0;
    } else if (c != '\r') {
      if (g_line_len < LINE_BUF_SIZE - 1) g_line[g_line_len++] = c;
      else g_line_len = 0;  // overflow: drop frame, resync on next newline
    }
  }

  // Unsolicited safety telemetry: e-stop transitions announce themselves
  // instead of waiting for the host to poll.
  static bool last_estop = false;
  if (g_estop != last_estop) {
    last_estop = g_estop;
    send_reply("estop_event", g_rx_seq,
               g_estop ? "{\"estopped\":true}" : "{\"estopped\":false}");
  }

  // Idle heartbeat keeps the host's link watchdog fed.
  if (millis() - g_last_beat >= HEARTBEAT_MS) {
    g_last_beat = millis();
    char p[64];
    snprintf(p, sizeof(p), "{\"alive\":true,\"uptime_ms\":%lu}", millis());
    send_reply("heartbeat", g_rx_seq, p);
  }
}
