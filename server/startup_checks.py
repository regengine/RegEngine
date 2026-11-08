"""Startup checks for the consolidated monolith (tech-debt WI-14, 2026-11-04).

Split out of ``server/main.py``: the import-time environment and secret
gates, and the lifespan's best-effort initialisation steps. ``server.main``
keeps the lifespan itself (its order is the contract the deploy log is read
against) and calls these in the same sequence as before. Every log event name
and its order are unchanged; the lazy imports inside each function are kept
so the tests that monkeypatch the source modules keep working.
"""

from __future__ import annotations

import logging

from shared.observability.context import logger


def run_import_time_checks() -> None:
    """Gates evaluated while ``server.main`` is imported (before any request).

    ``validate_auth_config`` refuses to boot with an unusable auth
    configuration. The two secrets checks fail fast in production when
    required credentials are missing or still set to insecure placeholders:
    startup requires DATABASE_URL; unset optional subsystem values (Neo4j,
    object storage) stay unset so those paths degrade (no-op or 503) instead
    of aborting boot. The credential getters keep their own
    fail-closed-on-use contract.
    """
    from shared.auth import validate_auth_config

    validate_auth_config()

    from shared.secrets_manager import (
        require_secure_secrets_in_production,
        validate_production_secrets,
    )

    require_secure_secrets_in_production()
    validate_production_secrets()


def init_admin_database() -> None:
    """RLS posture probe + SQLite dev tables; PostgreSQL DDL is Alembic-owned."""
    try:
        from services.admin.app.database import init_db

        init_db()
        logger.info("admin_database_initialized")
    except Exception as exc:
        logger.warning("admin_database_init_skipped", error=str(exc))


def register_integration_connectors() -> None:
    """Register integration connectors (best-effort)."""
    try:
        from shared.external_connectors.register_all import register_all_connectors

        register_all_connectors()
        logger.info("integration_connectors_registered")
    except Exception as exc:
        logger.warning("connector_registration_skipped", error=str(exc))


def log_integration_config() -> None:
    """Log whether the optional TypeSafe Jev and LlamaIndex Extract integrations are live.

    An operator confirms a newly added key from the deploy logs without
    reading the variable (CLAUDE.md names the ``jev_configured`` and
    ``document_extract_configured`` lines). Logs switches only, never a key.
    Through stdlib logging, like registered_connector: the structlog chain
    drops INFO events without a sampled trace when LOG_ALL_SAMPLED_OUT=false
    (sampling_aware_filter), and startup has no trace.
    """
    try:
        from shared.jev import JevSettings

        summary = JevSettings.from_env().public_summary()
        logging.getLogger("jev").info(
            "jev_configured %s", " ".join(f"{name}={value}" for name, value in summary.items())
        )
    except Exception as exc:
        logger.warning("jev_config_probe_failed", error=str(exc))

    # Same for LlamaIndex Extract (document extraction on the bulk-upload PDF
    # path). Never the key: public_summary() reports key_present only.
    try:
        from shared.document_extract import DocumentExtractSettings

        summary = DocumentExtractSettings.from_env().public_summary()
        logging.getLogger("document_extract").info(
            "document_extract_configured %s", " ".join(f"{name}={value}" for name, value in summary.items())
        )
    except Exception as exc:
        logger.warning("document_extract_config_probe_failed", error=str(exc))


def configure_audit_logger(is_prod: bool) -> None:
    """#2854: GDPR / FSMA audit events join the hash chain, not an in-process list."""
    from shared.audit_logging import AuditLogger, PostgresHashChainAuditStorage

    AuditLogger.configure(
        storage=PostgresHashChainAuditStorage(),
        environment="production" if is_prod else "development",
        service_name="regengine",
    )
