"""Thin, fail-open wrapper around the TypeSafe AI Python SDK.

Jev is TypeSafe's "System One" model: it does not generate text. A request
sends *state* (a string, JSON object, or array) plus named, typed *questions*
(``Choice``, ``Score``, ``Noul``) and receives calibrated answers with
probabilities and confidence. RegEngine uses it for narrow judgments inside
normalization (which canonical field does a source column mean, which CTE
type is a row), where hand-written matching is brittle and a text-generating
LLM is too slow and unstructured.

Guarantees this module provides to the production spine:

* **Optional.** Without ``TYPESAFE_API_KEY`` the decider reports
  ``enabled == False`` and every ``ask`` raises :class:`JevUnavailable`
  immediately, so callers fall back to their deterministic path.
* **Fail-open.** Every SDK error (auth, rate limit, timeout, 5xx, malformed
  response) becomes :class:`JevUnavailable` with a short ``reason``; the
  ingestion path is never blocked by the vendor.
* **Bounded latency.** Per-attempt timeout and retry count come from
  :class:`~shared.jev.settings.JevSettings`; the retry budget is derived so a
  call can never exceed roughly ``timeout * (retries + 1)`` seconds.
* **No state in logs.** Only metadata (purpose, model, request id, latency,
  token usage, question count) is logged. The SDK's own logger prints request
  bodies at ``DEBUG``; :func:`guard_sdk_logging` caps it at ``INFO`` unless an
  operator opted in via ``TYPESAFE_LOG_LEVEL``.
* **Evidence.** Every answer set carries a :class:`JevEvidence` record (model,
  request id, latency, usage, SDK version, question ids) so a suggestion can be
  persisted and audited alongside the decision it influenced.

Tenant isolation is the caller's responsibility: build ``state`` only from the
tenant-scoped record being normalized. Send column headers and canonical
vocabularies, not whole uploads.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog
from typesafe_sdk import (
    AsyncTypeSafeClient,
    ChoiceAnswer,
    NoulAnswer,
    RetryPolicy,
    ScoreAnswer,
    SystemOneResponse,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPIResponseValidationError,
    TypeSafeAPITimeoutError,
    TypeSafeAuthenticationError,
    TypeSafeBadRequestError,
    TypeSafeClient,
    TypeSafeError,
    TypeSafePermissionDeniedError,
    TypeSafeRateLimitError,
    TypeSafeUnprocessableEntityError,
    __version__ as _sdk_version,
)

from .settings import JevSettings

logger = structlog.get_logger("jev")

PROVIDER = "typesafe"
_SDK_LOGGER_NAME = "typesafe_sdk"
_SDK_LOG_LEVEL_ENV = "TYPESAFE_LOG_LEVEL"


class JevUnavailable(RuntimeError):
    """Jev could not answer; the caller must use its deterministic path.

    ``reason`` is a short, stable token suitable for metrics and evidence:
    ``disabled``, ``auth``, ``rate_limited``, ``timeout``, ``connection``,
    ``bad_request``, ``invalid_response``, ``server_error``, ``api_error``,
    ``sdk_error``.
    """

    def __init__(self, reason: str, *, purpose: str, status: int | None = None, request_id: str | None = None) -> None:
        self.reason = reason
        self.purpose = purpose
        self.status = status
        self.request_id = request_id
        detail = f"jev unavailable for {purpose}: {reason}"
        if status is not None:
            detail += f" (status={status})"
        super().__init__(detail)


@dataclass(frozen=True)
class ChoiceResult:
    choice: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class NoulResult:
    probability: float


@dataclass(frozen=True)
class ScoreResult:
    score: float
    confidence: float
    probabilities: dict[int, float] = field(default_factory=dict)
    legend: dict[int, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class JevEvidence:
    """Provenance for one Jev call, persisted next to any decision it influenced."""

    purpose: str
    requested_model: str
    model: str
    request_id: str | None
    latency_ms: int
    question_ids: tuple[str, ...]
    questions_version: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider: str = PROVIDER
    sdk_version: str = _sdk_version

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["question_ids"] = list(self.question_ids)
        return data


@dataclass(frozen=True)
class JevAnswers:
    """Typed answers keyed by question id, plus the evidence for the call."""

    evidence: JevEvidence
    choices: dict[str, ChoiceResult] = field(default_factory=dict)
    nouls: dict[str, NoulResult] = field(default_factory=dict)
    scores: dict[str, ScoreResult] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence": self.evidence.to_dict(),
            "choices": {key: asdict(value) for key, value in self.choices.items()},
            "nouls": {key: asdict(value) for key, value in self.nouls.items()},
            "scores": {key: asdict(value) for key, value in self.scores.items()},
        }


def classify_error(exc: TypeSafeError) -> str:
    """Map an SDK exception to a stable ``JevUnavailable.reason`` token."""
    if isinstance(exc, TypeSafeAPITimeoutError):
        return "timeout"
    if isinstance(exc, TypeSafeAPIConnectionError):
        return "connection"
    if isinstance(exc, TypeSafeRateLimitError):
        return "rate_limited"
    if isinstance(exc, (TypeSafeAuthenticationError, TypeSafePermissionDeniedError)):
        return "auth"
    if isinstance(exc, TypeSafeAPIResponseValidationError):
        return "invalid_response"
    if isinstance(exc, (TypeSafeBadRequestError, TypeSafeUnprocessableEntityError)):
        return "bad_request"
    if isinstance(exc, TypeSafeAPIError):
        return "server_error" if exc.status >= 500 else "api_error"
    return "sdk_error"


def guard_sdk_logging() -> None:
    """Keep the SDK from logging request/response bodies unless an operator opted in.

    ``typesafe_sdk`` logs full bodies at ``DEBUG``. Bodies carry tenant data,
    so if the effective level is below ``INFO`` (for example because the root
    logger runs at ``DEBUG`` locally) and ``TYPESAFE_LOG_LEVEL`` was not set
    explicitly, raise the SDK logger to ``INFO``.
    """
    if os.environ.get(_SDK_LOG_LEVEL_ENV, "").strip():
        return
    sdk_logger = logging.getLogger(_SDK_LOGGER_NAME)
    if sdk_logger.getEffectiveLevel() < logging.INFO:
        sdk_logger.setLevel(logging.INFO)
        logger.info("jev.sdk_logging_capped", sdk_logger=_SDK_LOGGER_NAME, level="INFO")


def _unit(value: float) -> float:
    """A vendor confidence or probability as a finite number in ``[0, 1]``.

    The SDK's response schema types these as plain floats, unbounded. Float
    noise such as ``1.0000001`` would fail every response model that bounds
    them (``CsvIngestResponse``: a 500 after the rows were stored), so
    values are clamped. A non-finite value is no information and reads as
    0.0, which no confidence band acts on.
    """
    value = float(value)
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def _convert(
    response: SystemOneResponse,
) -> tuple[dict[str, ChoiceResult], dict[str, NoulResult], dict[str, ScoreResult]]:
    choices: dict[str, ChoiceResult] = {}
    nouls: dict[str, NoulResult] = {}
    scores: dict[str, ScoreResult] = {}
    for question_id, answer in response.answers.items():
        if isinstance(answer, ChoiceAnswer):
            choices[question_id] = ChoiceResult(
                choice=answer.choice,
                confidence=_unit(answer.confidence),
                probabilities={label: _unit(p) for label, p in answer.probabilities.items()},
            )
        elif isinstance(answer, NoulAnswer):
            nouls[question_id] = NoulResult(probability=_unit(answer.noul))
        elif isinstance(answer, ScoreAnswer):
            scores[question_id] = ScoreResult(
                score=float(answer.score),
                confidence=_unit(answer.confidence),
                probabilities={int(level): _unit(p) for level, p in answer.probabilities.items()},
                legend={int(level): text for level, text in answer.legend.items()},
            )
    return choices, nouls, scores


class JevDecider:
    """Answer typed questions with Jev, or raise :class:`JevUnavailable`.

    One instance owns one SDK client per flavour (sync/async), created lazily
    from :class:`JevSettings`. ``transport`` / ``async_transport`` accept an
    ``httpx2`` transport (``httpx2.MockTransport`` in tests) so no test ever
    reaches the network.
    """

    def __init__(
        self,
        settings: JevSettings | None = None,
        *,
        transport: Any | None = None,
        async_transport: Any | None = None,
    ) -> None:
        self._settings = settings if settings is not None else JevSettings.from_env()
        self._transport = transport
        self._async_transport = async_transport
        self._client: TypeSafeClient | None = None
        self._async_client: AsyncTypeSafeClient | None = None
        self._lock = threading.Lock()
        if self._settings.enabled:
            guard_sdk_logging()

    @property
    def settings(self) -> JevSettings:
        return self._settings

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    # -- client construction -------------------------------------------------

    def _retry_policy(self) -> RetryPolicy:
        return RetryPolicy(max_retries=self._settings.max_retries, timeout=self._settings.retry_budget_seconds)

    def _sync_client(self) -> TypeSafeClient:
        with self._lock:
            if self._client is None:
                self._client = TypeSafeClient(
                    api_key=self._settings.api_key,
                    model=self._settings.model,
                    base_url=self._settings.base_url,
                    retry=self._retry_policy(),
                    timeout=self._settings.timeout_seconds,
                    transport=self._transport,
                )
            return self._client

    def _aio_client(self) -> AsyncTypeSafeClient:
        with self._lock:
            if self._async_client is None:
                self._async_client = AsyncTypeSafeClient(
                    api_key=self._settings.api_key,
                    model=self._settings.model,
                    base_url=self._settings.base_url,
                    retry=self._retry_policy(),
                    timeout=self._settings.timeout_seconds,
                    transport=self._async_transport,
                )
            return self._async_client

    # -- asking ---------------------------------------------------------------

    def _require_enabled(self, purpose: str) -> None:
        if not self._settings.enabled:
            raise JevUnavailable("disabled", purpose=purpose)

    def _unavailable(self, exc: TypeSafeError, *, purpose: str, started: float) -> JevUnavailable:
        reason = classify_error(exc)
        status = exc.status if isinstance(exc, TypeSafeAPIError) else None
        request_id = exc.request_id if isinstance(exc, TypeSafeAPIError) else None
        logger.warning(
            "jev.unavailable",
            purpose=purpose,
            reason=reason,
            status=status,
            request_id=request_id,
            latency_ms=_elapsed_ms(started),
            error_type=type(exc).__name__,
        )
        return JevUnavailable(reason, purpose=purpose, status=status, request_id=request_id)

    def _answers(
        self,
        response: SystemOneResponse,
        *,
        purpose: str,
        questions_version: str,
        questions: Mapping[str, Any],
        started: float,
    ) -> JevAnswers:
        choices, nouls, scores = _convert(response)
        request_id = response.raw_http_response.headers.get("x-typesafe-request-id")
        evidence = JevEvidence(
            purpose=purpose,
            requested_model=self._settings.model,
            model=response.model,
            request_id=request_id,
            latency_ms=_elapsed_ms(started),
            question_ids=tuple(questions.keys()),
            questions_version=questions_version,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        logger.info(
            "jev.answered",
            purpose=purpose,
            model=evidence.model,
            request_id=evidence.request_id,
            latency_ms=evidence.latency_ms,
            input_tokens=evidence.input_tokens,
            output_tokens=evidence.output_tokens,
            question_count=len(evidence.question_ids),
        )
        return JevAnswers(evidence=evidence, choices=choices, nouls=nouls, scores=scores)

    def ask(
        self,
        state: Any,
        questions: Mapping[str, Any],
        *,
        purpose: str,
        questions_version: str = "1",
    ) -> JevAnswers:
        """Synchronously answer ``questions`` about ``state``.

        ``purpose`` names the decision being made (for example
        ``"header_mapping"``) and is the only description of the call that
        reaches logs and evidence. ``questions_version`` identifies the
        revision of the question set so evidence stays interpretable after the
        wording changes.
        """
        self._require_enabled(purpose)
        started = time.perf_counter()
        try:
            response = self._sync_client().system_one(state, questions)
        except TypeSafeError as exc:
            raise self._unavailable(exc, purpose=purpose, started=started) from exc
        return self._answers(
            response, purpose=purpose, questions_version=questions_version, questions=questions, started=started
        )

    async def ask_async(
        self,
        state: Any,
        questions: Mapping[str, Any],
        *,
        purpose: str,
        questions_version: str = "1",
    ) -> JevAnswers:
        """Asynchronous twin of :meth:`ask` for request handlers on the event loop."""
        self._require_enabled(purpose)
        started = time.perf_counter()
        try:
            response = await self._aio_client().system_one(state, questions)
        except TypeSafeError as exc:
            raise self._unavailable(exc, purpose=purpose, started=started) from exc
        return self._answers(
            response, purpose=purpose, questions_version=questions_version, questions=questions, started=started
        )

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            client, self._client = self._client, None
        if client is not None:
            client.close()

    async def aclose(self) -> None:
        with self._lock:
            client, self._async_client = self._async_client, None
        if client is not None:
            await client.aclose()


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


_default_decider: JevDecider | None = None
_default_lock = threading.Lock()


def get_jev_decider() -> JevDecider:
    """Process-wide decider built from the environment on first use."""
    global _default_decider
    with _default_lock:
        if _default_decider is None:
            _default_decider = JevDecider()
        return _default_decider


def reset_jev_decider() -> None:
    """Drop the cached decider (tests, or after rotating ``TYPESAFE_API_KEY``)."""
    global _default_decider
    with _default_lock:
        decider, _default_decider = _default_decider, None
    if decider is not None:
        decider.close()
