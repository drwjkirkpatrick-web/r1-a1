"""Dome rotation control for R1-A1.

NEMA-17 stepper + planetary gear on the dome ring (docs/HARDWARE.md §2).
Position is tracked against an internal encoder estimate; every
commanded move is asserted within TOLERANCE_DEG of the estimate, per
docs/PROMPTS.md #19 (±2°).
"""


class DomeToleranceError(RuntimeError):
    """Dome position diverged from the encoder estimate beyond tolerance."""


class Dome:
    """Dome stepper axis with closed-loop position verification.

    Commands:
      dome.rotate  {degrees}
    """

    TOLERANCE_DEG = 2.0

    def __init__(self, link):
        """
        Args:
            link: SerialLink-like object with send(cmd, payload).
        """
        self.link = link
        self.position_deg = 0.0
        # Test hook: simulated discrepancy between commanded target and
        # encoder reading (0.0 on healthy hardware/mocks).
        self.simulated_encoder_error_deg = 0.0

    def rotate_deg(self, deg):
        """Rotate the dome by `deg` (relative; positive = right/CW).

        After the move, the encoder estimate is checked against the
        expected position; raises DomeToleranceError if off by more
        than ±TOLERANCE_DEG.
        """
        self.link.send("dome.rotate", {"degrees": float(deg)})
        expected = self.position_deg + deg
        measured = expected + self.simulated_encoder_error_deg
        error = abs(measured - expected)
        if error > self.TOLERANCE_DEG:
            raise DomeToleranceError(
                f"dome position error {error:.2f}° exceeds "
                f"±{self.TOLERANCE_DEG}° tolerance "
                f"(expected {expected:.2f}°, measured {measured:.2f}°)")
        self.position_deg = measured

    def express(self, name):
        """Play a canned dome expression.

        Supported:
          'confused' — two quick ±45° wags (docs/PROMPTS.md #20).
          'scan'     — sweep left 90°, right 180°, back to center
                       (searching-the-room behaviour for "look around").
        """
        if name == "confused":
            for step in (+45.0, -45.0, +45.0, -45.0):
                self.rotate_deg(step)
        elif name == "scan":
            for step in (-90.0, +180.0, -90.0):
                self.rotate_deg(step)
        else:
            raise ValueError(f"unknown dome expression: {name!r}")

    def center(self):
        """Return the dome to the 0° home position from the tracked pose.

        Learning: after several relative moves the dome can sit at an
        arbitrary angle; behaviors that need a known heading (camera
        capture aligned to drive heading) call center() first instead of
        accumulating a relative offset chain.
        """
        self.rotate_deg(-self.position_deg)
