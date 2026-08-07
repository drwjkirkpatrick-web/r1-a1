"""R1-A1 brain package: LLM client, memory, agent routing, and optional bridges."""

from .llm_client import LLMClient
from .memory import Memory
from .agent import Agent
from .personality import PersonalityBridge
from .limbic import LimbicBridge

__all__ = [
    "LLMClient",
    "Memory",
    "Agent",
    "PersonalityBridge",
    "LimbicBridge",
    "KeepAlive",
]


def __getattr__(name: str):
    """Lazy KeepAlive import — keeps package importable on minimal
    checkouts where keepalive.py may not be present yet."""
    if name == "KeepAlive":
        from .keepalive import KeepAlive
        return KeepAlive
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")