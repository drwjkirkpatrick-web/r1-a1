"""LLM client for the R1-A1 brain.

Talks to a local Ollama server via its /api/generate endpoint. The host is
agnostic (see docs/HARDWARE.md): anything serving Ollama's API works.

The HTTP layer is injectable: pass ``http_client`` (a callable taking
``(url, json_payload, timeout)`` and returning a dict-like response) to
mock the network in tests or swap transports on different hardware.

Efficiency notes
----------------
- The default transport reuses a single ``requests.Session`` so TCP/TLS
  connections to the LLM server are kept alive between turns — on a
  conversational robot this saves a connection handshake per utterance.
- ``generate()`` accepts ``keep_alive`` so callers can pin the model in
  RAM (Ollama ``keep_alive`` parameter) instead of letting it unload
  after the default idle window.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

DEFAULT_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"
DEFAULT_FALLBACK_MODEL = "gemma2:2b"
DEFAULT_TIMEOUT = 120.0
DEFAULT_KEEP_ALIVE = "30m"


class _SessionHttpClient:
    """Connection-reusing default transport (learning: one Session, many
    POSTs — the LLM server is localhost, so pooling is pure win)."""

    def __init__(self) -> None:
        import requests

        self._session = requests.Session()

    def __call__(self, url: str, payload: dict, timeout: float) -> dict:
        resp = self._session.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()


def _requests_http_client(url: str, payload: dict, timeout: float) -> dict:
    """Legacy one-shot transport (kept for backward compatibility)."""
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
        keep_alive: str = DEFAULT_KEEP_ALIVE,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.primary_model = model
        self.fallback_model = fallback_model
        self._active_model = model
        # Learning: default to the pooling session client; callers can
        # still inject any callable for tests or alternate transports.
        self.http_client = http_client or _SessionHttpClient()
        self.timeout = timeout
        self.keep_alive = keep_alive

    def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        keep_alive: Optional[str] = None,
    ) -> str:
        """Generate a completion for ``prompt``.

        Uses the active model unless ``model`` is given explicitly.
        ``keep_alive`` overrides how long Ollama keeps the model resident
        (e.g. ``"30m"``); pass ``"0"`` to force an unload after this call.
        Returns the response text from Ollama.
        """
        use_model = model or self._active_model
        payload = {
            "model": use_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive if keep_alive is not None else self.keep_alive,
        }
        result: dict[str, Any] = self.http_client(
            f"{self.base_url}/api/generate", payload, self.timeout
        )
        return result.get("response", "")

    def server_alive(self, timeout: float = 3.0) -> bool:
        """Cheap liveness probe against the Ollama server.

        Uses GET /api/tags (no inference, just model list) so it never
        perturbs the loaded model. Returns False on any error — a probe
        must never raise into a control loop.
        """
        try:
            import requests

            resp = requests.get(f"{self.base_url}/api/tags", timeout=timeout)
            return resp.status_code == 200
        except Exception:
            return False

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
