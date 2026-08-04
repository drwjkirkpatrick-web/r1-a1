"""Whole-body expressive gaits for R1-A1.

Canned motion expressions built on the drive base. All motion still
flows through the injected SerialLink (via the Drive instance), per
docs/PROMPTS.md #16.
"""


class Express:
    """Expressive body motions.

    Args:
        drive: a motion.drive.Drive instance (owns the SerialLink).
    """

    WIGGLE_AMPLITUDE_DEG = 5.0

    def __init__(self, drive):
        self.drive = drive

    def wiggle(self, pulses=4):
        """Excited wiggle: alternating ±5° rotation pulses.

        Each pair of pulses returns the base to its original heading.
        `pulses` is the total number of ± pulses (default 4 = two full
        left-right cycles).
        """
        if pulses <= 0:
            raise ValueError("pulses must be positive")
        for i in range(pulses):
            direction = 1.0 if i % 2 == 0 else -1.0
            self.drive.rotate(direction * self.WIGGLE_AMPLITUDE_DEG)
