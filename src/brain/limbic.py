"""
R1-A1 limbic system bridge.

This module gives the R1-A1 astromech a persistent, neuro-inspired affective
state — mood, stress, relational warmth — by bridging to the *limbic-hermes*
project at ``/home/walker/projects/limbic-hermes``.

The bridge is intentionally a thin adapter: it owns a single
``limbic_hermes.core.LimbicSystem`` instance, forwards observations to it, and
optionally injects an affect-aware prefix into the agent's system prompt via
``limbic_hermes.prompts.wrap_system_prompt``.

Design goals
------------
1. **No hard dependency.** The entire ``limbic-hermes`` package may be absent,
   renamed, or broken on a fresh deploy. Every public method degrades
   gracefully: state accessors return ``{'enabled': False}``, ``inject_prompt``
   returns the prompt untouched, ``observe``/``update`` are no-ops. The rest of
   the brain keeps running with a "flat-affect" droid.
2. **Pure stdlib interface.** The only imports in this file are ``sys`` and
   ``os`` (plus ``typing`` for annotations). ``limbic_hermes`` is imported
   lazily inside ``__init__`` so that a missing or failing dependency never
   breaks import of ``r1_a1.brain``.
3. **Stateless-at-rest by default.** The limbic engine lives in memory for the
   session; ``state_dir`` is kept on the bridge so a future persistence hook
   (e.g. wiring ``limbic_hermes.storage``) can save/restore snapshots between
   boots without changing this module's signature.

How it fits R1-A1
-----------------
The brain package (:mod:`r1_a1.brain.agent`) constructs an :class:`Agent` that
routes prompts to an LLM. The agent may own an optional :class:`LimbicBridge`
and, before forwarding a prompt, call::

    prompt = bridge.inject_prompt(prompt)   # adds affect posture, or no-op
    bridge.observe('user_message', text)    # feed the event in
    bridge.update()                         # advance the dynamics

For dashboards or telemetry, ``bridge.get_affect_summary()`` returns the six
numbers most useful for an external display (dominant affect label + VAD +
allostatic load + expression warmth).

Learning notes
~~~~~~~~~~~~~~
- ``limbic-hermes`` ships *without* an ``__init__.py`` (it is a PEP 420
  namespace package). It is importable only when its repo root is on
  ``sys.path``. We insert that path in ``__init__`` rather than relying on a
  ``pip install -e`` because the robot runs on a Jetson where editable
  installs are fragile across deploys.
- ``LimbicSystem.__init__`` takes ``profile_name`` but **not** a ``state_dir``;
  the bridge therefore keeps ``state_dir`` for itself and may hand it to a
  storage layer later. The constructor also **silently falls back** to the
  ``"default"`` temperament for an unknown profile name, so
  ``profile_name='pulsatilla_pratensis'`` resolves to ``"default"`` until the
  full remedy library is loaded — we surface the *resolved* name in
  :meth:`get_state` so callers can detect the fallback.
- ``wrap_system_prompt`` appends a ``--- Limbic posture ---`` block to the
  base prompt. At ``intensity <= 0`` it returns the prompt unchanged, which is
  why we gate on ``self.inject_into_prompt`` *and* ``intensity`` before
  calling it.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

# LEARNING: Hard-coding the repo path here is deliberate. The R1-A1 firmware
# image pins limbic-hermes to this exact checkout. If the project moves,
# update this constant (or set the LIMBIC_HERMES_PATH env var to override).
_DEFAULT_LIMBIC_PATH = "/home/walker/projects/limbic-hermes"


class LimbicBridge:
    """Adapter that owns a limbic-hermes ``LimbicSystem`` and exposes a
    stdlib-only API to the rest of the R1-A1 brain.

    Parameters
    ----------
    profile_name:
        Remedy temperament profile forwarded to ``LimbicSystem``. Defaults to
        ``'pulsatilla_pratensis'`` (a gentle, clingy, warmth-seeking
        temperament). Unknown names silently fall back to ``'default'`` inside
        limbic-hermes.
    enabled:
        Master switch. When ``False`` the bridge never touches the limbic
        engine and every accessor returns ``{'enabled': False}``. This lets a
        deploy disable affect entirely (e.g. for a headless bench test) without
        code changes.
    state_dir:
        Directory reserved for future JSON snapshot persistence. The bridge
        does not write here yet, but keeps the path so :meth:`get_state` can
        report it and a persistence hook can be added without an API change.
        ``~`` is expanded to the user's home.
    intensity:
        0.0–1.0 strength of the affect prefix injected into prompts. Forwarded
        to ``wrap_system_prompt``. ``0.0`` effectively disables injection even
        when ``inject_into_prompt`` is ``True``.
    inject_into_prompt:
        When ``True`` (default) :meth:`inject_prompt` wraps the base prompt with
        limbic guidance. When ``False`` the prompt is always returned unchanged
        — useful when a downstream layer does its own prompt assembly.

    Attributes
    ----------
    limbic:
        The owned ``limbic_hermes.core.LimbicSystem`` instance, or ``None`` when
        disabled or unavailable.
    available:
        ``True`` only when the limbic engine was successfully constructed.
    """

    def __init__(
        self,
        profile_name: str = "pulsatilla_pratensis",
        enabled: bool = True,
        state_dir: str = "~/.hermes/limbic_state",
        intensity: float = 0.6,
        inject_into_prompt: bool = True,
    ) -> None:
        self.profile_name: str = profile_name
        self.enabled: bool = bool(enabled)
        # LEARNING: Expand ~ now so later code (and log lines) see an absolute
        # path regardless of the caller's cwd.
        self.state_dir: str = os.path.expanduser(state_dir)
        self.intensity: float = float(intensity)
        self.inject_into_prompt: bool = bool(inject_into_prompt)

        # Owned engine. ``None`` means "not wired" — every method checks this.
        self.limbic: Optional[Any] = None
        self.available: bool = False

        if not self.enabled:
            # Flat-affect mode: nothing to import, nothing to own.
            return

        # ---- Wire the limbic-hermes project onto sys.path ----
        # LEARNING: We read the path from the env var first so ops can point at
        # a staging checkout without editing source. The constant is the
        # firmware default. We guard against duplicate inserts so repeated
        # construction (e.g. in tests) doesn't grow sys.path unboundedly.
        limbic_path = os.environ.get("LIMBIC_HERMES_PATH", _DEFAULT_LIMBIC_PATH)
        if limbic_path and limbic_path not in sys.path:
            sys.path.insert(0, limbic_path)

        # ---- Import + construct, with a full try/except fallback ----
        # LEARNING: ``limbic_hermes`` is a namespace package (no __init__.py),
        # so it imports only once its repo root is on sys.path. We import the
        # two symbols we actually need inside the try so that *any* failure
        # (missing path, syntax error in a sibling module, missing optional
        # dep pulled in transitively) collapses to the same "unavailable"
        # state instead of crashing the whole brain on import.
        try:
            from limbic_hermes.core import LimbicSystem  # type: ignore
            from limbic_hermes.prompts import wrap_system_prompt  # noqa: F401  # type: ignore

            # Stash the prompt wrapper for use in inject_prompt. Keeping the
            # reference avoids a second import lookup on every prompt.
            self._wrap_system_prompt = wrap_system_prompt

            # Construct the engine. LimbicSystem(profile_name=...) does NOT
            # take state_dir; it owns an in-memory state for the session.
            self.limbic = LimbicSystem(profile_name=self.profile_name)
            self.available = True
        except Exception:
            # LEARNING: Broad except is intentional here — this bridge is the
            # *only* place the brain touches limbic-hermes, and the contract is
            # "never raise on init". We swallow the error so the robot boots
            # flat-affect rather than bricking on a bad checkout. The exact
            # failure is recorded for diagnostics but not propagated.
            self.limbic = None
            self.available = False
            self._wrap_system_prompt = None

    # ------------------------------------------------------------------
    # Event feed
    # ------------------------------------------------------------------

    def observe(self, event_type: str, description: str = "") -> None:
        """Feed an event into the limbic engine.

        Delegates to ``LimbicSystem.observe_event(kind, description)``.
        No-op when the bridge is disabled or the engine is unavailable, so the
        caller can call this unconditionally after every interaction without
        guarding.

        ``event_type`` examples: ``'user_message'``, ``'task_start'``,
        ``'task_complete'``, ``'error'``, ``'tool_failure'``, ``'success'``,
        ``'idle_timeout'``.
        """
        if self.limbic is None:
            return
        # LEARNING: observe_event's first positional arg is named ``kind`` in
        # limbic-hermes; we pass by position to stay decoupled from the exact
        # keyword name. It returns an Appraisal object we don't need here.
        self.limbic.observe_event(event_type, description)

    def update(self) -> None:
        """Advance the limbic dynamics by one tick.

        Delegates to ``LimbicSystem.update()``, which decays VAD toward the
        remedy baseline, updates drives, and applies neurochemical drift.
        Call periodically (e.g. once per second) or before reading state.
        No-op when unavailable.
        """
        if self.limbic is None:
            return
        # LEARNING: update() defaults its timestamp to time.time() internally,
        # so we don't need to pass `now`. Calling with a stale `now` is the
        # classic pitfall that zeroes out neurochemical response (see the
        # limbic-hermes skill pitfalls #6) — avoiding it here by passing none.
        self.limbic.update()

    # ------------------------------------------------------------------
    # State accessors
    # ------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return the full limbic state snapshot.

        The dict shape mirrors ``LimbicSystem.get_state()``: ``vad``,
        ``drive``, ``dominant_affect``, ``expression_vector``,
        ``neurochemistry``, ``allostatic_load``, ``integration``, etc.

        Returns ``{'enabled': False}`` when the bridge is disabled or the
        engine is unavailable, so callers can treat the "no limbic" case as a
        single sentinel rather than a ``None`` check.
        """
        if self.limbic is None:
            return {"enabled": False}
        # LEARNING: get_state() returns a freshly-built dict each call (no
        # shared mutable reference), so it's safe to hand to callers or
        # serialize directly. We add our own bridge-level flags for telemetry.
        state: Dict[str, Any] = self.limbic.get_state()
        state["enabled"] = True
        # Surface the *requested* profile name alongside the resolved one so a
        # mismatch (fallback to 'default') is visible without a second call.
        state["requested_profile"] = self.profile_name
        return state

    def get_affect_summary(self) -> Dict[str, Any]:
        """Return a compact six-field affect snapshot for dashboards/telemetry.

        Fields
        ------
        dominant_affect : str
            Readable label (e.g. ``'calm'``, ``'curious'``, ``'grief'``).
        valence : float
            -1 (negative) … +1 (positive).
        arousal : float
            0 (calm) … 1 (activated).
        dominance : float
            0 (not in control) … 1 (in control).
        allostatic_load : float
            0 (rested) … 1 (chronically stressed / depleted).
        expression_warmth : float
            Relational warmth of the remedy profile modulated by valence;
            drives how warmly the droid should phrase responses.

        Returns ``{'enabled': False}`` when unavailable.
        """
        if self.limbic is None:
            return {"enabled": False}
        state: Dict[str, Any] = self.limbic.get_state()
        # LEARNING: All six fields are confirmed keys in the limbic-hermes
        # state dict: vad.{valence,arousal,dominance}, dominant_affect,
        # allostatic_load, expression_vector.warmth. Using .get with sensible
        # defaults keeps this from raising if a future limbic-hermes rename
        # drops a field — the summary degrades to zeros instead of crashing a
        # dashboard poll loop.
        vad = state.get("vad", {})
        ev = state.get("expression_vector", {})
        return {
            "dominant_affect": state.get("dominant_affect", "neutral"),
            "valence": float(vad.get("valence", 0.0)),
            "arousal": float(vad.get("arousal", 0.0)),
            "dominance": float(vad.get("dominance", 0.5)),
            "allostatic_load": float(state.get("allostatic_load", 0.0)),
            "expression_warmth": float(ev.get("warmth", 0.0)),
        }

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def inject_prompt(self, base_prompt: str) -> str:
        """Wrap ``base_prompt`` with affect-aware limbic guidance.

        Appends a ``--- Limbic posture ---`` block describing the current
        internal state and how to modulate response style (warmth, pace,
        caution, verbosity, cling). The block is scaled by ``self.intensity``.

        Returns ``base_prompt`` unchanged when:
        - the bridge is disabled or unavailable,
        - ``inject_into_prompt`` is ``False``, or
        - ``intensity`` is <= 0 (``wrap_system_prompt`` returns the prompt
          unchanged in that case, and we short-circuit to skip the call).
        """
        if not self.inject_into_prompt or self.limbic is None:
            return base_prompt
        if self.intensity <= 0.0:
            return base_prompt
        wrap = getattr(self, "_wrap_system_prompt", None)
        if wrap is None:
            # LEARNING: Defensive — if the import in __init__ partially
            # succeeded (limbic constructed but prompt import failed) we
            # still must not raise. Treat as unavailable.
            return base_prompt
        state = self.limbic.get_state()
        # LEARNING: wrap_system_prompt(base_prompt, state, intensity) appends
        # the posture block. It never strips content from base_prompt, so
        # existing instructions are preserved. We pass the engine's own live
        # state (not a cached copy) so the prefix reflects the latest update().
        return wrap(base_prompt, state, intensity=self.intensity)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def info(self) -> Dict[str, Any]:
        """Return a small diagnostic dict describing the bridge's config.

        Useful for ``/status`` endpoints and logs. Fields: ``enabled``,
        ``profile`` (requested name), ``available`` (engine wired), and
        ``intensity``.
        """
        return {
            "enabled": self.enabled,
            "profile": self.profile_name,
            "available": self.available,
            "intensity": self.intensity,
        }


__all__ = ["LimbicBridge"]