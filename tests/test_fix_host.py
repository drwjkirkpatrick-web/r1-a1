"""Regression tests for the host-side code-review fixes (docs/CODE_REVIEW.md).

Covers:
    F13 cli.py config path one directory too high
    F14 cli.py doctor() exit code ignores FAIL statuses
    F18 thermal fan boundary contradicts MIN_FAN_RPM comment
    F19 thermal host-rate pairs ΔT and Δt from different intervals
    F20 PowerMonitor.telemetry() reads the sensor twice
    F21 Memory.save() crashes on a bare-filename persist path
    F22 projector cooldown timer races with lamp relight
    F23 requirements.txt extras markers never install optional deps

All hardware is mocked; no devices required.
"""

import threading
import time
from pathlib import Path

import pytest

from src import cli
from src.brain.memory import Memory
from src.power.monitor import PowerMonitor
from src.projector import beam as beam_mod
from src.projector.beam import COOLDOWN_S, Beam
from src.thermal.monitor import FAN_COUNT, MIN_FAN_RPM, ThermalMonitor

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# F13 / F14 — src/cli.py
# ---------------------------------------------------------------------------

class TestCliConfigPath:
    def test_show_config_finds_repo_config_from_any_cwd(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)  # must not depend on the caller's cwd
        assert cli._show_config() == 0
        out = capsys.readouterr().out
        expected = (REPO_ROOT / "config" / "r1a1.yaml").read_text()
        assert out.strip() == expected.strip()

    def test_show_config_prints_real_file_not_parent_dir(self, monkeypatch, capsys):
        monkeypatch.chdir(REPO_ROOT)
        assert cli._show_config() == 0
        out = capsys.readouterr().out
        assert "Config file not found" not in out


class TestDoctorExitCode:
    CHECK_NAMES = [
        "_check_interconnect", "_check_brain", "_check_thermal", "_check_power",
        "_check_motion", "_check_awareness", "_check_eye", "_check_hermes_node",
        "_check_comms", "_check_personality", "_check_limbic", "_check_dashboard",
    ]

    def _patch_all_ok(self, monkeypatch):
        for name in self.CHECK_NAMES:
            monkeypatch.setattr(cli, name, lambda: "module OK")

    def test_fail_status_string_yields_nonzero_exit(self, monkeypatch, capsys):
        self._patch_all_ok(monkeypatch)
        monkeypatch.setattr(cli, "_check_interconnect", lambda: "FAIL import: boom")
        assert cli.doctor() == 1
        assert "FAIL" in capsys.readouterr().out

    def test_error_status_string_yields_nonzero_exit(self, monkeypatch, capsys):
        self._patch_all_ok(monkeypatch)

        def boom():
            raise RuntimeError("kaboom")

        monkeypatch.setattr(cli, "_check_power", boom)
        assert cli.doctor() == 1

    def test_all_ok_yields_zero_exit(self, monkeypatch, capsys):
        self._patch_all_ok(monkeypatch)
        assert cli.doctor() == 0

    def test_main_dispatches_doctor_exit_code(self, monkeypatch, capsys):
        self._patch_all_ok(monkeypatch)
        monkeypatch.setattr(cli, "_check_eye", lambda: "FAIL import: no camera")
        assert cli.main(["doctor"]) == 1


# ---------------------------------------------------------------------------
# F21 — src/brain/memory.py
# ---------------------------------------------------------------------------

class TestMemoryBareFilename:
    def test_save_with_bare_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mem = Memory(persist_path="memory.json")
        mem.remember("operator", "walker")
        mem.add_turn("user", "hello")
        mem.save()  # must not raise FileNotFoundError
        assert (tmp_path / "memory.json").exists()

    def test_bare_filename_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        mem = Memory(persist_path="memory.json", autosave=True)
        mem.remember("Name", "R1-A1")
        reloaded = Memory(persist_path="memory.json")
        assert reloaded.recall("name") == "R1-A1"

    def test_save_with_directory_path_still_works(self, tmp_path):
        target = tmp_path / "nested" / "dir" / "memory.json"
        mem = Memory(persist_path=str(target))
        mem.remember("k", "v")
        mem.save()
        assert target.exists()


# ---------------------------------------------------------------------------
# F20 — src/power/monitor.py
# ---------------------------------------------------------------------------

