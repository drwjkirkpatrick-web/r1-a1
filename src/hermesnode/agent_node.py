"""Client for the R1-A1 dome Hermes agent node.

The Hermes node is a hidden second Jetson Nano in the dome, mounted beside
the vision node. It hosts the Hermes agent layer — personality (remedy
selection), limbic state (affective profiles), and short-term orchestration
— and speaks to the main brain host over the dome's gigabit slip-ring.

Keeping this layer on its own board means the main LLM host's RAM, memory
bandwidth, and thermal budget stay dedicated to inference; the agent-layer
traffic is small JSON exchanged with a networked peer instead of in-process
work competing with token generation.

Endpoints exposed by the node:

- ``GET  /health``       -> ``{'ok': True, 'node_id': ..., 'uptime_s': ...}``
- ``GET  /state``        -> ``dict`` of current agent state
- ``POST /prompt``       ``{'text': str}`` -> ``{'reply': str}``
- ``POST /personality``  ``{'remedy': str}`` -> ``{'remedy': ..., 'emoji': ...}``
- ``POST /limbic``       ``{'profile': str}`` -> ``{'profile': ..., 'vad': {...}}``

The HTTP transport is injectable: pass ``http_client`` (a callable taking
``(method, url, json_payload, timeout)`` and returning the decoded JSON
dict — like ``requests.request(...).json()``) to mock the network in tests
or swap transports on different hardware. Without one, ``requests`` is
imported lazily on first use so the module stays import-clean on stdlib
alone.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:9299"
DEFAULT_NODE_ID = "dome-hermes-01"
DEFAULT_TIMEOUT = 5.0

HttpClient = Callable[[str, str, Optional[dict], float], dict]


class HermesNodeError(RuntimeError):
    """Raised when the Hermes agent node is unreachable or returns an error."""


def _requests_http_client(
    method: str, url: str, json_payload: Optional[dict], timeout: float
) -> dict:
    """Default HTTP transport using requests (only real dep beyond stdlib).

    Imported lazily: keeping the import inside the function means this module
    (and anything importing it) loads fine on a stdlib-only install, e.g. on
    the main brain host where requests may not be present yet.
    """
    import requests

    resp = requests.request(method, url, json=json_payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


class HermesNode:
    """Client for the dome's Hermes agent node (hidden second Jetson Nano).

    All network failures (connect errors, timeouts, bad HTTP status, broken
    JSON) are normalised into :class:`HermesNodeError` with a message naming
    the endpoint, so callers never need to know which transport is in use.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        node_id: str = DEFAULT_NODE_ID,
        timeout: float = DEFAULT_TIMEOUT,
        http_client: Optional[HttpClient] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.node_id = node_id
        self.timeout = timeout
        self.http_client = http_client or _requests_http_client
        # Injected clock (time.monotonic by default) so tests can control
        # time deterministically — the same pattern used by power/thermal.
        self._clock = clock
        self._last_contact_s: Optional[float] = None

    @property
    def last_contact_s(self) -> Optional[float]:
        """Clock value of the last successful call, or None before the first."""
        return self._last_contact_s

    def _call(
        self, method: str, path: str, payload: Optional[dict] = None
    ) -> dict:
        """Perform one HTTP round-trip, normalising failures to HermesNodeError.

        ``last_contact_s`` is only stamped *after* a successful response —
        a failed call must not make the node look recently alive.
        """
        url = f"{self.base_url}{path}"
        try:
            result = self.http_client(method, url, payload, self.timeout)
        except HermesNodeError:
            raise
        except Exception as exc:  # connect error, timeout, bad status, ...
            raise HermesNodeError(
                f"Hermes node {self.node_id} {method} {path} failed: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise HermesNodeError(
                f"Hermes node {self.node_id} {method} {path} returned "
                f"non-dict response: {result!r}"
            )
        self._last_contact_s = self._clock()
        return result

    def health(self) -> dict:
        """GET /health — raise HermesNodeError if the node is not healthy."""
        result = self._call("GET", "/health")
        if not result.get("ok"):
            raise HermesNodeError(
                f"Hermes node {self.node_id} reports unhealthy: {result}"
            )
        return result

    def state(self) -> dict:
        """GET /state — the node's current agent state as a dict."""
        return self._call("GET", "/state")

    def ask(self, text: str) -> str:
        """POST /prompt — send ``text`` to the agent, return its reply string."""
        result = self._call("POST", "/prompt", {"text": text})
        reply = result.get("reply")
        if not isinstance(reply, str):
            raise HermesNodeError(
                f"Hermes node {self.node_id} /prompt missing 'reply': {result}"
            )
        return reply

    def set_personality(self, remedy: str) -> dict:
        """POST /personality — select a remedy, returns {'remedy', 'emoji'}."""
        return self._call("POST", "/personality", {"remedy": remedy})

    def set_limbic(self, profile: str) -> dict:
        """POST /limbic — select an affective profile, returns {'profile', 'vad'}."""
        return self._call("POST", "/limbic", {"profile": profile})

    def is_alive(self) -> bool:
        """Health check that never raises: True if the node answered healthy."""
        try:
            self.health()
            return True
        except HermesNodeError:
            return False
