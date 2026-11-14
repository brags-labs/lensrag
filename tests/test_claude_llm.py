import os, unittest
from types import SimpleNamespace as NS
from unittest import mock
from lensrag.full.claude_llm import ClaudeClient, ClaudeRefusal
from lensrag.full.providers import resolve_provider, create_llm


def reply(text, stop="end_turn", **usage):
    u = NS(input_tokens=usage.get("inp", 100), output_tokens=usage.get("out", 20),
           cache_read_input_tokens=usage.get("read", 0), cache_creation_input_tokens=usage.get("write", 0))
    return NS(content=[NS(type="thinking", thinking=""), NS(type="text", text=text)], stop_reason=stop,
              stop_details=NS(category="cyber") if stop == "refusal" else None, usage=u)


class FakeMessages:
    def __init__(self, replies): self.replies, self.calls = list(replies), []
    def create(self, **kw):
        self.calls.append(kw)
        return self.replies.pop(0)


class FakeAnthropic:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)
        self.beta = NS(messages=self.messages)


class ClaudeClientTests(unittest.TestCase):
    def test_json_parses_fenced_reply_and_tracks_usage(self):
        fake = FakeAnthropic([reply('```json\n{"answer": 28}\n```', read=900, write=0)])
        llm = ClaudeClient(client=fake)
        self.assertEqual(llm.json("Extract.", "q"), {"answer": 28})
        call = fake.messages.calls[0]
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["output_config"], {"effort": "medium"})
        self.assertEqual(call["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertEqual((call["betas"], call["fallbacks"]), (["server-side-fallback-2026-07-01"], "default"))
        for removed in ("temperature", "top_p", "top_k", "thinking"):
            self.assertNotIn(removed, call)
        self.assertEqual(llm.usage["prompt_tokens"], 1000)
        self.assertEqual(llm.usage["cache_read_tokens"], 900)

    def test_invalid_json_is_retried_once(self):
        fake = FakeAnthropic([reply("Sure! Here you go."), reply('{"ok": true}')])
        llm = ClaudeClient(client=fake)
        self.assertEqual(llm.json("s", "u"), {"ok": True})
        self.assertIn("not valid JSON", fake.messages.calls[1]["messages"][0]["content"])
        self.assertEqual(llm.usage["calls"], 2)

    def test_refusal_and_truncation_raise(self):
        with self.assertRaises(ClaudeRefusal):
            ClaudeClient(client=FakeAnthropic([reply("", stop="refusal")])).text("s", "u")
        with self.assertRaises(RuntimeError):
            ClaudeClient(client=FakeAnthropic([reply("cut", stop="max_tokens")])).text("s", "u")

    def test_fallbacks_only_on_models_that_accept_them(self):
        fake = FakeAnthropic([reply("hi")])
        ClaudeClient(model="claude-haiku-5-5", client=fake).text("s", "u")
        self.assertNotIn("fallbacks", fake.messages.calls[0])
        fake = FakeAnthropic([reply("hi")])
        ClaudeClient(fallbacks="off", client=fake).text("s", "u")
        self.assertNotIn("fallbacks", fake.messages.calls[0])


class ProviderTests(unittest.TestCase):
    def test_auto_prefers_claude_then_openai(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x", "OPENAI_API_KEY": "y"}, clear=True):
            self.assertEqual(resolve_provider(), "anthropic")
        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "y"}, clear=True):
            self.assertEqual(resolve_provider(), "openai")
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                resolve_provider()
            self.assertEqual(resolve_provider("claude"), "anthropic")

    def test_create_llm_builds_claude_client(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            llm = create_llm()
        self.assertIsInstance(llm, ClaudeClient)
        self.assertEqual(llm.model, "claude-opus-5-5")


if __name__ == "__main__":
    unittest.main()
