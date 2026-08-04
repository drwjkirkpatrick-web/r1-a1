"""Serial link to the Teensy MCU.

Protocol: JSON-lines framing over USB CDC, 115200 baud 8N1.
Each frame is one line containing a single JSON object:

    {"cmd": <str>, "seq": <int>, "payload": <object>, "crc": <int>}

crc is the CRC-32 (zlib polynomial, as returned by ``zlib.crc32``) of the
byte string ``cmd + str(seq) + json.dumps(payload)`` encoded as UTF-8.

The serial object itself is dependency-injected via ``serial_factory`` so
the module is fully hardware-mockable. With no factory given, pyserial is
imported lazily (optional dependency — not needed for tests/mocks).
"""

from __future__ import annotations

import json
import time
import zlib
from typing import Any, Callable, Optional

DEFAULT_BAUD = 115200
DEFAULT_TIMEOUT = 1.0  # seconds


class LinkError(Exception):
    """Base class for interconnect errors."""


class LinkTimeout(LinkError):
    """Raised when recv() does not get a complete frame within timeout."""


class LinkCRCError(LinkError):
    """Raised when a received frame fails CRC validation."""


def compute_crc(cmd: str, seq: int, payload: Any) -> int:
    """CRC-32 of cmd + str(seq) + canonical-JSON payload."""
    body = cmd + str(seq) + json.dumps(payload, separators=(",", ":"))
    return zlib.crc32(body.encode("utf-8")) & 0xFFFFFFFF


def _default_serial_factory(port: str, baud: int, timeout: float = 0.0):
    """Lazily open a real serial port (pyserial is an optional dep)."""
    try:
        import serial  # type: ignore
    except ImportError as exc:  # pragma: no cover - hardware path
        raise LinkError(
            "pyserial is not installed and no serial_factory was provided; "
            "install pyserial or inject a serial object for testing"
        ) from exc
    return serial.Serial(port=port, baudrate=baud, timeout=timeout)


class SerialLink:
    """Framed JSON-lines link to the MCU.

    Parameters
    ----------
    port:
        OS path of the USB CDC device, e.g. ``/dev/ttyACM0``.
    baud:
        Baud rate; 115200 per the hardware spec.
    serial_factory:
        Optional callable ``(port, baud, timeout) -> serial-like object``.
        The object must provide ``write(bytes)``, ``read(n) -> bytes`` and
        ideally ``reset_input_buffer()``/``reset_output_buffer()`` (called
        via getattr, so they are optional). Inject a fake for tests.
    """

    def __init__(
        self,
        port: str,
        baud: int = DEFAULT_BAUD,
        serial_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.port = port
        self.baud = baud
        factory = serial_factory or _default_serial_factory
        self._serial = factory(port, baud, 0.0)
        self._seq = 0
        self._rx_buf = bytearray()

    # ------------------------------------------------------------------
    # framing
    # ------------------------------------------------------------------
    def _next_seq(self) -> int:
        seq = self._seq
        self._seq = (self._seq + 1) & 0x7FFFFFFF
        return seq

    def encode_frame(self, cmd: str, seq: int, payload: Any) -> bytes:
        """Build one newline-terminated JSON frame."""
        frame = {
            "cmd": cmd,
            "seq": seq,
            "payload": payload,
            "crc": compute_crc(cmd, seq, payload),
        }
        return (json.dumps(frame, separators=(",", ":")) + "\n").encode("utf-8")

    @staticmethod
    def validate_frame(frame: dict) -> None:
        """Raise LinkError if a decoded frame is malformed or CRC-bad."""
        for key in ("cmd", "seq", "payload", "crc"):
            if key not in frame:
                raise LinkError(f"frame missing key {key!r}: {frame!r}")
        expected = compute_crc(frame["cmd"], frame["seq"], frame["payload"])
        if int(frame["crc"]) != expected:
            raise LinkCRCError(
                f"crc mismatch on seq={frame['seq']}: "
                f"got {frame['crc']}, expected {expected}"
            )

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def send(self, cmd: str, payload: Any = None) -> int:
        """Send one framed command; returns the sequence number used."""
        seq = self._next_seq()
        self._serial.write(self.encode_frame(cmd, seq, payload))
        return seq

    def recv(self, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """Receive one frame within ``timeout`` seconds.

        Returns the decoded (CRC-validated) frame dict. Raises LinkTimeout
        if no complete line arrives in time, LinkError on malformed JSON,
        and LinkCRCError on a bad checksum.
        """
        deadline = time.monotonic() + timeout
        while True:
            newline = self._rx_buf.find(b"\n")
            if newline >= 0:
                line = bytes(self._rx_buf[:newline])
                del self._rx_buf[: newline + 1]
                if not line.strip():
                    continue  # tolerate blank lines on the wire
                try:
                    frame = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise LinkError(f"malformed frame: {line!r}") from exc
                if not isinstance(frame, dict):
                    raise LinkError(f"frame is not a JSON object: {frame!r}")
                self.validate_frame(frame)
                return frame

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LinkTimeout(
                    f"no frame received on {self.port} within {timeout:.3f}s"
                )
            chunk = self._serial.read(256)
            if chunk:
                self._rx_buf.extend(chunk)
            else:
                # Nothing available; small sleep to avoid busy-spinning on
                # real ports (fakes return immediately, this keeps CPU sane).
                time.sleep(min(0.005, remaining))

    # ------------------------------------------------------------------
    # convenience commands
    # ------------------------------------------------------------------
    def heartbeat(self, timeout: float = DEFAULT_TIMEOUT) -> bool:
        """Ping the MCU; True iff it replies to ``heartbeat`` in time.

        Any response frame counts as a liveness proof; a timeout or link
        error returns False rather than raising (heartbeat is a probe).
        """
        try:
            self.send("heartbeat", {"t": time.time()})
            self.recv(timeout=timeout)
            return True
        except LinkError:
            return False

    def estop_sense(self, timeout: float = DEFAULT_TIMEOUT) -> bool:
        """Query the hardware e-stop loop. True = ESTOPPED (loop open).

        The MCU replies with payload {"estop": <bool>}. Per HARDWARE.md the
        e-stop loop is hardwired; the MCU only senses it — a link failure
        here must be treated as estopped (fail-safe), so errors return True.
        """
        try:
            self.send("estop_sense", {})
            frame = self.recv(timeout=timeout)
            payload = frame.get("payload") or {}
            return bool(payload.get("estop", True))
        except LinkError:
            return True  # fail-safe: unknown link state => treat as estopped

    def echo(self, data: Any, timeout: float = DEFAULT_TIMEOUT) -> bool:
        """Loopback check: send ``echo`` with data, expect identical payload."""
        try:
            self.send("echo", data)
            frame = self.recv(timeout=timeout)
            return frame.get("cmd") == "echo" and frame.get("payload") == data
        except LinkError:
            return False

    def close(self) -> None:
        close = getattr(self._serial, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "SerialLink":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