class TestPowerTelemetrySingleRead:
    def test_telemetry_reads_sensor_exactly_once(self):
        calls = []

        def reader():
            calls.append(1)
            return {"soc_pct": 55.0, "voltage_v": 12.1, "current_a": 0.4}

        mon = PowerMonitor(reader)
        tele = mon.telemetry()
        assert len(calls) == 1
        assert tele == {"soc_pct": 55.0, "voltage_v": 12.1, "current_a": 0.4}

    def test_telemetry_soc_is_clamped_from_the_same_read(self):
        # A reader whose value changes per call would previously leak the
        # second read into soc_pct; now one read feeds everything.
        reads = iter([{"soc_pct": 140.0, "voltage_v": 12.6}, {"soc_pct": 10.0}])
        mon = PowerMonitor(lambda: next(reads))
        tele = mon.telemetry()
        assert tele["soc_pct"] == 100.0  # clamped, and from read #1
        assert tele["voltage_v"] == 12.6

    def test_telemetry_with_float_reader(self):
        calls = []

        def reader():
            calls.append(1)
            return 42.0

        mon = PowerMonitor(reader)
        assert mon.telemetry() == {"soc_pct": 42.0}
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# F18 / F19 — src/thermal/monitor.py
# ---------------------------------------------------------------------------

def make_thermal(rpms=None, clock=None):
    rpms = rpms if rpms is not None else [3000] * FAN_COUNT
    return ThermalMonitor(
        host_reader=lambda: 40.0,
        bay_reader=lambda: 40.0,
        motor_bay_reader=lambda: 40.0,
        battery_reader=lambda: 30.0,
        fan_tach_reader=lambda i: rpms[i],
        clock=clock,
    )


class TestFanBoundary:
    def test_rpm_equal_to_min_counts_as_stalled(self):
        mon = make_thermal(rpms=[MIN_FAN_RPM] * FAN_COUNT)
        result = mon.fan_check()
        assert result["ok"] is False
        assert all(not f["ok"] for f in result["fans"].values())

    def test_rpm_just_above_min_is_healthy(self):
        mon = make_thermal(rpms=[MIN_FAN_RPM + 1] * FAN_COUNT)
        assert mon.fan_check()["ok"] is True

    def test_zero_rpm_is_stalled(self):
        mon = make_thermal(rpms=[0] * FAN_COUNT)
        assert mon.fan_check()["ok"] is False


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class TestHostRatePairing:
    def test_rate_none_until_two_samples(self):
        clock = FakeClock()
        mon = make_thermal(clock=clock)
        assert mon.host_rate_c_per_s() is None
        mon.report()
        assert mon.host_rate_c_per_s() is None

    def test_rate_uniform_interval(self):
        clock = FakeClock()
        temps = iter([30.0, 40.0])
        mon = make_thermal(clock=clock)
        mon._host_reader = lambda: next(temps)
        mon.report()                       # t=0, 30 °C
        clock.advance(10.0)
        mon.report()                       # t=10, 40 °C
        assert mon.host_rate_c_per_s() == pytest.approx(1.0)

    def test_rate_uses_matching_interval_under_jitter(self):
        """ΔT and Δt must come from the same interval (F19).

        Samples: (40 °C, t=0), (46 °C, t=3). Correct rate is 6/3 = 2.0.
        The buggy pairing (older ΔT over newer Δt) would give 10/3 ≈ 3.33.
        """
        clock = FakeClock()
        temps = iter([30.0, 40.0, 46.0])
        mon = make_thermal(clock=clock)
        mon._host_reader = lambda: next(temps)
        mon.report()                       # t=0,  30 °C
        clock.advance(10.0)
        mon.report()                       # t=10, 40 °C
        clock.advance(3.0)
        mon.report()                       # t=13, 46 °C
        assert mon.host_rate_c_per_s() == pytest.approx(2.0)

    def test_rate_none_when_timestamps_do_not_advance(self):
        mon = make_thermal(clock=lambda: 1.0)  # frozen clock
        mon.report()
        mon.report()
        assert mon.host_rate_c_per_s() is None


# ---------------------------------------------------------------------------
# F22 — src/projector/beam.py
# ---------------------------------------------------------------------------

class FakeTimer:
    """Deterministic stand-in for threading.Timer.

    fire() invokes the callback even after cancel() — exactly the lost
    cancel race a real threading.Timer can produce.
    """

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


class FakeTimerFactory:
    def __init__(self):
        self.timers = []

    def __call__(self, delay, callback):
        timer = FakeTimer(delay, callback)
        self.timers.append(timer)
        return timer

    @property
    def last(self):
        return self.timers[-1]


