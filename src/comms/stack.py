"""CommsStack: one failure-tolerant facade over R1-A1's optional comms hardware.

Subsystems (all optional — the robot still works with none of them):

- **GPS** (u-blox NEO-M9N, USB/UART): injected as a ``gps_reader``
  callable returning ``{'lat': float, 'lon': float, 'fix': bool,
  'sats': int, 'alt_m': float | None}``.
- **Cellular hotspot** (4G/5G USB modem): duck-typed object with
  ``.connected() -> bool``, ``.connect() -> bool``, ``.signal_pct() -> int``.
- **WiFi router** (onboard AP for the operator's phone): duck-typed
  object with ``.connected() -> bool``, ``.ssid() -> str``,
  ``.clients() -> int``.

WAN policy: WiFi is preferred (free, fast); cellular is the failover
backhaul for when the robot roams out of AP range. ``ensure_wan()``
brings cellular up when WiFi is down, but rate-limits connect attempts
to one per CONNECT_COOLDOWN_S — USB modems are slow to negotiate and a
flapping link hammered with connects never settles.

Robustness rule: *absent hardware never raises* — unwired subsystems
report available=False / None. Only programming errors (a gps_reader
returning a malformed dict) raise CommsError, because silently ignoring
garbage telemetry would let the robot navigate on phantom coordinates.
"""

from __future__ import annotations

import math
import time
from typing import Callable, Optional, Tuple

CONNECT_COOLDOWN_S = 30.0  # min seconds between cellular connect attempts

# Keys every gps_reader result must carry (docs/HARDWARE.md: NEO-M9N NMEA feed).
_GPS_REQUIRED_KEYS = ("lat", "lon", "fix", "sats", "alt_m")


class CommsError(RuntimeError):
    """Programming error in the comms layer (e.g. malformed GPS reading).

    Never raised for absent hardware — an unwired subsystem is a normal
    configuration, not an error.
    """


class CommsStack:
    """Failure-tolerant facade over GPS + cellular + WiFi subsystems."""

    def __init__(
        self,
        gps_reader: Optional[Callable[[], dict]] = None,
        cellular=None,
        wifi=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._gps_reader = gps_reader
        self._cellular = cellular
        self._wifi = wifi
        # Injected clock (monotonic) so tests can advance time without sleeping.
        self._clock = clock
        # Clock time of the most recent reading with fix=True; None until then.
        self._last_fix_at: Optional[float] = None
        # Clock time of the last cellular connect attempt; None = never tried.
        self._last_connect_attempt: Optional[float] = None

    # ------------------------------------------------------------------ GPS

    @staticmethod
    def _validate_fix(reading) -> dict:
        """Normalize/validate a gps_reader result, raising CommsError on garbage.

        A bad reader is a programming error, not a hardware condition —
        better to crash the caller loudly than navigate on phantom data.
        """
        if not isinstance(reading, dict):
            raise CommsError(f"gps_reader must return a dict, got {type(reading).__name__}")
        missing = [k for k in _GPS_REQUIRED_KEYS if k not in reading]
        if missing:
            raise CommsError(f"gps_reader result missing keys: {missing}")
        data = dict(reading)
        try:
            data["lat"] = float(data["lat"])
            data["lon"] = float(data["lon"])
        except (TypeError, ValueError) as exc:
            raise CommsError(f"non-numeric lat/lon in GPS reading: {reading!r}") from exc
        if not (math.isfinite(data["lat"]) and math.isfinite(data["lon"])):
            raise CommsError(f"non-finite lat/lon in GPS reading: {reading!r}")
        if not -90.0 <= data["lat"] <= 90.0 or not -180.0 <= data["lon"] <= 180.0:
            raise CommsError(f"lat/lon out of range in GPS reading: {reading!r}")
        data["fix"] = bool(data["fix"])
        try:
            data["sats"] = int(data["sats"])
        except (TypeError, ValueError) as exc:
            raise CommsError(f"non-integer sats in GPS reading: {reading!r}") from exc
        if data["alt_m"] is not None:
            try:
                data["alt_m"] = float(data["alt_m"])
            except (TypeError, ValueError) as exc:
                raise CommsError(f"non-numeric alt_m in GPS reading: {reading!r}") from exc
        return data

    def gps_fix(self) -> Optional[dict]:
        """Current GPS reading, or None when no GPS receiver is wired.

        The returned dict gains ``age_s``: seconds since the receiver last
        reported a true fix (0.0 when this very reading has a fix; None if
        the receiver has never had a fix). A growing age_s means the robot
        is coasting on stale coordinates — treat them as approximate.
        """
        if self._gps_reader is None:
            return None
        data = self._validate_fix(self._gps_reader())
        now = self._clock()
        if data["fix"]:
            self._last_fix_at = now
            data["age_s"] = 0.0
        elif self._last_fix_at is not None:
            data["age_s"] = now - self._last_fix_at
        else:
            data["age_s"] = None
        return data

    def has_fix(self) -> bool:
        """True when a GPS receiver is wired and currently reporting a fix."""
        fix = self.gps_fix()
        return bool(fix and fix["fix"])

    def position(self) -> Optional[Tuple[float, float]]:
        """(lat, lon) from the current fix, or None without a valid fix."""
        fix = self.gps_fix()
        if fix is None or not fix["fix"]:
            return None
        return (fix["lat"], fix["lon"])

    # ------------------------------------------------------------------ WAN

    def wan_status(self) -> dict:
        """Snapshot of both WAN paths and which one is carrying traffic.

        active:
          - 'wifi'     — WiFi AP link up (preferred path),
          - 'cellular' — WiFi down but cellular up (failover_active=True),
          - 'offline'  — neither path available.
        """
        # Branch on the object itself so each duck-typed call is guarded.
        wifi_connected = self._wifi is not None and bool(self._wifi.connected())
        cellular_connected = self._cellular is not None and bool(self._cellular.connected())
        if wifi_connected:
            active = "wifi"
        elif cellular_connected:
            active = "cellular"
        else:
            active = "offline"
        return {
            "wifi_connected": wifi_connected,
            "wifi_ssid": self._wifi.ssid() if wifi_connected and self._wifi else None,
            "cellular_connected": cellular_connected,
            "cellular_signal_pct": (
                self._cellular.signal_pct()
                if cellular_connected and self._cellular
                else None
            ),
            "active": active,
            # Failover means: primary (wifi) lost, secondary (cellular) carrying.
            "failover_active": active == "cellular",
        }

    def ensure_wan(self) -> dict:
        """Best-effort: guarantee some WAN path, then return wan_status().

        If WiFi is down and a cellular modem is present but not connected,
        place exactly one connect attempt per CONNECT_COOLDOWN_S window.
        The cooldown matters: USB modems take seconds to negotiate, and
        hammering connect() on a flapping link keeps it from ever settling.
        """
        status = self.wan_status()
        if status["wifi_connected"] or status["cellular_connected"]:
            return status  # already have a path — nothing to do
        if self._cellular is None:
            return status  # no failover hardware — offline is a valid answer
        now = self._clock()
        if (
            self._last_connect_attempt is None
            or now - self._last_connect_attempt >= CONNECT_COOLDOWN_S
        ):
            self._last_connect_attempt = now
            self._cellular.connect()
        return self.wan_status()

    # -------------------------------------------------------------- combined

    def status(self) -> dict:
        """Combined GPS + WAN snapshot for the dashboard."""
        return {"gps": self.gps_fix(), "wan": self.wan_status()}
