"""Extract a DeonticIR from statutory text with a local Ollama model.

Uses structured output (format = DeonticIR JSON schema). Falls back to the
checked-in fixture when OLLAMA_MODEL is unset, Ollama is unreachable, or the
reply does not validate. This module never pulls models.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from pydantic import ValidationError

from schemas import DeonticIR

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "co_sb205_ir.json"

SYSTEM_PROMPT = (
    "You convert statutory text into a DeonticIR JSON object. Use rule_id "
    "US_CO_SB205_V2. applicability_predicates are the facts that make the duty "
    "apply. action_required is a snake_case control name that satisfies the duty. "
    "max_penalty_usd is the per violation civil penalty. Reply with JSON only."
)


def load_fixture() -> DeonticIR:
    return DeonticIR.model_validate_json(FIXTURE.read_text())


def extract_ir(statutory_text: str, timeout: float = 120.0) -> tuple[DeonticIR, str]:
    """Return (ir, source). source is 'ollama:<model>' or 'fixture:<reason>'."""
    model = os.environ.get("OLLAMA_MODEL", "").strip()
    if not model:
        return load_fixture(), "fixture:OLLAMA_MODEL unset"
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
        return load_fixture(), f"fixture:ollama unavailable ({type(exc).__name__})"
    except (ValidationError, KeyError, ValueError, TypeError) as exc:
        return load_fixture(), f"fixture:invalid model output ({type(exc).__name__})"
    return ir, f"ollama:{model}"
