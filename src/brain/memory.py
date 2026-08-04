"""Short-term memory for the R1-A1 brain.

Two stores:
- a rolling conversation buffer (deque, max 20 turns) of (role, text)
- a persistent fact store (dict) for explicit "remember that ..." facts

Pure stdlib, hardware-free, trivially mockable.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Optional, Tuple

MAX_TURNS = 20


class Memory:
    """Conversation buffer plus key/value fact store."""

    def __init__(self, max_turns: int = MAX_TURNS) -> None:
        self.turns: Deque[Tuple[str, str]] = deque(maxlen=max_turns)
        self.facts: dict[str, str] = {}

    def add_turn(self, role: str, text: str) -> None:
        """Append a (role, text) turn to the conversation buffer."""
        self.turns.append((role, text))

    def remember(self, key: str, value: str) -> None:
        """Store a fact under ``key`` (normalized to lowercase, stripped)."""
        self.facts[key.strip().lower()] = value.strip()

    def recall(self, key: str) -> Optional[str]:
        """Recall a fact by ``key``; None if unknown."""
        return self.facts.get(key.strip().lower())

    def summarize_last(self) -> str:
        """Summarize the most recent user turn.

        Returns a short human-readable summary of the last thing the user
        said, or a notice that nothing has been said yet.
        """
        for role, text in reversed(self.turns):
            if role == "user":
                text = text.strip()
                if len(text) > 80:
                    text = text[:77] + "..."
                return f"The last thing you asked was: {text}"
        return "You haven't asked me anything yet."
