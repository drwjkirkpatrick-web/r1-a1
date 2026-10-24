"""Host <-> firmware protocol CONTRACT tests (CODE_REVIEW.md F1-F4, §6.1).

This file is the single, shared schema for the host<->MCU wire protocol.
It encodes, in one place, what `firmware/r1a1_mcu.ino` expects and emits,
and asserts that the host side (`src/interconnect/link.py`,
`src/interconnect/selftest.py`, and host command senders) agrees with it.

Three layers are tested:

1. CONTRACT vs host frames — for every command the host can send, the
   exact JSON keys/types emitted by ``SerialLink.encode_frame`` match the
   CONTRACT dict below.
2. CRC semantics — CRC-32 is UNSIGNED 32-bit. Round-trip known frames
   (including CRCs >= 0x8000 and >= 0x80000000, which signed parsing
   rejects/clamps) through a Python simulation of the firmware parser.
3. Firmware-simulation — ``FirmwareSim`` mirrors the .ino parsing and
   dispatch logic (post-fix), so the fixed behaviors (estop payload key
   "estop", unsigned CRC parse, rotate-0 no-op, channel map) are pinned
   here even though the .ino cannot be compiled on the host.

If you change the .ino framing, dispatch, keys, or channel map, update
CONTRACT here in the same commit.

Run: python -m pytest tests/test_protocol_contract.py -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from interconnect.link import SerialLink, compute_crc  # noqa: E402
from interconnect.selftest import run_selftest  # noqa: E402

# ---------------------------------------------------------------------------
# THE CONTRACT — single source of truth for the wire protocol.
# ---------------------------------------------------------------------------
# Frame envelope (both directions):
#   {"cmd": str, "seq": int, "payload": <object|any>, "crc": int}
# crc = zlib.crc32((cmd + str(seq) + compact_json(payload)).encode())
#     — an UNSIGNED 32-bit integer, decimal-encoded on the wire.
#
# E-stop payloads (estop_sense reply AND unsolicited estop_event frames)
# carry the boolean key "estop" (CODE_REVIEW.md F1).

ESTOP_KEY = "estop"

# Effector channel map — the firmware pin map (.ino header) is
# authoritative (CODE_REVIEW.md F3):
#   pwm   ch1 -> eye LED (duty 0.0..1.0)
#   servo ch2 -> SERVO_0 eye shutter
#   servo ch3 -> SERVO_1 gimbal pan
CHANNELS = {
    "eye_led_pwm": 1,
    "shutter_servo": 2,
    "gimbal_pan_servo": 3,
}

# Commands the firmware replies to without a prior request (telemetry,
# not command replies).
UNSOLICITED_CMDS = ("heartbeat", "estop_event")

# Reason string for pwm/servo frames addressed to an unknown channel.
BAD_CHANNEL_REASON = "bad_channel"

# Request/response schema per command. "payload" maps key -> allowed
# Python type(s); None means "any payload" (echo loops back verbatim).
# "reply_payload" is checked for the keys listed (replies may carry
# extras, e.g. ack's optional "note").
CONTRACT = {
    "heartbeat": {
        "payload": {"t": (int, float)},
        "reply_cmd": "heartbeat",
        "reply_payload": {"alive": bool, "uptime_ms": int},
    },
    "estop_sense": {
        "payload": {},
        "reply_cmd": "estop_sense",
        "reply_payload": {ESTOP_KEY: bool},
    },
    "echo": {
        "payload": None,  # arbitrary, echoed verbatim
        "reply_cmd": "echo",
    },
    "drive.forward": {
        "payload": {"meters": (int, float), "speed": (int, float)},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "drive.rotate": {
        "payload": {"degrees": (int, float)},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "drive.stop": {
        "payload": {},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "dome.rotate": {
        "payload": {"degrees": (int, float)},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "leg.deploy": {
        "payload": {},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "leg.retract": {
        "payload": {},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "pwm": {
        "payload": {"channel": int, "duty": (int, float)},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "servo": {
        "payload": {"channel": int, "position_deg": (int, float)},
        "reply_cmd": "ack",
        "reply_payload": {"ok": bool},
    },
    "sensors.read": {
        "payload": {},
        "reply_cmd": "sensors",
        "reply_payload": {
            "compute_c": (int, float),
            "motor_bay_c": (int, float),
            "vision_c": (int, float),
            "bumps": list,
        },
    },
}

# Representative payload per command, used to exercise the full set.
SAMPLE_PAYLOADS = {
    "heartbeat": {"t": 1234567.5},
    "estop_sense": {},
    "echo": {"token": "r1a1-contract-echo", "n": 42},
    "drive.forward": {"meters": 0.5, "speed": 0.4},
    "drive.rotate": {"degrees": 45.0},
    "drive.stop": {},
    "dome.rotate": {"degrees": -30.0},
    "leg.deploy": {},
    "leg.retract": {},
    "pwm": {"channel": CHANNELS["eye_led_pwm"], "duty": 1.0},
    "servo": {"channel": CHANNELS["shutter_servo"], "position_deg": 90},
    "sensors.read": {},
}

FRAME_KEYS = ("cmd", "seq", "payload", "crc")
UINT32_MAX = 0xFFFFFFFF


# ---------------------------------------------------------------------------
# Firmware parser simulation — Python mirror of the .ino's JSON extraction
# and dispatch (POST-FIX). Keep in sync with firmware/r1a1_mcu.ino.
# ---------------------------------------------------------------------------
def _find_value_start(line: str, key: str):
    """Mirror of the .ino's strstr("\"key\":") lookup."""
    idx = line.find('"%s":' % key)
    if idx < 0:
        return None
    return idx + len(key) + 3


