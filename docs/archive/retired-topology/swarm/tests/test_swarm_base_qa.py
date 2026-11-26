"""Deep QA for the editable swarm modules: base (messages, memory,
lifecycle), llm (JSON retry, mock client, factory) and the SSE extras not
covered by tests/swarm/test_sse_parser.py.

All tests are local and deterministic: MockLLMClient or scripted stubs, no
network, no sleeps. Product code under test lives outside the in-flight
swarm files (agents.py, cli.py, coordinator.py, github_integration.py),
which are exercised but never edited.
"""

from __future__ import annotations

import asyncio
import copy
import json

import pytest

from regengine.swarm.base import AgentMemory, AgentMessage, BaseAgent, MessageType
from regengine.swarm.llm import BaseLLMClient, LLMClientFactory, MockLLMClient
from regengine.swarm.sse import (
    collect_openai_stream_text,
    iter_sse_payloads,
    parse_openai_response_events,
)


class _EchoAgent(BaseAgent):
    async def think(self, task, context=None):
        return {"echo": task}

    async def act(self, plan):
        return {"acted": True, "plan": plan}

    async def reflect(self, result):
        return {"status": "completed"}


class _ScriptedClient(BaseLLMClient):
    """Returns canned strings in order; records every prompt it was given."""

    def __init__(self, script):
        super().__init__(model="test", timeout=1)
        self.script = list(script)
        self.prompts = []

    def generate(self, prompt, system_prompt=""):
        self.prompts.append(prompt)
        return self.script.pop(0)


def _message_dict():
    return {
        "sender": "PlannerAgent",
        "receiver": "CoderAgent",
        "message_type": "task",
        "content": {"goal": "ship it"},
        "timestamp": "2026-01-01T00:00:00+00:00",
        "correlation_id": "corr-1",
        "iteration": 2,
    }


class TestAgentMessage:
    def test_round_trip_preserves_every_field(self):
        original = AgentMessage(
            sender="A",
            receiver="B",
            message_type=MessageType.PLAN,
            content={"p": 1},
            correlation_id="c",
            iteration=3,
        )
        as_dict = original.to_dict()
        assert as_dict["message_type"] == "plan"
        restored = AgentMessage.from_dict(as_dict)
        assert (restored.sender, restored.receiver, restored.message_type) == ("A", "B", MessageType.PLAN)
        assert restored.content == {"p": 1}
        assert (restored.correlation_id, restored.iteration) == ("c", 3)

    def test_from_dict_does_not_mutate_the_input(self):
        """from_dict converted the caller's 'task' string into a
        MessageType in place, so reusing or logging the dict afterwards saw
        an enum instead of the string that was passed in."""
        data = _message_dict()
        before = copy.deepcopy(data)
        AgentMessage.from_dict(data)
        assert data == before

    def test_from_dict_rejects_unknown_message_type(self):
        with pytest.raises(ValueError):
            AgentMessage.from_dict({**_message_dict(), "message_type": "teleport"})


class TestAgentMemory:
    def test_recall_on_missing_log_returns_empty(self, tmp_path):
        assert AgentMemory("ghost", base_dir=tmp_path).recall() == []

    def test_record_recall_filter_and_limit(self, tmp_path):
        memory = AgentMemory("worker", base_dir=tmp_path)
        memory.record("started", {"n": 1})
        memory.record("progress", {"n": 2})
        memory.record("started", {"n": 3})

        assert [e["data"]["n"] for e in memory.recall()] == [1, 2, 3]
        assert [e["data"]["n"] for e in memory.recall(event_type="started")] == [1, 3]
        assert [e["data"]["n"] for e in memory.recall(limit=2)] == [2, 3]

    def test_corrupt_lines_are_skipped(self, tmp_path):
        memory = AgentMemory("worker", base_dir=tmp_path)
        memory.record("started", {"n": 1})
        with open(memory.log_file, "a", encoding="utf-8") as f:
            f.write("{not json\n\n")
        memory.record("done", {"n": 2})
        assert [e["data"]["n"] for e in memory.recall()] == [1, 2]

    def test_clear_removes_the_log(self, tmp_path):
        memory = AgentMemory("worker", base_dir=tmp_path)
        memory.record("started", {})
        memory.clear()
        assert memory.recall() == []
        assert not memory.log_file.exists()


