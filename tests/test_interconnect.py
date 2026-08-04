"""Tests for src/interconnect: framing, CRC, timeout, heartbeat, estop,
and the selftest green/failure paths — all against a FakeSerial mock, no
hardware required.

Run: python -m unittest tests.test_interconnect -v   (or pytest)
"""

from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from interconnect import (  # noqa: E402
    LinkCRCError,
    LinkError,
    LinkTimeout,
    SerialLink,
    run_selftest,
)
from interconnect.link import compute_crc  # noqa: E402


class FakeSerial:
    """Minimal serial-port stand-in with a scriptable reply queue.

    ``script`` maps a cmd string to the payload the "MCU" should reply with
    (use the string "TIMEOUT" to simulate silence). Replies are framed and
    CRC'd exactly like the real firmware would, unless ``corrupt`` is set.
    """

    def __init__(self, script=None, corrupt=False, baud=115200):
        self.script = dict(script or {})
        self.corrupt = corrupt
        self.written = bytearray()   # everything the host sent us
        self._rx = bytearray()       # bytes queued for the host to read
        self.baud = baud
        self.closed = False

    # -- host side -----------------------------------------------------
    def write(self, data: bytes) -> int:
        self.written.extend(data)
        # A real MCU answers as soon as it gets a full line; emulate that.
        line = bytes(self.written).split(b"\n")[-2] if self.written.endswith(b"\n") else None
        if line is not None:
            try:
                req = json.loads(line.decode("utf-8"))
                self._enqueue_reply(req)
            except (ValueError, IndexError):
                pass
        return len(data)

    def read(self, n: int) -> bytes:
        if not self._rx:
            return b""
        out = bytes(self._rx[:n])
        del self._rx[:n]
        return out

    def close(self):
        self.closed = True

    # -- MCU emulation -------------------------------------------------
    def _enqueue_reply(self, req: dict) -> None:
        cmd = req.get("cmd")
        spec = self.script.get(cmd, "TIMEOUT")
        if spec == "TIMEOUT":
            return
        payload = spec(req.get("payload")) if callable(spec) else spec
        seq = req.get("seq", 0)
        crc = compute_crc(cmd, seq, payload)
        if self.corrupt:
            crc ^= 0xDEADBEEF
        frame = {"cmd": cmd, "seq": seq, "payload": payload, "crc": crc}
        self._rx.extend((json.dumps(frame) + "\n").encode("utf-8"))


def make_link(script=None, **fake_kwargs):
    fake = FakeSerial(script, **fake_kwargs)
    link = SerialLink("/dev/ttyFAKE0", 115200, serial_factory=lambda *a, **k: fake)
    return link, fake


class TestFraming(unittest.TestCase):
    def test_frame_format_keys_and_newline(self):
        link, fake = make_link()
        link.send("motor", {"left": 10, "right": -10})
        raw = bytes(fake.written)
        self.assertTrue(raw.endswith(b"\n"), "frame must be newline-terminated")
        self.assertEqual(raw.count(b"\n"), 1, "exactly one line per frame")
        frame = json.loads(raw.decode("utf-8"))
        self.assertEqual(set(frame.keys()), {"cmd", "seq", "payload", "crc"})
        self.assertEqual(frame["cmd"], "motor")
        self.assertEqual(frame["payload"], {"left": 10, "right": -10})
        self.assertIsInstance(frame["seq"], int)
        self.assertIsInstance(frame["crc"], int)

    def test_seq_increments(self):
        link, fake = make_link()
        s0 = link.send("a", None)
        s1 = link.send("b", None)
        self.assertEqual(s1, s0 + 1)

    def test_crc_matches_cmd_seq_payload(self):
        link, fake = make_link()
        link.send("servo", {"ch": 3, "deg": 45})
        frame = json.loads(bytes(fake.written).decode("utf-8"))
        self.assertEqual(
            frame["crc"],
            compute_crc("servo", frame["seq"], {"ch": 3, "deg": 45}),
        )

    def test_crc_detects_corruption(self):
        link, _ = make_link({"heartbeat": {"ok": True}}, corrupt=True)
        link.send("heartbeat", {})
        with self.assertRaises(LinkCRCError):
            link.recv(timeout=0.2)


class TestRecvTimeout(unittest.TestCase):
    def test_recv_timeout_raises_linktimeout(self):
        link, _ = make_link()  # no scripted replies => silence
        link.send("heartbeat", {})
        with self.assertRaises(LinkTimeout):
            link.recv(timeout=0.05)

    def test_recv_success_returns_validated_frame(self):
        link, _ = make_link({"ping": {"pong": 1}})
        link.send("ping", None)
        frame = link.recv(timeout=0.5)
        self.assertEqual(frame["cmd"], "ping")
        self.assertEqual(frame["payload"], {"pong": 1})

    def test_malformed_json_raises_linkerror(self):
        link, fake = make_link()
        fake._rx.extend(b"{not json}\n")
        with self.assertRaises(LinkError):
            link.recv(timeout=0.2)


class TestHeartbeatAndEstop(unittest.TestCase):
    def test_heartbeat_true_when_mcu_answers(self):
        link, _ = make_link({"heartbeat": {"alive": True}})
        self.assertTrue(link.heartbeat(timeout=0.5))

    def test_heartbeat_false_on_timeout(self):
        link, _ = make_link()
        self.assertFalse(link.heartbeat(timeout=0.05))

    def test_estop_sense_clear(self):
        link, _ = make_link({"estop_sense": {"estop": False}})
        self.assertFalse(link.estop_sense(timeout=0.5))

    def test_estop_sense_engaged(self):
        link, _ = make_link({"estop_sense": {"estop": True}})
        self.assertTrue(link.estop_sense(timeout=0.5))

    def test_estop_sense_failsafe_on_timeout(self):
        """A dead link must report ESTOPPED (fail-safe), never 'all clear'."""
        link, _ = make_link()
        self.assertTrue(link.estop_sense(timeout=0.05))


class TestSelftest(unittest.TestCase):
    GOOD_SCRIPT = {
        "heartbeat": {"alive": True},
        "estop_sense": {"estop": False},
        "echo": lambda payload: payload,  # loop back whatever we send
    }

    def test_green_path(self):
        link, _ = make_link(self.GOOD_SCRIPT)
        result = run_selftest(link, timeout=0.5)
        self.assertEqual(result, {"heartbeat": True, "estop": True, "echo": True})

    def test_failure_path_all_dead(self):
        link, _ = make_link()  # MCU silent on every channel
        result = run_selftest(link, timeout=0.05)
        self.assertEqual(result, {"heartbeat": False, "estop": False, "echo": False})

    def test_failure_path_bad_echo(self):
        script = dict(self.GOOD_SCRIPT)
        script["echo"] = {"wrong": "payload"}  # MCU echoes garbage
        link, _ = make_link(script)
        result = run_selftest(link, timeout=0.5)
        self.assertTrue(result["heartbeat"])
        self.assertTrue(result["estop"])
        self.assertFalse(result["echo"])

    def test_failure_path_corrupt_wire(self):
        link, _ = make_link(self.GOOD_SCRIPT, corrupt=True)
        result = run_selftest(link, timeout=0.5)
        self.assertEqual(result, {"heartbeat": False, "estop": False, "echo": False})

    def test_selftest_never_raises_on_link_faults(self):
        link, _ = make_link()
        try:
            run_selftest(link, timeout=0.02)
        except LinkError as exc:
            self.fail(f"run_selftest raised {exc!r} instead of reporting in dict")


if __name__ == "__main__":
    unittest.main()
