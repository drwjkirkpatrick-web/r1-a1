"""Eye subsystem: dome camera (IMX477) and wink effector (LED + shutter servo)."""

from .camera import EyeCamera
from .wink import Wink

__all__ = ["EyeCamera", "Wink"]
