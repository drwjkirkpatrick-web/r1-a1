"""R1-A1 remedy personality bridge.

This module bridges the R1-A1 robot brain to the Hermes
``remedy_personality_picker`` skill, which maintains a curated catalogue of
100 homeopathic *remedy personalities* — each a short system-prompt modifier
that nudges an LLM toward a distinct working style (e.g. ``arsenicum_album``
= meticulous perfectionist, ``pulsatilla_pratensis`` = empathetic adapter).

The personality data lives outside this repo, in the skill's scripts
directory::

    /home/walker/.hermes/skills/remedy_personality_picker/scripts/session_personality.py

That module defines ``PERSONALITY_PROMPTS``: a ``dict[str, str]`` keyed by
snake_case remedy name (``"bryonia_alba"``, ``"pulsatilla_pratensis"``,
``"arsenicum_album"``, ...). Each value is a one-line prompt prefix such as
``"You are meticulous, precise, and thorough. ..."``.

Design goals
------------
* **Optional dependency.** The skill may not be installed on every robot
  image. The bridge must import cleanly with *no* external deps and degrade
  to ``None`` when the skill is absent — the robot keeps working, just
  without a flavoured personality.
* **No I/O at import time beyond the one import.** We insert the skill
  scripts dir onto ``sys.path`` and attempt to import
  ``session_personality``. Any failure (missing path, syntax error,
  ``ImportError``) is swallowed so the rest of the brain still boots.
* **Emoji always available.** ``get_emoji()`` is backed by a *hardcoded*
  ``EMOJI_MAP`` so a recognisable glyph is returned even when the skill is
  gone — useful for status displays and logs.
* **Pure stdlib.** Only ``sys``, ``os`` and ``typing`` are used, matching the
  project's "pure stdlib where possible" convention.

Typical use
-----------
::

    from r1_a1.brain.personality import PersonalityBridge

    bridge = PersonalityBridge("arsenicum_album")
    prefix = bridge.get_prompt_prefix()  # the meticulous prompt, or None
    emoji = bridge.get_emoji()            # "🧐"
    system = (prefix + "\\n\\n") if prefix else ""
    reply = llm.generate(system + user_prompt)

If the operator disables personalities at runtime, pass ``enabled=False`` and
every accessor collapses to a neutral default — no code paths change.
"""

# Learning annotation: ``from __future__ import annotations`` makes all type
# hints *strings* until they are explicitly resolved (PEP 563). It lets us
# write ``Optional[str]`` and forward references without importing
# ``annotations`` machinery, and keeps the file importable on older Pythons
# that otherwise could not parse newer hint syntax. The sibling ``agent.py``
# uses the same convention.
from __future__ import annotations

# Learning annotation: we keep imports to the standard library only.
# ``sys`` lets us temporarily extend ``sys.path`` so the skill's scripts dir
# becomes importable; ``os`` is used purely to guard the path insertion when
# the directory does not exist (avoids a confusing import attempt); the
# typing import is optional under ``from __future__ import annotations`` but
# kept for clarity and for runtime ``Optional`` use in ``__init__`` defaults.
import os
import sys
from typing import Optional

# Learning annotation: the skill ships its personality prompts in this
# standalone script. We resolve the path once at module load so every
# ``PersonalityBridge`` instance shares it. Hard-coding the absolute path is
# deliberate: the skill is a per-user Hermes install and is not on the
# robot's normal ``PYTHONPATH``. If the path ever moves, only this constant
# changes.
_SKILL_SCRIPTS_DIR = (
    "/home/walker/.hermes/skills/remedy_personality_picker/scripts"
)

# Learning annotation: a module-level cache of the imported dict. We import
# lazily inside ``PersonalityBridge.__init__`` (so a missing skill never
# breaks *importing* this module) but cache the result here so the
# (slightly costly) path manipulation + import runs at most once per
# process. ``None`` is the sentinel meaning "not yet attempted"; an empty
# dict means "attempted and unavailable".
_PERSONALITY_PROMPTS: Optional[dict] = None
_IMPORT_ATTEMPTED = False


