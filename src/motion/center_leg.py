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
        if self._deployed:
            return  # idempotent: re-deploy is a no-op, not a re-command
        self.link.send("leg.deploy", {})
        self._deployed = True

    def retract(self):
        """Retract the center leg (return to two-leg mode)."""
        if not self._deployed:
            return  # idempotent: never retract an already-stowed leg
        self.link.send("leg.retract", {})
        self._deployed = False

    def is_deployed(self):
        """Return True if the center leg is currently deployed."""
        return self._deployed

    def drive_guard(self, drive):
        """Raise if ``drive`` is asked to move while the leg is deployed.

        Learning: 2-3-2 mode is a *stationary* stability stance — the
        center foot is not powered. Driving with the leg down grinds the
        foot pad and fights the drive motors. Behaviors call this before
        forward()/rotate() when the leg might be down. Returns the drive
        so it can be used inline: ``leg.drive_guard(drive).forward(...)``
        is NOT supported (we return None on pass to keep call sites
        explicit) — call as a bare statement before the motion command.
        """
        if self._deployed:
            raise RuntimeError(
                "center leg deployed (2-3-2 stance); retract() before driving"
            )
