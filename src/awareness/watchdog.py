"""Subsystem watchdog — liveness supervision for the MCU link and sensors.

On a safety-critical robot you don't just ask "is the software running?"
You ask "are the things that keep us safe *answering*?" The classic
watchdog pattern inverts responsibility: instead of detecting failure
after it happens, every critical subsystem must continuously *prove* it
is alive, and silence — not an error message — is the failure signal.
Silence is unambiguous: a crashed MCU can't send an exception.

Learning annotations
--------------------
1. **Tick-driven, no threads.** The main control loop calls ``tick()``
   once per cycle. Threads inside safety logic make liveness proofs
   untestable and non-deterministic; a single-threaded tick means a
   failing supervisor is itself observable by whatever calls it.

2. **Heartbeats count *misses*, not errors.** ``link.heartbeat()`` is
   boolean. We escalate only after ``max_missed_heartbeats`` consecutive
   misses — one dropped USB packet shouldn't kill the robot, but three
   in a row means the MCU is gone and the motors are unsupervised.

3. **Critical vs. informational sensors.** A dead camera degrades
   autonomy; a dead cliff sensor on a moving 38 kg robot is an estop.
   ``critical=True`` probes failing force escalation immediately, the
   same as exhausting the heartbeat budget.

4. **Edge detection on escalation.** ``estop_required`` is a *level*
   (stays True while the fault persists); ``escalated`` is an *edge*
   (True only on the tick where it first becomes True). The caller
   latches estop on the edge exactly once, instead of spamming the MCU
   with estop frames every cycle.

5. **Duck-typed link, injected clock.** ``link`` only needs
   ``heartbeat(timeout) -> bool`` and ``estop_sense(timeout) -> bool``
   (matching ``interconnect.SerialLink``); ``clock`` defaults to
   ``time.monotonic`` but tests inject a fake so "time since last OK"
   is deterministic.
"""

from __future__ import annotations

import time
from typing import Callable, Dict, Optional


class Watchdog:
    """Periodic liveness supervisor for the MCU link and named sensors.

    Parameters
    ----------
    link:
        Duck-typed serial link. Must provide ``heartbeat(timeout) -> bool``
        and ``estop_sense(timeout) -> bool``. Exceptions from these calls
        are treated as failure (a raised LinkError is still a miss).
    estop_budget_s:
        Timeout handed to each link call — the per-tick deadline we are
        willing to spend proving liveness.
    max_missed_heartbeats:
        Consecutive heartbeat misses before ``estop_required`` goes True.
    clock:
        Monotonic clock callable, injected for deterministic tests.
    """

    def __init__(
        self,
        link,
        estop_budget_s: float = 0.1,
        max_missed_heartbeats: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_missed_heartbeats < 1:
            raise ValueError("max_missed_heartbeats must be >= 1")
        if estop_budget_s <= 0:
            raise ValueError("estop_budget_s must be positive")
        self._link = link
        self._budget = float(estop_budget_s)
        self._max_missed = int(max_missed_heartbeats)
        self._clock = clock

        self._missed = 0
        self._ticked = False
        self._estop_required = False  # level (previous tick), for edge detection
        # name -> {'probe', 'critical', 'failures', 'last_ok_s'}
        self._sensors: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # sensor registry
    # ------------------------------------------------------------------
    def register_sensor(
        self,
        name: str,
        probe: Callable[[], bool],
        critical: bool = False,
    ) -> None:
        """Register a named liveness probe run on every tick.

        ``probe()`` returns True when the sensor is alive. Exceptions are
        caught and counted as failure — a crashed probe is a dead sensor.
        """
        if not callable(probe):
            raise ValueError("probe must be callable: probe() -> bool")
        self._sensors[name] = {
            "probe": probe,
            "critical": bool(critical),
            "failures": 0,
            "last_ok_s": None,
        }

    def unregister_sensor(self, name: str) -> None:
        """Remove a sensor from supervision. Unknown names are ignored."""
        self._sensors.pop(name, None)

    # ------------------------------------------------------------------
    # supervision
    # ------------------------------------------------------------------
    def _heartbeat(self) -> bool:
        """One link liveness check; any exception counts as a miss."""
        try:
            return bool(self._link.heartbeat(timeout=self._budget))
        except Exception:
            return False

    def tick(self) -> dict:
        """Run one supervision cycle and return a status snapshot.

        Escalation policy: ``estop_required`` when the heartbeat miss
        count reaches the budget OR any critical sensor failed this tick.
        ``escalated`` is True only on the rising edge so the caller can
        fire the estop exactly once.
        """
        link_ok = self._heartbeat()
        if link_ok:
            self._missed = 0
        else:
            self._missed += 1

        sensor_report: Dict[str, dict] = {}
        critical_failed = False
        now = self._clock()
        for name, entry in self._sensors.items():
            try:
                ok = bool(entry["probe"]())
            except Exception:
                ok = False
            if ok:
                entry["last_ok_s"] = now
            else:
                entry["failures"] += 1
                if entry["critical"]:
                    critical_failed = True
            sensor_report[name] = {
                "ok": ok,
                "critical": entry["critical"],
                "failures": entry["failures"],
            }

        estop_required = (
            self._missed >= self._max_missed or critical_failed
        )
        escalated = estop_required and not self._estop_required
        self._estop_required = estop_required
        self._ticked = True

        return {
            "link_alive": link_ok,
            "missed_heartbeats": self._missed,
            "estop_required": estop_required,
            "sensors": sensor_report,
            "escalated": escalated,
        }

    # ------------------------------------------------------------------
    # introspection
    # ------------------------------------------------------------------
    @property
    def link_alive(self) -> Optional[bool]:
        """True/False after the first tick; None before any tick ran."""
        if not self._ticked:
            return None
        return self._missed == 0

    def sensor_status(self, name: str) -> Optional[dict]:
        """Snapshot of one sensor's record, or None if not registered."""
        entry = self._sensors.get(name)
        if entry is None:
            return None
        return {
            "critical": entry["critical"],
            "failures": entry["failures"],
            "last_ok_s": entry["last_ok_s"],
        }