def _load_personality_prompts() -> dict:
    """Import the skill's ``PERSONALITY_PROMPTS`` dict, or return ``{}``.

    This is the single chokepoint for the optional dependency. It is safe to
    call repeatedly: after the first attempt it returns the cached result.

    Learning annotation: we mutate ``sys.path`` *then* import. The order
    matters — Python's import system searches ``sys.path`` entries in order,
    so inserting at index 0 makes the skill dir win over any same-named
    module elsewhere on the path. We deliberately do *not* restore
    ``sys.path`` afterwards: the skill's own ``session_personality`` module
    performs a similar insert for its ``personality_engine`` dependency, and
    leaving our entry in place keeps a second ``import session_personality``
    (e.g. by ``list_remedies``) cheap.
    """
    # Learning annotation: ``global`` is required because we *rebind* the
    # module-level names below. Without it, the assignments would create
    # local variables instead of populating the cache.
    global _PERSONALITY_PROMPTS, _IMPORT_ATTEMPTED

    if _IMPORT_ATTEMPTED:
        # Already tried — return whatever we got (possibly an empty dict).
        return _PERSONALITY_PROMPTS or {}

    _IMPORT_ATTEMPTED = True

    # Learning annotation: guard the path insertion with ``os.path.isdir``.
    # ``sys.path.insert`` accepts any string, but importing from a
    # non-existent directory triggers a noisier ``ModuleNotFoundError``;
    # checking first lets us skip straight to the empty-dict fallback and
    # keeps the except block for genuine import-time failures only.
    if not os.path.isdir(_SKILL_SCRIPTS_DIR):
        return {}

    # Learning annotation: catch *both* the directory case and a stray
    # file by only inserting when the dir exists. We insert at index 0 so
    # the skill's modules take precedence over any shadowing package.
    if _SKILL_SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SKILL_SCRIPTS_DIR)

    try:
        # Learning annotation: importing ``session_personality`` runs its
        # module body, which itself does ``sys.path.insert`` and imports
        # ``personality_engine``. If either of those pieces is missing or
        # broken, we want to fall through to the empty dict rather than
        # crash the robot brain. We therefore catch ``Exception`` broadly
        # here (not just ``ImportError``) because a syntax error or a
        # missing transitive dependency inside the skill would surface as
        # ``SyntaxError`` / ``NameError`` rather than ``ImportError``.
        import session_personality  # type: ignore[import-not-found]
    except Exception:
        # Learning annotation: broad ``except`` is intentional and scoped:
        # the only consequence is "no personalities this session". We do
        # NOT re-raise, because personality is an enhancement, not a
        # requirement, for the robot's core loop.
        return {}

    # Learning annotation: ``getattr`` with a default guards against a
    # future skill version that renames the dict. We copy into a new dict
    # so callers cannot accidentally mutate the skill's canonical object.
    prompts = getattr(session_personality, "PERSONALITY_PROMPTS", None)
    if isinstance(prompts, dict):
        _PERSONALITY_PROMPTS = dict(prompts)
        return _PERSONALITY_PROMPTS

    return {}


# Learning annotation: a *hardcoded* emoji table means ``get_emoji()`` works
# with zero dependencies — handy for HUDs, logs, and Telegram status lines
# even when the skill is absent. The keys mirror the snake_case remedy names
# used by ``PERSONALITY_PROMPTS``. Emojis are chosen to evoke each remedy's
# signature temperament (e.g. ``bryonia_alba`` = the grumpy deep-work hermit
# -> 🦔 hedgehog; ``lachesis_muta`` = the cunning bushmaster snake -> 🐍).
# Remedies not listed here fall back to ``_DEFAULT_EMOJI`` below.
EMOJI_MAP: dict[str, str] = {
    # --- the explicitly requested anchor remedies ---
    "bryonia_alba": "🦔",            # deep-work hermit, prickly & withdrawn
    "pulsatilla_pratensis": "🌸",  # empathetic adapter, gentle windflower
    "arsenicum_album": "🧐",        # analytical perfectionist, scrutinising
    "sulphur": "🔮",                # visionary theorist, far-seeing
    "phosphorus": "🔥",             # charismatic communicator, luminous
    "nux_vomica": "⚡",             # driven executive, fast & decisive
    # --- additional common remedies (≥20 total) ---
    "aconitum_napellus": "⚠️",      # urgent, sudden, alarm-first
    "anacardium_orientale": "🔨",   # stress-testing, breaking things open
    "argentum_nitricum": "🗺️",      # planner, anticipating contingencies
    "aurum_metallicum": "👑",       # weighty conscience, gold, leadership
    "belladonna": "💥",            # volatile innovator, sudden bursts
    "calcarea_carbonica": "🏗️",    # methodical builder, solid foundations
    "causticum": "✊",             # principled advocate, fighting fist
    "chamomilla": "😤",            # irritable, reactive, huffy
    "cicuta_virosa": "🔁",         # repetitive, convulsive loops
    "cocculus_indicus": "🚢",       # motion-sick, logistics-worried
    "coffea_cruda": "☕",          # hypervigilant, racing, caffeinated
    "crocus_sativus": "🎭",        # dramatic, theatrical, mood-swinging
    "hyoscyamus_niger": "📢",      # shameless exhibitionist, attention-seeking
    "ignatia_amara": "💧",         # sensitive soul, deeply feeling
    "kalium_carbonicum": "📋",     # checklist-driven, anxious operator
    "lachesis_muta": "🐍",         # cunning negotiator, bushmaster snake
    "lycopodium_clavatum": "🧠",   # strategic intellectual
    "mercurius_solubilis": "🔍",   # relentless investigator
    "natrum_muriaticum": "🛡️",    # guarded guardian, protective
    "sepia_officinalis": "🦑",     # stoic executor, cuttlefish ink
    "silicea_terra": "💎",         # refining polisher, gemstone
    "staphysagria": "⚖️",          # dignified advocate, justice scales
    "stramonium": "😱",           # terrified, fear-aware
    "tarentula_hispanica": "🕷️",  # hyperkinetic, restless spider
    "veratrum_album": "📏",        # zealous enforcer, strict ruler
}