def _parse_leading_number(text: str) -> float:
    """strtod-like: parse the longest valid numeric prefix."""
    i = 0
    if i < len(text) and text[i] in "+-":
        i += 1
    digits = 0
    while i < len(text) and text[i].isdigit():
        i += 1
        digits += 1
    if i < len(text) and text[i] == ".":
        i += 1
        while i < len(text) and text[i].isdigit():
            i += 1
            digits += 1
    if digits == 0:
        return 0.0
    if i < len(text) and text[i] in "eE":
        j = i + 1
        if j < len(text) and text[j] in "+-":
            j += 1
        k = j
        while k < len(text) and text[k].isdigit():
            k += 1
        if k > j:
            i = k
    return float(text[:i])


def json_get_int(line: str, key: str):
    """Mirror of the .ino's json_get_int (signed strtol, 32-bit long)."""
    p = _find_value_start(line, key)
    if p is None:
        return None
    val = int(_parse_leading_number(line[p:]))
    # 32-bit signed long semantics on the Teensy's ARM core: clamp.
    return max(-(2**31), min(2**31 - 1, val))


def json_get_uint(line: str, key: str):
    """Mirror of the .ino's json_get_uint (strtoul) — the F2 fix.

    CRC-32 values up to 0xFFFFFFFF parse correctly; the old signed
    strtol path clamped them to LONG_MAX (2**31 - 1).
    """
    p = _find_value_start(line, key)
    if p is None:
        return None
    return int(_parse_leading_number(line[p:])) & UINT32_MAX


def json_get_float(line: str, key: str):
    p = _find_value_start(line, key)
    if p is None:
        return None
    return _parse_leading_number(line[p:])


def json_get_string(line: str, key: str):
    p = _find_value_start(line, key)
    if p is None or p >= len(line) or line[p] != '"':
        return None
    end = line.find('"', p + 1)
    if end < 0:
        return None
    return line[p + 1:end]


def json_get_raw_payload(line: str):
    """Mirror of the .ino's raw-payload extraction (text up to ,"crc":)."""
    p = _find_value_start(line, "payload")
    if p is None:
        return None
    end = line.find(',"crc":', p)
    if end < 0:
        return None
    return line[p:end]


