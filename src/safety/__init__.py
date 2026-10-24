"""Safety subsystem: hazard assessment + emergency response decisions.

- ``hazard``    — HazardType catalogue and the Hazard value object
                  (severity 1-10 -> escalation level 1-4).
- ``response``  — SafetyController: ordered response plans, per-system
                  interlocks, acknowledge/clear bookkeeping with
                  clear-hysteresis.

Pure logic over injected callables; no hardware access here.
"""

from .hazard import Hazard, HazardType
from .response import SafetyController

__all__ = ["Hazard", "HazardType", "SafetyController"]
