"""R1-A1 spatial-awareness subsystem.

Eight upgrades over the base bump-switch build:

1. ``mmwave``      — 3× LD2450 24 GHz human-tracking radar (sees in the dark)
2. ``ultrasonic``  — 4-sensor ultrasonic ring for mid-range obstacles
3. ``cliff``       — downward ToF cliff/stair detection
4. ``pose``        — IMU+odometry complementary-filter pose fusion
5. ``occupancy``   — ego-centric occupancy grid with confidence decay
6. ``proximity``   — speed-limit policy zones around obstacles
7. ``fusion``      — one-call sensor refresh + status report
8. ``motion.refine`` — MovementRefiner: speed scaling, detours, pursuit

All hardware access is dependency-injected; everything here is testable
without a robot attached.
"""

from .mmwave import MMWaveArray
from .ultrasonic import UltrasonicRing
from .cliff import CliffSensors
from .pose import PoseFilter
from .occupancy import OccupancyGrid
from .proximity import ProximityPolicy
from .fusion import AwarenessFusion

__all__ = [
    "MMWaveArray",
    "UltrasonicRing",
    "CliffSensors",
    "PoseFilter",
    "OccupancyGrid",
    "ProximityPolicy",
    "AwarenessFusion",
]
