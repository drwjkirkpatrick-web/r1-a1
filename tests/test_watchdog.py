"""Tests for the subsystem watchdog (awareness.watchdog).

The fake link scripts heartbeat pass/fail per call; the fake clock makes
last_ok_s timestamps deterministic. No threads, no sleeps — the watchdog
is tick-driven, so every scenario is a plain sequence of tick() calls.
"""

from __future__ import annotations

import pytest

from src.awareness.watchdog import Watchdog


class FakeLink:
    """Scripted stand-in for interconnect.SerialLink.

    ``heartbeat_script`` is consumed one value per heartbeat() call;
    when exhausted it repeats the last value (a steady-state link).
    """

    def __init__(self, heartbeat_script):
        self._script = list(heartbeat_script)
        self.heartbeat_timeouts = []
        self.estop_sense_calls = 0

    def heartbeat(self, timeout):
        self.heartbeat_timeouts.append(timeout)
        if len(self._script) > 1:
            return self._script.pop(0)
        return self._script[0]

    def estop_sense(self, timeout):
        self.estop_sense_calls += 1
        return False


class FakeClock:
    def __init__(self, start=100.0, step=0.05):
        self.t = start
        self.step = step

    def __call__(self):
        t = self.t
        self.t += self.step
        return t


def make_watchdog(script=(True,), **kwargs):
    link = FakeLink(script)
    wd = Watchdog(link, clock=FakeClock(), **kwargs)
    return wd, link


# ---------------------------------------------------------------------------
# heartbeat counting
# ---------------------------------------------------------------------------

def test_heartbeat_success_resets_miss_counter():
    wd, _ = make_watchdog((False, False, True))
    assert wd.tick()["missed_heartbeats"] == 1
    assert wd.tick()["missed_heartbeats"] == 2
    result = wd.tick()
    assert result["link_alive"] is True
    assert result["missed_heartbeats"] == 0


def test_missed_heartbeats_increment_on_failure():
    wd, _ = make_watchdog((False,))
    for expected in (1, 2, 3, 4):
        assert wd.tick()["missed_heartbeats"] == expected


def test_heartbeat_receives_estop_budget_as_timeout():
    wd, link = make_watchdog((True,), estop_budget_s=0.25)
    wd.tick()
    assert link.heartbeat_timeouts == [0.25]


def test_heartbeat_exception_counts_as_miss():
    class BrokenLink(FakeLink):
        def heartbeat(self, timeout):
            raise RuntimeError("serial port vanished")

    wd = Watchdog(BrokenLink((True,)), max_missed_heartbeats=2)
    assert wd.tick()["link_alive"] is False
    assert wd.tick()["estop_required"] is True


# ---------------------------------------------------------------------------
# escalation + edge detection
# ---------------------------------------------------------------------------

def test_estop_required_after_max_missed_heartbeats():
    wd, _ = make_watchdog((False,), max_missed_heartbeats=3)
    assert wd.tick()["estop_required"] is False
    assert wd.tick()["estop_required"] is False
    assert wd.tick()["estop_required"] is True


def test_escalated_fires_exactly_once_on_rising_edge():
    wd, _ = make_watchdog((False, False, False, False, True))
    results = [wd.tick() for _ in range(5)]
    escalations = [r["escalated"] for r in results]
    # only the 3rd tick crosses the threshold; staying failed is not a re-edge
    assert escalations == [False, False, True, False, False]
    # a recovered link clears the level, so a later fault may re-escalate
    assert results[4]["estop_required"] is False


def test_escalation_rearms_after_recovery():
    wd, _ = make_watchdog((False, False, True, False, False),
                          max_missed_heartbeats=2)
    escalations = [wd.tick()["escalated"] for _ in range(5)]
    assert escalations == [False, True, False, False, True]


# ---------------------------------------------------------------------------
# sensors
# ---------------------------------------------------------------------------

def test_critical_sensor_failure_forces_escalation():
    wd, _ = make_watchdog((True,), max_missed_heartbeats=5)
    wd.register_sensor("cliff", lambda: False, critical=True)
    result = wd.tick()
    assert result["estop_required"] is True
    assert result["escalated"] is True
    assert result["missed_heartbeats"] == 0  # link itself is fine


def test_non_critical_sensor_failure_does_not_escalate():
    wd, _ = make_watchdog((True,), max_missed_heartbeats=5)
    wd.register_sensor("camera", lambda: False, critical=False)
    result = wd.tick()
    assert result["estop_required"] is False
    assert result["escalated"] is False
    assert result["sensors"]["camera"] == {
        "ok": False, "critical": False, "failures": 1,
    }


def test_probe_exception_counts_as_failure():
    def boom():
        raise ValueError("i2c bus locked")

    wd, _ = make_watchdog((True,))
    wd.register_sensor("imu", boom, critical=True)
    result = wd.tick()
    assert result["sensors"]["imu"]["ok"] is False
    assert result["estop_required"] is True


def test_sensor_report_records_last_ok_and_failures():
    wd, _ = make_watchdog((True,))
    state = {"alive": True}
    wd.register_sensor("tof", lambda: state["alive"])
    wd.tick()  # ok at t=100.0
    status = wd.sensor_status("tof")
    assert status is not None
    assert status["failures"] == 0
    assert status["last_ok_s"] == pytest.approx(100.0)
    state["alive"] = False
    wd.tick()
    wd.tick()
    status = wd.sensor_status("tof")
    assert status is not None
    assert status["failures"] == 2
    assert status["last_ok_s"] == pytest.approx(100.0)  # unchanged


def test_unregister_sensor_stops_supervision():
    wd, _ = make_watchdog((True,))
    wd.register_sensor("lidar", lambda: False, critical=True)
    wd.unregister_sensor("lidar")
    result = wd.tick()
    assert result["sensors"] == {}
    assert result["estop_required"] is False
    assert wd.sensor_status("lidar") is None
    wd.unregister_sensor("lidar")  # unknown name: no-op, no error


# ---------------------------------------------------------------------------
# link_alive property
# ---------------------------------------------------------------------------

def test_link_alive_none_before_first_tick():
    wd, _ = make_watchdog((True,))
    assert wd.link_alive is None


def test_link_alive_reflects_last_tick():
    wd, _ = make_watchdog((True, False, True))
    wd.tick()
    assert wd.link_alive is True
    wd.tick()
    assert wd.link_alive is False
    wd.tick()
    assert wd.link_alive is True
