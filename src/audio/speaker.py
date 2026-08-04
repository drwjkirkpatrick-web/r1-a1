"""Speaker: speech output, canned astromech chirps, and mute control.

All audio output is via injected callables so the module is fully
mockable:
    - say(text, voice_fn): voice_fn(text) is called with the utterance
      unless the speaker is muted.
    - chirp(mood): looks up the canned beep pattern for the mood and
      plays it via the optional beep_fn(pattern) injected at
      construction. Returns the pattern either way.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

# Canned astromech beep patterns: list of (freq_hz, duration_s) pairs.
CHIRPS = {
    "happy":    [(880, 0.10), (1175, 0.10), (1568, 0.15), (1175, 0.08)],
    "sad":      [(660, 0.20), (494, 0.20), (392, 0.35)],
    "alert":    [(1568, 0.08), (1568, 0.08), (1568, 0.08), (2093, 0.20)],
    "confused": [(880, 0.10), (698, 0.10), (880, 0.10), (587, 0.18)],
}


class Speaker:
    def __init__(self, beep_fn: Optional[Callable[[list], None]] = None) -> None:
        self._beep_fn = beep_fn
        self._muted_until: float = 0.0  # monotonic timestamp

    # ------------------------------------------------------------------
    # Speech
    # ------------------------------------------------------------------
    def say(self, text: str, voice_fn: Callable[[str], object]):
        """Speak `text` via the injected voice_fn. Returns voice_fn's
        result, or None if muted (voice_fn is not called when muted)."""
        if self.is_muted():
            return None
        return voice_fn(text)

    # ------------------------------------------------------------------
    # Chirps
    # ------------------------------------------------------------------
    def chirp(self, mood: str) -> list:
        """Play a canned astromech chirp for `mood` ('happy', 'sad',
        'alert', 'confused'). Returns the (freq, duration) pattern.
        Raises ValueError for unknown moods. Suppressed while muted
        (returns the pattern but does not call beep_fn)."""
        if mood not in CHIRPS:
            raise ValueError(
                f"unknown chirp mood {mood!r}; expected one of {sorted(CHIRPS)}"
            )
        pattern = CHIRPS[mood]
        if not self.is_muted() and self._beep_fn is not None:
            self._beep_fn(pattern)
        return pattern

    # ------------------------------------------------------------------
    # Mute
    # ------------------------------------------------------------------
    def mute_until(self, seconds: float) -> None:
        """Mute the speaker for `seconds` seconds from now."""
        self._muted_until = time.monotonic() + float(seconds)

    def unmute(self) -> None:
        """Cancel any active mute."""
        self._muted_until = 0.0

    def is_muted(self) -> bool:
        """True while the mute window is active."""
        return time.monotonic() < self._muted_until
