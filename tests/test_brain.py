"""Tests for the R1-A1 brain package (llm_client, memory, agent).

All HTTP is mocked via the injectable http_client callable — no network,
no Ollama server required.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from brain.agent import Agent
from brain.llm_client import LLMClient
from brain.memory import Memory


def make_mock_http(response_text="mock reply"):
    mock = MagicMock(return_value={"response": response_text, "done": True})
    return mock


class TestLLMClient(unittest.TestCase):
    def test_generate_posts_to_api_generate(self):
        http = make_mock_http("hello there")
        client = LLMClient(http_client=http)
        out = client.generate("Say hi")
        self.assertEqual(out, "hello there")
        url, payload, _timeout = http.call_args[0]
        self.assertEqual(url, "http://localhost:11434/api/generate")
        self.assertEqual(payload["model"], "qwen2.5:3b")
        self.assertEqual(payload["prompt"], "Say hi")
        self.assertFalse(payload["stream"])

    def test_generate_with_explicit_model_override(self):
        http = make_mock_http()
        client = LLMClient(http_client=http)
        client.generate("hi", model="custom:1b")
        self.assertEqual(http.call_args[0][1]["model"], "custom:1b")
        # Active model unchanged by one-shot override
        self.assertEqual(client.current_model(), "qwen2.5:3b")

    def test_model_switching(self):
        client = LLMClient(http_client=make_mock_http())
        self.assertEqual(client.current_model(), "qwen2.5:3b")
        self.assertEqual(client.switch_to_fallback(), "gemma2:2b")
        self.assertEqual(client.current_model(), "gemma2:2b")
        self.assertEqual(client.switch_to_primary(), "qwen2.5:3b")
        self.assertEqual(client.current_model(), "qwen2.5:3b")

    def test_generate_uses_active_model_after_switch(self):
        http = make_mock_http()
        client = LLMClient(http_client=http)
        client.switch_to_fallback()
        client.generate("hi")
        self.assertEqual(http.call_args[0][1]["model"], "gemma2:2b")

    def test_custom_base_url(self):
        http = make_mock_http()
        client = LLMClient(base_url="http://192.168.1.10:11434/", http_client=http)
        client.generate("hi")
        self.assertEqual(http.call_args[0][0], "http://192.168.1.10:11434/api/generate")


class TestMemory(unittest.TestCase):
    def test_add_turn_and_buffer_cap(self):
        mem = Memory()
        for i in range(30):
            mem.add_turn("user", f"turn {i}")
        self.assertEqual(len(mem.turns), 20)
        self.assertEqual(mem.turns[-1], ("user", "turn 29"))
        self.assertEqual(mem.turns[0], ("user", "turn 10"))

    def test_remember_and_recall(self):
        mem = Memory()
        mem.remember("name", "Walker")
        self.assertEqual(mem.recall("name"), "Walker")
        self.assertEqual(mem.recall("NAME"), "Walker")  # case-insensitive
        self.assertIsNone(mem.recall("favorite color"))

    def test_summarize_last(self):
        mem = Memory()
        self.assertIn("haven't asked", mem.summarize_last())
        mem.add_turn("user", "What is your battery level?")
        mem.add_turn("assistant", "87 percent.")
        summary = mem.summarize_last()
        self.assertIn("What is your battery level?", summary)

    def test_summarize_last_skips_assistant_turns(self):
        mem = Memory()
        mem.add_turn("user", "first question")
        mem.add_turn("user", "second question")
        mem.add_turn("assistant", "an answer")
        self.assertIn("second question", mem.summarize_last())


class TestAgentRouting(unittest.TestCase):
    def setUp(self):
        self.http = make_mock_http("LLM says hello")
        self.llm = LLMClient(http_client=self.http)
        self.agent = Agent(llm=self.llm, memory=Memory())

    def test_what_model_meta_prompt_no_llm_call(self):
        reply = self.agent.handle("What model are you running right now?")
        self.assertIn("qwen2.5:3b", reply)
        self.http.assert_not_called()

    def test_switch_model_meta_prompt_no_llm_call(self):
        reply = self.agent.handle("Switch to your small model.")
        self.assertIn("gemma2:2b", reply)
        self.assertEqual(self.llm.current_model(), "gemma2:2b")
        self.http.assert_not_called()
        reply = self.agent.handle("Switch back to your primary model.")
        self.assertIn("qwen2.5:3b", reply)
        self.assertEqual(self.llm.current_model(), "qwen2.5:3b")
        self.http.assert_not_called()

    def test_remember_meta_prompt_no_llm_call(self):
        reply = self.agent.handle("Remember that my name is Walker.")
        self.assertIn("Walker", reply)
        self.assertEqual(self.agent.memory.recall("name"), "Walker")
        self.http.assert_not_called()

    def test_recall_meta_prompt_no_llm_call(self):
        self.agent.handle("Remember that my name is Walker.")
        self.http.reset_mock()
        reply = self.agent.handle("What's my name?")
        self.assertEqual(reply, "Your name is Walker.")
        self.http.assert_not_called()

    def test_recall_unknown_fact(self):
        reply = self.agent.handle("What's my favorite color?")
        self.assertIn("don't know", reply)
        self.http.assert_not_called()

    def test_summarize_meta_prompt_no_llm_call(self):
        self.agent.memory.add_turn("user", "Drive forward one meter.")
        reply = self.agent.handle("Summarize the last thing I asked you.")
        self.assertIn("Drive forward one meter.", reply)
        self.http.assert_not_called()

    def test_normal_prompt_hits_llm_and_logs_memory(self):
        reply = self.agent.handle("Tell me a joke about droids.")
        self.assertEqual(reply, "LLM says hello")
        self.http.assert_called_once()
        turns = list(self.agent.memory.turns)
        self.assertEqual(turns[0], ("user", "Tell me a joke about droids."))
        self.assertEqual(turns[1], ("assistant", "LLM says hello"))

    def test_llm_uses_switched_model(self):
        self.agent.handle("Switch to your small model.")
        self.agent.handle("Hello?")
        self.assertEqual(self.http.call_args[0][1]["model"], "gemma2:2b")


if __name__ == "__main__":
    unittest.main()
