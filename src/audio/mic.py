"""MicArray: ReSpeaker USB 4-mic array capture and direction-of-arrival.

All hardware access is via injected callables:
    capture_fn(timeout) -> audio frame (bytes/list), or None on timeout.
    doa_fn()            -> raw direction-of-arrival estimate in degrees;
                           the returned value is clamped/normalized into
                           [0, 360) before being reported.
"""

from __future__ import annotations

from typing import Callable, Optional


def _clamp_degrees(angle: float) -> float:
    """Normalize any angle to the [0, 360) range."""
    return float(angle) % 360.0


class MicArray:
    def __init__(
        self,
        capture_fn: Callable[[float], object],
        doa_fn: Optional[Callable[[], float]] = None,
    ) -> None:
        self._capture_fn = capture_fn
        self._doa_fn = doa_fn
        self.last_audio = None

    def listen(self, timeout: float = 5.0):
        """Capture audio for up to `timeout` seconds via the injected
        capture_fn. Returns the audio frame, or None on timeout."""
        self.last_audio = self._capture_fn(timeout)
        return self.last_audio

    def doa(self) -> float:
        """Direction of arrival in degrees, normalized to [0, 360).

        Uses the injected doa_fn; returns 0.0 when no estimator is
        wired (e.g. single-channel capture with no beamforming)."""
        if self._doa_fn is None:
            return 0.0
        return _clamp_degrees(float(self._doa_fn()))
