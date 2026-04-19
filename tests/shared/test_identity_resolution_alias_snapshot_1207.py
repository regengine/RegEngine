"""Regression tests for #1207 — lossless merge/split via alias snapshot.

Before: ``split_entity`` restored ONLY the canonical-name alias by
exact-string match. All GLN/GTIN/FDA identifier aliases that
originally belonged to the source entity silently stayed with the
target. For FSMA 204 audit reversal that was a false-rollback — the
merge history said "reversed" but the source entity came back as a
crippled shell missing its identifiers.

After:
- ``merge_entities`` captures the source entity's full alias set
  into ``entity_merge_history.alias_snapshot`` (JSONB) BEFORE
  re-pointing aliases.
- ``split_entity`` replays the snapshot — every alias that was on
  the source at merge time goes back to the source on split.
- Pre-migration merges (``alias_snapshot IS NULL``) are refused by
  ``split_entity`` to prevent the old silent-loss behavior.

Schema support: ``alembic/versions/20260418_v069_entity_merge_alias_snapshot_1207.py``
adds the ``alias_snapshot JSONB`` column (nullable).

These tests are session-mocked — no real DB.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService


TENANT = "tenant-1207"
SRC = "11111111-1111-1111-1111-111111111111"
TGT = "22222222-2222-2222-2222-222222222222"
MERGE_ID = "mmmmmmmm-mmmm-mmmm-mmmm-mmmmmmmmmmmm"


# ---------------------------------------------------------------------------
# Scripted sessions
# ---------------------------------------------------------------------------


class _MergeSession:
    """Fake session for ``merge_entities`` tests.

    Answers:
      - _require_entity lookups (entity existence) — succeed
      - pre-merge alias snapshot SELECT — returns seeded aliases
      - all UPDATE/INSERT/DELETE — no-op
    """

    def __init__(self, source_aliases: List[Tuple[str, str]]):
        self._source_aliases = source_aliases
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        params = params or {}

        # _require_entity — returns (1,) to signal existence.
        if "SELECT 1 FROM fsma.canonical_entities" in sql:
            self.calls.append(("require_entity", dict(params)))
            result.fetchone.return_value = (1,)
            return result

        # Pre-merge source-alias SELECT for snapshot.
        if (
            "FROM fsma.entity_aliases" in sql
            and "alias_type, alias_value" in sql
            and "entity_id = :source_entity_id" in sql
        ):
            self.calls.append(("snapshot_select", dict(params)))
            result.fetchall.return_value = list(self._source_aliases)
            return result

        # Everything else — record kind and return a no-op.
        if "UPDATE" in sql and "fsma.entity_aliases" in sql:
            self.calls.append(("alias_update", dict(params)))
        elif "DELETE FROM fsma.entity_aliases" in sql:
            self.calls.append(("alias_delete", dict(params)))
        elif "UPDATE fsma.canonical_entities" in sql:
            self.calls.append(("entity_update", dict(params)))
        elif "INSERT INTO fsma.entity_merge_history" in sql:
            self.calls.append(("history_insert", dict(params)))
        elif "UPDATE fsma.identity_review_queue" in sql:
            self.calls.append(("review_close", dict(params)))
        else:
            self.calls.append(("other", dict(params)))
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result


class _SplitSession:
    """Fake session for ``split_entity`` tests.

    Answers:
      - the merge-history fetch with a configurable row (including
        ``alias_snapshot`` — pass None to simulate pre-v069 merges).
      - all other queries — no-op.
    """

    def __init__(self, merge_row: Optional[Tuple[Any, ...]]):
        self.merge_row = merge_row
        self.calls: List[Tuple[str, Dict[str, Any]]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        result = MagicMock()
        params = params or {}

        if "FROM fsma.entity_merge_history" in sql and "merge_id = :merge_id" in sql:
            self.calls.append(("history_fetch", dict(params)))
            result.fetchone.return_value = self.merge_row
            return result
        if "FROM fsma.canonical_entities" in sql and "canonical_name" in sql:
            # source entity canonical-name lookup (unused after #1207, but
            # still referenced by tests that hit the old path — return a
            # dummy row just in case).
            self.calls.append(("canonical_name", dict(params)))
            result.fetchone.return_value = ("SomeName",)
            return result

        if "UPDATE fsma.canonical_entities" in sql:
            self.calls.append(("entity_reactivate", dict(params)))
        elif "UPDATE fsma.entity_aliases" in sql:
            self.calls.append(("alias_move_back", dict(params)))
        elif "INSERT INTO fsma.entity_merge_history" in sql:
            self.calls.append(("split_record", dict(params)))
        elif "UPDATE fsma.entity_merge_history" in sql:
            self.calls.append(("mark_reversed", dict(params)))
        else:
            self.calls.append(("other", dict(params)))
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result


def _svc(session):
    return IdentityResolutionService(session)


# ===========================================================================
# merge_entities captures a full alias snapshot
# ===========================================================================


class TestMergeCapturesSnapshot_Issue1207:
    def test_snapshot_contains_all_source_aliases(self):
        """merge_entities must SELECT the source's full alias set before
        re-pointing and persist it into entity_merge_history.alias_snapshot."""
        aliases = [
            ("name", "ABC Foods"),
            ("gln", "0123456789012"),
            ("gtin", "9876543210987"),
            ("fda_reg", "FR-999"),
        ]
        session = _MergeSession(source_aliases=aliases)
        _svc(session).merge_entities(
            tenant_id=TENANT,
            source_entity_id=SRC,
            target_entity_id=TGT,
            reason="dedupe",
            performed_by="op-1",
        )
        # The snapshot SELECT must have fired before the history INSERT.
        kinds = [c[0] for c in session.calls]
        snap_idx = kinds.index("snapshot_select")
        ins_idx = kinds.index("history_insert")
        assert snap_idx < ins_idx, (
            f"snapshot_select must precede history_insert; got {kinds}"
        )
        # The INSERT params must carry the full alias list as JSON.
        insert_params = dict(
            c for c in session.calls if c[0] == "history_insert"
        )
        raw = insert_params["history_insert"]["alias_snapshot"]
        snapshot = json.loads(raw)
        assert SRC in snapshot
        stored_pairs = {
            (a["alias_type"], a["alias_value"]) for a in snapshot[SRC]
        }
        assert stored_pairs == set(aliases), (
            f"snapshot must preserve all 4 aliases, got {stored_pairs}"
        )

    def test_empty_source_aliases_snapshot_is_empty_list(self):
        """If the source has zero aliases, the snapshot still records an
        empty list — distinguishable from NULL (= pre-v069)."""
        session = _MergeSession(source_aliases=[])
        _svc(session).merge_entities(
            tenant_id=TENANT,
            source_entity_id=SRC,
            target_entity_id=TGT,
            reason="dedupe",
            performed_by="op-1",
        )
        insert_call = next(c for c in session.calls if c[0] == "history_insert")
        raw = insert_call[1]["alias_snapshot"]
        snapshot = json.loads(raw)
        assert snapshot == {SRC: []}


# ===========================================================================
# split_entity replays the snapshot
# ===========================================================================


class TestSplitReplaysSnapshot_Issue1207:
    def test_all_snapshot_aliases_are_moved_back(self):
        """split_entity must issue one UPDATE per aliased (type,value)
        in the snapshot, moving it from target back to source."""
        snapshot = {
            SRC: [
                {"alias_type": "name", "alias_value": "ABC Foods"},
                {"alias_type": "gln", "alias_value": "0123456789012"},
                {"alias_type": "gtin", "alias_value": "9876543210987"},
            ]
        }
        # merge_row columns: (merge_id, source_entity_ids[], target_id,
        #                     action, is_reversed, alias_snapshot)
        merge_row = (MERGE_ID, [SRC], TGT, "merge", False, snapshot)
        session = _SplitSession(merge_row=merge_row)

        _svc(session).split_entity(
            tenant_id=TENANT, merge_id=MERGE_ID, performed_by="op-2"
        )

        # 3 alias_move_back calls (one per snapshot entry).
        moves = [c for c in session.calls if c[0] == "alias_move_back"]
        assert len(moves) == 3, (
            f"expected 3 alias moves (name + gln + gtin), got {len(moves)}"
        )
        moved_pairs = {
            (m[1]["alias_type"], m[1]["alias_value"]) for m in moves
        }
        assert moved_pairs == {
            ("name", "ABC Foods"),
            ("gln", "0123456789012"),
            ("gtin", "9876543210987"),
        }
        # Every move must be (target -> source), not the other way.
        for _, params in moves:
            assert params["source_entity_id"] == SRC
            assert params["target_entity_id"] == TGT

    def test_snapshot_as_json_string_is_parsed(self):
        """Some drivers return JSONB as a string. split_entity must
        handle both dict and string shapes."""
        snapshot_obj = {SRC: [{"alias_type": "gln", "alias_value": "XYZ"}]}
        merge_row = (MERGE_ID, [SRC], TGT, "merge", False, json.dumps(snapshot_obj))
        session = _SplitSession(merge_row=merge_row)

        _svc(session).split_entity(
            tenant_id=TENANT, merge_id=MERGE_ID, performed_by="op-2"
        )

        moves = [c for c in session.calls if c[0] == "alias_move_back"]
        assert len(moves) == 1
        assert moves[0][1]["alias_type"] == "gln"
        assert moves[0][1]["alias_value"] == "XYZ"

    def test_empty_snapshot_entry_makes_no_alias_moves(self):
        """A snapshot with an empty list for the source = entity had no
        aliases at merge time. No UPDATEs should be issued."""
        merge_row = (MERGE_ID, [SRC], TGT, "merge", False, {SRC: []})
        session = _SplitSession(merge_row=merge_row)

        _svc(session).split_entity(
            tenant_id=TENANT, merge_id=MERGE_ID, performed_by="op-2"
        )

        moves = [c for c in session.calls if c[0] == "alias_move_back"]
        assert moves == []


# ===========================================================================
# split_entity REFUSES to reverse pre-v069 merges
# ===========================================================================


class TestSplitRefusesPreV069Merge_Issue1207:
    def test_null_snapshot_raises(self):
        """A merge without an alias_snapshot (pre-v069) cannot be
        safely reversed — split_entity must raise rather than silently
        lose aliases. This is the whole point of #1207."""
        merge_row = (MERGE_ID, [SRC], TGT, "merge", False, None)
        session = _SplitSession(merge_row=merge_row)

        with pytest.raises(ValueError, match="no alias_snapshot"):
            _svc(session).split_entity(
                tenant_id=TENANT, merge_id=MERGE_ID, performed_by="op-2"
            )

    def test_null_snapshot_issues_no_mutations(self):
        """When the pre-v069 guard fires, NO alias moves or
        reactivations should occur — the merge stays unreversed."""
        merge_row = (MERGE_ID, [SRC], TGT, "merge", False, None)
        session = _SplitSession(merge_row=merge_row)

        with pytest.raises(ValueError):
            _svc(session).split_entity(
                tenant_id=TENANT, merge_id=MERGE_ID, performed_by="op-2"
            )

        kinds = [c[0] for c in session.calls]
        # Only the history_fetch should have run.
        assert kinds == ["history_fetch"], (
            f"guard fired after side effects: {kinds}"
        )