class TestAgentLifecycle:
    def test_run_executes_think_act_reflect_and_records_memory(self, tmp_path):
        agent = _EchoAgent(
            name="echo",
            role="test",
            system_prompt="",
            llm_client=MockLLMClient(),
            memory_dir=tmp_path,
        )
        result = asyncio.run(agent.run("do the thing"))

        assert result["agent"] == "echo"
        assert result["plan"] == {"echo": "do the thing"}
        assert result["result"] == {"acted": True, "plan": {"echo": "do the thing"}}
        assert result["assessment"] == {"status": "completed"}
        assert result["duration_seconds"] >= 0

        events = [e["event"] for e in agent.memory.recall(limit=10)]
        assert events == ["task_received", "plan_created", "action_completed", "reflection"]


class TestGenerateJsonRetry:
    def test_succeeds_on_second_attempt_after_hint(self):
        client = _ScriptedClient(["{not json", '{"ok": true}'])
        assert client.generate_json('{"a": 1}') == {"ok": True}
        assert len(client.prompts) == 2
        assert "not valid JSON" in client.prompts[1]

    def test_returns_empty_dict_after_three_failures(self):
        client = _ScriptedClient(["nope-1", "nope-2", "nope-3", '{"late": true}'])
        assert client.generate_json("hi") == {}
        assert len(client.prompts) == 3


class TestMockLLMClient:
    def test_predefined_responses_are_served_then_clamped(self):
        client = MockLLMClient(responses=["first", "second"])
        assert client.generate("a") == "first"
        assert client.generate("b") == "second"
        assert client.generate("c") == "second"

    @pytest.mark.parametrize(
        ("system_prompt", "key", "value"),
        [
            ("You are the Planner", "files_to_edit", ["main.py"]),
            ("Coder instructions", "files_written", ["main.py"]),
            ("Reviewer notes", "verdict", "approve"),
            ("Tester duties", "verdict", "pass"),
        ],
    )
    def test_role_branches_return_structured_json(self, system_prompt, key, value):
        assert json.loads(MockLLMClient().generate("task", system_prompt))[key] == value


class TestLLMClientFactory:
    def test_mock_mode_env_selects_mock_client(self, monkeypatch):
        monkeypatch.setenv("REGENGINE_USE_MOCK_LLM", "true")
        assert isinstance(LLMClientFactory.create(), MockLLMClient)

    def test_default_model_selects_ollama_with_configured_host(self, monkeypatch):
        monkeypatch.delenv("REGENGINE_USE_MOCK_LLM", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
        monkeypatch.setenv("LLM_MODEL", "llama3:8b")
        monkeypatch.setenv("OLLAMA_HOST", "http://ollama-test:11434")
        monkeypatch.setenv("LLM_TIMEOUT_S", "5")
        from regengine.swarm.llm import OllamaClient

        client = LLMClientFactory.create()
        assert isinstance(client, OllamaClient)
        assert client.host == "http://ollama-test:11434"
        assert client.timeout == 5


class TestSseExtras:
    def test_comment_lines_are_skipped(self):
        chunks = [": heartbeat\n", 'data: {"type":"response.created"}\n\n']
        assert list(iter_sse_payloads(chunks)) == ['{"type":"response.created"}']

    def test_multi_line_data_blocks_are_joined(self):
        chunks = ["data: line-one\ndata: line-two\n\n"]
        assert list(iter_sse_payloads(chunks)) == ["line-one\nline-two"]

    def test_trailing_payload_without_terminator_is_yielded(self):
        chunks = ['data: {"type":"response.output_text.delta","delta":"Hi"}\n\n', "data: [DONE]"]
        assert list(iter_sse_payloads(chunks))[-1] == "[DONE]"

    def test_events_after_done_are_ignored(self):
        chunks = [
            'data: {"type":"response.output_text.delta","delta":"Hi"}\n\n',
            "data: [DONE]\n\n",
            'data: {"type":"response.output_text.delta","delta":" ignored"}\n\n',
        ]
        assert collect_openai_stream_text(chunks) == "Hi"

    def test_non_string_delta_is_ignored(self):
        chunks = ['data: {"type":"response.output_text.delta","delta":123}\n\n', "data: [DONE]\n\n"]
        assert collect_openai_stream_text(chunks) == ""

    def test_deltas_win_over_completed_fallback(self):
        completed = {
            "type": "response.completed",
            "response": {"output": [{"content": [{"text": "Fallback"}]}]},
        }
        chunks = [
            'data: {"type":"response.output_text.delta","delta":"Live"}\n\n',
            f"data: {json.dumps(completed)}\n\n",
            "data: [DONE]\n\n",
        ]
        assert collect_openai_stream_text(chunks) == "Live"

    def test_completed_event_without_deltas_still_resolves(self):
        assert collect_openai_stream_text([]) == ""
        events = list(parse_openai_response_events(['data: {"type":"other"}\n\n', "data: [DONE]\n\n"]))
        assert [e["type"] for e in events] == ["other"]
