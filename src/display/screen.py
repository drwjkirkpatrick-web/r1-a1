"""Front logic display — Waveshare 5" round LCD in the dome surround.

All panel access goes through an injected ``writer(frame: bytes)`` callable,
so the module is fully mockable. Frames are simple text rasters
(``WIDTH`` x ``HEIGHT`` characters, newline-joined, UTF-8 encoded); the real
writer blits them to the HDMI framebuffer, tests just record them.

``sleep_fn`` is injectable so scroll timing does not slow down tests.
"""

from __future__ import annotations

import time
from typing import Callable

WIDTH = 24
HEIGHT = 8

GLYPHS = {
    "smile": (
        "                        ",
        "   ####        ####     ",
        "  ######      ######    ",
        "   ####        ####     ",
        "                        ",
        "  #                #    ",
        "   ####      ####       ",
        "      ########          ",
    ),
    "neutral": (
        "                        ",
        "   ####        ####     ",
        "  ######      ######    ",
        "   ####        ####     ",
        "                        ",
        "                        ",
        "    ##############      ",
        "                        ",
    ),
    "alert": (
        "         !!!!           ",
        "         !!!!           ",
        "         !!!!           ",
        "         !!!!           ",
        "         !!!!           ",
        "                        ",
        "         !!!!           ",
        "                        ",
    ),
}

GAUGE_WIDTH = 20
SCROLL_STEP_DELAY_S = 0.08


class Screen:
    """Canned glyphs, gauges, scrolling text, and sleep/wake on the LCD."""

    def __init__(
        self,
        writer: Callable[[bytes], None],
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not callable(writer):
            raise TypeError("writer must be a callable accepting frame bytes")
        self._writer = writer
        self._sleep_fn = sleep_fn
        self.asleep = False
        self.last_frame: bytes = b""

    # -- internal helpers -------------------------------------------------

    @staticmethod
    def _encode(rows) -> bytes:
        if len(rows) != HEIGHT:
            raise ValueError(f"frame must have {HEIGHT} rows")
        return "\n".join(rows).encode("utf-8")

    def _emit(self, frame: bytes) -> None:
        self._writer(frame)
        self.last_frame = frame

    # -- public API ---------------------------------------------------------

    def show(self, name: str) -> None:
        """Display a canned glyph: 'smile', 'neutral', or 'alert'."""
        if name not in GLYPHS:
            raise ValueError(
                f"unknown glyph {name!r}; expected one of {sorted(GLYPHS)}"
            )
        self.asleep = False
        self._emit(self._encode(GLYPHS[name]))

    def gauge(self, pct: float) -> None:
        """Render a horizontal bar gauge for ``pct`` (clamped to 0-100)."""
        pct = max(0.0, min(100.0, float(pct)))
        filled = round(pct / 100.0 * GAUGE_WIDTH)
        bar = "#" * filled + "-" * (GAUGE_WIDTH - filled)
        label = f"{pct:5.1f}%"
        rows = [""] * HEIGHT
        rows[2] = "  [" + bar + "]"
        rows[3] = "  " + label
        rows = [r.ljust(WIDTH)[:WIDTH] for r in rows]
        self.asleep = False
        self._emit(self._encode(rows))

    def scroll_text(self, text: str) -> None:
        """Scroll ``text`` across the display, one frame per step."""
        if not text:
            raise ValueError("text must be non-empty")
        padded = " " * WIDTH + text + " " * WIDTH
        steps = len(padded) - WIDTH + 1
        self.asleep = False
        for i in range(steps):
            window = padded[i : i + WIDTH]
            rows = [""] * HEIGHT
            rows[HEIGHT // 2] = window
            rows = [r.ljust(WIDTH)[:WIDTH] for r in rows]
            self._emit(self._encode(rows))
            self._sleep_fn(SCROLL_STEP_DELAY_S)

    def sleep(self) -> None:
        """Blank the panel."""
        self.asleep = True
        self._emit(self._encode([" " * WIDTH] * HEIGHT))

    def wake(self) -> None:
        """Wake the panel back to the neutral glyph."""
        self.asleep = False
        self.show("neutral")
