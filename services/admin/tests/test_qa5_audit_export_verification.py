"""QA5: audit export chain verification must verify canonical row values.

``GET /v1/audit/export?include_verification=true`` fed the PII-masked
display entries into ``verify_chain``, but the chain was hashed over
raw metadata, raw actor fields, and a top-level severity. Two
independent defects made verification false-alarm on legitimate rows:

* ``verify_chain`` read ``severity`` only at the top level while the
  export nests it under ``event.severity`` (always recomputed as None).
* The route verified the redacted view instead of the canonical values.

Plus a counting fix: ``verified`` subtracted error objects from the
entry count, which goes negative when one row yields two errors.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.audit import compute_integrity_hash  # noqa: E402
from app.audit_integrity import verify_chain  # noqa: E402
from app.audit_routes import (  # noqa: E402
    _build_verification_entries,
    _redact_metadata_pii,
)

TENANT = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
NOW_ISO = "2026-10-01T12:00:00.123456+00:00"


def _writer_hash(**overrides):
    params = {
        "prev_hash": None,
        "tenant_id": TENANT,
        "timestamp": NOW_ISO,
        "event_type": "auth.login",
        "action": "login",
        "resource_id": None,
        "metadata": {},
        "actor_id": None,
        "actor_email": "curator@example.com",
        "severity": "info",
        "endpoint": "/login",
        "sequence_num": 1,
    }
    params.update(overrides)
    return compute_integrity_hash(**params)


def _export_shaped_entry(entry_id=1, **writer_overrides):
    """An entry shaped exactly like audit_routes builds it: severity
    nested under ``event``, no top-level ``severity`` key."""
    metadata = writer_overrides.get("metadata", {})
    actor_email = writer_overrides.get("actor_email", "curator@example.com")
    severity = writer_overrides.get("severity", "info")
    return {
        "id": entry_id,
        "tenant_id": TENANT,
        "timestamp": NOW_ISO,
        "actor": {"id": writer_overrides.get("actor_id"), "email": actor_email},
        "event": {"type": "auth.login", "category": "auth", "action": "login", "severity": severity},
        "resource": {"type": None, "id": None},
        "endpoint": "/login",
        "metadata": metadata,
        "integrity": {
            "prev_hash": None,
            "hash": _writer_hash(**writer_overrides),
            "sequence_num": 1,
        },
    }


class TestExportShapedSeverity:
    def test_export_shaped_entry_with_nested_severity_verifies(self):
        """Pre-fix this failed: the verifier read top-level severity
        (missing -> None) while the writer hashed ``info``."""
        result = verify_chain([_export_shaped_entry()])
        assert result["valid"] is True, result["errors"]
        assert result["verified"] == 1

    def test_top_level_severity_still_preferred(self):
        """Writer-shaped entries (severity at top level) keep working."""
        entry = _export_shaped_entry()
        entry["severity"] = "info"
        result = verify_chain([entry])
        assert result["valid"] is True, result["errors"]

    def test_wrong_nested_severity_still_fails(self):
        """The fallback must not blindly accept: a tampered severity
        must still mismatch."""
        entry = _export_shaped_entry()
        entry["event"]["severity"] = "critical"
        result = verify_chain([entry])
        assert result["valid"] is False
        assert any(e["error"] == "integrity_hash_mismatch" for e in result["errors"])


class TestVerifiedCountFloor:
    def test_single_broken_row_never_reports_negative_verified(self):
        """A row with both prev_hash_mismatch and integrity_hash_mismatch
        used to report ``verified: -1``. It must report 0 of 1."""
        good = _export_shaped_entry(entry_id=1)
        bad = _export_shaped_entry(entry_id=2, metadata={"k": "v"})
        bad["integrity"]["prev_hash"] = "0" * 64  # wrong linkage
        bad["integrity"]["hash"] = "f" * 64  # wrong hash
        result = verify_chain([good, bad])
        assert result["valid"] is False
        assert result["total_entries"] == 2
        assert result["verified"] == 1
        assert result["verified"] >= 0


class TestRedactedViewCannotVerify:
    def test_redacted_metadata_view_fails_while_canonical_passes(self):
        """The core F3 proof: metadata containing an email address is
        transformed by the export redaction pass, so verifying the
        display view false-alarms. The canonical builder preserves the
        raw values the writer hashed."""
        raw_metadata = {"contact": "curator@example.com", "note": "routine review"}
        row = SimpleNamespace(
            id=7,
            tenant_id=uuid.UUID(TENANT),
            timestamp=datetime(2026, 10, 1, 12, 0, 0, 123456, tzinfo=timezone.utc),
            actor_id=uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            actor_email="curator@example.com",
            event_type="review.decision",
            event_category="review",
            action="approve",
            severity="info",
            resource_type="review",
            resource_id="review-1",
            endpoint="/review/approve",
            metadata_=dict(raw_metadata),
            request_id=None,
            prev_hash=None,
            sequence_num=1,
            integrity_hash=_writer_hash(
                event_type="review.decision",
                action="approve",
                resource_id="review-1",
                metadata=raw_metadata,
                actor_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
                timestamp="2026-10-01T12:00:00.123456+00:00",
                endpoint="/review/approve",
            ),
        )

        canonical = _build_verification_entries([row])
        assert canonical[0]["metadata"] == raw_metadata
        assert canonical[0]["actor"]["email"] == "curator@example.com"
        assert canonical[0]["severity"] == "info"
        assert verify_chain(canonical)["valid"] is True

        # The display view the old code verified must differ (redacted).
        display_metadata = _redact_metadata_pii(row.metadata_)
        assert display_metadata != raw_metadata

    def test_canonical_builder_keeps_raw_actor_and_top_level_severity(self):
        row = SimpleNamespace(
            id=3,
            tenant_id=uuid.UUID(TENANT),
            timestamp=datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc),
            actor_id=None,
            actor_email=None,
            event_type="auth.login",
            event_category="auth",
            action="login",
            severity="warning",
            resource_type=None,
            resource_id=None,
            endpoint=None,
            metadata_={},
            request_id=None,
            prev_hash=None,
            sequence_num=1,
            integrity_hash="x" * 64,
        )
        canonical = _build_verification_entries([row])[0]
        assert canonical["actor"] == {"id": None, "email": None}
        assert canonical["severity"] == "warning"
        assert canonical["event"]["severity"] == "warning"
        assert canonical["integrity"] == {"prev_hash": None, "hash": "x" * 64, "sequence_num": 1}
