import json
import importlib.util
from pathlib import Path


_SSE_PATH = Path(__file__).resolve().parents[2] / "regengine" / "swarm" / "sse.py"
_SSE_SPEC = importlib.util.spec_from_file_location("swarm_sse", _SSE_PATH)
assert _SSE_SPEC and _SSE_SPEC.loader
_SSE_MODULE = importlib.util.module_from_spec(_SSE_SPEC)
_SSE_SPEC.loader.exec_module(_SSE_MODULE)

collect_openai_stream_text = _SSE_MODULE.collect_openai_stream_text
iter_sse_payloads = _SSE_MODULE.iter_sse_payloads
parse_openai_response_events = _SSE_MODULE.parse_openai_response_events


def test_iter_sse_payloads_handles_chunk_boundaries() -> None:
    chunks = [
        "event: message\n",
        "data: {\"type\":\"response.created\"}\n\n",
        "data: {\"type\":\"response.output_text.delta\",\"delta\":\"Hel",
        "lo\"}\n\n",
        "data: [DONE]\n\n",
    ]

    payloads = list(iter_sse_payloads(chunks))
    assert payloads[0] == '{"type":"response.created"}'
    assert payloads[1] == '{"type":"response.output_text.delta","delta":"Hello"}'
    assert payloads[2] == "[DONE]"


def test_parse_openai_response_events_skips_bad_json() -> None:
    chunks = [
        "data: {\"type\":\"response.output_text.delta\",\"delta\":\"Hi\"}\n\n",
        "data: {not-valid-json}\n\n",
        "data: {\"type\":\"response.output_text.delta\",\"delta\":\" there\"}\n\n",
        "data: [DONE]\n\n",
    ]

    events = list(parse_openai_response_events(chunks))
    assert len(events) == 2
    assert events[0]["delta"] == "Hi"
    assert events[1]["delta"] == " there"


def test_collect_openai_stream_text_prefers_deltas() -> None:
    chunks = [
        "data: {\"type\":\"response.output_text.delta\",\"delta\":\"Hello\"}\n\n",
        "data: {\"type\":\"response.output_text.delta\",\"delta\":\" world\"}\n\n",
        "data: [DONE]\n\n",
    ]

    text = collect_openai_stream_text(chunks)
    assert text == "Hello world"


def test_collect_openai_stream_text_uses_completed_fallback() -> None:
    completed = {
        "type": "response.completed",
        "response": {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "Fallback"},
                        {"type": "output_text", "text": " text"},
                    ]
                }
            ]
        },
    }

    chunks = [f"data: {json.dumps(completed)}\n\n", "data: [DONE]\n\n"]
    assert collect_openai_stream_text(chunks) == "Fallback text"
