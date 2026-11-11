"""SSE helpers for robust OpenAI Responses API streaming.

This parser intentionally consumes a stream as independent SSE events and
JSON-parses each `data:` payload separately.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Iterator, List, Optional


def iter_sse_payloads(chunks: Iterable[str]) -> Iterator[str]:
    """Yield complete SSE `data:` payloads from chunked text input."""
    buffer = ""

    def pop_event(raw_event: str) -> Optional[str]:
        data_parts: List[str] = []
        for raw_line in raw_event.split("\n"):
            line = raw_line.strip("\r")
            if not line or line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_parts.append(line[5:].lstrip(" "))
        if not data_parts:
            return None
        return "\n".join(data_parts)

    for chunk in chunks:
        if not chunk:
            continue
        normalized = chunk.replace("\r\n", "\n")
        buffer += normalized

        while "\n\n" in buffer:
            raw_event, buffer = buffer.split("\n\n", 1)
            payload = pop_event(raw_event)
            if payload is not None:
                yield payload

    trailing = buffer.strip()
    if trailing:
        payload = pop_event(trailing)
        if payload is not None:
            yield payload


def parse_openai_response_events(chunks: Iterable[str]) -> Iterator[Dict[str, Any]]:
    """Parse OpenAI streamed SSE payloads into JSON objects."""
    for payload in iter_sse_payloads(chunks):
        if payload == "[DONE]":
            break
        try:
            message = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(message, dict):
            yield message


def _extract_text_from_completed_event(message: Dict[str, Any]) -> str:
    response = message.get("response")
    if not isinstance(response, dict):
        return ""

    output = response.get("output")
    if not isinstance(output, list):
        return ""

    text_parts: List[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text_value = block.get("text")
            if isinstance(text_value, str):
                text_parts.append(text_value)
    return "".join(text_parts)


def collect_openai_stream_text(chunks: Iterable[str]) -> str:
    """Collect final text from OpenAI streamed events."""
    parts: List[str] = []

    for message in parse_openai_response_events(chunks):
        msg_type = message.get("type")
        if msg_type == "response.output_text.delta":
            delta = message.get("delta", "")
            if isinstance(delta, str):
                parts.append(delta)
            continue

        if msg_type == "response.completed" and not parts:
            completed_text = _extract_text_from_completed_event(message)
            if completed_text:
                parts.append(completed_text)

    return "".join(parts)
