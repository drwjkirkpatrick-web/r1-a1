"""Hermes agent node client for the R1-A1 dome.

The R1-A1 dome hides a second Jetson Nano beside the vision node. That
Nano hosts the *Hermes agent layer* — personality (remedy selection),
limbic state (affective VAD profiles), and short-term orchestration — and
is reachable over the dome's gigabit slip-ring as a networked peer of the
main brain host.

Why a separate node? The main LLM host keeps its RAM, memory bandwidth,
and thermal headroom dedicated to inference. Personality/limbic traffic is
small, chatty, and latency-tolerant, so it is offloaded to the Nano and
exchanged as compact JSON over HTTP instead of competing with token
generation on the primary machine.

The HTTP layer is injectable (``http_client`` callable) so the module is
fully mockable in tests and transport-swappable on real hardware.
"""

from .agent_node import HermesNode, HermesNodeError

__all__ = ["HermesNode", "HermesNodeError"]
