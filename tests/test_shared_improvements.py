"""Tests for the v0.5.0 shared-file improvements.

Covers the parent-owned edits: memory persistence, LLM session/keep_alive,
SerialLink retry, drive odometry freshness, power validation, thermal
trend, dome scan/center, center-leg guards, and agent context + safe
generate.
"""

import math
import os
import tempfile

import pytest

from src.brain.memory import Memory
from src.brain.llm_client import LLMClient
from src.brain.agent import Agent
from src.interconnect.link import SerialLink, LinkError, LinkTimeout
from src.motion.drive import Drive
from src.motion.dome import Dome
from src.motion.center_leg import CenterLeg
from src.power.monitor import PowerMonitor
from src.thermal.monitor import ThermalMonitor


# ─── Memory persistence ──────────────────────────────────────────────

class TestMemoryPersistence:
    def test_facts_survive_roundtrip(self, tmp_path):
        path = str(tmp_path / "mem.json")
        m1 = Memory(persist_path=path)
        m1.remember("name", "Walker")
        m1.add_turn("user", "hello")
        m1.save()
        m2 = Memory(persist_path=path)
        assert m2.recall("name") == "Walker"
        assert ("user", "hello") in list(m2.turns)

    def test_autosave_writes_on_remember(self, tmp_path):
        path = str(tmp_path / "mem.json")
        m = Memory(persist_path=path, autosave=True)
        m.remember("color", "blue")
        assert os.path.exists(path)

    def test_corrupt_file_loads_fresh(self, tmp_path):
        path = tmp_path / "mem.json"
        path.write_text("{not json")
        m = Memory(persist_path=str(path))  # must not raise
        assert m.facts == {}

    def test_no_persist_path_is_noop(self):
        m = Memory()
        m.remember("x", "y")
        m.save()  # must not raise


# ─── LLM keep_alive / session ────────────────────────────────────────

class TestLLMKeepAlive:
    def _client(self):
        calls = []

        def fake(url, payload, timeout):
            calls.append(payload)
            return {"response": "ok"}

        return LLMClient(http_client=fake), calls

    def test_generate_includes_keep_alive(self):
        client, calls = self._client()
        client.generate("hi")
        assert calls[0]["keep_alive"] == "30m"

    def test_keep_alive_override(self):
        client, calls = self._client()
        client.generate("hi", keep_alive="0")
        assert calls[0]["keep_alive"] == "0"

    def test_payload_still_has_model_and_prompt(self):
        client, calls = self._client()
        client.generate("hello")
        assert calls[0]["model"] == "qwen2.5:3b"
        assert calls[0]["prompt"] == "hello"


# ─── SerialLink retry ────────────────────────────────────────────────

