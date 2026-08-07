"""Tests for the Hermes agent node client (src/hermesnode).

All network access is replaced by a FakeHttpClient — no sockets are opened.
The fake records calls (so we can assert method/url/payload/timeout) and
serves canned responses or raises programmed exceptions per URL path.
"""

from __future__ import annotations

import pytest

from src.hermesnode import HermesNode, HermesNodeError


class FakeHttpClient:
    """Injectable stand-in for requests: path -> response dict or exception."""

    def __init__(self, responses=None, errors=None):
        self.responses = responses or {}
        self.errors = errors or {}
        self.calls = []  # (method, url, json_payload, timeout)

    def __call__(self, method, url, json_payload, timeout):
        self.calls.append((method, url, json_payload, timeout))
        path = url.split("127.0.0.1:9299")[-1]  # strip default base
        if path in self.errors:
            raise self.errors[path]
        return self.responses.get(path, {"ok": True})


class FakeClock:
    """Controllable monotonic clock for last_contact assertions."""

    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return FakeClock()


def make_node(fake=None, clock=None, **kwargs):
    fake = fake or FakeHttpClient()
    clock = clock or FakeClock()
    return HermesNode(http_client=fake, clock=clock, **kwargs), fake, clock


def test_health_happy_path(clock):
    fake = FakeHttpClient({"/health": {"ok": True, "node_id": "dome-hermes-01",
                                       "uptime_s": 42.0}})
    node, _, _ = make_node(fake, clock)
    result = node.health()
    assert result["ok"] is True
    assert result["node_id"] == "dome-hermes-01"
    method, url, payload, timeout = fake.calls[0]
    assert (method, url) == ("GET", "http://127.0.0.1:9299/health")
    assert payload is None and timeout == 5.0


def test_state_happy_path():
    fake = FakeHttpClient({"/state": {"remedy": "chamomilla", "profile": "calm"}})
    node, _, _ = make_node(fake)
    assert node.state() == {"remedy": "chamomilla", "profile": "calm"}


def test_ask_happy_path():
    fake = FakeHttpClient({"/prompt": {"reply": "Beep boop, at your service."}})
    node, _, _ = make_node(fake)
    reply = node.ask("Status report?")
    assert reply == "Beep boop, at your service."
    assert fake.calls[0][2] == {"text": "Status report?"}
    assert fake.calls[0][0] == "POST"


def test_set_personality_happy_path():
    fake = FakeHttpClient({"/personality": {"remedy": "nux-vomica", "emoji": "😤"}})
    node, _, _ = make_node(fake)
    result = node.set_personality("nux-vomica")
    assert result == {"remedy": "nux-vomica", "emoji": "😤"}
    assert fake.calls[0][2] == {"remedy": "nux-vomica"}


def test_set_limbic_happy_path():
    vad = {"valence": 0.4, "arousal": -0.2, "dominance": 0.1}
    fake = FakeHttpClient({"/limbic": {"profile": "calm", "vad": vad}})
    node, _, _ = make_node(fake)
    result = node.set_limbic("calm")
    assert result["profile"] == "calm"
    assert result["vad"] == vad
    assert fake.calls[0][2] == {"profile": "calm"}


def test_health_raises_on_unreachable():
    fake = FakeHttpClient(errors={"/health": ConnectionError("slip-ring down")})
    node, _, _ = make_node(fake)
    with pytest.raises(HermesNodeError, match="/health"):
        node.health()


def test_ask_raises_on_timeout():
    fake = FakeHttpClient(errors={"/prompt": TimeoutError("read timed out")})
    node, _, _ = make_node(fake)
    with pytest.raises(HermesNodeError, match="timed out"):
        node.ask("hello")


def test_state_raises_on_http_error():
    fake = FakeHttpClient(errors={"/state": RuntimeError("500 Server Error")})
    node, _, _ = make_node(fake)
    with pytest.raises(HermesNodeError):
        node.state()


def test_health_raises_when_node_reports_not_ok():
    fake = FakeHttpClient({"/health": {"ok": False, "node_id": "dome-hermes-01"}})
    node, _, _ = make_node(fake)
    with pytest.raises(HermesNodeError, match="unhealthy"):
        node.health()


def test_ask_raises_on_missing_reply():
    fake = FakeHttpClient({"/prompt": {"status": "busy"}})
    node, _, _ = make_node(fake)
    with pytest.raises(HermesNodeError, match="reply"):
        node.ask("ping")


def test_non_dict_response_raises():
    fake = FakeHttpClient({"/state": ["not", "a", "dict"]})
    node, _, _ = make_node(fake)
    with pytest.raises(HermesNodeError, match="non-dict"):
        node.state()


def test_is_alive_true_when_healthy():
    fake = FakeHttpClient({"/health": {"ok": True, "node_id": "x", "uptime_s": 1}})
    node, _, _ = make_node(fake)
    assert node.is_alive() is True


def test_is_alive_false_on_failure_without_raising():
    fake = FakeHttpClient(errors={"/health": ConnectionError("unreachable")})
    node, _, _ = make_node(fake)
    assert node.is_alive() is False


def test_last_contact_none_until_first_success(clock):
    fake = FakeHttpClient({"/health": {"ok": True}})
    node, _, _ = make_node(fake, clock)
    assert node.last_contact_s is None
    node.health()
    assert node.last_contact_s == 1000.0
    clock.now = 1012.5
    node.health()
    assert node.last_contact_s == 1012.5


def test_last_contact_not_updated_on_failure(clock):
    good = FakeHttpClient({"/health": {"ok": True}})
    node, fake, clock = make_node(good, clock)
    node.health()
    assert node.last_contact_s == 1000.0
    clock.now = 2000.0
    fake.errors["/health"] = ConnectionError("dropped")
    with pytest.raises(HermesNodeError):
        node.health()
    assert node.last_contact_s == 1000.0  # unchanged by the failed call


def test_custom_base_url_and_timeout():
    fake = FakeHttpClient()
    node = HermesNode(base_url="http://10.0.0.42:9299/", timeout=2.5,
                      node_id="dome-hermes-02", http_client=fake,
                      clock=FakeClock())
    node.state()
    method, url, payload, timeout = fake.calls[0]
    assert url == "http://10.0.0.42:9299/state"  # trailing slash stripped
    assert timeout == 2.5
    assert node.node_id == "dome-hermes-02"
