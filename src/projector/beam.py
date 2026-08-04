"""Projector beam — AAXA P6X pico projector, gutted for DC-in.

All hardware access is injected:

- ``lamp_fn(on: bool)``        -> drive the lamp power line
- ``fan_fn(on: bool)``         -> drive the cooling fan
- ``brightness_fn(level)``     -> set LED drive level, 0.0-1.0
- ``output_fn(frame)``         -> push a frame to the HDMI output (optional)
- ``timer_factory(delay, cb)`` -> returns an object with ``start()`` /
  ``cancel()`` (defaults to :class:`threading.Timer`); inject a fake in
  tests to control the 30 s cooldown deterministically.

Power-down policy: killing the lamp always starts a ``COOLDOWN_S`` fan
cooldown; the fan only stops when the timer fires. Calling :meth:`on`
during cooldown cancels the timer (fan keeps running for the relit lamp).
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

COOLDOWN_S = 30.0


class Beam:
    """Projector lamp/fan control, frame output, and camera mirroring."""

    def __init__(
        self,
        lamp_fn: Callable[[bool], None],
        fan_fn: Callable[[bool], None],
        brightness_fn: Optional[Callable[[float], None]] = None,
        output_fn: Optional[Callable[[Any], None]] = None,
        timer_factory: Callable[[float, Callable[[], None]], Any] = threading.Timer,
    ) -> None:
        for name, fn in (("lamp_fn", lamp_fn), ("fan_fn", fan_fn)):
            if not callable(fn):
                raise TypeError(f"{name} must be callable")
        self._lamp_fn = lamp_fn
        self._fan_fn = fan_fn
        self._brightness_fn = brightness_fn
        self._output_fn = output_fn
        self._timer_factory = timer_factory

        self.is_on = False
        self.brightness = 1.0
        self._cooldown_timer: Optional[Any] = None

    # -- properties -------------------------------------------------------

    @property
    def cooling_down(self) -> bool:
        """True while the fan cooldown timer is pending after lamp kill."""
        return self._cooldown_timer is not None

    # -- power ------------------------------------------------------------

    def on(self) -> None:
        """Light the lamp. Cancels any pending fan cooldown."""
        if self._cooldown_timer is not None:
            self._cooldown_timer.cancel()
            self._cooldown_timer = None
        self._fan_fn(True)
        self._lamp_fn(True)
        self.is_on = True

    def off(self) -> None:
        """Kill the lamp, then run the fan for COOLDOWN_S before stopping it."""
        self._lamp_fn(False)
        self.is_on = False
        if self._cooldown_timer is not None:
            self._cooldown_timer.cancel()
        timer = self._timer_factory(COOLDOWN_S, self._cooldown_done)
        self._cooldown_timer = timer
        timer.start()

    def _cooldown_done(self) -> None:
        self._cooldown_timer = None
        self._fan_fn(False)

    # -- output -------------------------------------------------------------

    def show(self, frame: Any) -> None:
        """Project a frame (image bytes, or a canned name like 'map')."""
        if not self.is_on:
            raise RuntimeError("projector lamp is off; call on() first")
        if self._output_fn is not None:
            self._output_fn(frame)

    def mirror_camera(self, camera: Any) -> bytes:
        """Snapshot an EyeCamera and project its live frame."""
        frame = camera.snapshot()
        self.show(frame)
        return frame

    # -- brightness ---------------------------------------------------------

    def set_brightness(self, level: float) -> float:
        """Set LED drive level, clamped to [0.0, 1.0]. Returns the clamped value."""
        level = max(0.0, min(1.0, float(level)))
        self.brightness = level
        if self._brightness_fn is not None:
            self._brightness_fn(level)
        return level
