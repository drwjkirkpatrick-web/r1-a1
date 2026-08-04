"""ThermalMonitor: zone temperature reporting, fan tach checks, and
thermal-policy flag enforcement per docs/HARDWARE.md §4.

Policy thresholds:
    - any compute/bay zone  > 75 °C -> throttle flag (fan 100 %, smaller LLM)
    - any compute/bay zone  > 85 °C -> shutdown flag (graceful inference stop)
    - battery               > 50 °C -> full_stop flag (stop, charge-inhibit, alert)

All hardware access is via injected callables so every code path is
testable with mocks. Reader protocol:
    host_reader()        -> float, host (CPU/GPU) temperature in °C
    bay_reader()         -> float, compute-bay probe (DS18B20 #1) °C
    motor_bay_reader()   -> float, motor-bay probe (DS18B20 #2) °C
    battery_reader()     -> float, battery bay temperature °C (optional)
    fan_tach_reader(i)   -> int RPM of fan i, 0 <= i < FAN_COUNT (optional)
"""

from __future__ import annotations

from typing import Callable, Optional

THROTTLE_C = 75.0
SHUTDOWN_C = 85.0
BATTERY_FULL_STOP_C = 50.0
FAN_COUNT = 5
MIN_FAN_RPM = 1  # tach reading at or below this counts as a stalled/dead fan


class ThermalMonitor:
    def __init__(
        self,
        host_reader: Callable[[], float],
        bay_reader: Callable[[], float],
        motor_bay_reader: Callable[[], float],
        battery_reader: Optional[Callable[[], float]] = None,
        fan_tach_reader: Optional[Callable[[int], float]] = None,
    ) -> None:
        self._host_reader = host_reader
        self._bay_reader = bay_reader
        self._motor_bay_reader = motor_bay_reader
        self._battery_reader = battery_reader
        self._fan_tach_reader = fan_tach_reader

        # Simulated values override live readers (set via simulate()).
        self._sim_temp: Optional[float] = None
        self._sim_battery: Optional[float] = None

        # Policy flags (sticky until reset_flags()).
        self.throttle_flag: bool = False
        self.shutdown_flag: bool = False
        self.full_stop_flag: bool = False

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def report(self) -> dict:
        """Return current zone temperatures as
        {"host_c": float, "bay_c": float, "motor_bay_c": float}.

        Also evaluates the thermal policy and updates the flags.
        """
        if self._sim_temp is not None:
            temps = {
                "host_c": float(self._sim_temp),
                "bay_c": float(self._sim_temp),
                "motor_bay_c": float(self._sim_temp),
            }
        else:
            temps = {
                "host_c": float(self._host_reader()),
                "bay_c": float(self._bay_reader()),
                "motor_bay_c": float(self._motor_bay_reader()),
            }
        self._evaluate_policy(temps, self.battery_c())
        return temps

    def battery_c(self) -> float:
        """Current battery-bay temperature (0.0 if no reader wired)."""
        if self._sim_battery is not None:
            return float(self._sim_battery)
        if self._battery_reader is None:
            return 0.0
        return float(self._battery_reader())

    # ------------------------------------------------------------------
    # Fans
    # ------------------------------------------------------------------
    def fan_check(self) -> dict:
        """Verify tach output on all FAN_COUNT fans.

        Returns {"ok": bool, "fans": {index: {"rpm": float, "ok": bool}}}.
        "ok" is True only if every fan reports RPM above MIN_FAN_RPM.
        """
        fans = {}
        all_ok = True
        for i in range(FAN_COUNT):
            rpm = float(self._fan_tach_reader(i)) if self._fan_tach_reader else 0.0
            ok = rpm >= MIN_FAN_RPM and self._fan_tach_reader is not None
            fans[i] = {"rpm": rpm, "ok": ok}
            all_ok = all_ok and ok
        return {"ok": all_ok, "fans": fans}

    # ------------------------------------------------------------------
    # Simulation (testing / what-if)
    # ------------------------------------------------------------------
    def simulate(self, temp_c: float, battery_c: Optional[float] = None) -> dict:
        """Inject a fake temperature into all compute/bay zones.

        battery_c injects a fake battery-bay temperature (defaults to
        temp_c). Pass clear=True via clear_simulation() to resume live
        readings. Returns the policy flags after evaluation.
        """
        self._sim_temp = float(temp_c)
        self._sim_battery = float(battery_c) if battery_c is not None else float(temp_c)
        temps = {
            "host_c": self._sim_temp,
            "bay_c": self._sim_temp,
            "motor_bay_c": self._sim_temp,
        }
        self._evaluate_policy(temps, self._sim_battery)
        return self.flags()

    def clear_simulation(self) -> None:
        """Resume live sensor readings."""
        self._sim_temp = None
        self._sim_battery = None

    # ------------------------------------------------------------------
    # Policy
    # ------------------------------------------------------------------
    def _evaluate_policy(self, temps: dict, battery_c: float) -> None:
        if any(v > THROTTLE_C for v in temps.values()):
            self.throttle_flag = True
        if any(v > SHUTDOWN_C for v in temps.values()):
            self.shutdown_flag = True
        if battery_c > BATTERY_FULL_STOP_C:
            self.full_stop_flag = True

    def flags(self) -> dict:
        """Current policy flags as a dict."""
        return {
            "throttle": self.throttle_flag,
            "shutdown": self.shutdown_flag,
            "full_stop": self.full_stop_flag,
        }

    def reset_flags(self) -> None:
        """Clear all policy flags."""
        self.throttle_flag = False
        self.shutdown_flag = False
        self.full_stop_flag = False
