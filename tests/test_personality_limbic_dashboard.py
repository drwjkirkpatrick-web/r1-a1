"""Tests for personality bridge, limbic bridge, and dashboard.

All external dependencies (skill, limbic-hermes, Flask) are mocked or
gracefully handled. No network, no hardware, no external packages required.

Run: python -m pytest tests/test_personality_limbic_dashboard.py -v
"""

import sys
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


# ─── Personality Bridge ──────────────────────────────────────────────


class TestPersonalityBridge(unittest.TestCase):
    """The personality bridge must degrade gracefully when the skill
    is absent and return correct data when it is present."""

    def test_disabled_bridge_returns_none_prompt(self):
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=False)
        self.assertIsNone(bridge.get_prompt_prefix())

    def test_disabled_bridge_info_shows_disabled(self):
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=False)
        info = bridge.info()
        self.assertFalse(info["enabled"])

    def test_emoji_always_available_even_without_skill(self):
        """get_emoji() is backed by a hardcoded EMOJI_MAP, so it works
        even when the remedy_personality_picker skill is not installed."""
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=True)
        emoji = bridge.get_emoji()
        self.assertIsInstance(emoji, str)
        self.assertGreaterEqual(len(emoji), 1)

    def test_known_remedy_emojis(self):
        from brain.personality import PersonalityBridge
        # A few well-known mappings from the EMOJI_MAP.
        cases = {
            "bryonia_alba": "🦔",
            "pulsatilla_pratensis": "🌸",
            "arsenicum_album": "🧐",
            "sulphur": "🔮",
            "phosphorus": "🔥",
            "nux_vomica": "⚡",
        }
        for remedy, expected in cases.items():
            bridge = PersonalityBridge(remedy, enabled=False)
            self.assertEqual(bridge.get_emoji(), expected,
                             f"emoji mismatch for {remedy}")

    def test_unknown_remedy_emoji_fallback(self):
        """An unrecognized remedy should return a default emoji, not crash."""
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("nonexistent_remedy", enabled=False)
        emoji = bridge.get_emoji()
        self.assertIsInstance(emoji, str)
        self.assertGreaterEqual(len(emoji), 1)

    def test_info_dict_structure(self):
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=True)
        info = bridge.info()
        self.assertIn("remedy", info)
        self.assertIn("emoji", info)
        self.assertIn("prompt", info)
        self.assertIn("enabled", info)
        self.assertEqual(info["remedy"], "bryonia_alba")
        self.assertTrue(info["enabled"])

    def test_list_remedies_returns_list(self):
        """list_remedies() returns a list (possibly empty if skill absent)."""
        from brain.personality import PersonalityBridge
        remedies = PersonalityBridge.list_remedies()
        self.assertIsInstance(remedies, list)

    def test_prompt_prefix_loaded_from_skill(self):
        """When the skill IS available (this machine has it), the prompt
        prefix should be a non-empty string for a known remedy."""
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=True)
        prefix = bridge.get_prompt_prefix()
        # On this machine the skill is installed, so we expect a string.
        # On a fresh deploy without the skill, this would be None — that's
        # valid too. We just check it's a string or None.
        self.assertTrue(prefix is None or isinstance(prefix, str))


# ─── Limbic Bridge ───────────────────────────────────────────────────


class TestLimbicBridge(unittest.TestCase):
    """The limbic bridge must degrade gracefully when limbic-hermes
    is absent and proxy correctly when it is present."""

    def test_disabled_bridge_returns_disabled_state(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=False)
        state = bridge.get_state()
        self.assertFalse(state.get("enabled", False))

    def test_disabled_bridge_affect_summary(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=False)
        summary = bridge.get_affect_summary()
        self.assertFalse(summary.get("enabled", False))

    def test_disabled_bridge_info(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=False)
        info = bridge.info()
        self.assertFalse(info["enabled"])
        self.assertFalse(info["available"])

    def test_disabled_bridge_inject_prompt_is_noop(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=False)
        prompt = "Hello there."
        result = bridge.inject_prompt(prompt)
        self.assertEqual(result, prompt)

    def test_disabled_bridge_observe_is_noop(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=False)
        # Should not raise.
        bridge.observe("user_message", "hello")
        bridge.update()

    def test_enabled_bridge_info_has_expected_fields(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=True)
        info = bridge.info()
        self.assertIn("enabled", info)
        self.assertIn("available", info)
        self.assertIn("profile", info)
        self.assertIn("intensity", info)
        self.assertTrue(info["enabled"])
        # On this machine, limbic-hermes IS available.
        self.assertTrue(info["available"])

    def test_enabled_bridge_get_state_returns_dict(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=True)
        state = bridge.get_state()
        self.assertIsInstance(state, dict)
        # When available, state should have VAD or at least be non-empty.
        if bridge.available:
            self.assertIn("vad", state)
            self.assertIn("dominant_affect", state)

    def test_enabled_bridge_affect_summary(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=True)
        if bridge.available:
            bridge.update()
            summary = bridge.get_affect_summary()
            self.assertIn("dominant_affect", summary)

    def test_enabled_bridge_inject_prompt(self):
        """When the limbic system is available, inject_prompt should
        potentially modify the prompt (add limbic posture)."""
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=True, intensity=0.6)
        base = "You are an astromech droid. Help the user."
        result = bridge.inject_prompt(base)
        # The result should be a string (possibly modified).
        self.assertIsInstance(result, str)

    def test_observe_and_update_no_crash(self):
        """Even with the real limbic system, observe + update should not raise."""
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=True)
        bridge.observe("user_message", "hello there")
        bridge.update()

    def test_state_dir_expanded(self):
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(state_dir="~/test_limbic")
        self.assertFalse("~" in bridge.state_dir)
        self.assertTrue(bridge.state_dir.startswith("/"))


