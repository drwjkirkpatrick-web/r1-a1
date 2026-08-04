"""Cliff detection — 3× VL53L1X ToF sensors pointing down past the skirt.

Stairs and table edges are the classic astromech killers: drive sensors
see open air, the floor drops away, and 38 kg of robot takes a tumble.
Three downward time-of-flight rangers (front-left, front-right, rear)
measure drop distance; anything past the threshold is a cliff.

    read_fn(index) -> drop distance in millimeters (float)

Sensor layout (robot frame, 0° = forward):
    index 0: front-left   (~ +30°)
    index 1: front-right  (~ −30°)
    index 2: rear         (180°)
"""

from __future__ import annotations

SENSOR_DIRECTIONS = ("front-left", "front-right", "rear")


class CliffSensors:
    def __init__(self, read_fn, threshold_mm: float = 80.0):
        if not callable(read_fn):
            raise ValueError("read_fn must be callable: read_fn(index) -> mm")
        if threshold_mm <= 0:
            raise ValueError("threshold_mm must be positive")
        self._read = read_fn
        self._threshold = float(threshold_mm)

    def readings_mm(self) -> list[float]:
        return [float(self._read(i)) for i in range(3)]

    def is_cliff(self) -> bool:
        """True when ANY sensor sees a drop beyond the threshold."""
        return any(r > self._threshold for r in self.readings_mm())

    def tripped(self) -> list[str]:
        """Direction names of currently-tripped sensors (may be empty)."""
        return [
            name
            for name, r in zip(SENSOR_DIRECTIONS, self.readings_mm())
            if r > self._threshold
        ]

    def safest_turn(self) -> str:
        """'left' | 'right' | 'back' — rotation away from the hazard.

        Front-left tripped → turn right; front-right → left; rear →
        either side is fine, we pick 'left' (arbitrary but consistent).
        Multiple tripped → 'back' (retreat, reassess).
        """
        hit = self.tripped()
        if not hit:
            return "left"  # no hazard; harmless default
        if len(hit) > 1 or hit[0] == "rear":
            return "back"
        return "right" if hit[0] == "front-left" else "left"
