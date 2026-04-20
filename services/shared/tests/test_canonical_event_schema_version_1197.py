"""Tests for envelope ``schema_version`` on ``TraceabilityEvent`` (#1197).

The issue: the canonical event flowing between producer and consumer
(Kafka, fsma.task_queue, graph_outbox) had no envelope version. A
breaking change to the wire format would have mixed old and new events
indistinguishably, causing either consumer crashes or — worse — silent
partial parses.

These tests lock in:

  * ``schema_version`` is an integer and defaults to ``1`` on construction.
  * ``parse_traceability_event`` treats a missing ``schema_version`` as
    ``1`` so pre-#1197 events still hydrate without a data migration.
  * Unknown versions are rejected with a grep-friendly error prefix
    (``schema_version_unsupported``) for metrics/DLQ taxonomy.
  * ``.model_dump()`` / ``.model_dump_json()`` include the field so it
    survives a round-trip through JSON-valued columns (``normalized_payload``)
    and Kafka messages.

The tests are unit-level (no DB, no Kafka) — the schema_version dispatch
is a pure contract on the shared model, and higher layers each test the
field on top of it. See ``services/graph/scripts/fsma_sync_worker.py``
for the first consumer that actually enforces the ``KNOWN_VERSIONS``
guard end-to-end.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Import shared.canonical_event without needing a package ``__init__``.
# Mirrors the approach used by test_tenant_context.py in this directory
# so the test runs correctly under pytest-as-invoked-from-services/shared.
# ---------------------------------------------------------------------------
_SHARED_DIR = Path(__file__).resolve().parent.parent
_SERVICES_DIR = _SHARED_DIR.parent
for _p in (_SHARED_DIR, _SERVICES_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from shared.canonical_event import (  # noqa: E402
    KNOWN_VERSIONS,
    SCHEMA_VERSION,
    CTEType,
    IngestionSource,
    TraceabilityEvent,
    parse_traceability_event,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT_ID = uuid4()


def _minimal_event_kwargs() -> dict:
    """Minimum fields required to construct a ``TraceabilityEvent``.

    Intentionally short — the schema_version contract is orthogonal to
    every other field, so these tests use the smallest valid event and
    do NOT cover cross-field invariants (those live in
    ``tests/test_canonical_event.py``).
    """
    return dict(
        tenant_id=TENANT_ID,
        source_system=IngestionSource.WEBHOOK_API,
        event_type=CTEType.RECEIVING,
        event_timestamp="2026-04-20T12:00:00Z",
        traceability_lot_code="TLC-TEST-1197",
        quantity=10.0,
        unit_of_measure="each",
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestSchemaVersionDefault:
    """Construction-time behaviour of the ``schema_version`` field."""

    def test_new_event_has_schema_version_default_1(self) -> None:
        """A fresh event with no explicit version must default to v1.

        This is the producer-side contract: every event minted today
        is v1, the only version ``KNOWN_VERSIONS`` currently knows.
        """
        event = TraceabilityEvent(**_minimal_event_kwargs())
        assert event.schema_version == 1
        assert isinstance(event.schema_version, int)
        # Module-level constant must match the default — consumers that
        # compare ``event.schema_version == SCHEMA_VERSION`` are a
        # common idiom, protect them.
        assert SCHEMA_VERSION == 1

    def test_explicit_int_schema_version_accepted(self) -> None:
        """Explicit integer version passes through unchanged."""
        event = TraceabilityEvent(schema_version=1, **_minimal_event_kwargs())
        assert event.schema_version == 1

    def test_schema_version_in_known_versions(self) -> None:
        """The default must be in the accepted set.

        Guards against accidentally bumping ``SCHEMA_VERSION`` without
        extending ``KNOWN_VERSIONS`` — a misconfig where every producer
        emits unparseable events.
        """
        assert SCHEMA_VERSION in KNOWN_VERSIONS


# ---------------------------------------------------------------------------
# Legacy / backward compat
# ---------------------------------------------------------------------------

class TestLegacyStringCoercion:
    """Pre-#1197 rows stored ``schema_version`` as a semver string
    (``"1.0.0"``). Round-tripping through the updated Pydantic model
    must not raise — a backfill migration would be a giant multi-tenant
    write and the value collapses cleanly to integer 1."""

    @pytest.mark.parametrize(
        "legacy",
        ["1.0.0", "1.0", "1", "v1", "v1.0", "v1.0.0"],
    )
    def test_legacy_string_coerces_to_1(self, legacy: str) -> None:
        event = TraceabilityEvent(schema_version=legacy, **_minimal_event_kwargs())
        assert event.schema_version == 1

    def test_unknown_string_rejected(self) -> None:
        """A string that is neither numeric nor a known legacy alias
        must fail loudly. Silent coercion here is the exact failure mode
        #1197 exists to prevent — a v3 producer on a v1 consumer."""
        with pytest.raises(ValueError, match="schema_version"):
            TraceabilityEvent(schema_version="banana", **_minimal_event_kwargs())

    def test_bool_rejected(self) -> None:
        """``bool`` is an ``int`` subclass in Python; without an explicit
        guard ``True`` would be accepted as ``1`` (a known version)
        which is nonsense. Reject it explicitly."""
        with pytest.raises(ValueError, match="bool"):
            TraceabilityEvent(schema_version=True, **_minimal_event_kwargs())


# ---------------------------------------------------------------------------
# parse_traceability_event dispatch
# ---------------------------------------------------------------------------

