"""Audio I/O for R1-A1: speaker output, astromech chirps, and mic array."""

from .speaker import Speaker
from .mic import MicArray

__all__ = ["Speaker", "MicArray"]
