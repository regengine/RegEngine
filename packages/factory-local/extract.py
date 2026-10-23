"""Extract a DeonticIR from statutory text with a local Ollama model.

Uses structured output (format = DeonticIR JSON schema). No rule is returned
without source text and a valid model response. This module never pulls models.
"""

from __future__ import annotations

import os

import httpx
from pydantic import ValidationError
from schemas import DeonticIR

SYSTEM_PROMPT = (
    "You convert statutory text into a DeonticIR JSON object. "
    "applicability_predicates are the facts that make the duty "
    "apply. action_required is a snake_case control name that satisfies the duty. "
    "max_penalty_usd is the per violation civil penalty. Reply with JSON only."
)


def extract_ir(statutory_text: str, timeout: float = 120.0) -> tuple[DeonticIR | None, str]:
    """Return (ir, source), or (None, reason) when extraction has no result."""
    if not statutory_text.strip():
        return None, "No data yet: statutory text is empty"
    model = os.environ.get("OLLAMA_MODEL", "").strip()
    if not model:
        return None, "No data yet: OLLAMA_MODEL unset"
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": statutory_text},
        ],
        "format": DeonticIR.model_json_schema(),
        "stream": False,
        "options": {"temperature": 0},
    }
    try:
        resp = httpx.post(f"{host}/api/chat", json=body, timeout=timeout)
        resp.raise_for_status()
        ir = DeonticIR.model_validate_json(resp.json()["message"]["content"])
    except httpx.HTTPError as exc:
        return None, f"No data yet: Ollama unavailable ({type(exc).__name__})"
    except (ValidationError, KeyError, ValueError, TypeError) as exc:
        return None, f"No data yet: invalid model output ({type(exc).__name__})"
    return ir, f"ollama:{model}"
