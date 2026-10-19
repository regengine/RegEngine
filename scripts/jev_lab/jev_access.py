"""How the lab reaches Jev: the live API or the offline fake, behind a request budget and a cache.

Every request the lab makes goes through :class:`LabDecider`:

* **Budget.** At most ``max_requests`` requests leave the process per lab
  process; past it every ask raises ``JevUnavailable("lab_budget")`` so a
  runaway loop cannot spend credits.
* **Cache.** An identical request (same model, state and questions) is
  answered from the cache instead of being sent again. A loop generation that
  rewrites only the header-mapping wording re-asks nothing about file CTEs.
  The on-disk cache stores a SHA-256 of the request and Jev's answers, never
  the request itself.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from shared.jev import (
    ChoiceResult,
    JevAnswers,
    JevDecider,
    JevEvidence,
    JevSettings,
    JevUnavailable,
    NoulResult,
    ScoreResult,
)

from . import fake_jev

LIVE = "live"
FAKE = "fake"
# The fake transport never reads it; JevSettings only needs a non-empty key to be enabled.
FAKE_KEY = "offline-fake-jev"  # pragma: allowlist secret
DEFAULT_MAX_REQUESTS = 400


def fake_settings() -> JevSettings:
    return JevSettings(api_key=FAKE_KEY, model=fake_jev.MODEL, max_retries=0, header_sample_values=0)


def build_decider(mode: str, settings: JevSettings | None = None) -> JevDecider:
    """A :class:`JevDecider` for ``mode``. ``live`` needs ``settings`` with a key; ``fake`` never sends anything."""
    if mode == FAKE:
        return JevDecider(fake_settings(), transport=fake_jev.transport())
    if settings is None:
        raise ValueError("live mode needs settings")
    # Headers only, whatever the operator's ingestion knob says.
    return JevDecider(dataclasses.replace(settings, header_sample_values=0))


def request_key(model: str, state: Any, questions: Mapping[str, Any]) -> str:
    payload = json.dumps({"model": model, "state": state, "questions": questions}, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def answers_from_dict(data: Mapping[str, Any]) -> JevAnswers:
    evidence = dict(data["evidence"])
    evidence["question_ids"] = tuple(evidence.get("question_ids") or ())
    return JevAnswers(
        evidence=JevEvidence(**evidence),
        choices={key: ChoiceResult(**value) for key, value in (data.get("choices") or {}).items()},
        nouls={key: NoulResult(**value) for key, value in (data.get("nouls") or {}).items()},
        scores={
            key: ScoreResult(
                score=value["score"],
                confidence=value["confidence"],
                probabilities={int(level): p for level, p in (value.get("probabilities") or {}).items()},
                legend={int(level): text for level, text in (value.get("legend") or {}).items()},
            )
            for key, value in (data.get("scores") or {}).items()
        },
    )


class LabDecider:
    """A :class:`JevDecider` with a request budget and an answer cache. Thread-safe."""

    def __init__(
        self,
        decider: JevDecider,
        *,
        mode: str,
        max_requests: int = DEFAULT_MAX_REQUESTS,
        cache_path: Path | None = None,
    ) -> None:
        self._decider = decider
        self.mode = mode
        self.max_requests = max_requests
        self._cache_path = cache_path
        self._cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self.sent = 0
        self.failed = 0
        self.cache_hits = 0
        if cache_path is not None and cache_path.exists():
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    answers_from_dict(row["answers"])  # a hand-edited row is skipped here, never mid-run
                    self._cache[row["key"]] = row["answers"]
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue

    @property
    def settings(self) -> JevSettings:
        return self._decider.settings

    @property
    def enabled(self) -> bool:
        return self._decider.enabled

    @property
    def remaining(self) -> int:
        return max(0, self.max_requests - self.sent)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "mode": self.mode,
                "model": self.settings.model,
                "sent": self.sent,
                "failed": self.failed,
                "cache_hits": self.cache_hits,
                "max_requests": self.max_requests,
                "remaining": max(0, self.max_requests - self.sent),
            }

    def ask(
        self,
        state: Any,
        questions: Mapping[str, Any],
        *,
        purpose: str,
        questions_version: str = "1",
        use_cache: bool = True,
    ) -> JevAnswers:
        key = request_key(self.settings.model, state, questions)
        with self._lock:
            cached = self._cache.get(key) if use_cache else None
            if cached is not None:
                self.cache_hits += 1
                return answers_from_dict(cached)
            if self.sent >= self.max_requests:
                raise JevUnavailable("lab_budget", purpose=purpose)
            self.sent += 1
        try:
            answers = self._decider.ask(state, questions, purpose=purpose, questions_version=questions_version)
        except JevUnavailable:
            with self._lock:
                self.failed += 1
            raise
        stored = answers.to_dict()
        with self._lock:
            if not use_cache and key in self._cache:
                return answers
            self._cache[key] = stored
            if self._cache_path is not None:
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                with self._cache_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"key": key, "answers": stored}) + "\n")
        return answers

    def close(self) -> None:
        self._decider.close()


class Uncached:
    """A view of a :class:`LabDecider` that always sends: how the loop measures Jev's repeat noise."""

    def __init__(self, decider: LabDecider) -> None:
        self._decider = decider
        self.mode = decider.mode

    @property
    def settings(self) -> JevSettings:
        return self._decider.settings

    @property
    def enabled(self) -> bool:
        return self._decider.enabled

    def stats(self) -> dict[str, Any]:
        return self._decider.stats()

    def ask(
        self, state: Any, questions: Mapping[str, Any], *, purpose: str, questions_version: str = "1"
    ) -> JevAnswers:
        return self._decider.ask(
            state, questions, purpose=purpose, questions_version=questions_version, use_cache=False
        )
