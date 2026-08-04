"""R1-A1 motion subsystem.

All motion commands flow through an injected SerialLink-like object
exposing ``send(cmd, payload)`` (JSON-lines framed USB CDC link to the
real-time MCU, see docs/HARDWARE.md §1). Every class here is fully
hardware-mockable: pass a fake link in tests.
"""

from .drive import Drive, EstopTimeoutError
from .dome import Dome, DomeToleranceError
from .center_leg import CenterLeg
from .express import Express
from .refine import MovementRefiner

__all__ = [
    "Drive",
    "EstopTimeoutError",
    "Dome",
    "DomeToleranceError",
    "CenterLeg",
    "Express",
    "MovementRefiner",
]
