"""LLM keep-alive / warm-model management for the R1-A1 brain.

Why this exists on a robot
--------------------------
Ollama unloads models from RAM after an idle period (default ~5 min).
On an astromech droid that is *mostly quiet*, the first question after a
lull would hit a cold model: a large LLM can take many seconds to page
back in, and the droid just stands there, silent, mid-conversation. A
multi-second stall before speech is exactly the kind of latency that
makes a robot feel broken instead of alive.

KeepAlive solves two related problems:

1. **Warmth** — it periodically sends a trivial ``'ping'`` generation so
   the active model never goes idle long enough to be evicted.
2. **Liveness + graceful degradation** — it counts consecutive ping
   failures. When the primary model (or the Ollama server itself) stops
   responding, it switches the client to the small fallback model so the
   droid keeps talking (a little dumber) instead of freezing.

Design notes (learning annotations)
-----------------------------------
* **Tick-driven, no threads.** This is a pure policy object. The operator
  loop calls :meth:`tick` whenever it likes; KeepAlive decides whether a
  ping is due. Threads would make tests racy and reasoning about failure
  counting much harder — injected ``clock``/``sleeper`` callables keep
  everything deterministic and mockable (the same convention the rest of
  the codebase uses for hardware).
* **Duck-typed client.** Anything with ``generate(prompt, model=...)``,
  ``current_model()``, ``switch_to_fallback()`` and
  ``switch_to_primary()`` works. ``base_url`` / ``fallback_model`` /
  ``primary_model`` attributes are optional and probed with ``getattr``.
* **Failure accounting is shared** between :meth:`ping` and
  :meth:`generate`: a successful real generation is just as good evidence
  of life as a ping, so both reset the counter.

Typical wiring::

    keepalive = KeepAlive(llm_client, ping_interval_s=30.0)
    while True:                      # operator loop
        status = keepalive.tick()
        ...
        reply = keepalive.generate(prompt)   # instead of llm.generate
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

PING_PROMPT = "ping"


class KeepAlive:
    """Keep an Ollama model warm and auto-fallback when it goes quiet.

    Parameters
    ----------
    llm:
        The LLM client to wrap (see :class:`src.brain.llm_client.LLMClient`
        for the reference implementation). Duck-typed — only the methods
        listed in the module docstring are required.
    ping_interval_s:
        Minimum seconds between pings. :meth:`tick` pings at most this
        often, no matter how frequently it is called.
    ping_timeout_s:
        Advisory timeout for ping generations. Stored for callers that
        surface it in status UIs; the wrapped client's own timeout governs
        the actual HTTP call.
    max_consecutive_failures:
        How many consecutive failures trigger an automatic switch to the
        fallback model.
    clock, sleeper:
        Injected time functions (``time.monotonic`` / ``time.sleep`` by
        default) so tests can control time without real waiting.
    """

    def __init__(
        self,
        llm: Any,
        ping_interval_s: float = 30.0,
        ping_timeout_s: float = 3.0,
        max_consecutive_failures: int = 2,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.llm = llm
        self.ping_interval_s = ping_interval_s
        self.ping_timeout_s = ping_timeout_s
        self.max_consecutive_failures = max_consecutive_failures
        self.clock = clock
        self.sleeper = sleeper

        self.consecutive_failures = 0
        self.last_ok_s: Optional[float] = None
        # None means "never pinged" — the first tick always pings.
        self.last_ping_s: Optional[float] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------
    @property
    def alive(self) -> bool:
        """True while the last observed interaction succeeded."""
        return self.consecutive_failures == 0

    @property
    def using_fallback(self) -> bool:
        """True if the client is currently on its small fallback model."""
        fallback = getattr(self.llm, "fallback_model", None)
        if fallback is None:
            return False
        return self.llm.current_model() == fallback

    # ------------------------------------------------------------------
    # Core behaviour
    # ------------------------------------------------------------------
    def ping(self) -> bool:
        """Send a trivial generation to keep the model warm.

        Returns True when a non-empty string comes back, False on any
        exception or empty reply. Updates ``consecutive_failures`` and
        ``last_ok_s`` either way, and records ``last_ping_s`` so
        :meth:`tick` knows when the next ping is due.
        """
        self.last_ping_s = self.clock()
        try:
            reply = self.llm.generate(PING_PROMPT, model=self.llm.current_model())
        except Exception:
            self._record_failure()
            return False
        if isinstance(reply, str) and reply:
            self._record_success()
            return True
        # Empty/odd replies are treated as failures: a server that answers
        # with nothing is not keeping the model meaningfully warm.
        self._record_failure()
        return False

    def tick(self) -> Dict[str, Any]:
        """Advance the keep-alive policy one step.

        Pings if the interval has elapsed (or if we have never pinged),
        then switches to the fallback model when failures have piled up
        while still on the primary. Returns a status dict suitable for
        dashboards/logging.
        """
        now = self.clock()
        if self.last_ping_s is None or (now - self.last_ping_s) >= self.ping_interval_s:
            self.ping()

        auto_fallback = False
        if (
            self.consecutive_failures >= self.max_consecutive_failures
            and self._on_primary_model()
        ):
            self.llm.switch_to_fallback()
            auto_fallback = True

        return {
            "alive": self.alive,
            "model": self.llm.current_model(),
            "consecutive_failures": self.consecutive_failures,
            "auto_fallback": auto_fallback,
            "last_ok_s": self.last_ok_s,
        }

    def generate(self, prompt: str) -> str:
        """Pass-through to ``llm.generate`` with failure accounting.

        A successful generation is evidence of life, so it resets the
        failure counter (and refreshes ``last_ok_s``). A failure is
        counted and then re-raised — the caller still needs to know the
        generation itself failed.
        """
        try:
            reply = self.llm.generate(prompt, model=self.llm.current_model())
        except Exception:
            self._record_failure()
            raise
        self._record_success()
        return reply

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _record_success(self) -> None:
        self.consecutive_failures = 0
        self.last_ok_s = self.clock()

    def _record_failure(self) -> None:
        self.consecutive_failures += 1

    def _on_primary_model(self) -> bool:
        """Best-effort check: is the client still on its primary model?"""
        primary = getattr(self.llm, "primary_model", None)
        if primary is not None:
            return self.llm.current_model() == primary
        # Without a primary_model attribute, fall back to "not already on
        # the fallback" so we don't switch twice.
        return not self.using_fallback