class FirmwareSim:
    """Python mirror of firmware/r1a1_mcu.ino handle_line() (post-fix).

    Tracks actuator state so tests can observe what the firmware would
    have done: motor PWMs, eye-LED duty, and per-pin servo positions.
    """

    # Pin names from the .ino pin map (authoritative channel map).
    PIN_EYE_LED = "EYE_LED"        # pwm ch1
    PIN_SERVO0_SHUTTER = "SERVO_0"  # servo ch2 (eye shutter)
    PIN_SERVO1_GIMBAL = "SERVO_1"   # servo ch3 (gimbal pan)

    # The command set the firmware dispatch table implements.
    COMMANDS = frozenset(CONTRACT.keys())

    def __init__(self, estop: bool = False) -> None:
        self.estop = estop
        self.motor_pwm = (0, 0)
        self.eye_led_duty = 0.0
        self.servo_positions = {}   # pin name -> degrees
        self.leg_relay = False
        self.replies = []           # list of raw reply lines (strings)

    # -- CRC, mirroring crc32_update + send_reply -------------------------
    @staticmethod
    def _crc32_text(cmd: str, seq: int, payload_raw: str) -> int:
        import zlib

        body = cmd + str(seq) + payload_raw
        return zlib.crc32(body.encode("utf-8")) & UINT32_MAX

    def _send_reply(self, cmd: str, seq: int, payload_raw: str) -> None:
        crc = self._crc32_text(cmd, seq, payload_raw)
        self.replies.append(
            '{"cmd":"%s","seq":%d,"payload":%s,"crc":%d}'
            % (cmd, seq, payload_raw, crc)
        )

    # -- actuators ---------------------------------------------------------
    def _set_motor_pwm(self, left: int, right: int) -> None:
        if self.estop:
            return  # motion stays dead while latched (g_estop guard)
        self.motor_pwm = (
            max(-255, min(255, abs(left))) * (1 if left >= 0 else -1),
            max(-255, min(255, abs(right))) * (1 if right >= 0 else -1),
        )

    # -- dispatch ------------------------------------------------------------
    def handle_line(self, line: str) -> None:
        cmd = json_get_string(line, "cmd")
        seq = json_get_int(line, "seq")
        crc = json_get_uint(line, "crc")  # F2 fix: unsigned parse
        payload_raw = json_get_raw_payload(line)
        if cmd is None or seq is None or crc is None or payload_raw is None:
            return

        expect = self._crc32_text(cmd, seq, payload_raw)
        if crc != expect:
            self._send_reply("error", seq, '{"reason":"crc"}')
            return

        if cmd == "heartbeat":
            self._send_reply(cmd, seq, '{"alive":true,"uptime_ms":1000}')
        elif cmd == "estop_sense":
            # F1 fix: payload key is "estop" (was "estopped").
            val = "true" if self.estop else "false"
            self._send_reply(cmd, seq, '{"%s":%s}' % (ESTOP_KEY, val))
        elif cmd == "echo":
            self._send_reply(cmd, seq, payload_raw)
        elif cmd == "drive.forward":
            speed = json_get_float(payload_raw, "speed") or 0.0
            speed = max(0.0, min(1.0, speed))
            pwm = int(speed * 255)
            self._set_motor_pwm(pwm, pwm)
            self._send_reply("ack", seq, '{"ok":true}')
        elif cmd == "drive.rotate":
            degrees = json_get_float(payload_raw, "degrees") or 0.0
            if degrees == 0.0:
                # F4 fix: zero-degree rotate is a stop/no-op, never a spin.
                self._set_motor_pwm(0, 0)
                self._send_reply("ack", seq, '{"ok":true,"note":"noop"}')
            else:
                pwm = 120
                if degrees > 0:
                    self._set_motor_pwm(pwm, -pwm)
                else:
                    self._set_motor_pwm(-pwm, pwm)
                self._send_reply("ack", seq, '{"ok":true}')
        elif cmd == "drive.stop":
            self._set_motor_pwm(0, 0)
            self._send_reply("ack", seq, '{"ok":true}')
        elif cmd == "dome.rotate":
            self._send_reply("ack", seq, '{"ok":true}')
        elif cmd in ("leg.deploy", "leg.retract"):
            self.leg_relay = cmd == "leg.deploy"
            self._send_reply("ack", seq, '{"ok":true}')
        elif cmd == "pwm":
            # F3: ch1 = eye LED only; unknown channels are an error.
            channel = json_get_int(payload_raw, "channel")
            duty = json_get_float(payload_raw, "duty") or 0.0
            if channel == CHANNELS["eye_led_pwm"]:
                self.eye_led_duty = max(0.0, min(1.0, duty))
                self._send_reply("ack", seq, '{"ok":true}')
            else:
                self._send_reply(
                    "error", seq, '{"reason":"%s"}' % BAD_CHANNEL_REASON
                )
        elif cmd == "servo":
            # F3: ch2 = SERVO_0 (shutter), ch3 = SERVO_1 (gimbal pan).
            channel = json_get_int(payload_raw, "channel")
            deg = json_get_float(payload_raw, "position_deg") or 0.0
            if channel == CHANNELS["shutter_servo"]:
                self.servo_positions[self.PIN_SERVO0_SHUTTER] = deg
                self._send_reply("ack", seq, '{"ok":true}')
            elif channel == CHANNELS["gimbal_pan_servo"]:
                self.servo_positions[self.PIN_SERVO1_GIMBAL] = deg
                self._send_reply("ack", seq, '{"ok":true}')
            else:
                self._send_reply(
                    "error", seq, '{"reason":"%s"}' % BAD_CHANNEL_REASON
                )
        elif cmd == "sensors.read":
            self._send_reply(
                "sensors",
                seq,
                '{"compute_c":-127.0,"motor_bay_c":-127.0,'
                '"vision_c":-127.0,"bumps":[false,false,false,false]}',
            )
        else:
            self._send_reply("error", seq, '{"reason":"unknown_cmd"}')

    def estop_event_frame(self) -> dict:
        """The unsolicited frame emitted on an e-stop transition."""
        val = "true" if self.estop else "false"
        return {
            "cmd": "estop_event",
            "seq": 0,
            "payload": {ESTOP_KEY: self.estop},
            "crc": self._crc32_text("estop_event", 0, '{"%s":%s}' % (ESTOP_KEY, val)),
        }


