"""Runtime settings for the LlamaCloud "Extract" document-extraction integration.

Extract is optional. It is enabled only when ``LLAMA_CLOUD_API_KEY`` is
present and ``REGENGINE_LLAMA_EXTRACT_ENABLED`` is not switched off; every
other value has a production-safe default. Invalid values never raise here:
a typo in an operator knob degrades to the default rather than blocking a
caller.

Environment variables
---------------------
``LLAMA_CLOUD_API_KEY``                      Vendor credential (also read natively by the SDK).
``LLAMA_CLOUD_BASE_URL``                     API root override (gateways, proxies, EU region).
``LLAMA_CLOUD_PROJECT_ID``                   LlamaCloud project to upload into and run under.
                                             Unset = the key's default project.
``REGENGINE_LLAMA_EXTRACT_ENABLED``          ``0``/``false`` disables the integration even with a key.
``REGENGINE_LLAMA_EXTRACT_TIER``             ``cost_effective`` | ``agentic`` (default) |
                                             ``agentic_plus`` | ``turbo``.
``REGENGINE_LLAMA_EXTRACT_VERSION``          Extract release to run. RegEngine pins ``2.5``
                                             by default rather than the floating ``latest``
                                             so results stay comparable across uploads; the
                                             job's concrete resolved version is recorded in
                                             evidence either way.
``REGENGINE_LLAMA_EXTRACT_TIMEOUT_SECONDS``  Wall-clock budget for one document, upload plus
                                             polling (default 600s).
``REGENGINE_LLAMA_EXTRACT_MAX_PAGES``        Pages per document the vendor may process
                                             (default 0 = no limit).
``REGENGINE_LLAMA_EXTRACT_CITE_SOURCES``     ``0``/``false`` drops per-field citations
                                             (default on: they are the evidence trail).
``REGENGINE_LLAMA_EXTRACT_CONFIDENCE_SCORES`` ``0``/``false`` drops per-field confidence
                                             (default on).
``REGENGINE_LLAMA_EXTRACT_DISABLE_CACHE``    ``0``/``false`` lets the vendor keep and reuse
                                             extraction results (default on = results are
                                             not retained vendor-side).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger("llama_extract.settings")

DEFAULT_TIER = "agentic"
DEFAULT_VERSION = "2.5"
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_PAGES = 0

TIERS: tuple[str, ...] = ("cost_effective", "agentic", "agentic_plus", "turbo")

API_KEY_ENV = "LLAMA_CLOUD_API_KEY"  # pragma: allowlist secret
BASE_URL_ENV = "LLAMA_CLOUD_BASE_URL"
PROJECT_ID_ENV = "LLAMA_CLOUD_PROJECT_ID"
ENABLED_ENV = "REGENGINE_LLAMA_EXTRACT_ENABLED"
TIER_ENV = "REGENGINE_LLAMA_EXTRACT_TIER"
VERSION_ENV = "REGENGINE_LLAMA_EXTRACT_VERSION"
TIMEOUT_ENV = "REGENGINE_LLAMA_EXTRACT_TIMEOUT_SECONDS"
MAX_PAGES_ENV = "REGENGINE_LLAMA_EXTRACT_MAX_PAGES"
CITE_SOURCES_ENV = "REGENGINE_LLAMA_EXTRACT_CITE_SOURCES"
CONFIDENCE_SCORES_ENV = "REGENGINE_LLAMA_EXTRACT_CONFIDENCE_SCORES"
DISABLE_CACHE_ENV = "REGENGINE_LLAMA_EXTRACT_DISABLE_CACHE"

_FALSE_VALUES = {"0", "false", "no", "off"}


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_default_on(env: Mapping[str, str], name: str) -> bool:
    """A switch that is on unless explicitly set to a false value."""
    raw = _read(env, name)
    return raw is None or raw.lower() not in _FALSE_VALUES


def _read_float(env: Mapping[str, str], name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("llama_extract.settings.invalid", variable=name, fallback=default)
        return default
    if not (minimum <= value <= maximum):
        logger.warning("llama_extract.settings.out_of_range", variable=name, fallback=default)
        return default
    return value


def _read_int(env: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("llama_extract.settings.invalid", variable=name, fallback=default)
        return default
    if not (minimum <= value <= maximum):
        logger.warning("llama_extract.settings.out_of_range", variable=name, fallback=default)
        return default
    return value


def _read_tier(env: Mapping[str, str]) -> str:
    raw = _read(env, TIER_ENV)
    if raw is None:
        return DEFAULT_TIER
    tier = raw.lower()
    if tier not in TIERS:
        logger.warning("llama_extract.settings.invalid", variable=TIER_ENV, fallback=DEFAULT_TIER)
        return DEFAULT_TIER
    return tier


@dataclass(frozen=True)
class LlamaExtractSettings:
    """Resolved configuration for one :class:`~shared.llama_extract.client.DocumentExtractor`."""

    # repr=False keeps the credential out of reprs, tracebacks and any log
    # line that formats the settings object.
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    project_id: str | None = None
    enabled_flag: bool = True
    tier: str = DEFAULT_TIER
    version: str = DEFAULT_VERSION
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
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
            "project_id_set": bool(self.project_id),
            "max_pages": self.max_pages,
            "cite_sources": self.cite_sources,
            "confidence_scores": self.confidence_scores,
            "disable_cache": self.disable_cache,
        }

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LlamaExtractSettings:
        """Build settings from ``env`` (defaults to ``os.environ``) without raising."""
        source: Mapping[str, str] = os.environ if env is None else env
        return cls(
            api_key=_read(source, API_KEY_ENV),
            base_url=_read(source, BASE_URL_ENV),
            project_id=_read(source, PROJECT_ID_ENV),
            enabled_flag=_read_default_on(source, ENABLED_ENV),
            tier=_read_tier(source),
            version=_read(source, VERSION_ENV) or DEFAULT_VERSION,
            timeout_seconds=_read_float(
                source, TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS, minimum=5.0, maximum=7200.0
            ),
            max_pages=_read_int(source, MAX_PAGES_ENV, DEFAULT_MAX_PAGES, minimum=0, maximum=10_000),
            cite_sources=_read_default_on(source, CITE_SOURCES_ENV),
            confidence_scores=_read_default_on(source, CONFIDENCE_SCORES_ENV),
            disable_cache=_read_default_on(source, DISABLE_CACHE_ENV),
        )
