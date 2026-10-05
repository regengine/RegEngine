"""Thin, fail-open wrapper around the LlamaCloud SDK for LlamaIndex Extract.

Extract is LlamaIndex's schema-guided document extraction agent (the v2.5
line, released 2026-10-01, is the first RegEngine runs). One call uploads a
document, runs an extraction job against a JSON Schema and returns the
extracted object(s) plus, per field, a citation and a confidence. RegEngine
uses it where the deterministic parsers stop: supplier PDFs with no tables
(scanned forms, letters, mixed layouts) on the bulk-upload path, and ad-hoc
operator extraction through ``scripts/extract_document.py``.

Guarantees this module provides to the production spine:

* **Optional.** Without ``LLAMA_CLOUD_API_KEY`` the extractor reports
  ``enabled == False`` and every ``extract`` raises
  :class:`DocumentExtractUnavailable` immediately, so callers keep their
  deterministic path.
* **Fail-open.** Every SDK error (auth, rate limit, timeout, 5xx, job
  failure, polling timeout, malformed response) becomes
  :class:`DocumentExtractUnavailable` with a short ``reason``; an upload is
  never blocked by the vendor.
* **Bounded latency.** Per-request timeout, retries and the job budget come
  from :class:`~shared.document_extract.settings.DocumentExtractSettings`.
* **Data minimisation.** The whole document is sent (that is the point), so:
  the vendor-side file is deleted after the job, best effort; result caching
  is disabled by default; and only metadata (purpose, job id, tier, version,
  pages, latency) is logged. Extracted values never appear in log records.
* **Evidence.** Every result carries a :class:`ExtractEvidence` record (job
  id, resolved tier and version, pages, credits, latency, SDK version,
  schema version) so the extraction can be persisted and audited next to the
  records it produced.

Tenant isolation is the caller's responsibility: send one tenant's document
per call and keep the result inside that tenant's session.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import structlog
from llama_cloud import (
    APIConnectionError,
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncLlamaCloud,
    AuthenticationError,
    BadRequestError,
    LlamaCloud,
    LlamaCloudError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
    __version__ as _sdk_version,
    omit,
)
from llama_cloud._polling import PollingError, PollingTimeoutError

from .settings import EXTRACTION_TARGETS, DocumentExtractSettings

logger = structlog.get_logger("document_extract")
# Production drops structlog INFO events without a sampled trace, so this
# stdlib line is what lets an operator see in the deploy log that the key
# works and Extract is being used. Metadata only, like the structlog event.
_ops_log = logging.getLogger("document_extract")

PROVIDER = "llamaindex"
PRODUCT = "extract"
_UPLOAD_PURPOSE = "extract"

_MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "webp": "image/webp",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "txt": "text/plain",
    "html": "text/html",
}

_SDK_ERRORS: tuple[type[BaseException], ...] = (LlamaCloudError, PollingError, PollingTimeoutError)


class DocumentExtractUnavailable(RuntimeError):
    """Extract could not answer; the caller must keep its deterministic path.

    ``reason`` is a short, stable token suitable for metrics and evidence:
    ``disabled``, ``auth``, ``rate_limited``, ``timeout``, ``connection``,
    ``bad_request``, ``not_found``, ``invalid_response``, ``server_error``,
    ``api_error``, ``job_failed``, ``job_timeout``, ``empty_result``,
    ``sdk_error``.
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
        detail = f"document extract unavailable for {purpose}: {reason}"
        if status is not None:
            detail += f" (status={status})"
        super().__init__(detail)


@dataclass(frozen=True)
class ExtractEvidence:
    """Provenance for one extraction job, persisted next to the records it produced."""

    purpose: str
    requested_tier: str
    requested_version: str
    tier: str | None
    version: str | None
    job_id: str
    file_id: str | None
    extraction_target: str
    schema_version: str
    latency_ms: int
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
    """What one job returned: data conforming to the schema, per-field metadata, evidence."""

    evidence: ExtractEvidence
    data: dict[str, Any] | list[Any]
    field_metadata: dict[str, Any] | None = None
    page_metadata: list[Any] | None = None
    row_metadata: list[Any] | None = None

    def records(self) -> list[dict[str, Any]]:
        """The extracted objects as a list: one for ``per_doc``, one per page or row otherwise."""
        if isinstance(self.data, dict):
            return [self.data]
        return [item for item in self.data if isinstance(item, dict)]

    def confidence_summary(self) -> dict[str, Any]:
        """Count, minimum and mean of every per-field confidence the vendor returned."""
        return summarize_confidences(self.field_metadata, self.page_metadata, self.row_metadata)

    def to_dict(self, *, include_data: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "evidence": self.evidence.to_dict(),
            "confidence": self.confidence_summary(),
        }
        if include_data:
            payload["data"] = self.data
            payload["field_metadata"] = self.field_metadata
            if self.page_metadata is not None:
                payload["page_metadata"] = self.page_metadata
            if self.row_metadata is not None:
                payload["row_metadata"] = self.row_metadata
        return payload