def make_beam():
    calls = []
    timers = FakeTimerFactory()
    beam = Beam(
        lamp_fn=lambda on: calls.append(("lamp", on)),
        fan_fn=lambda on: calls.append(("fan", on)),
        timer_factory=timers,
    )
    return beam, calls, timers


class TestCooldownRace:
    def test_normal_cooldown_still_works(self):
        beam, calls, timers = make_beam()
        beam.on()
        beam.off()
        assert beam.cooling_down
        timers.last.fire()
        assert ("fan", False) in calls
        assert not beam.cooling_down

    def test_stale_timer_fire_after_relight_keeps_fan_on(self):
        """The lost-race case: on() cancels, but the timer callback runs
        anyway (already started on the timer thread). The fan must NOT be
        turned off after the lamp was relit."""
        beam, calls, timers = make_beam()
        beam.on()
        beam.off()
        timer = timers.last
        beam.on()                      # cancel loses the race...
        timer.fire()                   # ...callback fires anyway
        assert beam.is_on
        assert ("fan", False) not in calls
        # Last fan call is the relight's fan-on.
        fan_calls = [c for c in calls if c[0] == "fan"]
        assert fan_calls[-1] == ("fan", True)

    def test_superseded_timer_cannot_kill_fan(self):
        """off(); off(); the first (replaced) timer firing must be a no-op;
        only the live timer stops the fan."""
        beam, calls, timers = make_beam()
        beam.on()
        beam.off()
        first = timers.last
        beam.off()
        first.fire()                   # stale — must not stop the fan
        assert ("fan", False) not in calls
        assert beam.cooling_down
        timers.last.fire()             # the live one still works
        assert ("fan", False) in calls
        assert not beam.cooling_down

    def test_concurrent_on_off_never_leaves_lamp_lit_fan_off(self, monkeypatch):
        """Stress the real-thread race: rapid on/off cycling with a short
        real cooldown must never end in the forbidden state (lamp on,
        fan off)."""
        monkeypatch.setattr(beam_mod, "COOLDOWN_S", 0.005)
        state_lock = threading.Lock()
        events = []

        def record(name):
            def fn(on):
                with state_lock:
                    events.append((name, on))
            return fn

        beam = Beam(lamp_fn=record("lamp"), fan_fn=record("fan"))
        try:
            for _ in range(100):
                beam.on()
                beam.off()
                beam.on()
            time.sleep(0.2)  # let every pending timer fire
        finally:
            beam.off()
            time.sleep(0.2)

        # Invariant: at no point may a fan-off follow a lamp-on without an
        # intervening lamp-off. Equivalent: whenever the lamp is lit, the
        # fan is on. Check pairwise ordering over the event log.
        lamp_on = False
        fan_on = False
        for name, on in events:
            if name == "lamp":
                lamp_on = on
            else:
                fan_on = on
                if not on:
                    assert not lamp_on, "fan stopped while lamp was lit (F22)"


# ---------------------------------------------------------------------------
# F23 — requirements.txt
# ---------------------------------------------------------------------------

def _req_lines(path):
    return [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


class TestRequirements:
    def test_no_extras_markers_in_requirements(self):
        for line in _req_lines(REPO_ROOT / "requirements.txt"):
            assert "extra ==" not in line, f"invalid extras marker survived: {line}"

    def test_core_deps_kept(self):
        lines = _req_lines(REPO_ROOT / "requirements.txt")
        assert any(l.startswith("requests") for l in lines)
        assert any(l.startswith("pyserial") for l in lines)
        assert any(l.startswith("pytest") for l in lines)

    def test_optional_deps_split_into_own_files(self):
        dashboard = _req_lines(REPO_ROOT / "requirements-dashboard.txt")
        exoplanet = _req_lines(REPO_ROOT / "requirements-exoplanet.txt")
        assert any(l.startswith("flask") for l in dashboard)
        assert any(l.startswith("lightkurve") for l in exoplanet)
        assert any(l.startswith("numpy") for l in exoplanet)

    def test_split_files_parse_as_plain_requirements(self):
        # Every requirement line must be a plain name[op][version] spec —
        # no markers other than platform_system (which pip does support).
        for fname in ("requirements.txt", "requirements-dashboard.txt",
                      "requirements-exoplanet.txt"):
            for line in _req_lines(REPO_ROOT / fname):
                if ";" in line:
                    marker = line.split(";", 1)[1]
                    assert "extra" not in marker
