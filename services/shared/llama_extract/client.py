"""Thin, fail-open wrapper around the LlamaCloud Python SDK's Extract v2 API.

LlamaCloud "Extract" turns a document (PDF, image, scan, DOCX, spreadsheet)
plus a JSON Schema into a JSON object that conforms to that schema, with a
citation and a confidence score per field. RegEngine uses it for the
unstructured paperwork that arrives next to the structured feeds: invoices,
bills of lading, receiving logs, packing lists and certificates whose KDEs
would otherwise be keyed by hand.

Guarantees this module provides to the production spine:

* **Optional.** Without ``LLAMA_CLOUD_API_KEY`` the extractor reports
  ``enabled == False`` and every ``extract`` raises
  :class:`LlamaExtractUnavailable` immediately, so callers fall back to their
  deterministic path (or tell the user the document must be keyed).
* **Fail-open.** Every SDK error (auth, rate limit, timeout, 5xx, failed job,
  malformed response) becomes :class:`LlamaExtractUnavailable` with a short,
  stable ``reason``; nothing in the ingestion path is blocked by the vendor.
* **Bounded latency.** Upload plus polling is capped by
  :attr:`~shared.llama_extract.settings.LlamaExtractSettings.timeout_seconds`.
* **No document content in logs.** Only metadata (purpose, tier, version, job
  id, latency, page counts, credits) is logged. The SDK's own logger prints
  request bodies at ``DEBUG``; :func:`guard_sdk_logging` caps it at ``INFO``
  unless an operator opted in via ``LLAMA_CLOUD_LOG``.
* **Evidence.** Every result carries an :class:`ExtractionEvidence` record
  (provider, tier, requested and resolved version, job and file ids, latency,
  pages billed, credits, SDK version, schema digest) so an extraction can be
  persisted and audited alongside the record it produced.

Tenant isolation is the caller's responsibility: the document itself leaves
the process for the vendor, so send only the tenant-scoped file the caller is
authorised to read, and persist the result under that tenant.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog
from llama_cloud import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    LlamaCloud,
    LlamaCloudError,
    PermissionDeniedError,
    PollingError,
    PollingTimeoutError,
    RateLimitError,
    UnprocessableEntityError,
    __version__ as _sdk_version,
)
from pydantic import BaseModel

from .settings import TIERS, LlamaExtractSettings

logger = structlog.get_logger("llama_extract")
# Production drops structlog INFO events that have no sampled trace
# (sampling_aware_filter with LOG_ALL_SAMPLED_OUT=false), so a successful call
# would leave no trace there while a failure (a warning) still shows. This
# stdlib line is what lets an operator see in the deploy log that the key
# works and Extract is being used. Metadata only, like the structlog event.
_ops_log = logging.getLogger("llama_extract")

PROVIDER = "llama_cloud"
PRODUCT = "extract_v2"
FILE_PURPOSE = "extract"
EXTRACTION_TARGETS: tuple[str, ...] = ("per_doc", "per_page", "per_table_row")

_SDK_LOGGER_NAME = "llama_cloud"
_SDK_LOG_LEVEL_ENV = "LLAMA_CLOUD_LOG"

# The SDK's own polling floor; the client budget below is split between the
# upload request and the polling loop.
_POLLING_INTERVAL_SECONDS = 1.0
_POLLING_MAX_INTERVAL_SECONDS = 5.0
_UPLOAD_TIMEOUT_SECONDS = 120.0


class LlamaExtractUnavailable(RuntimeError):
    """Extract could not answer; the caller must use its deterministic path.

    ``reason`` is a short, stable token suitable for metrics and evidence:
    ``disabled``, ``auth``, ``rate_limited``, ``timeout``, ``connection``,
    ``bad_request``, ``invalid_response``, ``server_error``, ``api_error``,
    ``job_failed``, ``sdk_error``, ``empty_result``.
    """

    def __init__(
        self,
        reason: str,
        *,
        purpose: str,
        status: int | None = None,
        job_id: str | None = None,
    ) -> None:
        self.reason = reason
        self.purpose = purpose
        self.status = status
        self.job_id = job_id
        detail = f"llama extract unavailable for {purpose}: {reason}"
        if status is not None:
            detail += f" (status={status})"
        if job_id is not None:
            detail += f" (job={job_id})"
        super().__init__(detail)


@dataclass(frozen=True)
class ExtractionEvidence:
    """Provenance for one Extract call, persisted next to any record it produced."""

    purpose: str
    tier: str
    requested_version: str
    resolved_version: str | None
    extraction_target: str
    job_id: str
    file_id: str
    file_name: str
    latency_ms: int
    schema_sha256: str
    pages_extracted: int | None = None
    pages_billed: int | None = None
    credits: float | None = None
    parse_job_id: str | None = None
    provider: str = PROVIDER
    product: str = PRODUCT
    sdk_version: str = _sdk_version

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtractionResult:
    """What one document extracted to.

    ``data`` is the object conforming to the request schema (``per_doc``) or a
    list of such objects (``per_page`` / ``per_table_row``). ``field_metadata``
    is the vendor's per-field citation and confidence map when they were
    requested, keyed like ``data``; ``None`` when the vendor returned none.
    """

    data: dict[str, Any] | list[Any]
    evidence: ExtractionEvidence
    field_metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "field_metadata": self.field_metadata,
            "evidence": self.evidence.to_dict(),
        }


def classify_error(exc: BaseException) -> tuple[str, int | None]:
    """Map an SDK exception to a stable ``(reason, http_status)`` pair."""
    if isinstance(exc, PollingTimeoutError):
        return "timeout", None
    if isinstance(exc, PollingError):
        return "job_failed", None
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return "auth", exc.status_code
    if isinstance(exc, RateLimitError):
        return "rate_limited", exc.status_code
    if isinstance(exc, (BadRequestError, UnprocessableEntityError)):
        return "bad_request", exc.status_code
    if isinstance(exc, InternalServerError):
        return "server_error", exc.status_code
    if isinstance(exc, APIStatusError):
        return "api_error", exc.status_code
    if isinstance(exc, APITimeoutError):
        return "timeout", None
    if isinstance(exc, APIConnectionError):
        return "connection", None
    if isinstance(exc, APIResponseValidationError):
        return "invalid_response", None
    if isinstance(exc, LlamaCloudError):
        return "sdk_error", None
    return "sdk_error", None


def guard_sdk_logging() -> None:
    """Cap the SDK logger at INFO unless an operator opted into ``LLAMA_CLOUD_LOG``.

    The SDK logs request and response bodies at ``DEBUG``, which for this
    integration means document bytes and extracted values. A root logger set
    to ``DEBUG`` (tests, local debugging) would otherwise write them.
    """
    if os.environ.get(_SDK_LOG_LEVEL_ENV):
        return
    sdk_logger = logging.getLogger(_SDK_LOGGER_NAME)
    if sdk_logger.level == logging.NOTSET or sdk_logger.level < logging.INFO:
        sdk_logger.setLevel(logging.INFO)


def schema_from(data_schema: Mapping[str, Any] | type[BaseModel]) -> dict[str, Any]:
    """Accept a JSON Schema mapping or a pydantic model class; return a plain dict."""
    if isinstance(data_schema, type) and issubclass(data_schema, BaseModel):
        return data_schema.model_json_schema()
    if isinstance(data_schema, Mapping):
        return dict(data_schema)
    raise TypeError("data_schema must be a JSON Schema mapping or a pydantic BaseModel subclass")


def schema_digest(schema: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class DocumentExtractor:
    """Fail-open LlamaCloud Extract client; one instance is safe to share."""

    def __init__(
        self,
        settings: LlamaExtractSettings | None = None,
        *,
        http_client: httpx.Client | None = None,
        polling_interval: float = _POLLING_INTERVAL_SECONDS,
    ) -> None:
        self.settings = settings or LlamaExtractSettings.from_env()
        self._http_client = http_client
        self._polling_interval = max(0.0, polling_interval)
        self._client: LlamaCloud | None = None
        self._lock = threading.Lock()
        guard_sdk_logging()

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    def _sdk(self) -> LlamaCloud:
        with self._lock:
            if self._client is None:
                kwargs: dict[str, Any] = {
                    "api_key": self.settings.api_key,
                    # The SDK retries connection errors and 5xx on its own;
                    # one retry keeps the latency budget honest.
                    "max_retries": 1,
                    "timeout": _UPLOAD_TIMEOUT_SECONDS,
                }
                if self.settings.base_url:
                    kwargs["base_url"] = self.settings.base_url
                if self._http_client is not None:
                    kwargs["http_client"] = self._http_client
                self._client = LlamaCloud(**kwargs)
            return self._client

    def configuration(
        self,
        schema: Mapping[str, Any],
        *,
        extraction_target: str = "per_doc",
        system_prompt: str | None = None,
        target_pages: str | None = None,
        max_pages: int | None = None,
        spreadsheet_mode: bool = False,
        tier: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """The vendor configuration for one job: settings plus per-call overrides."""
        if extraction_target not in EXTRACTION_TARGETS:
            raise ValueError(f"extraction_target must be one of {EXTRACTION_TARGETS}")
        resolved_tier = tier or self.settings.tier
        if resolved_tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        config: dict[str, Any] = {
            "data_schema": dict(schema),
            "tier": resolved_tier,
            "version": version or self.settings.version,
            "extraction_target": extraction_target,
            "cite_sources": self.settings.cite_sources,
            "confidence_scores": self.settings.confidence_scores,
            "disable_cache": self.settings.disable_cache,
        }
        pages = self.settings.max_pages if max_pages is None else max_pages
        if pages and pages > 0:
            config["max_pages"] = pages
        if target_pages:
            config["target_pages"] = target_pages
        if system_prompt:
            config["system_prompt"] = system_prompt
        if spreadsheet_mode:
            config["spreadsheet_mode"] = True
        return config

    def extract(
        self,
        document: bytes | str | Path,
        *,
        file_name: str | None = None,
        data_schema: Mapping[str, Any] | type[BaseModel],
        purpose: str,
        extraction_target: str = "per_doc",
        system_prompt: str | None = None,
        target_pages: str | None = None,
        max_pages: int | None = None,
        spreadsheet_mode: bool = False,
        tier: str | None = None,
        version: str | None = None,
    ) -> ExtractionResult:
        """Upload ``document`` and extract ``data_schema`` from it.

        ``document`` is raw bytes (then ``file_name`` is required, extension
        included, so the vendor knows the format) or a path. ``purpose`` is a
        short caller tag for logs and evidence (``receiving_invoice``,
        ``cli``), never document content.
        """
        if not self.enabled:
            raise LlamaExtractUnavailable("disabled", purpose=purpose)

        if isinstance(document, (str, Path)):
            path = Path(document)
            content = path.read_bytes()
            name = file_name or path.name
        else:
            content = bytes(document)
            if not file_name:
                raise ValueError("file_name is required when document is given as bytes")
            name = file_name

        schema = schema_from(data_schema)
        config = self.configuration(
            schema,
            extraction_target=extraction_target,
            system_prompt=system_prompt,
            target_pages=target_pages,
            max_pages=max_pages,
            spreadsheet_mode=spreadsheet_mode,
            tier=tier,
            version=version,
        )
        digest = schema_digest(schema)
        scope: dict[str, Any] = {}
        if self.settings.project_id:
            scope["project_id"] = self.settings.project_id

        started = time.perf_counter()
        job_id: str | None = None
        try:
            sdk = self._sdk()
            uploaded = sdk.files.create(file=(name, content), purpose=FILE_PURPOSE, **scope)
            remaining = max(5.0, self.settings.timeout_seconds - (time.perf_counter() - started))
            created = sdk.extract.create(file_input=uploaded.id, configuration=config, **scope)
            job_id = created.id
            job = sdk.extract.wait_for_completion(
                created.id,
                polling_interval=self._polling_interval,
                max_interval=max(self._polling_interval, _POLLING_MAX_INTERVAL_SECONDS),
                timeout=remaining,
                **scope,
            )
        except Exception as exc:  # noqa: BLE001 - every vendor failure is fail-open
            reason, status = classify_error(exc)
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "llama_extract.unavailable",
                purpose=purpose,
                reason=reason,
                status=status,
                job_id=job_id,
                tier=config["tier"],
                version=config["version"],
                latency_ms=latency_ms,
                error_type=type(exc).__name__,
            )
            raise LlamaExtractUnavailable(reason, purpose=purpose, status=status, job_id=job_id) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if job.extract_result is None:
            logger.warning("llama_extract.empty_result", purpose=purpose, job_id=job.id, latency_ms=latency_ms)
            raise LlamaExtractUnavailable("empty_result", purpose=purpose, job_id=job.id)

        resolved_version = job.configuration.version if job.configuration is not None else None
        usage = job.metadata.usage if job.metadata is not None else None
        credits = job.usage.credits if job.usage is not None else None
        parse_job_id = job.extract_metadata.parse_job_id if job.extract_metadata is not None else None
        evidence = ExtractionEvidence(
            purpose=purpose,
            tier=config["tier"],
            requested_version=config["version"],
            resolved_version=resolved_version,
            extraction_target=extraction_target,
            job_id=job.id,
            file_id=uploaded.id,
            file_name=name,
            latency_ms=latency_ms,
            schema_sha256=digest,
            pages_extracted=usage.num_pages_extracted if usage is not None else None,
            pages_billed=usage.num_pages_billed if usage is not None else None,
            credits=credits,
            parse_job_id=parse_job_id,
        )
        field_metadata = _field_metadata(job, extraction_target)

        logger.info(
            "llama_extract.completed",
            purpose=purpose,
            job_id=job.id,
            tier=evidence.tier,
            version=evidence.resolved_version or evidence.requested_version,
            latency_ms=latency_ms,
            pages_billed=evidence.pages_billed,
            credits=evidence.credits,
        )
        _ops_log.info(
            "llama_extract_completed purpose=%s job=%s tier=%s version=%s latency_ms=%d pages_billed=%s",
            purpose,
            job.id,
            evidence.tier,
            evidence.resolved_version or evidence.requested_version,
            latency_ms,
            evidence.pages_billed,
        )
        return ExtractionResult(data=job.extract_result, evidence=evidence, field_metadata=field_metadata)


def _field_metadata(job: Any, extraction_target: str) -> dict[str, Any] | None:
    metadata = getattr(job, "extract_metadata", None)
    fields = getattr(metadata, "field_metadata", None)
    if fields is None:
        return None
    if extraction_target == "per_page":
        chosen = fields.page_metadata
    elif extraction_target == "per_table_row":
        chosen = fields.row_metadata
    else:
        chosen = fields.document_metadata
    if chosen is None:
        return None
    return {"target": extraction_target, "fields": chosen}


_extractor: DocumentExtractor | None = None
_extractor_lock = threading.Lock()


def get_document_extractor() -> DocumentExtractor:
    """Process-wide extractor built from the environment (lazily, once)."""
    global _extractor
    with _extractor_lock:
        if _extractor is None:
            _extractor = DocumentExtractor(LlamaExtractSettings.from_env())
        return _extractor


def reset_document_extractor() -> None:
    """Drop the cached extractor (tests, or after rotating ``LLAMA_CLOUD_API_KEY``)."""
    global _extractor
    with _extractor_lock:
        _extractor = None
