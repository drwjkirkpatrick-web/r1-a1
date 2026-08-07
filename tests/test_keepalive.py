"""Tests for src.brain.keepalive.KeepAlive.

A small stub LLM plus a fake clock keep everything deterministic — no
Ollama server, no real sleeping (same injectable-callable convention the
rest of the codebase uses for hardware).
"""

import pytest

from src.brain.keepalive import KeepAlive


class FakeLLM:
    """Minimal duck-typed stand-in for src.brain.llm_client.LLMClient."""

    def __init__(self, reply="pong"):
        self.primary_model = "big:70b"
        self.fallback_model = "small:2b"
        self._active = self.primary_model
        self.reply = reply
        self.calls = []          # list of (prompt, model) actually sent
        self.fail_next = 0       # raise on this many upcoming generate()s

    def generate(self, prompt, model=None):
        self.calls.append((prompt, model))
        if self.fail_next > 0:
            self.fail_next -= 1
            raise ConnectionError("ollama is gone")
        return self.reply

    def current_model(self):
        return self._active

    def switch_to_fallback(self):
        self._active = self.fallback_model
        return self._active

    def switch_to_primary(self):
        self._active = self.primary_model
        return self._active


class FakeClock:
    """Manually advanced monotonic clock."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make_keepalive(**kwargs):
    llm = kwargs.pop("llm", FakeLLM())
    clock = kwargs.pop("clock", FakeClock())
    ka = KeepAlive(llm, clock=clock, sleeper=lambda s: None, **kwargs)
    return ka, llm, clock


# ------------------------------------------------------------------
# ping()
# ------------------------------------------------------------------

def test_ping_success_returns_true_and_stamps_last_ok():
    ka, llm, clock = make_keepalive()
    assert ka.ping() is True
    assert llm.calls == [("ping", "big:70b")]
    assert ka.consecutive_failures == 0
    assert ka.last_ok_s == clock.now


def test_ping_failure_returns_false_and_counts():
    ka, llm, _ = make_keepalive(llm=FakeLLM())
    llm.fail_next = 1
    assert ka.ping() is False
    assert ka.consecutive_failures == 1
    assert ka.last_ok_s is None


def test_ping_empty_reply_counts_as_failure():
    ka, _, _ = make_keepalive(llm=FakeLLM(reply=""))
    assert ka.ping() is False
    assert ka.consecutive_failures == 1


def test_ping_success_resets_failure_counter():
    ka, llm, _ = make_keepalive()
    llm.fail_next = 1
    ka.ping()
    assert ka.consecutive_failures == 1
    assert ka.ping() is True
    assert ka.consecutive_failures == 0


# ------------------------------------------------------------------
# tick()
# ------------------------------------------------------------------

def test_first_tick_pings_immediately():
    ka, llm, _ = make_keepalive()
    status = ka.tick()
    assert len(llm.calls) == 1
    assert status["alive"] is True
    assert status["model"] == "big:70b"
    assert status["auto_fallback"] is False
    assert status["consecutive_failures"] == 0
    assert status["last_ok_s"] is not None


def test_tick_before_interval_does_not_ping_again():
    ka, llm, clock = make_keepalive(ping_interval_s=30.0)
    ka.tick()
    clock.advance(10.0)
    ka.tick()
    assert len(llm.calls) == 1  # still just the first ping


def test_tick_after_interval_pings_again():
    ka, llm, clock = make_keepalive(ping_interval_s=30.0)
    ka.tick()
    clock.advance(31.0)
    ka.tick()
    assert len(llm.calls) == 2


def test_tick_auto_fallback_after_max_failures():
    ka, llm, clock = make_keepalive(ping_interval_s=30.0, max_consecutive_failures=2)
    llm.fail_next = 10
    status1 = ka.tick()               # failure #1
    assert status1["auto_fallback"] is False
    clock.advance(31.0)
    status2 = ka.tick()               # failure #2 -> switch
    assert status2["auto_fallback"] is True
    assert status2["model"] == "small:2b"
    assert llm.current_model() == "small:2b"


def test_tick_does_not_switch_twice_when_already_on_fallback():
    ka, llm, clock = make_keepalive(ping_interval_s=30.0, max_consecutive_failures=2)
    llm.fail_next = 10
    ka.tick()
    clock.advance(31.0)
    ka.tick()                          # triggers fallback
    clock.advance(31.0)
    status = ka.tick()                 # still failing, but already on fallback
    assert status["auto_fallback"] is False
    assert status["alive"] is False
    assert status["consecutive_failures"] >= 2


# ------------------------------------------------------------------
# generate() pass-through
# ------------------------------------------------------------------

def test_generate_pass_through_resets_failures_on_success():
    ka, llm, _ = make_keepalive()
    llm.fail_next = 1
    ka.ping()                          # 1 failure on the books
    out = ka.generate("Hello R1")
    assert out == "pong"
    assert llm.calls[-1] == ("Hello R1", "big:70b")
    assert ka.consecutive_failures == 0
    assert ka.alive is True


def test_generate_failure_increments_and_reraises():
    ka, llm, _ = make_keepalive()
    llm.fail_next = 1
    with pytest.raises(ConnectionError):
        ka.generate("Hello R1")
    assert ka.consecutive_failures == 1
    assert ka.alive is False


# ------------------------------------------------------------------
# Properties
# ------------------------------------------------------------------

def test_using_fallback_property_tracks_active_model():
    ka, llm, _ = make_keepalive()
    assert ka.using_fallback is False
    llm.switch_to_fallback()
    assert ka.using_fallback is True


def test_using_fallback_false_when_client_lacks_fallback_model_attr():
    class BareLLM:
        def __init__(self):
            self._m = "only:model"

        def generate(self, prompt, model=None):
            return "ok"

        def current_model(self):
            return self._m

        def switch_to_fallback(self):
            return self._m

        def switch_to_primary(self):
            return self._m

    ka = KeepAlive(BareLLM(), clock=FakeClock(), sleeper=lambda s: None)
    assert ka.using_fallback is False