class _FlakySerial:
    """Serial fake whose read() returns scripted byte chunks."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.written = []

    def write(self, b):
        self.written.append(b)

    def read(self, n):
        return self._chunks.pop(0) if self._chunks else b""


class TestSerialRetry:
    def _link(self, chunks, retry_count):
        serial = _FlakySerial(chunks)
        link = SerialLink(
            "/dev/fake",
            serial_factory=lambda p, b, t: serial,
            retry_count=retry_count,
            sleeper=lambda s: None,
        )
        return link, serial

    def _frame_bytes(self):
        import json
        link, _ = SerialLink.__new__(SerialLink), None
        # build a valid frame via a real link
        l2, _ = self._link([], 0)
        return l2.encode_frame("echo", 0, "x")

    def test_retry_recovers_from_transient_timeout(self):
        link, _ = self._link([], retry_count=1)
        orig_recv = link.recv
        state = {"calls": 0}

        def flaky_recv(timeout=1.0):
            state["calls"] += 1
            if state["calls"] == 1:
                raise LinkTimeout("simulated transient dropout")
            return orig_recv(timeout=timeout)

        link.recv = flaky_recv
        link._serial.read = lambda n: self._frame_bytes()
        frame = link.roundtrip("echo", "x", timeout=0.5)
        assert frame["cmd"] == "echo"
        assert state["calls"] == 2

    def test_retry_exhaustion_raises(self):
        link, _ = self._link([], retry_count=2)

        def always_timeout(timeout=1.0):
            raise LinkTimeout("dead")

        link.recv = always_timeout
        with pytest.raises(LinkTimeout):
            link.roundtrip("echo", "x", timeout=0.1)

    def test_zero_retry_preserves_one_shot(self):
        link, _ = self._link([], retry_count=0)

        def always_timeout(timeout=1.0):
            raise LinkTimeout("dead")

        link.recv = always_timeout
        with pytest.raises(LinkTimeout):
            link.roundtrip("echo", "x", timeout=0.1)


# ─── Drive odometry freshness ────────────────────────────────────────

class _FakeLink:
    def __init__(self):
        self.sent = []

    def send(self, cmd, payload):
        self.sent.append((cmd, payload))


class TestDriveOdometry:
    def test_odometry_dict_shape(self):
        d = Drive(_FakeLink())
        odo = d.odometry()
        assert set(odo) >= {"x", "y", "heading_deg", "age_s"}

    def test_age_increases(self):
        t = [0.0]
        d = Drive(_FakeLink(), clock=lambda: t[0])
        d.forward(1.0, 0.5)
        t[0] = 5.0
        assert d.odometry_age_s() == pytest.approx(5.0)

    def test_odometry_read_tuple_unchanged(self):
        d = Drive(_FakeLink())
        d.forward(1.0, 0.5)
        x, y, h = d.odometry_read()
        assert (x, h) == (1.0, 0.0)


# ─── Power validation ────────────────────────────────────────────────

class TestPowerValidation:
    def test_nan_soc_raises(self):
        pm = PowerMonitor(lambda: float("nan"))
        with pytest.raises(ValueError):
            pm.soc()

    def test_inf_soc_raises(self):
        pm = PowerMonitor(lambda: float("inf"))
        with pytest.raises(ValueError):
            pm.soc()

    def test_dict_nan_raises(self):
        pm = PowerMonitor(lambda: {"soc_pct": float("nan")})
        with pytest.raises(ValueError):
            pm.soc()

    def test_valid_soc_still_clamped(self):
        pm = PowerMonitor(lambda: 150.0)
        assert pm.soc() == 100.0


# ─── Thermal trend ───────────────────────────────────────────────────

class TestThermalTrend:
    def _monitor(self, temps, times):
        ti = iter(temps)
        ci = iter(times)
        return ThermalMonitor(
            host_reader=lambda: next(ti),
            bay_reader=lambda: 40.0,
            motor_bay_reader=lambda: 40.0,
            clock=lambda: next(ci),
        )

    def test_first_sample_no_trend(self):
        m = ThermalMonitor(lambda: 50.0, lambda: 40.0, lambda: 40.0)
        m.report()
        assert m.host_rate_c_per_s() is None

    def test_rising_trend_positive(self):
        m = self._monitor([50.0, 60.0], [0.0, 10.0])
        m.report()
        m.report()
        rate = m.host_rate_c_per_s()
        assert rate == pytest.approx(1.0)  # 10°C / 10 s

    def test_cooling_trend_negative(self):
        m = self._monitor([60.0, 50.0], [0.0, 10.0])
        m.report()
        m.report()
        assert m.host_rate_c_per_s() == pytest.approx(-1.0)


# ─── Dome scan / center ──────────────────────────────────────────────

class TestDomeImprovements:
    def test_scan_expression(self):
        link = _FakeLink()
        d = Dome(link)
        d.express("scan")
        cmds = [c for c, _ in link.sent]
        assert cmds == ["dome.rotate"] * 3

    def test_center_returns_to_zero(self):
        link = _FakeLink()
        d = Dome(link)
        d.rotate_deg(120.0)
        d.center()
        assert d.position_deg == pytest.approx(0.0)

    def test_unknown_expression_still_raises(self):
        with pytest.raises(ValueError):
            Dome(_FakeLink()).express("backflip")


# ─── Center-leg guards ───────────────────────────────────────────────

class TestCenterLegGuards:
    def test_deploy_idempotent(self):
        link = _FakeLink()
        leg = CenterLeg(link)
        leg.deploy()
        leg.deploy()  # second call must not re-command
        assert len(link.sent) == 1

    def test_retract_idempotent(self):
        link = _FakeLink()
        leg = CenterLeg(link)
        leg.retract()  # retract while stowed: no command
        assert len(link.sent) == 0

    def test_drive_guard_raises_when_deployed(self):
        leg = CenterLeg(_FakeLink())
        leg.deploy()
        with pytest.raises(RuntimeError, match="retract"):
            leg.drive_guard(Drive(_FakeLink()))

    def test_drive_guard_passes_when_stowed(self):
        leg = CenterLeg(_FakeLink())
        leg.drive_guard(Drive(_FakeLink()))  # must not raise


# ─── Agent context + safe generate ───────────────────────────────────

class _FakeLLM:
    def __init__(self, fail=False):
        self.fail = fail
        self.prompts = []

    def generate(self, prompt, model=None, keep_alive=None):
        self.prompts.append(prompt)
        if self.fail:
            raise ConnectionError("server down")
        return "beep boop"

    def current_model(self):
        return "fake:1b"

    def switch_to_fallback(self):
        return "fake:small"

    def switch_to_primary(self):
        return "fake:1b"


class TestAgentWiring:
    def test_context_included_on_second_turn(self):
        llm = _FakeLLM()
        agent = Agent(llm=llm)
        agent.handle("tell me about astromechs")
        agent.handle("what makes them special?")
        # second prompt should carry the first turn as context
        assert "astromechs" in llm.prompts[1]
        assert "Conversation so far" in llm.prompts[1]

    def test_context_disabled_when_zero(self):
        llm = _FakeLLM()
        agent = Agent(llm=llm, context_turns=0)
        agent.handle("first")
        agent.handle("second")
        assert "Conversation so far" not in llm.prompts[1]

    def test_llm_failure_returns_fallback_utterance(self):
        agent = Agent(llm=_FakeLLM(fail=True))
        reply = agent.handle("tell me something")
        assert "tangled" in reply.lower()

    def test_empty_prompt_handled(self):
        agent = Agent(llm=_FakeLLM())
        assert "catch" in agent.handle("   ").lower()

    def test_meta_prompts_bypass_llm(self):
        llm = _FakeLLM()
        agent = Agent(llm=llm)
        agent.handle("remember that my name is Walker")
        assert llm.prompts == []  # LLM never called
