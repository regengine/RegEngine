"""Runtime settings for the LlamaIndex "Extract" (LlamaCloud) integration.

Document extraction is optional. It is enabled only when ``LLAMA_CLOUD_API_KEY``
is present and ``REGENGINE_DOC_EXTRACT_ENABLED`` is not switched off; every
other value has a production-safe default. Invalid values never raise here:
this module is read lazily on the upload request path, and a typo in an
operator knob must degrade to the default rather than block an upload.

Environment variables
---------------------
``LLAMA_CLOUD_API_KEY``                     Vendor credential (also read natively by the SDK).
``LLAMA_CLOUD_BASE_URL``                    API root override (gateways, EU region, proxies).
``REGENGINE_DOC_EXTRACT_ENABLED``           ``0``/``false`` disables the integration even with a key.
``REGENGINE_DOC_EXTRACT_TIER``              ``cost_effective``, ``agentic`` (default), ``agentic_plus``
                                            or ``turbo``. Advanced Citations (bounding boxes) need
                                            ``agentic`` or above.
``REGENGINE_DOC_EXTRACT_VERSION``           Extract release to run. The vendor accepts ``latest`` or
                                            a ``YYYY-MM-DD`` date, which resolves to the nearest
                                            release at or before that date. RegEngine pins the
                                            Extract v2.5 release date (``2026-10-01``) by default so
                                            behaviour does not float; the concrete version the job
                                            ran is recorded in evidence either way.
``REGENGINE_DOC_EXTRACT_PROJECT_ID``        LlamaCloud project to upload into (default: the key's
                                            default project).
``REGENGINE_DOC_EXTRACT_TIMEOUT_SECONDS``   Per-HTTP-attempt timeout (default 60s; the upload is one
                                            request).
``REGENGINE_DOC_EXTRACT_JOB_TIMEOUT_SECONDS`` Wall-clock budget for one extraction job, polling
                                            included (default 240s; the admin proxy allows 300s).
``REGENGINE_DOC_EXTRACT_MAX_RETRIES``       SDK retries per HTTP request (default 1).
``REGENGINE_DOC_EXTRACT_MAX_PAGES``         Pages per document sent for extraction (default 50).
                                            Callers may lower it further (the bulk-upload page cap
                                            still applies first).
``REGENGINE_DOC_EXTRACT_CITE_SOURCES``      ``0`` turns off citations (default on).
``REGENGINE_DOC_EXTRACT_CONFIDENCE_SCORES`` ``0`` turns off per-field confidence (default on).
``REGENGINE_DOC_EXTRACT_DISABLE_CACHE``     ``0`` lets the vendor cache and reuse results across
                                            jobs (default ``1``: tenant documents are not retained
                                            as reusable extraction cache).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("document_extract.settings")

TIERS: tuple[str, ...] = ("cost_effective", "agentic", "agentic_plus", "turbo")
EXTRACTION_TARGETS: tuple[str, ...] = ("per_doc", "per_page", "per_table_row")

DEFAULT_TIER = "agentic"
# Extract v2.5 shipped on 2026-10-01; a date pin resolves to the nearest
# release at or before it, so this stays on v2.5 until an operator moves it.
DEFAULT_VERSION = "2026-10-01"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_JOB_TIMEOUT_SECONDS = 240.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_MAX_PAGES = 50

API_KEY_ENV = "LLAMA_CLOUD_API_KEY"  # pragma: allowlist secret
BASE_URL_ENV = "LLAMA_CLOUD_BASE_URL"
ENABLED_ENV = "REGENGINE_DOC_EXTRACT_ENABLED"
TIER_ENV = "REGENGINE_DOC_EXTRACT_TIER"
VERSION_ENV = "REGENGINE_DOC_EXTRACT_VERSION"
PROJECT_ID_ENV = "REGENGINE_DOC_EXTRACT_PROJECT_ID"
TIMEOUT_ENV = "REGENGINE_DOC_EXTRACT_TIMEOUT_SECONDS"
JOB_TIMEOUT_ENV = "REGENGINE_DOC_EXTRACT_JOB_TIMEOUT_SECONDS"
MAX_RETRIES_ENV = "REGENGINE_DOC_EXTRACT_MAX_RETRIES"
MAX_PAGES_ENV = "REGENGINE_DOC_EXTRACT_MAX_PAGES"
CITE_SOURCES_ENV = "REGENGINE_DOC_EXTRACT_CITE_SOURCES"
CONFIDENCE_SCORES_ENV = "REGENGINE_DOC_EXTRACT_CONFIDENCE_SCORES"
DISABLE_CACHE_ENV = "REGENGINE_DOC_EXTRACT_DISABLE_CACHE"

_FALSE_VALUES = {"0", "false", "no", "off"}


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_default_on(env: Mapping[str, str], name: str) -> bool:
    """A default-on switch: off only for an explicit false value."""
    raw = _read(env, name)
    return raw is None or raw.lower() not in _FALSE_VALUES


def _read_float(env: Mapping[str, str], name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("document_extract.settings.invalid", variable=name, fallback=default)
        return default
    if not (minimum <= value <= maximum):
        logger.warning("document_extract.settings.out_of_range", variable=name, fallback=default)
        return default
    return value


def _read_int(env: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("document_extract.settings.invalid", variable=name, fallback=default)
        return default
    if not (minimum <= value <= maximum):
        logger.warning("document_extract.settings.out_of_range", variable=name, fallback=default)
        return default
    return value


def _read_tier(env: Mapping[str, str]) -> str:
    raw = _read(env, TIER_ENV)
    if raw is None:
        return DEFAULT_TIER
    tier = raw.lower()
    if tier not in TIERS:
        logger.warning("document_extract.settings.invalid", variable=TIER_ENV, fallback=DEFAULT_TIER)
        return DEFAULT_TIER
    return tier


@dataclass(frozen=True)
class DocumentExtractSettings:
    """Resolved configuration for one :class:`~shared.document_extract.client.DocumentExtractor`."""

    # repr=False keeps the credential out of reprs, tracebacks and any log
    # line that formats the settings object.
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    enabled_flag: bool = True
    tier: str = DEFAULT_TIER
    version: str = DEFAULT_VERSION
    project_id: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    job_timeout_seconds: float = DEFAULT_JOB_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    max_pages: int = DEFAULT_MAX_PAGES
    cite_sources: bool = True
    confidence_scores: bool = True
    disable_cache: bool = True

    @property
    def enabled(self) -> bool:
        """True when a credential is configured and the kill switch is not set."""
        return self.enabled_flag and bool(self.api_key)

    def public_summary(self) -> dict[str, object]:
        """The switches, safe to log or display: whether a key is set, never the key."""
        return {
            "enabled": self.enabled,
            "key_present": bool(self.api_key),
            "kill_switch": not self.enabled_flag,
            "tier": self.tier,
            "version": self.version,
            "max_pages": self.max_pages,
            "cite_sources": self.cite_sources,
            "confidence_scores": self.confidence_scores,
            "disable_cache": self.disable_cache,
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> DocumentExtractSettings:
        """Build settings from ``env`` (defaults to ``os.environ``) without raising."""
        source: Mapping[str, str] = os.environ if env is None else env
        return cls(
            api_key=_read(source, API_KEY_ENV),
            base_url=_read(source, BASE_URL_ENV),
            enabled_flag=_read_default_on(source, ENABLED_ENV),
            tier=_read_tier(source),
            version=_read(source, VERSION_ENV) or DEFAULT_VERSION,
            project_id=_read(source, PROJECT_ID_ENV),
            timeout_seconds=_read_float(source, TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS, minimum=1.0, maximum=300.0),
            job_timeout_seconds=_read_float(
                source, JOB_TIMEOUT_ENV, DEFAULT_JOB_TIMEOUT_SECONDS, minimum=5.0, maximum=3600.0
            ),
            max_retries=_read_int(source, MAX_RETRIES_ENV, DEFAULT_MAX_RETRIES, minimum=0, maximum=5),
            max_pages=_read_int(source, MAX_PAGES_ENV, DEFAULT_MAX_PAGES, minimum=1, maximum=1000),
            cite_sources=_read_default_on(source, CITE_SOURCES_ENV),
            confidence_scores=_read_default_on(source, CONFIDENCE_SCORES_ENV),
            disable_cache=_read_default_on(source, DISABLE_CACHE_ENV),
        )
