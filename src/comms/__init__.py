"""Onboard communications stack for R1-A1: GPS, cellular failover, WiFi AP.

R1-A1 carries three independent communications subsystems:

1. **GPS receiver** (u-blox NEO-M9N over USB/UART) — absolute position
   for roaming, geofencing, and "where did I leave the robot" telemetry.
2. **Cellular hotspot** (4G/5G USB modem) — wide-area backhaul when the
   robot roams out of WiFi range.
3. **WiFi router** — the robot's own local access point, which the
   operator's phone joins for direct control and the dashboard.

Failover matters because a roaming robot constantly crosses coverage
boundaries: it rolls out of the garage (WiFi) into the yard (dead zone)
and must keep a WAN path alive or the operator loses telemetry and the
LLM brain loses its cloud link. When WiFi drops, the stack brings up the
cellular modem — once, with a cooldown, so a flapping modem isn't
hammered with connect requests — and reports which path is active.

All hardware access is via injected callables/objects, so the module is
fully mockable. Absent hardware is normal (comms are optional) and never
raises; only *programming errors* (a gps_reader returning a malformed
dict) raise CommsError.
"""

from .stack import CommsError, CommsStack

__all__ = ["CommsStack", "CommsError"]