# ===========================================================================
# Existing error contracts preserved
# ===========================================================================


class TestSplitExistingGuards_Issue1207:
    def test_unknown_merge_id_raises(self):
        session = _SplitSession(merge_row=None)
        with pytest.raises(ValueError, match="not found"):
            _svc(session).split_entity(
                tenant_id=TENANT, merge_id="does-not-exist"
            )

    def test_non_merge_action_raises(self):
        # action = 'split' instead of 'merge'
        merge_row = (MERGE_ID, [SRC], TGT, "split", False, {SRC: []})
        session = _SplitSession(merge_row=merge_row)
        with pytest.raises(ValueError, match="not a merge action"):
            _svc(session).split_entity(
                tenant_id=TENANT, merge_id=MERGE_ID
            )

    def test_already_reversed_raises(self):
        merge_row = (MERGE_ID, [SRC], TGT, "merge", True, {SRC: []})
        session = _SplitSession(merge_row=merge_row)
        with pytest.raises(ValueError, match="already been reversed"):
            _svc(session).split_entity(
                tenant_id=TENANT, merge_id=MERGE_ID
            )


# ===========================================================================
# Merge doesn't self-merge + existing guards preserved
# ===========================================================================


class TestMergeExistingGuards_Issue1207:
    def test_self_merge_still_raises(self):
        session = _MergeSession(source_aliases=[])
        with pytest.raises(ValueError, match="itself"):
            _svc(session).merge_entities(
                tenant_id=TENANT,
                source_entity_id=SRC,
                target_entity_id=SRC,
                performed_by="op",
            )
