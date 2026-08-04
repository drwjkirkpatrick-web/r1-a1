"""PowerMonitor: battery state-of-charge, range estimate, and
charger-seek policy from the INA219 bus monitor (docs/HARDWARE.md §2).

All hardware access is via an injected reader so the module is fully
mockable. Reader protocol — ina219_reader() returns either:
    - a float/int: state of charge in percent, or
    - a dict with at least "soc_pct" (and optionally "voltage_v",
      "current_a") for richer telemetry.
"""

from __future__ import annotations

from typing import Callable, Union

METERS_PER_SOC_PERCENT = 12.0  # tuned from drive tests; soc × 12 = range in m
SEEK_CHARGER_SOC = 20.0        # below this, head for the charger


class PowerMonitor:
    def __init__(self, ina219_reader: Callable[[], Union[float, int, dict]]) -> None:
        self._reader = ina219_reader

    def _raw(self) -> dict:
        """Normalize the reader output to a telemetry dict."""
        reading = self._reader()
        if isinstance(reading, dict):
            data = dict(reading)
        else:
            data = {"soc_pct": float(reading)}
        data.setdefault("soc_pct", 0.0)
        return data

    def telemetry(self) -> dict:
        """Full normalized telemetry dict (soc_pct plus any raw fields)."""
        data = self._raw()
        data["soc_pct"] = self.soc()
        return data

    def soc(self) -> float:
        """State of charge in percent, clamped to [0, 100]."""
        return max(0.0, min(100.0, float(self._raw()["soc_pct"])))

    def estimate_range_m(self) -> float:
        """Estimated remaining drive range in metres (soc × 12 m per %)."""
        return self.soc() * METERS_PER_SOC_PERCENT

    def should_seek_charger(self) -> bool:
        """True when state of charge is below the seek-charger threshold."""
        return self.soc() < SEEK_CHARGER_SOC