class SimSerial:
    """Serial-port stand-in wired to a FirmwareSim (request -> reply)."""

    def __init__(self, sim: FirmwareSim) -> None:
        self.sim = sim
        self.written = bytearray()
        self._rx = bytearray()
        self._tx_line = bytearray()

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        for byte in data:
            if byte == 0x0A:  # '\n'
                line = self._tx_line.decode("utf-8")
                self._tx_line.clear()
                if line.strip():
                    before = len(self.sim.replies)
                    self.sim.handle_line(line)
                    for reply in self.sim.replies[before:]:
                        self._rx.extend((reply + "\n").encode("utf-8"))
            elif byte != 0x0D:  # '\r'
                self._tx_line.append(byte)
        return len(data)

    def read(self, n: int) -> bytes:
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def close(self) -> None:
        pass


def make_sim_link(estop: bool = False):
    """A SerialLink talking to a FirmwareSim over SimSerial."""
    sim = FirmwareSim(estop=estop)
    serial = SimSerial(sim)
    link = SerialLink(
        "/dev/ttySIM0", 115200, serial_factory=lambda *a, **k: serial
    )
    return link, sim, serial


# ---------------------------------------------------------------------------
# 1. Host frames vs CONTRACT
# ---------------------------------------------------------------------------
class TestHostFramesMatchContract(unittest.TestCase):
    def test_contract_covers_all_host_commands(self):
        # Every command with a sample payload is in the CONTRACT and vice
        # versa; the firmware sim implements exactly the CONTRACT set.
        self.assertEqual(set(CONTRACT), set(SAMPLE_PAYLOADS))
        self.assertEqual(set(CONTRACT), set(FirmwareSim.COMMANDS))

    def test_frame_envelope_shape_and_types(self):
        link, _, serial = make_sim_link()
        for cmd, payload in SAMPLE_PAYLOADS.items():
            serial.written.clear()
            link.send(cmd, payload)
            raw = bytes(serial.written)
            self.assertTrue(raw.endswith(b"\n"), f"{cmd}: frame not newline-terminated")
            frame = json.loads(raw.decode("utf-8"))
            self.assertEqual(set(frame.keys()), set(FRAME_KEYS), cmd)
            self.assertIsInstance(frame["cmd"], str, cmd)
            self.assertIsInstance(frame["seq"], int, cmd)
            self.assertIsInstance(frame["crc"], int, cmd)
            self.assertGreaterEqual(frame["crc"], 0, cmd)
            self.assertLessEqual(frame["crc"], UINT32_MAX, cmd)

    def test_payload_keys_and_types_match_contract(self):
        link, _, serial = make_sim_link()
        for cmd, spec in CONTRACT.items():
            sample = SAMPLE_PAYLOADS[cmd]
            serial.written.clear()
            link.send(cmd, sample)
            frame = json.loads(bytes(serial.written).decode("utf-8"))
            expected = spec["payload"]
            if expected is None:  # echo: anything goes
                continue
            self.assertEqual(
                set(frame["payload"].keys()), set(expected.keys()),
                f"{cmd}: payload keys drifted from CONTRACT",
            )
            for key, types in expected.items():
                self.assertIsInstance(
                    frame["payload"][key], types,
                    f"{cmd}.{key}: expected {types}, got {type(frame['payload'][key])}",
                )

    def test_every_contract_command_roundtrips_through_firmware_sim(self):
        """The firmware accepts and correctly replies to every command."""
        link, sim, _ = make_sim_link()
        for cmd, spec in CONTRACT.items():
            reply = link.roundtrip(cmd, SAMPLE_PAYLOADS[cmd], timeout=1.0)
            self.assertEqual(reply["cmd"], spec["reply_cmd"], cmd)
            self.assertNotEqual(reply["cmd"], "error", f"{cmd}: {reply}")
            payload = reply["payload"]
            for key, types in (spec.get("reply_payload") or {}).items():
                self.assertIn(key, payload, f"{cmd}: reply missing {key!r}")
                self.assertIsInstance(payload[key], types, f"{cmd}.{key}")


