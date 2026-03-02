from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def tokenize_pii(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"tok_{digest[:16]}"


def stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
