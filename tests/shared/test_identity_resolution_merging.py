"""Focused contract tests for services/shared/identity_resolution/merging.py.

Covers the main public behavior of the merge/split API:
``merge_entities`` (1:1 wrapper), ``merge_entities_bulk`` (N-way merge),
and ``split_entity`` (merge reversal).

Session-mocked, no real DB. Complements the issue-specific suites
(``test_identity_resolution_nway_merge_1195.py`` for the N-way history
contract and ``test_identity_resolution_alias_snapshot_1207.py`` for
alias snapshot/replay) by locking in return shapes, delegation,
review-queue closure, malformed-snapshot tolerance, and error guards.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from services.shared.identity_resolution import IdentityResolutionService

TENANT = "tenant-merging"
SRC_A = "11111111-1111-1111-1111-111111111111"
SRC_B = "33333333-3333-3333-3333-333333333333"
TGT = "22222222-2222-2222-2222-222222222222"
MERGE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class _FakeSession:
    """Scripted stand-in for a SQLAlchemy session.

    Answers entity-existence checks, the pre-merge alias snapshot
    SELECT, and the split merge-history fetch; records every other
    statement by kind for assertions.
    """

    def __init__(
        self,
        source_aliases: Optional[Dict[str, List[Tuple[str, str]]]] = None,
        merge_row: Optional[Tuple[Any, ...]] = None,
    ):
        self._source_aliases = source_aliases or {}
        self.merge_row = merge_row
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        params = dict(params or {})

        if "SELECT 1 FROM fsma.canonical_entities" in sql:
            self.calls.append(("require_entity", params))
            result.fetchone.return_value = (1,)
            return result

        if (
            "FROM fsma.entity_aliases" in sql
            and "alias_type, alias_value" in sql
            and "entity_id = :source_entity_id" in sql
        ):
            self.calls.append(("snapshot_select", params))
            aliases = self._source_aliases.get(params.get("source_entity_id"), [])
            result.fetchall.return_value = list(aliases)
            return result

        if "FROM fsma.entity_merge_history" in sql and "merge_id = :merge_id" in sql:
            self.calls.append(("history_fetch", params))
            result.fetchone.return_value = self.merge_row
            return result

        if "UPDATE" in sql and "fsma.entity_aliases" in sql:
            self.calls.append(("alias_update", params))
        elif "DELETE FROM fsma.entity_aliases" in sql:
            self.calls.append(("alias_delete", params))
        elif "UPDATE fsma.canonical_entities" in sql:
            kind = "entity_reactivate" if "is_active = TRUE" in sql else "entity_deactivate"
            self.calls.append((kind, params))
        elif "INSERT INTO fsma.entity_merge_history" in sql:
            self.calls.append(("history_insert", params))
        elif "UPDATE fsma.entity_merge_history" in sql:
            self.calls.append(("mark_reversed", params))
        elif "UPDATE fsma.identity_review_queue" in sql:
            self.calls.append(("review_close", params))
        else:
            self.calls.append(("other", params))
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result


def _svc(session, **kwargs):
    return IdentityResolutionService(session, **kwargs)


def _merge_row(snapshot):
    # merge_row columns: (merge_id, source_entity_ids[], target_id,
    #                     action, is_reversed, alias_snapshot)
    return (MERGE_ID, [SRC_A], TGT, "merge", False, snapshot)


def _kinds(session):
    return [c[0] for c in session.calls]


# ===========================================================================
# merge_entities_bulk: return shape and side effects
# ===========================================================================


class TestBulkMergeContract:
    def test_return_shape(self):
        session = _FakeSession()
        result = _svc(session).merge_entities_bulk(
            TENANT,
            [SRC_A, SRC_B],
            TGT,
            reason="dedupe",
            performed_by="op-1",
        )
        assert result["action"] == "merge"
        assert result["source_entity_ids"] == [SRC_A, SRC_B]
        assert result["target_entity_id"] == TGT
        assert result["reason"] == "dedupe"
        assert result["performed_by"] == "op-1"
        UUID(result["merge_id"])
        datetime.fromisoformat(result["performed_at"])

    def test_deactivates_sources_and_closes_pending_reviews(self):
        session = _FakeSession()
        _svc(session).merge_entities_bulk(TENANT, [SRC_A, SRC_B], TGT, performed_by="op-1")
        deactivations = [c for c in session.calls if c[0] == "entity_deactivate"]
        assert len(deactivations) == 1
        assert deactivations[0][1]["source_entity_ids"] == [SRC_A, SRC_B]
        closes = [c for c in session.calls if c[0] == "review_close"]
        assert len(closes) == 1
        assert closes[0][1]["source_entity_ids"] == [SRC_A, SRC_B]
        # SQL binds :performed_by into the resolved_by column.
        assert closes[0][1]["performed_by"] == "op-1"

    def test_empty_sources_rejected_before_side_effects(self):
        session = _FakeSession()
        with pytest.raises(ValueError, match="must not be empty"):
            _svc(session).merge_entities_bulk(TENANT, [], TGT)
        assert session.calls == []


# ===========================================================================
# merge_entities: thin 1:1 wrapper
# ===========================================================================


class TestSingleMergeWrapper:
    def test_delegates_with_reason_and_performer(self):
        session = _FakeSession()
        result = _svc(session).merge_entities(TENANT, SRC_A, TGT, reason="legacy", performed_by="op-9")
        assert result["source_entity_ids"] == [SRC_A]
        assert result["target_entity_id"] == TGT
        insert = next(c for c in session.calls if c[0] == "history_insert")
        assert insert[1]["source_entity_ids"] == [SRC_A]
        assert insert[1]["reason"] == "legacy"
        assert insert[1]["performed_by"] == "op-9"

    def test_self_merge_rejected(self):
        session = _FakeSession()
        with pytest.raises(ValueError, match="itself"):
            _svc(session).merge_entities(TENANT, SRC_A, SRC_A)


# ===========================================================================
# split_entity: reversal contract
# ===========================================================================


class TestSplitContract:
    def test_split_records_reversal_and_returns_shape(self):
        snapshot = {SRC_A: [{"alias_type": "gln", "alias_value": "0123"}]}
        session = _FakeSession(merge_row=_merge_row(snapshot))
        result = _svc(session).split_entity(TENANT, MERGE_ID, performed_by="op-2")
        UUID(result["split_id"])
        assert result["original_merge_id"] == MERGE_ID
        assert result["source_entity_ids"] == [SRC_A]
        assert result["target_entity_id"] == TGT
        assert result["performed_by"] == "op-2"
        datetime.fromisoformat(result["performed_at"])

        marked = [c for c in session.calls if c[0] == "mark_reversed"]
        assert len(marked) == 1
        assert marked[0][1]["merge_id"] == MERGE_ID
        # SQL binds :performed_by into the reversed_by column.
        assert marked[0][1]["performed_by"] == "op-2"

        split_record = next(c for c in session.calls if c[0] == "history_insert")
        assert split_record[1]["reason"] == f"Reversal of merge {MERGE_ID}"

        reactivations = [c for c in session.calls if c[0] == "entity_reactivate"]
        assert [c[1]["entity_id"] for c in reactivations] == [SRC_A]

    def test_split_skips_malformed_snapshot_entries(self):
        """Edge case: snapshot entries missing alias_type or alias_value
        are skipped, while well-formed entries still move back."""
        snapshot = {
            SRC_A: [
                {"alias_type": "gln", "alias_value": "0123"},
                {"alias_type": "", "alias_value": "no-type"},
                {"alias_type": "gtin"},
                {"alias_value": "no-key-at-all-but-value"},
                {},
            ]
        }
        session = _FakeSession(merge_row=_merge_row(snapshot))
        _svc(session).split_entity(TENANT, MERGE_ID, performed_by="op-2")
        moves = [c for c in session.calls if c[0] == "alias_update"]
        assert len(moves) == 1
        assert moves[0][1]["alias_type"] == "gln"
        assert moves[0][1]["alias_value"] == "0123"

    def test_unknown_merge_id_raises_without_mutations(self):
        session = _FakeSession(merge_row=None)
        with pytest.raises(ValueError, match="not found"):
            _svc(session).split_entity(TENANT, "does-not-exist")
        assert _kinds(session) == ["history_fetch"]

    def test_cross_tenant_write_blocked(self):
        session = _FakeSession()
        svc = _svc(session, principal_tenant_id="other-tenant")
        with pytest.raises(PermissionError):
            svc.merge_entities(TENANT, SRC_A, TGT)
        assert session.calls == []


# ===========================================================================
# Known limitation: bulk snapshot covers only one source
# ===========================================================================


class TestBulkSnapshotLimitation:
    @pytest.mark.xfail(
        strict=True,
        reason="bulk merge snapshots only the last source entity, "
        "so a multi-source split cannot restore every source's aliases",
    )
    def test_bulk_snapshot_covers_every_source(self):
        session = _FakeSession(
            source_aliases={
                SRC_A: [("gln", "aaaa")],
                SRC_B: [("gln", "bbbb")],
            }
        )
        _svc(session).merge_entities_bulk(TENANT, [SRC_A, SRC_B], TGT)
        insert = next(c for c in session.calls if c[0] == "history_insert")
        snapshot = json.loads(insert[1]["alias_snapshot"])
        assert set(snapshot.keys()) == {SRC_A, SRC_B}
