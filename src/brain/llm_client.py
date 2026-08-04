"""LLM client for the R1-A1 brain.

Talks to a local Ollama server via its /api/generate endpoint. The host is
agnostic (see docs/HARDWARE.md): anything serving Ollama's API works.

The HTTP layer is injectable: pass ``http_client`` (a callable taking
``(url, json_payload, timeout)`` and returning a dict-like response) to
mock the network in tests or swap transports on different hardware.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_FALLBACK_MODEL = "gemma2:2b"
DEFAULT_TIMEOUT = 120.0


def _requests_http_client(url: str, payload: dict, timeout: float) -> dict:
    """Default HTTP transport using requests (only real dep beyond stdlib)."""
    import requests

    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


class LLMClient:
    """Thin client over Ollama's /api/generate with primary/fallback models."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        fallback_model: str = DEFAULT_FALLBACK_MODEL,
        http_client: Optional[Callable[[str, dict, float], dict]] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.primary_model = model
        self.fallback_model = fallback_model
        self._active_model = model
        self.http_client = http_client or _requests_http_client
        self.timeout = timeout

    def generate(self, prompt: str, model: Optional[str] = None) -> str:
        """Generate a completion for ``prompt``.

        Uses the active model unless ``model`` is given explicitly.
        Returns the response text from Ollama.
        """
        use_model = model or self._active_model
        payload = {
            "model": use_model,
            "prompt": prompt,
            "stream": False,
        }
        result: dict[str, Any] = self.http_client(
            f"{self.base_url}/api/generate", payload, self.timeout
        )
        return result.get("response", "")

    def current_model(self) -> str:
        """Return the tag of the currently active model."""
        return self._active_model

    def switch_to_fallback(self) -> str:
        """Switch generation to the small fallback model. Returns its tag."""
        self._active_model = self.fallback_model
        return self._active_model

    def switch_to_primary(self) -> str:
        """Switch generation back to the primary model. Returns its tag."""
        self._active_model = self.primary_model
        return self._active_model