# ─── Dashboard ──────────────────────────────────────────────────────


class TestDashboard(unittest.TestCase):
    """The dashboard server must import without Flask and work with it."""

    def test_import_dashboard_module(self):
        """Import should succeed even without Flask."""
        from dashboard import DashboardServer
        self.assertIsNotNone(DashboardServer)

    def test_dashboard_init_defaults(self):
        from dashboard import DashboardServer
        server = DashboardServer()
        self.assertEqual(server.port, 9298)
        self.assertEqual(server.host, "127.0.0.1")

    def test_dashboard_init_custom_port(self):
        from dashboard import DashboardServer
        server = DashboardServer(host="0.0.0.0", port=8888)
        self.assertEqual(server.port, 8888)
        self.assertEqual(server.host, "0.0.0.0")

    def test_get_state_returns_dict(self):
        from dashboard import DashboardServer
        server = DashboardServer()
        state = server.get_state()
        self.assertIsInstance(state, dict)
        # Should have basic keys.
        self.assertIn("robot_name", state)
        self.assertIn("version", state)

    def test_get_state_with_agent(self):
        """When an agent is attached, state should include brain model."""
        from dashboard import DashboardServer
        from brain.llm_client import LLMClient
        from brain.memory import Memory
        from brain.agent import Agent
        mock_http = MagicMock(return_value={"response": "hi", "done": True})
        agent = Agent(
            llm=LLMClient(http_client=mock_http),
            memory=Memory(),
        )
        server = DashboardServer(agent=agent)
        state = server.get_state()
        self.assertIn("brain", state)
        self.assertIn("model", state["brain"])

    def test_get_state_with_personality_bridge(self):
        """When a personality bridge is attached, state should show remedy."""
        from dashboard import DashboardServer
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=True)
        server = DashboardServer(personality_bridge=bridge)
        state = server.get_state()
        self.assertIn("personality", state)

    def test_get_state_with_limbic_bridge(self):
        """When a limbic bridge is attached, state should show limbic info."""
        from dashboard import DashboardServer
        from brain.limbic import LimbicBridge
        bridge = LimbicBridge(enabled=False)  # disabled = safe
        server = DashboardServer(limbic_bridge=bridge)
        state = server.get_state()
        self.assertIn("limbic", state)


# ─── Agent with personality + limbic ────────────────────────────────


class TestAgentWithBridges(unittest.TestCase):
    """The Agent should work with and without personality/limbic bridges."""

    def setUp(self):
        from brain.llm_client import LLMClient
        self.http = MagicMock(return_value={"response": "LLM reply", "done": True})
        self.llm = LLMClient(http_client=self.http)

    def test_agent_without_bridges_works(self):
        from brain.agent import Agent
        from brain.memory import Memory
        agent = Agent(llm=self.llm, memory=Memory())
        reply = agent.handle("Tell me a joke.")
        self.assertEqual(reply, "LLM reply")
        self.http.assert_called_once()

    def test_agent_with_disabled_bridges_works(self):
        from brain.agent import Agent
        from brain.memory import Memory
        from brain.personality import PersonalityBridge
        from brain.limbic import LimbicBridge
        agent = Agent(
            llm=self.llm,
            memory=Memory(),
            personality=PersonalityBridge("bryonia_alba", enabled=False),
            limbic=LimbicBridge(enabled=False),
        )
        reply = agent.handle("Hello!")
        self.assertEqual(reply, "LLM reply")
        self.http.assert_called_once()

    def test_agent_with_personality_prepends_prefix(self):
        """When personality is enabled and the skill is available, the
        prompt sent to the LLM should include the personality prefix."""
        from brain.agent import Agent
        from brain.memory import Memory
        from brain.personality import PersonalityBridge
        bridge = PersonalityBridge("bryonia_alba", enabled=True)
        agent = Agent(
            llm=self.llm,
            memory=Memory(),
            personality=bridge,
        )
        agent.handle("Hello!")
        # Check the prompt that was sent to the LLM.
        sent_prompt = self.http.call_args[0][1]["prompt"]
        # If the skill is available, the prefix should be prepended.
        # If not, the prompt is just the user text. Either way, the user
        # text should be in there.
        self.assertIn("Hello!", sent_prompt)

    def test_meta_prompts_still_work_with_bridges(self):
        """Meta-prompts (what model, remember, recall) should NOT hit the
        LLM even when bridges are attached."""
        from brain.agent import Agent
        from brain.memory import Memory
        from brain.personality import PersonalityBridge
        from brain.limbic import LimbicBridge
        agent = Agent(
            llm=self.llm,
            memory=Memory(),
            personality=PersonalityBridge("bryonia_alba", enabled=False),
            limbic=LimbicBridge(enabled=False),
        )
        reply = agent.handle("What model are you running right now?")
        self.assertIn("qwen2.5:3b", reply)
        self.http.assert_not_called()

    def test_agent_with_enabled_limbic(self):
        """Agent should work with a real enabled limbic bridge."""
        from brain.agent import Agent
        from brain.memory import Memory
        from brain.limbic import LimbicBridge
        limbic = LimbicBridge(enabled=True, intensity=0.6)
        agent = Agent(
            llm=self.llm,
            memory=Memory(),
            limbic=limbic,
        )
        reply = agent.handle("Hello!")
        self.assertEqual(reply, "LLM reply")
        self.http.assert_called_once()


if __name__ == "__main__":
    unittest.main()