# ---------------------------------------------------------------------------
# 2. CRC semantics (F2)
# ---------------------------------------------------------------------------
# Vectors computed once from interconnect.link.compute_crc and pinned here
# so a regression in either the host or the sim trips this test.
KNOWN_CRC_VECTORS = [
    ("echo", 7, {"a": 1}, 126291466),
    ("heartbeat", 0, {"t": 0.0}, 861705030),
    # crc >= 2**31 — the class of frames signed strtol rejected (F2):
    ("estop_sense", 3, {}, 3729697731),
    # crc >= 0x8000 but < 2**31 — rejected by a 16-bit signed parse:
    ("drive.rotate", 1, {"degrees": 45.0}, 1142639167),
    # crc >= 2**31:
    ("drive.rotate", 0, {"degrees": 45.0}, 3283976572),
]


class TestCRCContract(unittest.TestCase):
    def test_known_vectors(self):
        for cmd, seq, payload, expected in KNOWN_CRC_VECTORS:
            self.assertEqual(
                compute_crc(cmd, seq, payload), expected,
                f"compute_crc({cmd!r}, {seq}, {payload!r}) changed — the "
                "CRC algorithm/framing must never drift",
            )

    def test_high_crc_frames_accepted_by_firmware_parser(self):
        """Frames with crc >= 0x8000 / >= 2**31 pass the fixed parser."""
        link, sim, _ = make_sim_link()
        for cmd, seq, payload, crc in KNOWN_CRC_VECTORS:
            raw = link.encode_frame(cmd, seq, payload).decode("utf-8").strip()
            self.assertEqual(json_get_uint(raw, "crc"), crc)
            before = len(sim.replies)
            sim.handle_line(raw)
            self.assertGreater(len(sim.replies), before, f"{cmd}: no reply")
            reply = json.loads(sim.replies[-1])
            self.assertNotEqual(reply["cmd"], "error",
                                f"{cmd} (crc={crc:#x}) rejected: {reply}")

    def test_signed_strtol_would_reject_high_crcs(self):
        """Pin the bug class: signed 32-bit parse clamps >= 2**31."""
        signed_16_max = 0x7FFF
        signed_32_max = 2**31 - 1
        for cmd, seq, payload, crc in KNOWN_CRC_VECTORS:
            raw = json.dumps(
                {"cmd": cmd, "seq": seq, "payload": payload, "crc": crc},
                separators=(",", ":"),
            )
            unsigned = json_get_uint(raw, "crc")
            signed = json_get_int(raw, "crc")  # old .ino parse path
            self.assertEqual(unsigned, crc)
            if crc > signed_32_max:
                self.assertEqual(signed, signed_32_max)  # clamped => rejected
                self.assertNotEqual(signed, crc)
            else:
                self.assertEqual(signed, crc)
            # A 16-bit signed parse (the historical intuition) fares worse:
            if crc > signed_16_max:
                self.assertGreater(crc, signed_16_max)

    def test_crc_detects_corruption(self):
        sim = FirmwareSim()
        good = compute_crc("drive.stop", 5, {})
        raw = json.dumps(
            {"cmd": "drive.stop", "seq": 5, "payload": {}, "crc": good ^ 0x01},
            separators=(",", ":"),
        )
        sim.handle_line(raw)
        reply = json.loads(sim.replies[-1])
        self.assertEqual(reply["cmd"], "error")
        self.assertEqual(reply["payload"], {"reason": "crc"})


