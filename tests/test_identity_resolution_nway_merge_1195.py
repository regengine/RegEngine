"""Regression tests for issue #1195 — N-way merge in identity_resolution.

Before this fix, ``merge_entities`` only accepted a single
``source_entity_id``. A 3-way merge (the "three duplicate 'Organic Apples'
SKUs — collapse all into the canonical one" case) therefore produced
THREE rows in ``fsma.entity_merge_history`` — two of which referenced
entities that were already inactive by the time they ran. That left
:meth:`split_entity` unable to cleanly reverse the merge, even though
the underlying schema (V047) stored ``source_entity_ids`` as ``UUID[]``
specifically to support the N-way case.

The fix adds :meth:`merge_entities_bulk` which writes **exactly one**
``entity_merge_history`` row with all source IDs as a UUID array, and
turns :meth:`merge_entities` into a thin 1:1 wrapper. :meth:`split_entity`
already iterates ``source_entity_ids`` correctly, so the N-way reversal
works for free.

These tests lock in the new contract:
- Exactly one history INSERT per N-way merge.
- Validation: non-empty, no duplicates, target not in source list.
- SQL uses ``ANY(:source_entity_ids)`` so one DB round trip updates all
  sources atomically (not N round trips).
- The 1:1 API still works unchanged (backward compat).
- ``split_entity`` reverses an N-way merge by re-activating every source.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.shared.identity_resolution import IdentityResolutionService


TENANT = "tenant-001"


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def svc(mock_session):
    # No principal_tenant_id — matches background-job / ingestion path
    # from the original test suite.
    return IdentityResolutionService(mock_session)


def _require_entity_all_exist(mock_session):
    """Configure the session so every ``_require_entity`` lookup and
    every other ``fetchone`` returns a truthy row. Keeps tests focused
    on the merge call pattern itself."""
    mock_session.execute.return_value.fetchone.return_value = (1,)


# ── Validation: rejects bad inputs before any DB side effects ──────────────


class TestMergeBulkValidation_Issue1195:
    def test_empty_source_list_raises(self, svc, mock_session):
        with pytest.raises(ValueError, match="must not be empty"):
            svc.merge_entities_bulk(TENANT, [], "eid-target")
        # Should reject before any side effects
        assert mock_session.execute.call_count == 0

    def test_duplicate_sources_raises(self, svc, mock_session):
        with pytest.raises(ValueError, match="duplicates"):
            svc.merge_entities_bulk(
                TENANT, ["eid-1", "eid-2", "eid-1"], "eid-target",
            )
        assert mock_session.execute.call_count == 0

    def test_target_in_sources_raises(self, svc, mock_session):
        with pytest.raises(ValueError, match="Cannot merge an entity with itself"):
            svc.merge_entities_bulk(
                TENANT, ["eid-1", "eid-target", "eid-2"], "eid-target",
            )
        assert mock_session.execute.call_count == 0

    def test_nonexistent_source_raises(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = None
        with pytest.raises(ValueError, match="not found"):
            svc.merge_entities_bulk(
                TENANT, ["eid-missing"], "eid-target",
            )


# ── Core contract: exactly ONE history row per N-way merge ─────────────────


class TestMergeBulkSingleHistoryRow_Issue1195:
    """The defect: pre-fix, a 3-way merge wrote 3 history rows. Now it
    must write exactly one, with all source_entity_ids in a UUID[]."""

    def test_three_way_merge_inserts_one_history_row(self, svc, mock_session):
        _require_entity_all_exist(mock_session)

        svc.merge_entities_bulk(
            TENANT,
            ["eid-a", "eid-b", "eid-c"],
            "eid-target",
            reason="Duplicate SKUs",
            performed_by="admin",
        )

        # Count INSERTs against entity_merge_history by inspecting the
        # SQL text of each execute() call.
        history_inserts = [
            call_args
            for call_args in mock_session.execute.call_args_list
            if "INSERT INTO fsma.entity_merge_history" in str(call_args[0][0])
        ]
        assert len(history_inserts) == 1, (
            f"Expected exactly 1 merge_history INSERT for a 3-way merge, "
            f"got {len(history_inserts)}. The pre-fix bug was N rows."
        )

    def test_history_row_carries_all_source_ids(self, svc, mock_session):
        """The single history row must carry the full source list — that's
        what :meth:`split_entity` reads back to reverse the merge."""
        _require_entity_all_exist(mock_session)

        svc.merge_entities_bulk(
            TENANT,
            ["eid-a", "eid-b", "eid-c"],
            "eid-target",
        )

        history_call = next(
            call_args
            for call_args in mock_session.execute.call_args_list
            if "INSERT INTO fsma.entity_merge_history" in str(call_args[0][0])
        )
        params = history_call[0][1]
        assert params["source_entity_ids"] == ["eid-a", "eid-b", "eid-c"]
        assert params["target_entity_id"] == "eid-target"

    def test_history_row_uses_uuid_array_cast(self, svc, mock_session):
        """The SQL must CAST the Python list to ``uuid[]`` so the
        ``source_entity_ids UUID[]`` column stores it as an array, not a
        scalar. Locking in the cast prevents a regression where the list
        gets stringified and defeats ``split_entity``."""
        _require_entity_all_exist(mock_session)

        svc.merge_entities_bulk(
            TENANT, ["eid-a", "eid-b"], "eid-target",
        )

        history_call = next(
            call_args
            for call_args in mock_session.execute.call_args_list
            if "INSERT INTO fsma.entity_merge_history" in str(call_args[0][0])
        )
        sql = str(history_call[0][0])
        assert "CAST(:source_entity_ids AS uuid[])" in sql

    def test_returned_audit_record_contains_all_sources(self, svc, mock_session):
        _require_entity_all_exist(mock_session)
        result = svc.merge_entities_bulk(
            TENANT,
            ["eid-a", "eid-b", "eid-c"],
            "eid-target",
            reason="Dedup",
            performed_by="admin",
        )
        assert result["action"] == "merge"
        assert result["source_entity_ids"] == ["eid-a", "eid-b", "eid-c"]
        assert result["target_entity_id"] == "eid-target"
        assert result["reason"] == "Dedup"
        assert result["performed_by"] == "admin"
        assert "merge_id" in result
        assert "performed_at" in result


# ── SQL uses ANY(:source_entity_ids) — one round trip, not N ───────────────


class TestMergeBulkSqlUsesAny_Issue1195:
    """A correct N-way implementation must not degrade to N separate
    UPDATEs (one per source) — that defeats atomicity. Lock in that the
    three mass-mutation statements use ``ANY(:source_entity_ids)``."""

    def test_alias_repoint_uses_any_array(self, svc, mock_session):
        _require_entity_all_exist(mock_session)
        svc.merge_entities_bulk(TENANT, ["eid-a", "eid-b"], "eid-target")

        alias_updates = [
            c for c in mock_session.execute.call_args_list
            if "UPDATE fsma.entity_aliases" in str(c[0][0])
            and "SET entity_id = :target_entity_id" in str(c[0][0])
        ]
        assert len(alias_updates) == 1
        assert "ANY(:source_entity_ids)" in str(alias_updates[0][0][0])

    def test_alias_cleanup_uses_any_array(self, svc, mock_session):
        _require_entity_all_exist(mock_session)
        svc.merge_entities_bulk(TENANT, ["eid-a", "eid-b"], "eid-target")

        alias_deletes = [
            c for c in mock_session.execute.call_args_list
            if "DELETE FROM fsma.entity_aliases" in str(c[0][0])
        ]
        assert len(alias_deletes) == 1
        assert "ANY(:source_entity_ids)" in str(alias_deletes[0][0][0])

    def test_deactivate_uses_any_array(self, svc, mock_session):
        _require_entity_all_exist(mock_session)
        svc.merge_entities_bulk(TENANT, ["eid-a", "eid-b"], "eid-target")

        deactivations = [
            c for c in mock_session.execute.call_args_list
            if "UPDATE fsma.canonical_entities" in str(c[0][0])
            and "is_active = FALSE" in str(c[0][0])
        ]
        assert len(deactivations) == 1
        assert "ANY(:source_entity_ids)" in str(deactivations[0][0][0])

    def test_review_queue_resolve_uses_any_array(self, svc, mock_session):
        _require_entity_all_exist(mock_session)
        svc.merge_entities_bulk(TENANT, ["eid-a", "eid-b"], "eid-target")

        review_updates = [
            c for c in mock_session.execute.call_args_list
            if "UPDATE fsma.identity_review_queue" in str(c[0][0])
        ]
        assert len(review_updates) == 1
        sql = str(review_updates[0][0][0])
        # Must match either-side on any source.
        assert "entity_a_id = ANY(:source_entity_ids)" in sql
        assert "entity_b_id = ANY(:source_entity_ids)" in sql


# ── _require_entity gates on every participant ──────────────────────────────


class TestMergeBulkValidatesAllParticipants_Issue1195:
    def test_requires_every_source_and_target(self, svc, mock_session):
        """_require_entity must be called for all N sources + the target
        BEFORE any mutation runs."""
        _require_entity_all_exist(mock_session)

        svc.merge_entities_bulk(
            TENANT, ["eid-a", "eid-b", "eid-c"], "eid-target",
        )

        # _require_entity is a SELECT with WHERE tenant_id AND entity_id.
        require_checks = [
            c for c in mock_session.execute.call_args_list
            if "SELECT 1 FROM fsma.canonical_entities" in str(c[0][0])
        ]
        # 3 sources + 1 target = 4 validation calls.
        assert len(require_checks) == 4


# ── Backward compat: 1:1 merge_entities still works ────────────────────────


class TestMergeEntitiesThinWrapper_Issue1195:
    """The public 1:1 API is preserved as a thin wrapper. Existing
    callers must not need refactoring."""

    def test_1to1_merge_still_works(self, svc, mock_session):
        _require_entity_all_exist(mock_session)
        result = svc.merge_entities(
            TENANT, "eid-source", "eid-target",
            reason="legacy", performed_by="admin",
        )
        assert result["action"] == "merge"
        assert result["source_entity_ids"] == ["eid-source"]
        assert result["target_entity_id"] == "eid-target"
        assert result["reason"] == "legacy"

    def test_1to1_self_merge_still_raises(self, svc, mock_session):
        with pytest.raises(ValueError, match="Cannot merge an entity with itself"):
            svc.merge_entities(TENANT, "eid-x", "eid-x")

    def test_1to1_writes_exactly_one_history_row(self, svc, mock_session):
        """Even for 1:1, the wrapper must write one history row — not
        regress the multi-row pattern."""
        _require_entity_all_exist(mock_session)
        svc.merge_entities(TENANT, "eid-source", "eid-target")

        history_inserts = [
            c for c in mock_session.execute.call_args_list
            if "INSERT INTO fsma.entity_merge_history" in str(c[0][0])
        ]
        assert len(history_inserts) == 1

    def test_1to1_history_params_are_single_element_list(self, svc, mock_session):
        """The thin wrapper must pass a list, not a bare string — the
        column is UUID[] and a scalar would fail the cast at runtime."""
        _require_entity_all_exist(mock_session)
        svc.merge_entities(TENANT, "eid-source", "eid-target")

        history_call = next(
            c for c in mock_session.execute.call_args_list
            if "INSERT INTO fsma.entity_merge_history" in str(c[0][0])
        )
        params = history_call[0][1]
        assert params["source_entity_ids"] == ["eid-source"]


# ── split_entity reverses an N-way merge ────────────────────────────────────


class TestSplitReversesNwayMerge_Issue1195:
    """The downstream consequence of the fix: a single N-way merge
    history row lets split_entity re-activate every source in one call."""

    def test_split_reactivates_every_source_from_nway_merge(self, svc, mock_session):
        # First execute(): fetch merge record with 3-source UUID array.
        fetch_merge = MagicMock()
        fetch_merge.fetchone.return_value = (
            "m1",
            ["eid-a", "eid-b", "eid-c"],  # UUID[]
            "eid-target",
            "merge",
            False,  # is_reversed
        )

        # Canonical-name lookups for the restore-alias path inside the
        # split loop — return a name for each source.
        name_mock = MagicMock()
        name_mock.fetchone.return_value = ("Source Name",)

        # Default for other calls (UPDATEs, etc.)
        default_mock = MagicMock()

        call_idx = [0]

        def execute_side_effect(*args, **kwargs):
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                return fetch_merge
            sql = str(args[0])
            if "SELECT canonical_name" in sql:
                return name_mock
            return default_mock

        mock_session.execute.side_effect = execute_side_effect

        result = svc.split_entity(TENANT, "m1", performed_by="admin")

        # Must re-activate each of the 3 sources.
        reactivations = [
            c for c in mock_session.execute.call_args_list
            if "UPDATE fsma.canonical_entities" in str(c[0][0])
            and "is_active = TRUE" in str(c[0][0])
        ]
        assert len(reactivations) == 3, (
            f"Expected 3 source re-activations for a 3-way split, "
            f"got {len(reactivations)}"
        )

        # Each re-activation targets one of the original sources.
        reactivated_ids = {
            c[0][1]["entity_id"] for c in reactivations
        }
        assert reactivated_ids == {"eid-a", "eid-b", "eid-c"}

        assert "split_id" in result
        assert result["original_merge_id"] == "m1"
        assert set(result["source_entity_ids"]) == {"eid-a", "eid-b", "eid-c"}
        assert result["target_entity_id"] == "eid-target"