def _unit(value: Any) -> float | None:
    """A vendor confidence as a finite number in ``[0, 1]``, or None when it is not a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return min(1.0, max(0.0, number))


def iter_confidences(node: Any) -> list[float]:
    """Every ``confidence`` number found anywhere in the vendor's field metadata."""
    found: list[float] = []
    if isinstance(node, Mapping):
        confidence = _unit(node.get("confidence"))
        if confidence is not None:
            found.append(confidence)
        for key, value in node.items():
            if key == "confidence":
                continue
            found.extend(iter_confidences(value))
    elif isinstance(node, (list, tuple)):
        for item in node:
            found.extend(iter_confidences(item))
    return found


def summarize_confidences(*nodes: Any) -> dict[str, Any]:
    values: list[float] = []
    for node in nodes:
        values.extend(iter_confidences(node))
    if not values:
        return {"fields": 0, "min": None, "mean": None}
    return {
        "fields": len(values),
        "min": round(min(values), 4),
        "mean": round(sum(values) / len(values), 4),
    }


def classify_error(exc: BaseException) -> str:
    """Map an SDK or polling exception to a stable ``DocumentExtractUnavailable.reason`` token."""
    if isinstance(exc, PollingTimeoutError):
        return "job_timeout"
    if isinstance(exc, PollingError):
        return "job_failed"
    if isinstance(exc, APITimeoutError):
        return "timeout"
    if isinstance(exc, APIConnectionError):
        return "connection"
    if isinstance(exc, RateLimitError):
        return "rate_limited"
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return "auth"
    if isinstance(exc, NotFoundError):
        return "not_found"
    if isinstance(exc, APIResponseValidationError):
        return "invalid_response"
    if isinstance(exc, (BadRequestError, UnprocessableEntityError)):
        return "bad_request"
    if isinstance(exc, APIStatusError):
        return "server_error" if exc.status_code >= 500 else "api_error"
    return "sdk_error"


