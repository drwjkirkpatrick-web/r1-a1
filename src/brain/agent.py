"""R1-A1 brain agent.

Composes an LLMClient and a Memory. ``handle(prompt)`` routes meta-prompts
(model status, model switching, remember/recall, summarization) locally
WITHOUT hitting the LLM; everything else is forwarded to the LLM and the
exchange is logged in memory.

Optional PersonalityBridge and LimbicBridge layers may be attached to
shape the prompt with a remedy temperament and affective state before it
reaches the LLM. Both degrade gracefully when disabled or unavailable.
"""

from __future__ import annotations

import re
from typing import Optional

from .llm_client import LLMClient
from .memory import Memory
from .personality import PersonalityBridge
from .limbic import LimbicBridge

_REMEMBER_RE = re.compile(
    r"^remember(?:\s+that)?(?:\s+my)?\s+(.+?)\s+is\s+(.+)$", re.IGNORECASE
)
_RECALL_RE = re.compile(
    r"^(?:what(?:'s| is)|whats|who(?:'s| is))\s+my\s+(.+?)\s*\??$", re.IGNORECASE
)


class Agent:
    """Routes user prompts between local meta-commands and the LLM.

    Optional personality and limbic bridges are injected at construction
    time. When present and enabled, the personality bridge prepends a
    temperament directive and the limbic bridge wraps the prompt with
    affect-aware guidance before the LLM is called.

    The LLM call itself is wrapped so a dead model server returns a
    graceful spoken fallback instead of raising through the audio loop.
    """

    # Learning: conversation context window sent to the LLM. Without it
    # the model sees each utterance in isolation and can't resolve
    # "what about tomorrow?" — a real wiring gap, not a style choice.
    CONTEXT_TURNS = 6

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        memory: Optional[Memory] = None,
        personality: Optional[PersonalityBridge] = None,
        limbic: Optional[LimbicBridge] = None,
        context_turns: int = CONTEXT_TURNS,
    ) -> None:
        self.llm = llm or LLMClient()
        self.memory = memory or Memory()
        self.personality = personality
        self.limbic = limbic
        self.context_turns = max(0, int(context_turns))

    def handle(self, prompt: str) -> str:
        """Handle a user prompt, returning the agent's reply text."""
        text = prompt.strip()
        if not text:
            return "I didn't catch that — say again?"

        # --- Meta-prompts (handled locally, LLM is NOT called) ---

        # Model status: "What model are you running right now?"
        if "what model" in text.lower():
            return f"I'm currently running {self.llm.current_model()}."

        # Model switching: "Switch to your small model." / "... big model."
        lower = text.lower()
        if "switch" in lower and "model" in lower:
            if any(w in lower for w in ("small", "fallback", "fast", "little")):
                tag = self.llm.switch_to_fallback()
                return f"Switched to my fallback model, {tag}."
            if any(w in lower for w in ("big", "primary", "main", "large", "default")):
                tag = self.llm.switch_to_primary()
                return f"Switched back to my primary model, {tag}."
            tag = self.llm.switch_to_fallback()
            return f"Switched to my fallback model, {tag}."

        # Remember: "Remember that my name is Walker."
        m = _REMEMBER_RE.match(text)
        if m:
            key, value = m.group(1), m.group(2).rstrip(".")
            self.memory.remember(key, value)
            return f"Got it — I'll remember that your {key} is {value}."

        # Recall: "What's my name?"
        m = _RECALL_RE.match(text)
        if m:
            key = m.group(1)
            value = self.memory.recall(key)
            if value is None:
                return f"I don't know your {key} yet."
            return f"Your {key} is {value}."

        # Summarize: "Summarize the last thing I asked you."
        if "summar" in lower:
            return self.memory.summarize_last()

        # --- Everything else goes to the LLM ---
        self.memory.add_turn("user", text)

        # Build the full prompt with optional personality + limbic layers.
        full_prompt = text
        prefix_parts: list[str] = []

        # Personality bridge: prepend temperament directive.
        if self.personality is not None:
            p_prefix = self.personality.get_prompt_prefix()
            if p_prefix:
                prefix_parts.append(p_prefix)

        # Conversation context: recent turns so the LLM can resolve
        # references ("it", "that", "what about..."). Excludes the turn
        # we just appended (it appears as the final line below).
        context_block = self._context_block()

        if prefix_parts:
            full_prompt = "\n\n".join(prefix_parts) + "\n\n" + text
        if context_block:
            full_prompt = (
                (("\n\n".join(prefix_parts) + "\n\n") if prefix_parts else "")
                + context_block
                + "\n\n"
                + text
            )

        # Limbic bridge: wrap the prompt with affect-aware guidance.
        if self.limbic is not None:
            full_prompt = self.limbic.inject_prompt(full_prompt)
            # Feed the event to the limbic system.
            self.limbic.observe("user_message", text)

        reply = self._safe_generate(full_prompt)
        self.memory.add_turn("assistant", reply)

        # Feed the reply to the limbic system as a success event.
        if self.limbic is not None:
            self.limbic.observe("assistant_reply", reply[:200])
            self.limbic.update()

        return reply

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _context_block(self) -> str:
        """Render recent turns as a transcript block for the LLM prompt.

        Returns "" when there is no history or context is disabled.
        Learning: the user turn for the *current* prompt was already
        appended to memory, so we drop the last entry to avoid sending
        it twice (once in context, once as the actual prompt).
        """
        if self.context_turns <= 0:
            return ""
        turns = list(self.memory.turns)[:-1][-self.context_turns:]
        if not turns:
            return ""
        lines = [f"{role.title()}: {t}" for role, t in turns]
        return "Conversation so far:\n" + "\n".join(lines)

    def _safe_generate(self, prompt: str) -> str:
        """Call the LLM; on transport/server failure return a spoken
        fallback instead of raising through the audio stack.

        Learning: a robot whose voice loop crashes when the model
        server restarts feels broken in exactly the moment it should
        feel most alive. We degrade to an honest "thinking" utterance.
        """
        try:
            return self.llm.generate(prompt)
        except Exception:
            return (
                "My thoughts are tangled for a moment — "
                "give me a second and ask again."
            )