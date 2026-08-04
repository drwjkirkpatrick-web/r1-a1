"""Dome eye camera — Arducam IMX477 behind the eye bezel.

All hardware access is injected so the module is fully mockable:

- ``capture_fn()``        -> raw frame bytes (JPEG/PNG) from the camera
- ``telemetry_fn()``      -> dict with at least ``exposure_us`` and ``gain``
- ``detector(frame)``     -> bool, True when a face is present in the frame

The vision-LLM client passed to :meth:`EyeCamera.caption` may be either a
callable ``(image_bytes, prompt) -> str`` or an object exposing
``caption(image_bytes, prompt) -> str`` (e.g. an OpenAI-compatible wrapper).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

DEFAULT_CAPTION_PROMPT = (
    "Describe in one short sentence what you see, from the robot's point of view."
)

# Calibration constant mapping (gain / exposure) to an approximate lux value.
# Tuned on the bench against a reference lux meter; see docs/HARDWARE.md §2.
_LUX_CALIBRATION = 250.0


class EyeCamera:
    """Primary dome eye: snapshot, caption, ambient light, face presence."""

    def __init__(
        self,
        capture_fn: Callable[[], bytes],
        telemetry_fn: Optional[Callable[[], dict]] = None,
        detector: Optional[Callable[[bytes], bool]] = None,
    ) -> None:
        if not callable(capture_fn):
            raise TypeError("capture_fn must be callable and return frame bytes")
        self._capture_fn = capture_fn
        self._telemetry_fn = telemetry_fn
        self._detector = detector

    def snapshot(self) -> bytes:
        """Capture a single frame and return it as encoded image bytes."""
        frame = self._capture_fn()
        if not isinstance(frame, (bytes, bytearray)):
            raise TypeError(
                f"capture_fn must return bytes, got {type(frame).__name__}"
            )
        return bytes(frame)

    def caption(self, vlm_client: Any, prompt: str = DEFAULT_CAPTION_PROMPT) -> str:
        """Snapshot the eye and ask a vision LLM to describe the scene.

        ``vlm_client`` is either a callable ``(image_bytes, prompt) -> str``
        or an object with a ``caption(image_bytes, prompt)`` method.
        """
        frame = self.snapshot()
        # Prefer a .caption(image, prompt) method when it yields a real
        # string; otherwise treat the client itself as a callable.
        # (Order matters for test doubles: a Mock with caption.return_value
        # set is a client object; a Mock(return_value=...) is a callable.)
        caption_fn = getattr(vlm_client, "caption", None)
        if callable(caption_fn):
            result = caption_fn(frame, prompt)
            if isinstance(result, str):
                return result
        if callable(vlm_client):
            return str(vlm_client(frame, prompt))
        raise TypeError(
            "vlm_client must be callable or expose a caption(image, prompt) method"
        )

    def ambient_lux(self) -> float:
        """Estimate ambient light (lux) from exposure telemetry.

        Uses ``telemetry_fn()`` which must return a dict containing
        ``exposure_us`` (shutter time in microseconds) and ``gain``
        (analog gain, >= 1.0). Brighter scenes need less exposure and gain,
        so lux scales with ``gain / exposure``.
        """
        if self._telemetry_fn is None:
            raise RuntimeError("no telemetry_fn injected; cannot read exposure")
        tele = self._telemetry_fn()
        exposure_us = float(tele["exposure_us"])
        gain = float(tele["gain"])
        if exposure_us <= 0:
            raise ValueError("exposure_us must be positive")
        # Normalise to a 1/30 s reference exposure at unity gain.
        reference_exposure_us = 1_000_000.0 / 30.0
        return _LUX_CALIBRATION * (reference_exposure_us / exposure_us) / gain

    def face_present(self) -> bool:
        """True when the injected detector finds a face in the current frame."""
        if self._detector is None:
            return False
        return bool(self._detector(self.snapshot()))