def mime_type_for(filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MIME_BY_EXTENSION.get(extension, "application/octet-stream")


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _to_plain(value: Any) -> Any:
    """SDK pydantic models (and their extras) as plain JSON-safe containers."""
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


class DocumentExtractor:
    """Run schema-guided extraction with LlamaIndex Extract, or raise :class:`DocumentExtractUnavailable`.

    One instance owns one SDK client per flavour (sync/async), created lazily
    from :class:`DocumentExtractSettings`. ``client`` / ``async_client``
    accept prebuilt clients (fakes in tests) so no test ever reaches the
    network.
    """

    def __init__(
        self,
        settings: DocumentExtractSettings | None = None,
        *,
        client: Any | None = None,
        async_client: Any | None = None,
    ) -> None:
        self._settings = settings if settings is not None else DocumentExtractSettings.from_env()
        self._client = client
        self._async_client = async_client
        self._lock = threading.Lock()

    @property
    def settings(self) -> DocumentExtractSettings:
        return self._settings

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    # -- client construction -------------------------------------------------

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "api_key": self._settings.api_key,
            "max_retries": self._settings.max_retries,
            "timeout": self._settings.timeout_seconds,
        }
        if self._settings.base_url:
            kwargs["base_url"] = self._settings.base_url
        return kwargs

    def _sync_client(self) -> Any:
        with self._lock:
            if self._client is None:
                self._client = LlamaCloud(**self._client_kwargs())
            return self._client

    def _aio_client(self) -> Any:
        with self._lock:
            if self._async_client is None:
                self._async_client = AsyncLlamaCloud(**self._client_kwargs())
            return self._async_client

    # -- request building ----------------------------------------------------

    def _require_enabled(self, purpose: str) -> None:
        if not self._settings.enabled:
            raise DocumentExtractUnavailable("disabled", purpose=purpose)

    def _configuration(
        self,
        data_schema: Mapping[str, Any],
        *,
        extraction_target: str,
        max_pages: int | None,
        system_prompt: str | None,
    ) -> dict[str, Any]:
        if extraction_target not in EXTRACTION_TARGETS:
            raise ValueError(f"extraction_target must be one of {EXTRACTION_TARGETS}, got {extraction_target!r}")
        pages = self._settings.max_pages if max_pages is None else max(1, min(max_pages, self._settings.max_pages))
        configuration: dict[str, Any] = {
            "data_schema": dict(data_schema),
            "tier": self._settings.tier,
            "version": self._settings.version,
            "extraction_target": extraction_target,
            "max_pages": pages,
            "cite_sources": self._settings.cite_sources,
            "confidence_scores": self._settings.confidence_scores,
            "disable_cache": self._settings.disable_cache,
        }
        if system_prompt:
            configuration["system_prompt"] = system_prompt
        return configuration

    def _project_id(self) -> Any:
        return self._settings.project_id or omit

    def _unavailable(
        self, exc: BaseException, *, purpose: str, started: float, job_id: str | None = None
    ) -> DocumentExtractUnavailable:
        reason = classify_error(exc)
        status = exc.status_code if isinstance(exc, APIStatusError) else None
        logger.warning(
            "document_extract.unavailable",
            purpose=purpose,
            reason=reason,
            status=status,
            job_id=job_id,
            latency_ms=_elapsed_ms(started),
            error_type=type(exc).__name__,
        )
        return DocumentExtractUnavailable(reason, purpose=purpose, status=status, job_id=job_id)

    def _result(
        self,
        job: Any,
        *,
        purpose: str,
        file_id: str | None,
        extraction_target: str,
        schema_version: str,
        started: float,
    ) -> ExtractionResult:
        data = job.extract_result
        if data is None or (isinstance(data, (dict, list)) and not data):
            logger.warning("document_extract.empty_result", purpose=purpose, job_id=job.id, status=job.status)
            raise DocumentExtractUnavailable("empty_result", purpose=purpose, job_id=job.id)

        configuration = job.configuration
        metadata = job.extract_metadata
        field_metadata = getattr(metadata, "field_metadata", None) if metadata is not None else None
        usage = getattr(getattr(job, "metadata", None), "usage", None)
        billing = getattr(job, "usage", None)

        evidence = ExtractEvidence(
            purpose=purpose,
            requested_tier=self._settings.tier,
            requested_version=self._settings.version,
            tier=getattr(configuration, "tier", None),
            version=getattr(configuration, "version", None),
            job_id=job.id,
            file_id=file_id,
            extraction_target=extraction_target,
            schema_version=schema_version,
            latency_ms=_elapsed_ms(started),
            pages_extracted=getattr(usage, "num_pages_extracted", None),
            pages_billed=getattr(usage, "num_pages_billed", None),
            credits=getattr(billing, "credits", None),
            parse_job_id=getattr(metadata, "parse_job_id", None),
        )
        result = ExtractionResult(
            evidence=evidence,
            data=_to_plain(data),
            field_metadata=_to_plain(getattr(field_metadata, "document_metadata", None)),
            page_metadata=_to_plain(getattr(field_metadata, "page_metadata", None)),
            row_metadata=_to_plain(getattr(field_metadata, "row_metadata", None)),
        )
        summary = result.confidence_summary()
        logger.info(
            "document_extract.completed",
            purpose=purpose,
            job_id=evidence.job_id,
            tier=evidence.tier,
            version=evidence.version,
            extraction_target=extraction_target,
            records=len(result.records()),
            pages_extracted=evidence.pages_extracted,
            pages_billed=evidence.pages_billed,
            credits=evidence.credits,
            latency_ms=evidence.latency_ms,
            confidence_fields=summary["fields"],
            confidence_min=summary["min"],
        )
        _ops_log.info(
            "document_extract_completed purpose=%s job_id=%s tier=%s version=%s records=%d pages=%s latency_ms=%s "
            "confidence_min=%s",
            purpose,
            evidence.job_id,
            evidence.tier,
            evidence.version,
            len(result.records()),
            evidence.pages_extracted,
            evidence.latency_ms,
            summary["min"],
        )
        return result

    # -- extracting ------------------------------------------------------------

    def extract(
        self,
        content: bytes,
        *,
        filename: str,
        data_schema: Mapping[str, Any],
        purpose: str,
        schema_version: str = "1",
        extraction_target: str = "per_doc",
        max_pages: int | None = None,
        system_prompt: str | None = None,
    ) -> ExtractionResult:
        """Synchronously extract ``data_schema`` from one document.

        ``purpose`` names the decision being made (for example
        ``"bulk_upload_pdf"``) and is the only description of the call that
        reaches logs and evidence. ``schema_version`` identifies the revision
        of the schema so evidence stays interpretable after it changes.
        """
        self._require_enabled(purpose)
        configuration = self._configuration(
            data_schema, extraction_target=extraction_target, max_pages=max_pages, system_prompt=system_prompt
        )
        started = time.perf_counter()
        client = self._sync_client()
        file_id: str | None = None
        job_id: str | None = None
        try:
            uploaded = client.files.create(
                file=(filename, content, mime_type_for(filename)),
                purpose=_UPLOAD_PURPOSE,
                project_id=self._project_id(),
            )
            file_id = uploaded.id
            job = client.extract.run(
                file_input=file_id,
                configuration=configuration,
                project_id=self._project_id(),
                polling_timeout=self._settings.job_timeout_seconds,
            )
            job_id = job.id
        except _SDK_ERRORS as exc:
            raise self._unavailable(exc, purpose=purpose, started=started, job_id=job_id) from exc
        finally:
            if file_id is not None:
                self._delete_file(client, file_id, purpose=purpose)
        return self._result(
            job,
            purpose=purpose,
            file_id=file_id,
            extraction_target=extraction_target,
            schema_version=schema_version,
            started=started,
        )

    async def extract_async(
        self,
        content: bytes,
        *,
        filename: str,
        data_schema: Mapping[str, Any],
        purpose: str,
        schema_version: str = "1",
        extraction_target: str = "per_doc",
        max_pages: int | None = None,
        system_prompt: str | None = None,
    ) -> ExtractionResult:
        """Asynchronous twin of :meth:`extract` for request handlers on the event loop."""
        self._require_enabled(purpose)
        configuration = self._configuration(
            data_schema, extraction_target=extraction_target, max_pages=max_pages, system_prompt=system_prompt
        )
        started = time.perf_counter()
        client = self._aio_client()
        file_id: str | None = None
        job_id: str | None = None
        try:
            uploaded = await client.files.create(
                file=(filename, content, mime_type_for(filename)),
                purpose=_UPLOAD_PURPOSE,
                project_id=self._project_id(),
            )
            file_id = uploaded.id
            job = await client.extract.run(
                file_input=file_id,
                configuration=configuration,
                project_id=self._project_id(),
                polling_timeout=self._settings.job_timeout_seconds,
            )
            job_id = job.id
        except _SDK_ERRORS as exc:
            raise self._unavailable(exc, purpose=purpose, started=started, job_id=job_id) from exc
        finally:
            if file_id is not None:
                await self._delete_file_async(client, file_id, purpose=purpose)
        return self._result(
            job,
            purpose=purpose,
            file_id=file_id,
            extraction_target=extraction_target,
            schema_version=schema_version,
            started=started,
        )

    # -- vendor-side cleanup ---------------------------------------------------

    def _delete_file(self, client: Any, file_id: str, *, purpose: str) -> None:
        try:
            client.files.delete(file_id, project_id=self._project_id())
        except _SDK_ERRORS as exc:
            logger.warning(
                "document_extract.file_delete_failed",
                purpose=purpose,
                file_id=file_id,
                reason=classify_error(exc),
                error_type=type(exc).__name__,
            )

    async def _delete_file_async(self, client: Any, file_id: str, *, purpose: str) -> None:
        try:
            await client.files.delete(file_id, project_id=self._project_id())
        except _SDK_ERRORS as exc:
            logger.warning(
                "document_extract.file_delete_failed",
                purpose=purpose,
                file_id=file_id,
                reason=classify_error(exc),
                error_type=type(exc).__name__,
            )

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            client, self._client = self._client, None
        if client is not None and hasattr(client, "close"):
            client.close()

    async def aclose(self) -> None:
        with self._lock:
            client, self._async_client = self._async_client, None
        if client is not None and hasattr(client, "close"):
            await client.close()


_default_extractor: DocumentExtractor | None = None
_default_lock = threading.Lock()


def get_document_extractor() -> DocumentExtractor:
    """Process-wide extractor built from the environment on first use."""
    global _default_extractor
    with _default_lock:
        if _default_extractor is None:
            _default_extractor = DocumentExtractor()
        return _default_extractor


def reset_document_extractor() -> None:
    """Drop the cached extractor (tests, or after rotating ``LLAMA_CLOUD_API_KEY``)."""
    global _default_extractor
    with _default_lock:
        extractor, _default_extractor = _default_extractor, None
    if extractor is not None:
        extractor.close()


__all__ = [
    "APIError",
    "DocumentExtractUnavailable",
    "DocumentExtractor",
    "ExtractEvidence",
    "ExtractionResult",
    "classify_error",
    "get_document_extractor",
    "iter_confidences",
    "mime_type_for",
    "reset_document_extractor",
    "summarize_confidences",
]
