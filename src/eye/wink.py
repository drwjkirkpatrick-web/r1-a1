"""Wink effector — 3W RGB eye LED (PWM) plus shutter servo, via the MCU link.

The injected ``link`` is the host↔MCU JSON-lines channel (see
docs/HARDWARE.md §3). It may be a callable ``link(command_dict)`` or an
object exposing ``send(command_dict)``. Every wink issues, in order:

1. PWM  — eye LED on (full duty)
2. SERVO — shutter closed
3. SERVO — shutter open
4. PWM  — eye LED off
"""

from __future__ import annotations

from typing import Any, Callable, Union

# MCU channel map (docs/HARDWARE.md §3: PWM ch0-7 -> eye LED, servos).
EYE_LED_PWM_CHANNEL = 2
SHUTTER_SERVO_CHANNEL = 3

LED_ON_DUTY = 1.0
LED_OFF_DUTY = 0.0
SHUTTER_CLOSED_DEG = 90
SHUTTER_OPEN_DEG = 0

Link = Union[Callable[[dict], Any], Any]


class Wink:
    """Blink the eye LED while cycling the shutter servo."""

    def __init__(self, link: Link) -> None:
        if not callable(link) and not hasattr(link, "send"):
            raise TypeError("link must be callable or expose a send(command) method")
        self._link = link

    def _send(self, command: dict) -> None:
        if callable(self._link):
            self._link(command)
        else:
            self._link.send(command)

    def wink(self, count: int = 1) -> None:
        """Perform ``count`` winks (LED flash + shutter cycle each)."""
        if count < 1:
            raise ValueError("count must be >= 1")
        for _ in range(count):
            self._send(
                {
                    "cmd": "pwm",
                    "channel": EYE_LED_PWM_CHANNEL,
                    "duty": LED_ON_DUTY,
                }
            )
            self._send(
                {
                    "cmd": "servo",
                    "channel": SHUTTER_SERVO_CHANNEL,
                    "position_deg": SHUTTER_CLOSED_DEG,
                }
            )
            self._send(
                {
                    "cmd": "servo",
                    "channel": SHUTTER_SERVO_CHANNEL,
                    "position_deg": SHUTTER_OPEN_DEG,
                }
            )
            self._send(
                {
                    "cmd": "pwm",
                    "channel": EYE_LED_PWM_CHANNEL,
                    "duty": LED_OFF_DUTY,
                }
            )
