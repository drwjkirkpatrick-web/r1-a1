"""Short-term memory for the R1-A1 brain.

Two stores:
- a rolling conversation buffer (deque, max 20 turns) of (role, text)
- a persistent fact store (dict) for explicit "remember that ..." facts

Optional JSON persistence lets facts and recent turns survive a brain
restart — an astromech that forgets your name every reboot feels broken.
Pure stdlib, hardware-free, trivially mockable.
"""

from __future__ import annotations

import json
import os
from collections import deque
from typing import Deque, Optional, Tuple

MAX_TURNS = 20


class Memory:
    """Conversation buffer plus key/value fact store, optionally persisted."""

    def __init__(
        self,
        max_turns: int = MAX_TURNS,
        persist_path: Optional[str] = None,
        autosave: bool = False,
    ) -> None:
        self.turns: Deque[Tuple[str, str]] = deque(maxlen=max_turns)
        self.facts: dict[str, str] = {}
        # Learning: expanduser so config can use "~/.r1a1/memory.json".
        self.persist_path = (
            os.path.expanduser(persist_path) if persist_path else None
        )
        self.autosave = autosave
        if self.persist_path and os.path.exists(self.persist_path):
            self.load()

    def add_turn(self, role: str, text: str) -> None:
        """Append a (role, text) turn to the conversation buffer."""
        self.turns.append((role, text))
        if self.autosave:
            self.save()

    def remember(self, key: str, value: str) -> None:
        """Store a fact under ``key`` (normalized to lowercase, stripped)."""
        self.facts[key.strip().lower()] = value.strip()
        if self.autosave:
            self.save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def save(self) -> None:
        """Write facts + recent turns to ``persist_path`` as JSON.

        No-op when no persist_path is configured. Writes are atomic-ish
        (write temp file, then replace) so a crash mid-save can't leave
        a truncated memory file the next boot can't parse.
        """
        if not self.persist_path:
            return
        data = {
            "facts": self.facts,
            "turns": [list(t) for t in self.turns],
        }
        tmp = self.persist_path + ".tmp"
        os.makedirs(os.path.dirname(self.persist_path), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, self.persist_path)

    def load(self) -> None:
        """Load facts + turns from ``persist_path``. Tolerates corruption."""
        if not self.persist_path or not os.path.exists(self.persist_path):
            return
        try:
            with open(self.persist_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return  # corrupt or unreadable: start fresh rather than crash
        facts = data.get("facts")
        if isinstance(facts, dict):
            self.facts = {str(k): str(v) for k, v in facts.items()}
        turns = data.get("turns")
        if isinstance(turns, list):
            for item in turns:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    self.turns.append((str(item[0]), str(item[1])))

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
