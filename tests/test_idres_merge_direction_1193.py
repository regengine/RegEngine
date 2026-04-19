"""Regression tests for #1193 — identity_resolution.resolve_review
must pick the merge direction deliberately, not silently pick whichever
UUID sorts lexicographically lower.

Bug shape: ``queue_for_review`` normalizes the pair via
``sorted([entity_a_id, entity_b_id])`` for idempotency (so (A,B) and
(B,A) collapse to one row). When a reviewer then marks the item
``confirmed_match``, the service called
``merge_entities(source=entity_a, target=entity_b)`` — meaning the
entity with the lex-lower UUID was always the one deactivated,
regardless of which entity was authoritative, verified, or higher-
confidence.

After the fix:
- The reviewer can opt in with ``target_entity_id=<uuid>`` to set the
  merge direction explicitly.
- Otherwise, the service picks deterministically on
  ``verification_status`` → ``confidence_score`` → ``created_at``
  (earliest wins), with a lex tiebreaker so the choice is
  reproducible.

These are pure-unit tests against a mocked SQLAlchemy session; no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService


TENANT = "tenant-001"


@pytest.fixture
def mock_session():
    return MagicMock()


@pytest.fixture
def svc(mock_session):
    return IdentityResolutionService(mock_session)


# ---------------------------------------------------------------------------
# Helpers — scripted execute() responses for resolve_review's call sequence
# ---------------------------------------------------------------------------


def _make_review_row(entity_a_id: str, entity_b_id: str):
    """Response for the initial SELECT that fetches the review item."""
    m = MagicMock()
    m.fetchone.return_value = ("r1", entity_a_id, entity_b_id, "pending")
    return m


def _make_entities_row(a_id, a_status, a_conf, a_created,
                       b_id, b_status, b_conf, b_created):
    """Response for the _pick_merge_target SELECT returning both rows."""
    m = MagicMock()
    m.fetchall.return_value = [
        (a_id, a_status, a_conf, a_created),
        (b_id, b_status, b_conf, b_created),
    ]
    return m


def _require_entity_row(entity_id):
    """Any non-None response; _require_entity just needs a row."""
    m = MagicMock()
    m.fetchone.return_value = (entity_id, TENANT, "facility", "Test", True)
    return m


# ---------------------------------------------------------------------------
# 1) Verification-status beats lex order
# ---------------------------------------------------------------------------


class TestMergeDirectionByVerification_Issue1193:
    def test_verified_beats_unverified_even_when_lex_higher(self, svc, mock_session):
        """eid-z is the lex-higher UUID but it's `verified` while eid-a is
        `unverified`. Target must be eid-z — the verified record must
        survive."""
        eid_a = "eid-a"  # lex-lower, unverified
        eid_z = "eid-z"  # lex-higher, verified
        now = datetime.now(timezone.utc)

        responses = iter([
            _make_review_row(eid_a, eid_z),   # initial fetch
            MagicMock(),                        # UPDATE review status
            _make_entities_row(
                eid_a, "unverified", 0.5, now,
                eid_z, "verified", 1.0, now,
            ),  # _pick_merge_target SELECT
            # merge_entities _verify_tenant_access (no-op here)
            _require_entity_row(eid_z),         # _require_entity(target)
            _require_entity_row(eid_a),         # _require_entity(source)
            MagicMock(),                        # UPDATE aliases
            MagicMock(),                        # UPDATE source deactivation
            MagicMock(),                        # UPDATE merge_history
            MagicMock(),                        # INSERT merge_history
            MagicMock(),                        # UPDATE any pending reviews
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(
            TENANT, "r1", "confirmed_match",
            resolved_by="alice",
        )

        assert "merge" in result
        rat = result["merge_target_rationale"]
        assert rat["tiebreaker"] == "verification_status"
        assert rat["target_entity_id"] == eid_z, (
            "verified entity must be the merge target, even though it "
            "sorts lex-higher than the unverified entity"
        )
        assert rat["source_entity_id"] == eid_a

    def test_pending_review_beats_unverified(self, svc, mock_session):
        eid_a, eid_b = "aaa", "bbb"
        now = datetime.now(timezone.utc)
        responses = iter([
            _make_review_row(eid_a, eid_b),
            MagicMock(),
            _make_entities_row(
                eid_a, "unverified", 1.0, now,
                eid_b, "pending_review", 1.0, now,
            ),
            _require_entity_row(eid_b),
            _require_entity_row(eid_a),
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(TENANT, "r1", "confirmed_match", resolved_by="alice")
        rat = result["merge_target_rationale"]
        assert rat["tiebreaker"] == "verification_status"
        assert rat["target_entity_id"] == eid_b


# ---------------------------------------------------------------------------
# 2) Confidence tiebreaker when verification equal
# ---------------------------------------------------------------------------


class TestMergeDirectionByConfidence_Issue1193:
    def test_higher_confidence_wins_when_verification_tied(self, svc, mock_session):
        eid_a, eid_b = "aaa", "bbb"
        now = datetime.now(timezone.utc)
        responses = iter([
            _make_review_row(eid_a, eid_b),
            MagicMock(),
            _make_entities_row(
                eid_a, "unverified", 0.60, now,
                eid_b, "unverified", 0.95, now,
            ),
            _require_entity_row(eid_b),
            _require_entity_row(eid_a),
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(TENANT, "r1", "confirmed_match", resolved_by="alice")
        rat = result["merge_target_rationale"]
        assert rat["tiebreaker"] == "confidence_score"
        assert rat["target_entity_id"] == eid_b


# ---------------------------------------------------------------------------
# 3) Created-at tiebreaker — earlier record wins
# ---------------------------------------------------------------------------


class TestMergeDirectionByCreatedAt_Issue1193:
    def test_earlier_created_at_wins(self, svc, mock_session):
        """When verification + confidence are identical, the older
        record survives — more history on it, more established as the
        canonical entity."""
        eid_a, eid_b = "aaa", "bbb"  # a is lex-lower
        older = datetime.now(timezone.utc) - timedelta(days=30)
        newer = datetime.now(timezone.utc)
        # eid_a is newer, eid_b is older — earlier-wins => eid_b
        responses = iter([
            _make_review_row(eid_a, eid_b),
            MagicMock(),
            _make_entities_row(
                eid_a, "unverified", 1.0, newer,
                eid_b, "unverified", 1.0, older,
            ),
            _require_entity_row(eid_b),
            _require_entity_row(eid_a),
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(TENANT, "r1", "confirmed_match", resolved_by="alice")
        rat = result["merge_target_rationale"]
        assert rat["tiebreaker"] == "created_at"
        assert rat["target_entity_id"] == eid_b, (
            "older entity must survive when newer record is a suspected "
            "duplicate"
        )


# ---------------------------------------------------------------------------
# 4) Explicit target_entity_id overrides deterministic pick
# ---------------------------------------------------------------------------


class TestExplicitTargetOverride_Issue1193:
    def test_explicit_target_wins_over_deterministic(self, svc, mock_session):
        """A reviewer that supplies target_entity_id=entity_a must get
        entity_a as target even if the deterministic pick would have
        chosen entity_b."""
        eid_a, eid_b = "aaa", "bbb"
        now = datetime.now(timezone.utc)
        responses = iter([
            _make_review_row(eid_a, eid_b),
            MagicMock(),
            # NO _pick_merge_target call — explicit override skips it.
            _require_entity_row(eid_a),  # merge_entities._require_entity(target)
            _require_entity_row(eid_b),  # merge_entities._require_entity(source)
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(
            TENANT, "r1", "confirmed_match",
            resolved_by="alice",
            target_entity_id=eid_a,
        )
        rat = result["merge_target_rationale"]
        assert rat["tiebreaker"] == "explicit_override"
        assert rat["target_entity_id"] == eid_a
        assert rat["source_entity_id"] == eid_b

    def test_explicit_target_must_be_in_review_pair(self, svc, mock_session):
        mock_session.execute.return_value.fetchone.return_value = (
            "r1", "eid-a", "eid-b", "pending",
        )
        with pytest.raises(ValueError, match="not part of review"):
            svc.resolve_review(
                TENANT, "r1", "confirmed_match",
                resolved_by="alice",
                target_entity_id="some-other-uuid",
            )


# ---------------------------------------------------------------------------
# 5) Original #1193 regression — lex-lower no longer always wins
# ---------------------------------------------------------------------------


class TestLexOrderNoLongerDecides_Issue1193:
    def test_verified_lex_higher_wins_over_unverified_lex_lower(
        self, svc, mock_session,
    ):
        """The EXACT shape of the bug: queue_for_review stored
        entity_a_id < entity_b_id. Without the fix, entity_a_id is
        always source (deactivated). With the fix, if entity_b is
        verified and entity_a is unverified, entity_b must be target."""
        eid_a = "00000000-0000-0000-0000-000000000001"
        eid_b = "ffffffff-ffff-ffff-ffff-ffffffffffff"
        assert eid_a < eid_b, "test premise: lex ordering"
        now = datetime.now(timezone.utc)

        responses = iter([
            _make_review_row(eid_a, eid_b),
            MagicMock(),
            _make_entities_row(
                eid_a, "unverified", 0.7, now,
                eid_b, "verified", 1.0, now,
            ),
            _require_entity_row(eid_b),
            _require_entity_row(eid_a),
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(TENANT, "r1", "confirmed_match", resolved_by="alice")
        # The fix: verified entity (lex-higher) survives.
        assert result["merge_target_rationale"]["target_entity_id"] == eid_b
        # And the lex-lower unverified entity is the deactivated one.
        assert result["merge_target_rationale"]["source_entity_id"] == eid_a


# ---------------------------------------------------------------------------
# 6) Fully-tied case falls back to lex for reproducibility
# ---------------------------------------------------------------------------


class TestFullyTiedFallsBackToLex_Issue1193:
    def test_identical_entities_fall_back_to_lex(self, svc, mock_session):
        """If two records are indistinguishable on verification,
        confidence, AND created_at, the tiebreaker is lex so the
        outcome is still deterministic — just reproducible, not
        arbitrary at runtime."""
        eid_a, eid_b = "aaa", "bbb"
        now = datetime.now(timezone.utc)
        responses = iter([
            _make_review_row(eid_a, eid_b),
            MagicMock(),
            _make_entities_row(
                eid_a, "unverified", 1.0, now,
                eid_b, "unverified", 1.0, now,
            ),
            _require_entity_row(eid_a),
            _require_entity_row(eid_b),
            MagicMock(), MagicMock(), MagicMock(),
            MagicMock(), MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(TENANT, "r1", "confirmed_match", resolved_by="alice")
        rat = result["merge_target_rationale"]
        assert rat["tiebreaker"] == "entity_id_lex"
        # Lex-lower wins on the pure-tiebreaker fallback.
        assert rat["target_entity_id"] == eid_a


# ---------------------------------------------------------------------------
# 7) confirmed_distinct / deferred do NOT call _pick_merge_target
# ---------------------------------------------------------------------------


class TestNonMergeResolutions_Issue1193:
    def test_confirmed_distinct_does_not_select_target(self, svc, mock_session):
        responses = iter([
            _make_review_row("eid-a", "eid-b"),
            MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(
            TENANT, "r1", "confirmed_distinct", resolved_by="alice",
        )
        assert "merge" not in result
        assert "merge_target_rationale" not in result
        # Should not have consumed any extra responses (no _pick + no merge).
        # If it had, StopIteration would fire on the next execute.

    def test_confirmed_match_with_auto_merge_false_does_not_select_target(
        self, svc, mock_session,
    ):
        responses = iter([
            _make_review_row("eid-a", "eid-b"),
            MagicMock(),
        ])
        mock_session.execute.side_effect = lambda *a, **kw: next(responses)

        result = svc.resolve_review(
            TENANT, "r1", "confirmed_match",
            resolved_by="alice",
            auto_merge=False,
        )
        assert "merge" not in result
        assert "merge_target_rationale" not in result
