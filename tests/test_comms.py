"""Tests for the comms stack (src/comms/stack.py).

Fakes mirror the injected-hardware convention: GPS is a plain callable,
cellular/wifi are small duck-typed stand-ins. A FakeClock lets us advance
monotonic time without sleeping, so the 30 s connect cooldown is tested
deterministically.
"""

from __future__ import annotations

from typing import Optional

import pytest

from src.comms import CommsError, CommsStack


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

class FakeClock:
    """Manually advanced monotonic clock."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def make_gps(fix=True, lat=45.5231, lon=-122.6765, sats=11, alt_m: Optional[float] = 15.2):
    """Factory returning a gps_reader callable over a fixed reading."""
    reading = {"lat": lat, "lon": lon, "fix": fix, "sats": sats, "alt_m": alt_m}
    return lambda: dict(reading)


class FakeCellular:
    def __init__(self, connected=False, signal=72, connect_succeeds=True):
        self._connected = connected
        self._signal = signal
        self._connect_succeeds = connect_succeeds
        self.connect_calls = 0

    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        self.connect_calls += 1
        if self._connect_succeeds:
            self._connected = True
        return self._connect_succeeds

    def signal_pct(self) -> int:
        return self._signal


class FakeWifi:
    def __init__(self, connected=True, ssid="R1A1-AP", clients=1):
        self._connected = connected
        self._ssid = ssid
        self._clients = clients

    def connected(self) -> bool:
        return self._connected

    def ssid(self) -> str:
        return self._ssid

    def clients(self) -> int:
        return self._clients


# --------------------------------------------------------------------------
# No hardware wired
# --------------------------------------------------------------------------

def test_no_hardware_gps_is_none_and_has_no_fix():
    stack = CommsStack()
    assert stack.gps_fix() is None
    assert stack.has_fix() is False
    assert stack.position() is None


def test_no_hardware_wan_is_offline():
    stack = CommsStack()
    wan = stack.wan_status()
    assert wan == {
        "wifi_connected": False,
        "wifi_ssid": None,
        "cellular_connected": False,
        "cellular_signal_pct": None,
        "active": "offline",
        "failover_active": False,
    }


def test_no_hardware_status_combines_gps_and_wan():
    stack = CommsStack()
    status = stack.status()
    assert status["gps"] is None
    assert status["wan"]["active"] == "offline"


# --------------------------------------------------------------------------
# GPS
# --------------------------------------------------------------------------

def test_gps_fix_happy_path_includes_zero_age():
    clock = FakeClock()
    stack = CommsStack(gps_reader=make_gps(), clock=clock)
    fix = stack.gps_fix()
    assert fix is not None
    assert fix["lat"] == pytest.approx(45.5231)
    assert fix["lon"] == pytest.approx(-122.6765)
    assert fix["fix"] is True
    assert fix["sats"] == 11
    assert fix["alt_m"] == pytest.approx(15.2)
    assert fix["age_s"] == 0.0  # this very reading has the fix


def test_gps_age_grows_after_fix_lost():
    clock = FakeClock()
    good = make_gps(fix=True)
    stack = CommsStack(gps_reader=good, clock=clock)
    stack.gps_fix()  # acquire fix at t=1000
    clock.advance(12.0)
    # Receiver now reports no fix; age_s should measure staleness.
    stack._gps_reader = make_gps(fix=False, sats=0, alt_m=None)
    fix = stack.gps_fix()
    assert fix is not None
    assert fix["fix"] is False
    assert fix["age_s"] == pytest.approx(12.0)


def test_gps_age_none_when_never_fixed():
    stack = CommsStack(gps_reader=make_gps(fix=False, sats=0, alt_m=None))
    fix = stack.gps_fix()
    assert fix is not None
    assert fix["age_s"] is None


@pytest.mark.parametrize(
    "bad",
    [
        "not a dict",
        {"lat": 1.0, "lon": 2.0},                       # missing keys
        {"lat": "x", "lon": 2.0, "fix": True, "sats": 5, "alt_m": None},
        {"lat": 91.0, "lon": 2.0, "fix": True, "sats": 5, "alt_m": None},
        {"lat": 1.0, "lon": 2.0, "fix": True, "sats": "many", "alt_m": None},
        {"lat": 1.0, "lon": 2.0, "fix": True, "sats": 5, "alt_m": "high"},
    ],
)
def test_malformed_gps_reading_raises_comms_error(bad):
    stack = CommsStack(gps_reader=lambda: bad)
    with pytest.raises(CommsError):
        stack.gps_fix()


def test_position_and_has_fix_with_lock():
    stack = CommsStack(gps_reader=make_gps(lat=10.0, lon=20.0))
    assert stack.has_fix() is True
    pos = stack.position()
    assert pos is not None
    assert pos[0] == pytest.approx(10.0)
    assert pos[1] == pytest.approx(20.0)


def test_position_none_without_fix():
    stack = CommsStack(gps_reader=make_gps(fix=False, sats=2, alt_m=None))
    assert stack.has_fix() is False
    assert stack.position() is None


# --------------------------------------------------------------------------
# WAN status transitions
# --------------------------------------------------------------------------

def test_wan_status_wifi_preferred_when_both_up():
    stack = CommsStack(cellular=FakeCellular(connected=True), wifi=FakeWifi())
    wan = stack.wan_status()
    assert wan["active"] == "wifi"
    assert wan["wifi_ssid"] == "R1A1-AP"
    assert wan["failover_active"] is False
    assert wan["cellular_signal_pct"] == 72


def test_wan_status_failover_to_cellular_when_wifi_down():
    stack = CommsStack(
        cellular=FakeCellular(connected=True, signal=55),
        wifi=FakeWifi(connected=False),
    )
    wan = stack.wan_status()
    assert wan["active"] == "cellular"
    assert wan["failover_active"] is True
    assert wan["wifi_ssid"] is None
    assert wan["cellular_signal_pct"] == 55


def test_wan_status_offline_when_neither_path():
    stack = CommsStack(cellular=FakeCellular(), wifi=FakeWifi(connected=False))
    wan = stack.wan_status()
    assert wan["active"] == "offline"
    assert wan["failover_active"] is False
    assert wan["cellular_signal_pct"] is None


# --------------------------------------------------------------------------
# ensure_wan
# --------------------------------------------------------------------------

def test_ensure_wan_connects_cellular_when_wifi_down():
    cell = FakeCellular(connected=False)
    stack = CommsStack(cellular=cell, wifi=FakeWifi(connected=False))
    wan = stack.ensure_wan()
    assert cell.connect_calls == 1
    assert wan["active"] == "cellular"
    assert wan["failover_active"] is True


def test_ensure_wan_noop_when_wifi_up():
    cell = FakeCellular(connected=False)
    stack = CommsStack(cellular=cell, wifi=FakeWifi(connected=True))
    wan = stack.ensure_wan()
    assert cell.connect_calls == 0
    assert wan["active"] == "wifi"


def test_ensure_wan_noop_without_cellular_hardware():
    stack = CommsStack(wifi=FakeWifi(connected=False))
    wan = stack.ensure_wan()
    assert wan["active"] == "offline"


def test_ensure_wan_respects_30s_cooldown():
    clock = FakeClock()
    cell = FakeCellular(connected=False, connect_succeeds=False)
    stack = CommsStack(cellular=cell, wifi=FakeWifi(connected=False), clock=clock)
    stack.ensure_wan()
    clock.advance(5.0)
    stack.ensure_wan()
    clock.advance(20.0)
    stack.ensure_wan()
    assert cell.connect_calls == 1  # hammering within the window is suppressed
    clock.advance(31.0)
    stack.ensure_wan()
    assert cell.connect_calls == 2  # cooldown elapsed — retry allowed


def test_ensure_wan_returns_wan_status_dict():
    stack = CommsStack(wifi=FakeWifi())
    wan = stack.ensure_wan()
    assert set(wan) == {
        "wifi_connected",
        "wifi_ssid",
        "cellular_connected",
        "cellular_signal_pct",
        "active",
        "failover_active",
    }
