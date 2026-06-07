"""JSON-schema loading and the eager inbound validator for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import json

import structlog
from jsonschema import Draft7Validator

logger = structlog.get_logger("nlp-consumer")


def _load_schema() -> Draft7Validator:
    """Load JSON schema using standardized project path discovery."""
    from shared.paths import project_root

    repo_root = project_root()
    schema_path = repo_root / "schemas" / "events" / "nlp.extracted.schema.json"

    if not schema_path.exists():
        logger.error("schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


def _load_inbound_schema() -> Draft7Validator:
    """Load inbound event schema for validating Kafka messages from ingestion.

    Addresses OWASP API10:2023 — Unsafe Consumption of APIs.
    """
    from shared.paths import project_root

    repo_root = project_root()
    schema_path = repo_root / "schemas" / "events" / "ingest.normalized.schema.json"

    if not schema_path.exists():
        logger.error("inbound_schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find inbound schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


# Eagerly load inbound schema at module level so validation is fast per-message
try:
    _INBOUND_VALIDATOR = _load_inbound_schema()
except (FileNotFoundError, json.JSONDecodeError) as _schema_err:
    logger.error("inbound_schema_load_failed", error=str(_schema_err))
    _INBOUND_VALIDATOR = None
