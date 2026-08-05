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
    """

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        memory: Optional[Memory] = None,
        personality: Optional[PersonalityBridge] = None,
        limbic: Optional[LimbicBridge] = None,
    ) -> None:
        self.llm = llm or LLMClient()
        self.memory = memory or Memory()
        self.personality = personality
        self.limbic = limbic

    def handle(self, prompt: str) -> str:
        """Handle a user prompt, returning the agent's reply text."""
        text = prompt.strip()

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

        # Combine personality prefix with the user text.
        if prefix_parts:
            full_prompt = "\n\n".join(prefix_parts) + "\n\n" + text

        # Limbic bridge: wrap the prompt with affect-aware guidance.
        if self.limbic is not None:
            full_prompt = self.limbic.inject_prompt(full_prompt)
            # Feed the event to the limbic system.
            self.limbic.observe("user_message", text)

        reply = self.llm.generate(full_prompt)
        self.memory.add_turn("assistant", reply)

        # Feed the reply to the limbic system as a success event.
        if self.limbic is not None:
            self.limbic.observe("assistant_reply", reply[:200])
            self.limbic.update()

        return reply