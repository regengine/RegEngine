"""JSON-schema loading and the eager inbound validator for the NLP consumer.

Split out of the original ``app/consumer.py`` module. All names are
re-exported from ``app.consumer`` for backward compatibility.
"""

from __future__ import annotations

import json

import structlog
from jsonschema import Draft7Validator, ValidationError

logger = structlog.get_logger("nlp-consumer")


def _load_schema() -> Draft7Validator:
    """Load JSON schema using standardized project path discovery."""
    from shared.paths import data_schemas_dir

    schema_path = data_schemas_dir() / "events" / "nlp.extracted.schema.json"

    if not schema_path.exists():
        logger.error("schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


def _load_inbound_schema() -> Draft7Validator:
    """Load inbound event schema for validating Kafka messages from ingestion.

    Addresses OWASP API10:2023 — Unsafe Consumption of APIs.
    """
    from shared.paths import data_schemas_dir

    schema_path = data_schemas_dir() / "events" / "ingest.normalized.schema.json"

    if not schema_path.exists():
        logger.error("inbound_schema_not_found", path=str(schema_path))
        raise FileNotFoundError(f"Could not find inbound schema at {schema_path}")

    schema = json.loads(schema_path.read_text())
    return Draft7Validator(schema)


class _UnavailableInboundValidator:
    """Fail-closed stand-in used when the inbound schema cannot be loaded.

    #2965: the previous fallback was ``_INBOUND_VALIDATOR = None``, and the
    consumer's ``if _INBOUND_VALIDATOR is not None`` guard turned that miss
    into "validate nothing" — every message, malformed or hostile, flowed
    straight into extraction with one ERROR log line as the only signal. That
    is fail-OPEN on a control the code names as OWASP API10:2023.

    This object keeps the consumer's ``is not None`` guard true and makes
    ``iter_errors`` yield one error for every instance, so an image or
    checkout missing ``data-schemas/`` rejects messages to the DLQ instead of
    waving them through. Deliberately not raising at import: the package is
    imported by ``server/workers/task_processor.py`` inside the monolith,
    which never runs the consumer loop, and taking the whole app down for a
    schema the running process will not use would be a worse trade.
    """

    __slots__ = ("reason",)

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def _error(self) -> ValidationError:
        return ValidationError(
            f"Inbound schema unavailable, message rejected (fail-closed): {self.reason}"
        )

    def iter_errors(self, instance):  # noqa: ANN001 — mirrors Draft7Validator
        yield self._error()

    def validate(self, instance) -> None:  # noqa: ANN001 — mirrors Draft7Validator
        raise self._error()

    def is_valid(self, instance) -> bool:  # noqa: ANN001 — mirrors Draft7Validator
        return False


# Eagerly load inbound schema at module level so validation is fast per-message
try:
    _INBOUND_VALIDATOR = _load_inbound_schema()
except (FileNotFoundError, json.JSONDecodeError) as _schema_err:
    logger.error(
        "inbound_schema_load_failed",
        error=str(_schema_err),
        effect="failing closed — every inbound message will be rejected",
    )
    _INBOUND_VALIDATOR = _UnavailableInboundValidator(str(_schema_err))
