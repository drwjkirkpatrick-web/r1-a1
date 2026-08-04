"""Interconnect: JSON-lines framed serial protocol between the LLM host
and the real-time MCU (Teensy 4.1) over USB CDC at 115200 baud.

See docs/HARDWARE.md §1 (Real-time companion MCU) for the link spec.
"""

from .link import SerialLink, LinkError, LinkTimeout, LinkCRCError
from .selftest import run_selftest

__all__ = [
    "SerialLink",
    "LinkError",
    "LinkTimeout",
    "LinkCRCError",
    "run_selftest",
]