# Learning annotation: a single fallback glyph for any remedy not enumerated
# in ``EMOJI_MAP``. Using a robot face keeps it on-theme for R1-A1.
_DEFAULT_EMOJI = "🤖"


class PersonalityBridge:
    """Bind a single remedy personality to the R1-A1 brain.

    Parameters
    ----------
    remedy_name:
        Snake_case key as used by the skill's ``PERSONALITY_PROMPTS`` dict,
        e.g. ``"arsenicum_album"``. Case is normalised to lowercase so a
        caller passing ``"Arsenicum_Album"`` still hits the dict.
    enabled:
        Master switch. When ``False`` every accessor reports the personality
        as inactive (``get_prompt_prefix`` returns ``None``, ``info``
        reports ``enabled=False``), but ``get_emoji`` still returns the
        remedy's glyph so UIs stay stable. Defaults to ``True``.

    The bridge is cheap to construct: the (potentially failing) skill import
    happens at most once per process via the module-level
    ``_load_personality_prompts`` cache.
    """

    def __init__(self, remedy_name: str, enabled: bool = True) -> None:
        # Learning annotation: store the normalised key. Lowercasing makes
        # lookups forgiving without forcing every caller to remember the
        # exact casing of the skill's keys.
        self.remedy_name: str = remedy_name.lower().strip()
        self.enabled: bool = bool(enabled)

        # Learning annotation: eagerly load the prompt cache on
        # construction so ``get_prompt_prefix`` is a pure lookup with no
        # surprise import side-effects later. If the skill is missing this
        # is just an empty dict; no exception escapes.
        self._prompts: dict = _load_personality_prompts()

    def get_prompt_prefix(self) -> Optional[str]:
        """Return the personality prompt string, or ``None``.

        Returns ``None`` when:
        * the bridge is disabled (``enabled=False``), or
        * the skill is not installed / the remedy is unknown.

        Learning annotation: returning ``Optional[str]`` (rather than an
        empty string) lets callers distinguish "no personality active" from
        "personality active but its prompt is empty" with a simple truthiness
        check — the common ``prefix + "\\n" if prefix else ""`` idiom.
        """
        if not self.enabled:
            return None
        # Learning annotation: ``dict.get`` returns ``None`` for missing
        # keys by default, which is exactly the "unavailable" semantic we
        # want — no need for an explicit ``in`` check.
        return self._prompts.get(self.remedy_name)

    def get_emoji(self) -> str:
        """Return a single emoji for the active remedy.

        Always returns a string — never ``None`` — so this is safe to use
        directly in f-strings and UI labels. Unknown remedies fall back to
        ``_DEFAULT_EMOJI``. The emoji is returned *regardless* of
        ``enabled``: disabling a personality changes behaviour, not
        identity, so a status LED/HUD can keep showing which remedy is
        nominally loaded.
        """
        # Learning annotation: ``EMOJI_MAP.get(key, default)`` is the
        # classic "lookup-with-fallback" — one line, no branching.
        return EMOJI_MAP.get(self.remedy_name, _DEFAULT_EMOJI)

    def info(self) -> dict:
        """Return a snapshot of the bridge's current state.

        The returned dict has the shape::

            {
                "remedy":   str,            # normalised remedy name
                "emoji":    str,            # single emoji, always present
                "prompt":   str | None,     # prompt prefix, or None
                "enabled":  bool,           # master switch state
            }

        Learning annotation: returning a plain ``dict`` (rather than a
        dataclass) keeps this module dependency-free and JSON-serialisable
        for telemetry/status endpoints. ``get_prompt_prefix`` is reused so
        the "disabled" and "unavailable" rules live in exactly one place.
        """
        return {
            "remedy": self.remedy_name,
            "emoji": self.get_emoji(),
            "prompt": self.get_prompt_prefix(),
            "enabled": self.enabled,
        }

    @staticmethod
    def list_remedies() -> list[str]:
        """Return the list of available remedy names, or ``[]``.

        Reflects the *currently importable* skill catalogue: if the skill
        is installed, returns the keys of ``PERSONALITY_PROMPTS`` (100
        entries); if it is absent, returns an empty list. This is handy for
        a "pick a personality" menu in the robot's UI.

        Learning annotation: marked ``@staticmethod`` because it does not
        depend on any instance state — it is a query about the skill
        catalogue as a whole. We reuse the module-level loader so the import
        is still attempted only once.
        """
        # Learning annotation: list(keys) materialises a copy so callers
        # can sort/mutate without touching the cached dict. Sorted output
        # makes menus deterministic.
        prompts = _load_personality_prompts()
        return sorted(prompts.keys())


if __name__ == "__main__":
    # Learning annotation: a tiny CLI smoke-test so you can sanity-check the
    # bridge from the shell without pytest:
    #   python -m r1_a1.brain.personality
    # It prints a sample bridge's info dict and the count of available
    # remedies, which doubles as a quick "is the skill installed?" probe.
    import json

    sample = PersonalityBridge("arsenicum_album")
    print(json.dumps(sample.info(), indent=2, ensure_ascii=False))
    print("available remedies:", len(PersonalityBridge.list_remedies()))