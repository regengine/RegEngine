"""Base configuration for all RegEngine services.

All per-service Settings classes should inherit from BaseServiceSettings
to ensure consistent env loading, logging, and model_config behavior.
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Accepted spellings of CANONICAL_LEGACY_DUAL_WRITE (compared lower-cased).
_DUAL_WRITE_FLAG_VALUES = frozenset({"on", "off", "1", "0", "true", "false", "yes", "no"})


class BaseServiceSettings(BaseSettings):
    """Common settings shared by all RegEngine services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    regengine_env: str = Field(default="development", alias="REGENGINE_ENV")
    # WI-12 PR B: ``on`` keeps the legacy fsma.cte_events dual-write; ``off``
    # makes the canonical writer skip it and count the skip. Read at write
    # time from the environment by
    # ``shared.canonical_persistence.legacy_dual_write.legacy_dual_write_enabled``
    # (the writer is shared code with no settings instance); declared here so
    # every service's Settings documents and validates the variable.
    canonical_legacy_dual_write: str = Field(
        default="on",
        alias="CANONICAL_LEGACY_DUAL_WRITE",
    )

    @field_validator("canonical_legacy_dual_write", mode="before")
    @classmethod
    def _normalise_dual_write_flag(cls, value: object) -> str:
        """Strip the value and treat an empty variable as the default (``on``).

        Railway adds a variable before it has a value, and a rollback may clear
        it; both must keep the monolith booting with the safe default rather
        than fail ``Settings()`` at import. The writer reads the same variable
        with ``.strip().lower()`` (``legacy_dual_write.legacy_dual_write_enabled``),
        so the two agree on every value.
        """
        if value is None:
            return "on"
        text = str(value).strip()
        if not text:
            return "on"
        if text.lower() not in _DUAL_WRITE_FLAG_VALUES:
            raise ValueError("CANONICAL_LEGACY_DUAL_WRITE must be one of on, off, 1, 0, true, false, yes, no")
        return text


class ObjectStorageMixin(BaseSettings):
    """Mixin for services that access S3-compatible object storage."""

    object_storage_endpoint_url: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ENDPOINT_URL",
    )
    object_storage_region: str = Field(
        default="us-east-1",
        alias="OBJECT_STORAGE_REGION",
    )
    object_storage_access_key_id: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_ACCESS_KEY_ID",
    )
    object_storage_secret_access_key: Optional[str] = Field(
        default=None,
        alias="OBJECT_STORAGE_SECRET_ACCESS_KEY",
    )