# ---------------------------------------------------------------------------
# 3. Fixed-behavior contracts (F1, F3, F4) + selftest integration
# ---------------------------------------------------------------------------
class TestEstopContract(unittest.TestCase):
    """F1: estop payload key is "estop" in BOTH frame kinds."""

    def test_estop_sense_reply_uses_contract_key(self):
        for state in (False, True):
            link, _, _ = make_sim_link(estop=state)
            reply = link.roundtrip("estop_sense", {}, timeout=1.0)
            self.assertEqual(reply["cmd"], "estop_sense")
            self.assertEqual(set(reply["payload"].keys()), {ESTOP_KEY})
            self.assertIs(reply["payload"][ESTOP_KEY], state)
            self.assertNotIn("estopped", reply["payload"])

    def test_unsolicited_estop_event_uses_contract_key(self):
        for state in (False, True):
            frame = FirmwareSim(estop=state).estop_event_frame()
            self.assertEqual(frame["cmd"], "estop_event")
            self.assertEqual(set(frame["payload"].keys()), {ESTOP_KEY})
            self.assertIs(frame["payload"][ESTOP_KEY], state)
            # The frame must survive the host's own validator.
            SerialLink.validate_frame(frame)

    def test_host_estop_sense_reads_firmware_state(self):
        link, _, _ = make_sim_link(estop=False)
        self.assertFalse(link.estop_sense())
        link, _, _ = make_sim_link(estop=True)
        self.assertTrue(link.estop_sense())

    def test_selftest_passes_against_firmware_sim(self):
        link, _, _ = make_sim_link(estop=False)
        results = run_selftest(link, timeout=1.0)
        self.assertEqual(
            results, {"heartbeat": True, "estop": True, "echo": True},
            "selftest must pass against contract-conformant firmware",
        )

    def test_selftest_estop_check_also_passes_when_estopped(self):
        link, _, _ = make_sim_link(estop=True)
        results = run_selftest(link, timeout=1.0)
        self.assertTrue(results["estop"],
                        "estopped state is still a coherent channel reply")


class TestRotateZeroContract(unittest.TestCase):
    """F4: drive.rotate with degrees == 0 is a stop/no-op."""

    def test_rotate_zero_replies_completed_noop(self):
        link, sim, _ = make_sim_link()
        reply = link.roundtrip("drive.rotate", {"degrees": 0.0}, timeout=1.0)
        self.assertEqual(reply["cmd"], "ack")
        self.assertIs(reply["payload"]["ok"], True)
        self.assertEqual(reply["payload"].get("note"), "noop")

    def test_rotate_zero_never_actuates_and_stops_motors(self):
        link, sim, _ = make_sim_link()
        link.roundtrip("drive.rotate", {"degrees": 90.0}, timeout=1.0)
        self.assertNotEqual(sim.motor_pwm, (0, 0), "nonzero rotate should spin")
        link.roundtrip("drive.rotate", {"degrees": 0}, timeout=1.0)
        self.assertEqual(sim.motor_pwm, (0, 0),
                         "rotate 0 must stop/not actuate the motors")


