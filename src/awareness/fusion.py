"""AwarenessFusion — one call to refresh the robot's whole world picture.

Composes the four sensor wrappers + occupancy grid into a single
refresh cycle:

    1. scan mmWave (moving humans)      → grid
    2. read ultrasonic ring (statics)   → grid
    3. read cliff sensors (drop-offs)   → grid as hard hazards
    4. grid.decay() (forget stale cells)

The returned dict is what ``motion.refine`` and the brain's status
prompts consume.
"""

from __future__ import annotations

import math

from .mmwave import MMWaveArray
from .ultrasonic import UltrasonicRing, SENSOR_HEADINGS_DEG
from .cliff import CliffSensors
from .pose import PoseFilter
from .occupancy import OccupancyGrid


class AwarenessFusion:
    def __init__(
        self,
        mmwave: MMWaveArray,
        ultrasonic: UltrasonicRing,
        cliff: CliffSensors,
        pose: PoseFilter,
        grid: OccupancyGrid | None = None,
    ):
        for name, obj in (
            ("mmwave", mmwave), ("ultrasonic", ultrasonic),
            ("cliff", cliff), ("pose", pose),
        ):
            if obj is None:
                raise ValueError(f"{name} sensor wrapper is required")
        self.mmwave = mmwave
        self.ultrasonic = ultrasonic
        self.cliff = cliff
        self.pose = pose
        self.grid = grid or OccupancyGrid()
        self._last: dict = {}

    def refresh(self) -> dict:
        """Poll every sensor, update the grid, return the fused picture."""
        targets = self.mmwave.scan()
        dists = self.ultrasonic.distances()
        cliff_dirs = self.cliff.tripped()

        self.grid.update_from_mmwave(targets)
        self.grid.update_from_ultrasonic(dists, SENSOR_HEADINGS_DEG)
        self.grid.update_from_cliff(cliff_dirs)
        self.grid.decay()

        nearest = min(dists) if dists else math.inf
        if targets:
            nearest_t = min(math.hypot(t["x_m"], t["y_m"]) for t in targets)
            nearest = min(nearest, nearest_t)

        self._last = {
            "human_present": bool(targets),
            "nearest_m": nearest,
            "cliff": bool(cliff_dirs),
            "pose": self.pose.pose(),
        }
        return dict(self._last)

    def status_report(self) -> dict:
        """Last refresh plus provenance — for the 'full self-check' prompt."""
        return {
            **self._last,
            "grid_cells": self.grid.cells * self.grid.cells,
            "sensors": ["mmwave", "ultrasonic", "cliff", "pose"],
        }
