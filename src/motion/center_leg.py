"""Center-leg (2-3-2 mode) linear actuator control for R1-A1.

150 mm stroke, 24 V actuator on an MCU-driven relay/H-bridge
(docs/HARDWARE.md §2). State is tracked locally so behavior is
verifiable without hardware; docs/PROMPTS.md #14/#15.
"""


class CenterLeg:
    """Center leg lift actuator.

    Commands:
      leg.deploy   {}
      leg.retract  {}
    """

    def __init__(self, link):
        """
        Args:
            link: SerialLink-like object with send(cmd, payload).
        """
        self.link = link
        self._deployed = False

    def deploy(self):
        """Extend the center leg (enter three-leg mode)."""
        self.link.send("leg.deploy", {})
        self._deployed = True

    def retract(self):
        """Retract the center leg (return to two-leg mode)."""
        self.link.send("leg.retract", {})
        self._deployed = False

    def is_deployed(self):
        """Return True if the center leg is currently deployed."""
        return self._deployed