class TestParseTraceabilityEvent:
    """Wire-format dispatch helper — the entry point consumers should
    use to hydrate a dict/bytes/str payload from Kafka, task_queue, or
    graph_outbox."""

    def _valid_payload(self) -> dict:
        """Round-trip a constructed event to a pure-JSON dict.

        Using ``model_dump(mode='json')`` rather than ``model_dump()``
        so UUIDs and datetimes become strings — matching what a real
        Kafka/task_queue consumer would read from JSON storage.
        """
        return TraceabilityEvent(**_minimal_event_kwargs()).model_dump(mode="json")

    def test_old_payload_without_schema_version_parses_as_v1(self) -> None:
        """Pre-#1197 events on the wire have no ``schema_version`` key
        at all. Those must still hydrate cleanly as v1 — dropping
        in-flight audit history at deploy time is unacceptable."""
        payload = self._valid_payload()
        payload.pop("schema_version", None)
        event = parse_traceability_event(payload)
        assert event.schema_version == 1

    def test_payload_with_int_schema_version_parses(self) -> None:
        payload = self._valid_payload()
        payload["schema_version"] = 1
        event = parse_traceability_event(payload)
        assert event.schema_version == 1

    def test_unknown_schema_version_rejected(self) -> None:
        """Critical #1197 invariant — an envelope the consumer doesn't
        know about MUST raise. A partial parse here is the silent
        data-loss path."""
        payload = self._valid_payload()
        payload["schema_version"] = 999
        with pytest.raises(ValueError, match="schema_version_unsupported"):
            parse_traceability_event(payload)

    def test_unknown_schema_version_as_negative_rejected(self) -> None:
        """Negative versions are obvious producer bugs, not a deliberate
        choice. Must reject with the same tag so metrics aggregate."""
        payload = self._valid_payload()
        payload["schema_version"] = -1
        with pytest.raises(ValueError, match="schema_version_unsupported"):
            parse_traceability_event(payload)

    def test_bytes_payload_accepted(self) -> None:
        """Kafka gives us ``bytes`` from the broker; the helper must
        handle it without forcing every consumer to decode first."""
        payload = self._valid_payload()
        raw = json.dumps(payload).encode("utf-8")
        event = parse_traceability_event(raw)
        assert event.schema_version == 1

    def test_str_payload_accepted(self) -> None:
        """Redis BLPOP returns ``bytes`` today but may return ``str`` in
        decoded-responses mode — cover both."""
        payload = self._valid_payload()
        raw = json.dumps(payload)
        event = parse_traceability_event(raw)
        assert event.schema_version == 1

    def test_malformed_json_raises_valueerror(self) -> None:
        """JSON decode failures must surface as ``ValueError`` so callers
        using ``except ValueError`` for "bad envelope" catch them —
        keeping the error taxonomy flat at the consumer boundary."""
        with pytest.raises(ValueError, match="traceability_event_payload_not_json"):
            parse_traceability_event(b"{not valid json")

    def test_non_object_json_rejected(self) -> None:
        """A JSON array or bare string is not a TraceabilityEvent — must
        reject before Pydantic surfaces a less-obvious error."""
        with pytest.raises(ValueError, match="traceability_event_payload_not_object"):
            parse_traceability_event(b"[1, 2, 3]")

    def test_wrong_type_raises_typeerror(self) -> None:
        """Anything other than bytes/str/dict is a programmer error."""
        with pytest.raises(TypeError):
            parse_traceability_event(12345)  # type: ignore[arg-type]

    def test_legacy_string_schema_version_in_payload(self) -> None:
        """A dict payload with legacy ``"1.0.0"`` passes the KNOWN_VERSIONS
        check (via the coercion) and hydrates cleanly."""
        payload = self._valid_payload()
        payload["schema_version"] = "1.0.0"
        event = parse_traceability_event(payload)
        assert event.schema_version == 1


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSchemaVersionSerialization:
    """The field must survive ``model_dump`` / ``model_dump_json``
    because downstream persistence stores the serialized form into a
    JSONB column (``fsma.traceability_events.normalized_payload``) and
    Kafka writes the JSON bytes directly."""

    def test_schema_version_serialized_in_dict(self) -> None:
        event = TraceabilityEvent(**_minimal_event_kwargs())
        dumped = event.model_dump()
        assert "schema_version" in dumped
        assert dumped["schema_version"] == 1

    def test_schema_version_serialized_in_json(self) -> None:
        event = TraceabilityEvent(**_minimal_event_kwargs())
        dumped = event.model_dump_json()
        parsed = json.loads(dumped)
        assert parsed["schema_version"] == 1

    def test_schema_version_in_normalized_payload(self) -> None:
        """``prepare_for_persistence`` builds ``normalized_payload`` from
        canonical fields — the ``schema_version`` stamp must be inside it
        so a row re-hydrated purely from ``normalized_payload`` (a path
        the writer supports) knows which envelope it came from."""
        event = TraceabilityEvent(**_minimal_event_kwargs()).prepare_for_persistence()
        assert "schema_version" in event.normalized_payload
        assert event.normalized_payload["schema_version"] == 1

    def test_round_trip_preserves_schema_version(self) -> None:
        event = TraceabilityEvent(**_minimal_event_kwargs())
        dumped = event.model_dump_json()
        rehydrated = parse_traceability_event(dumped)
        assert rehydrated.schema_version == event.schema_version == 1
