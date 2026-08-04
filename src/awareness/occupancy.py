"""Ego-centric occupancy grid — the robot's short-term spatial memory.

A 40×40 grid at 0.1 m resolution covers a 4 m bubble around the robot —
exactly the useful range of our sensors. Cells hold a confidence in
[0, 1]: sensor hits raise it, ``decay()`` fades it, so stale memories
of a person who walked away don't block the path forever.

Coordinates are robot frame (+x forward, +y left), robot at grid center.
"""

from __future__ import annotations

import math

GRID_CELLS = 40
CELL_M = 0.1
HIT_CONFIDENCE = 0.9
DECAY_RATE = 0.10  # 10 % confidence loss per decay() call


class OccupancyGrid:
    def __init__(self, cells: int = GRID_CELLS, cell_m: float = CELL_M):
        if cells <= 0 or cells % 2 != 0:
            raise ValueError("cells must be a positive even number")
        if cell_m <= 0:
            raise ValueError("cell_m must be positive")
        self.cells = cells
        self.cell_m = cell_m
        self._grid = [[0.0] * cells for _ in range(cells)]

    # -- coordinate mapping ---------------------------------------------

    def _to_cell(self, x_m: float, y_m: float) -> tuple[int, int] | None:
        half = self.cells // 2
        col = int(x_m / self.cell_m) + half
        row = int(y_m / self.cell_m) + half
        if 0 <= col < self.cells and 0 <= row < self.cells:
            return row, col
        return None

    def _mark(self, x_m: float, y_m: float, confidence: float = HIT_CONFIDENCE):
        cell = self._to_cell(x_m, y_m)
        if cell is not None:
            r, c = cell
            self._grid[r][c] = max(self._grid[r][c], confidence)

    # -- sensor feeds -----------------------------------------------------

    def update_from_mmwave(self, targets) -> None:
        """Mark cells containing robot-frame mmWave targets."""
        for t in targets or []:
            self._mark(float(t["x_m"]), float(t["y_m"]))

    def update_from_ultrasonic(self, distances, sensor_headings) -> None:
        """Mark a cell at each ranger's measured distance along its beam."""
        for d, hdg in zip(distances, sensor_headings):
            r = math.radians(hdg)
            self._mark(float(d) * math.cos(r), float(d) * math.sin(r))

    def update_from_cliff(self, cliff_dirs) -> None:
        """Mark hazard cells just beyond the skirt in tripped directions."""
        anchors = {"front-left": 30.0, "front-right": -30.0, "rear": 180.0}
        for name in cliff_dirs or []:
            if name not in anchors:
                raise ValueError(f"unknown cliff direction: {name!r}")
            r = math.radians(anchors[name])
            # hazard just past the skirt radius (~0.25 m)
            self._mark(0.30 * math.cos(r), 0.30 * math.sin(r), confidence=1.0)

    # -- queries ----------------------------------------------------------

    def is_cell_blocked(self, x_m: float, y_m: float) -> bool:
        cell = self._to_cell(x_m, y_m)
        if cell is None:
            return True  # outside the known bubble: treat as unknown/blocked
        r, c = cell
        return self._grid[r][c] >= 0.5

    def raycast_clear(self, heading_deg: float, max_m: float) -> bool:
        """Walk cells along a ray; False if any hit a blocked cell."""
        if max_m <= 0:
            raise ValueError("max_m must be positive")
        r = math.radians(heading_deg)
        steps = int(max_m / self.cell_m)
        for i in range(1, steps + 1):
            d = i * self.cell_m
            if self.is_cell_blocked(d * math.cos(r), d * math.sin(r)):
                return False
        return True

    def decay(self) -> None:
        """Fade all confidences — call once per fusion refresh cycle."""
        keep = 1.0 - DECAY_RATE
        for r in range(self.cells):
            row = self._grid[r]
            for c in range(self.cells):
                row[c] *= keep
