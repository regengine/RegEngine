"""Runtime settings for the TypeSafe AI "Jev" integration.

Jev is optional. It is enabled only when ``TYPESAFE_API_KEY`` is present and
``REGENGINE_JEV_ENABLED`` is not switched off; every other value has a
production-safe default. Invalid values never raise here: this module is
read lazily on the ingestion request path, and a typo in an operator knob
must degrade to the default rather than block an upload.

Environment variables
---------------------
``TYPESAFE_API_KEY``                    Vendor credential (also read natively by the SDK).
``TYPESAFE_DEFAULT_MODEL``              Model name. RegEngine pins ``jev-1.13.0`` by default
                                        rather than the floating ``jev-latest`` alias so the
                                        confidence thresholds below stay calibrated against a
                                        known model; the response's concrete model name is
                                        recorded in evidence either way.
``TYPESAFE_BASE_URL``                   API root override (gateways, proxies).
``REGENGINE_JEV_ENABLED``               ``0``/``false`` disables the integration even with a key.
``REGENGINE_JEV_TIMEOUT_SECONDS``       Per-HTTP-attempt timeout (default 5s).
``REGENGINE_JEV_MAX_RETRIES``           Retries after the first attempt (default 1).
``REGENGINE_JEV_AUTO_APPLY_CONFIDENCE`` Choice confidence at or above which a suggestion may be
                                        applied without human review (default 0.90).
``REGENGINE_JEV_REVIEW_CONFIDENCE``     Choice confidence at or above which a suggestion is
                                        surfaced for review; below it the suggestion is
                                        discarded (default 0.50).
``REGENGINE_JEV_APPLY_HEADER_MAPPINGS`` ``1``/``true`` lets ``/ingest/csv`` apply AUTO_APPLY-band
                                        header mappings to rows. Default off: suggestions are
                                        recorded as advisory agent artifacts and returned in
                                        the response, but rows are parsed exactly as before.
``REGENGINE_JEV_HEADER_SAMPLE_VALUES``  Number of PII-redacted sample values per unrecognised
                                        column to include in the request (0-5, default 0:
                                        only column headers leave the process).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

import structlog

from .routing import ConfidenceThresholds

logger = structlog.get_logger("jev.settings")

DEFAULT_MODEL = "jev-1.13.0"
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 1
DEFAULT_AUTO_APPLY_CONFIDENCE = 0.90
DEFAULT_REVIEW_CONFIDENCE = 0.50

API_KEY_ENV = "TYPESAFE_API_KEY"  # pragma: allowlist secret
MODEL_ENV = "TYPESAFE_DEFAULT_MODEL"
BASE_URL_ENV = "TYPESAFE_BASE_URL"
ENABLED_ENV = "REGENGINE_JEV_ENABLED"
TIMEOUT_ENV = "REGENGINE_JEV_TIMEOUT_SECONDS"
MAX_RETRIES_ENV = "REGENGINE_JEV_MAX_RETRIES"
AUTO_APPLY_CONFIDENCE_ENV = "REGENGINE_JEV_AUTO_APPLY_CONFIDENCE"
REVIEW_CONFIDENCE_ENV = "REGENGINE_JEV_REVIEW_CONFIDENCE"
APPLY_HEADER_MAPPINGS_ENV = "REGENGINE_JEV_APPLY_HEADER_MAPPINGS"
HEADER_SAMPLE_VALUES_ENV = "REGENGINE_JEV_HEADER_SAMPLE_VALUES"

DEFAULT_HEADER_SAMPLE_VALUES = 0
MAX_HEADER_SAMPLE_VALUES = 5

_FALSE_VALUES = {"0", "false", "no", "off"}
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _read(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _read_float(env: Mapping[str, str], name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("jev.settings.invalid", variable=name, fallback=default)
        return default
    if not (minimum <= value <= maximum):
        logger.warning("jev.settings.out_of_range", variable=name, fallback=default)
        return default
    return value


def _read_int(env: Mapping[str, str], name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = _read(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("jev.settings.invalid", variable=name, fallback=default)
        return default
    if not (minimum <= value <= maximum):
        logger.warning("jev.settings.out_of_range", variable=name, fallback=default)
        return default
    return value


@dataclass(frozen=True)
class JevSettings:
    """Resolved configuration for one :class:`~shared.jev.client.JevDecider`."""

    api_key: str | None = None
    model: str = DEFAULT_MODEL
    base_url: str | None = None
    enabled_flag: bool = True
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES
    auto_apply_confidence: float = DEFAULT_AUTO_APPLY_CONFIDENCE
    review_confidence: float = DEFAULT_REVIEW_CONFIDENCE
    apply_header_mappings: bool = False
    header_sample_values: int = DEFAULT_HEADER_SAMPLE_VALUES

    @property
    def enabled(self) -> bool:
        """True when a credential is configured and the kill switch is not set."""
        return self.enabled_flag and bool(self.api_key)

    @property
    def retry_budget_seconds(self) -> float:
        """Total wall-clock budget for one call, including retries and backoff."""
        return self.timeout_seconds * (self.max_retries + 1) + 1.0

    @property
    def thresholds(self) -> ConfidenceThresholds:
        return ConfidenceThresholds(auto_apply=self.auto_apply_confidence, review=self.review_confidence)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> JevSettings:
        """Build settings from ``env`` (defaults to ``os.environ``) without raising."""
        source: Mapping[str, str] = os.environ if env is None else env
        enabled_raw = _read(source, ENABLED_ENV)
        enabled_flag = True if enabled_raw is None else enabled_raw.lower() not in _FALSE_VALUES

        auto_apply = _read_float(
            source, AUTO_APPLY_CONFIDENCE_ENV, DEFAULT_AUTO_APPLY_CONFIDENCE, minimum=0.0, maximum=1.0
        )
        review = _read_float(source, REVIEW_CONFIDENCE_ENV, DEFAULT_REVIEW_CONFIDENCE, minimum=0.0, maximum=1.0)
        if review > auto_apply:
            logger.warning(
                "jev.settings.threshold_order",
                review=review,
                auto_apply=auto_apply,
                fallback_review=DEFAULT_REVIEW_CONFIDENCE,
                fallback_auto_apply=DEFAULT_AUTO_APPLY_CONFIDENCE,
            )
            auto_apply, review = DEFAULT_AUTO_APPLY_CONFIDENCE, DEFAULT_REVIEW_CONFIDENCE

        apply_raw = _read(source, APPLY_HEADER_MAPPINGS_ENV)
        apply_header_mappings = apply_raw is not None and apply_raw.lower() in _TRUE_VALUES

        return cls(
            api_key=_read(source, API_KEY_ENV),
            model=_read(source, MODEL_ENV) or DEFAULT_MODEL,
            base_url=_read(source, BASE_URL_ENV),
            enabled_flag=enabled_flag,
            timeout_seconds=_read_float(source, TIMEOUT_ENV, DEFAULT_TIMEOUT_SECONDS, minimum=0.1, maximum=60.0),
            max_retries=_read_int(source, MAX_RETRIES_ENV, DEFAULT_MAX_RETRIES, minimum=0, maximum=5),
            auto_apply_confidence=auto_apply,
            review_confidence=review,
            apply_header_mappings=apply_header_mappings,
            header_sample_values=_read_int(
                source,
                HEADER_SAMPLE_VALUES_ENV,
                DEFAULT_HEADER_SAMPLE_VALUES,
                minimum=0,
                maximum=MAX_HEADER_SAMPLE_VALUES,
            ),
        )