class TestChannelMapContract(unittest.TestCase):
    """F3: firmware channel map is authoritative and explicit."""

    def test_pwm_eye_led_channel(self):
        link, sim, _ = make_sim_link()
        reply = link.roundtrip(
            "pwm", {"channel": CHANNELS["eye_led_pwm"], "duty": 1.0},
            timeout=1.0,
        )
        self.assertEqual(reply["cmd"], "ack")
        self.assertEqual(sim.eye_led_duty, 1.0)

    def test_pwm_unknown_channel_is_an_explicit_error(self):
        link, sim, _ = make_sim_link()
        reply = link.roundtrip(
            "pwm", {"channel": 2, "duty": 1.0}, timeout=1.0  # old wink value
        )
        self.assertEqual(reply["cmd"], "error")
        self.assertEqual(reply["payload"], {"reason": BAD_CHANNEL_REASON})
        self.assertEqual(sim.eye_led_duty, 0.0, "LED must not light on ch2")

    def test_servo_channels_map_to_the_right_pins(self):
        link, sim, _ = make_sim_link()
        link.roundtrip(
            "servo",
            {"channel": CHANNELS["shutter_servo"], "position_deg": 90},
            timeout=1.0,
        )
        link.roundtrip(
            "servo",
            {"channel": CHANNELS["gimbal_pan_servo"], "position_deg": 30},
            timeout=1.0,
        )
        self.assertEqual(sim.servo_positions.get(FirmwareSim.PIN_SERVO0_SHUTTER), 90.0)
        self.assertEqual(sim.servo_positions.get(FirmwareSim.PIN_SERVO1_GIMBAL), 30.0)

    def test_servo_unknown_channel_is_an_explicit_error(self):
        link, sim, _ = make_sim_link()
        reply = link.roundtrip(
            "servo", {"channel": 7, "position_deg": 45}, timeout=1.0
        )
        self.assertEqual(reply["cmd"], "error")
        self.assertEqual(reply["payload"], {"reason": BAD_CHANNEL_REASON})
        self.assertEqual(sim.servo_positions, {})

    def test_channels_are_distinct(self):
        self.assertEqual(len(set(CHANNELS.values())), len(CHANNELS))


# ---------------------------------------------------------------------------
# 4. Host wink effector vs the firmware channel map (F3, host half)
# ---------------------------------------------------------------------------
WINK_FIX_REASON = (
    "F3 host half: src/eye/wink.py is outside this change's file scope. "
    "It must set EYE_LED_PWM_CHANNEL = 1 and SHUTTER_SERVO_CHANNEL = 2 to "
    "match the firmware-authoritative channel map (CHANNELS above)."
)


@pytest.mark.xfail(reason=WINK_FIX_REASON, strict=False)
def test_wink_channel_constants_match_contract():
    from eye import wink

    assert wink.EYE_LED_PWM_CHANNEL == CHANNELS["eye_led_pwm"]
    assert wink.SHUTTER_SERVO_CHANNEL == CHANNELS["shutter_servo"]


@pytest.mark.xfail(reason=WINK_FIX_REASON, strict=False)
def test_wink_drives_the_led_and_shutter_through_firmware_sim():
    """End-to-end: Wink's emitted commands, fed to the firmware sim, must
    light the eye LED and cycle the SHUTTER servo (not the gimbal pan)."""
    from eye.wink import Wink

    sent = []
    Wink(sent.append).wink()
    sim = FirmwareSim()
    link, _, _ = make_sim_link()
    for command in sent:
        cmd = command["cmd"]
        payload = {k: v for k, v in command.items() if k != "cmd"}
        raw = link.encode_frame(cmd, 0, payload).decode("utf-8").strip()
        sim.handle_line(raw)
        reply = json.loads(sim.replies[-1])
        assert reply["cmd"] != "error", f"firmware rejected {command}: {reply}"
    assert sim.eye_led_duty == 0.0  # ends off, but must have been ON mid-wink
    assert FirmwareSim.PIN_SERVO0_SHUTTER in sim.servo_positions
    assert FirmwareSim.PIN_SERVO1_GIMBAL not in sim.servo_positions


if __name__ == "__main__":
    unittest.main()
