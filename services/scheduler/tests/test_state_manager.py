"""Tests for StateManager deduplication logic.

Covers:
- Hash computation determinism
- New item detection
- Changed content detection
- Unchanged item recognition
- mark_seen creates/updates records
- cleanup_old_items
- get_seen_ids / get_stats
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Bootstrap imports
os.environ.setdefault("DATABASE_URL", "sqlite:///test_state.db")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")

_SERVICES_DIR = Path(__file__).resolve().parent.parent.parent
if str(_SERVICES_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVICES_DIR))

from shared.paths import ensure_shared_importable
ensure_shared_importable()

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.state import StateManager, SeenItem, Base


@pytest.fixture
def state_manager(tmp_path):
    """Create a StateManager backed by an in-memory SQLite database."""
    db_path = tmp_path / "test_state.db"
    db_url = f"sqlite:///{db_path}"
    mgr = StateManager(database_url=db_url)
    mgr.initialize()
    return mgr


# ─── Hash computation ────────────────────────────────────────────────────


class TestComputeHash:
    def test_deterministic(self):
        h1 = StateManager.compute_hash("test content")
        h2 = StateManager.compute_hash("test content")
        assert h1 == h2

    def test_different_content_different_hash(self):
        h1 = StateManager.compute_hash("content A")
        h2 = StateManager.compute_hash("content B")
        assert h1 != h2

    def test_returns_64_char_hex(self):
        h = StateManager.compute_hash("anything")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_string_hashes(self):
        h = StateManager.compute_hash("")
        assert len(h) == 64


# ─── is_new ──────────────────────────────────────────────────────────────


class TestIsNew:
    def test_never_seen_item_is_new(self, state_manager):
        assert state_manager.is_new("src-001", "some content") is True

    def test_seen_item_with_same_content_is_not_new(self, state_manager):
        state_manager.mark_seen("src-001", "fda_recall", "some content")
        assert state_manager.is_new("src-001", "some content") is False

    def test_seen_item_with_changed_content_is_not_new(self, state_manager):
        """#1158 — identity is by source_id only.

        FDA regularly edits recall metadata (classification upgrades,
        firm-name corrections, product-description edits). Those
        edits must NOT re-emit the same recall as a new event.
        """
        state_manager.mark_seen("src-001", "fda_recall", "original content")
        assert state_manager.is_new("src-001", "updated content") is False

    def test_different_source_ids_are_independent(self, state_manager):
        state_manager.mark_seen("src-001", "fda_recall", "content")
        assert state_manager.is_new("src-002", "content") is True


# ─── mark_seen ───────────────────────────────────────────────────────────


class TestMarkSeen:
    def test_creates_new_record(self, state_manager):
        state_manager.mark_seen(
            "src-001", "fda_recall", "content", title="Test", url="https://example.com"
        )
        ids = state_manager.get_seen_ids("fda_recall")
        assert "src-001" in ids

    def test_updates_existing_record_hash(self, state_manager):
        state_manager.mark_seen("src-001", "fda_recall", "old content")
        state_manager.mark_seen("src-001", "fda_recall", "new content")
        # After update, new content should not be considered new
        assert state_manager.is_new("src-001", "new content") is False

    def test_updates_title_and_url(self, state_manager):
        state_manager.mark_seen("src-001", "fda_recall", "c", title="V1")
        state_manager.mark_seen("src-001", "fda_recall", "c", title="V2", url="https://v2.com")
        # Verify via direct DB query
        session = state_manager._get_session()
        try:
            item = session.query(SeenItem).filter_by(source_id="src-001").first()
            assert item.title == "V2"
            assert item.url == "https://v2.com"
        finally:
            session.close()


# ─── get_seen_ids ────────────────────────────────────────────────────────


class TestGetSeenIds:
    def test_returns_empty_set_for_no_items(self, state_manager):
        ids = state_manager.get_seen_ids("fda_recall")
        assert ids == set()

    def test_returns_correct_ids_by_type(self, state_manager):
        state_manager.mark_seen("recall-1", "fda_recall", "c1")
        state_manager.mark_seen("recall-2", "fda_recall", "c2")
        state_manager.mark_seen("alert-1", "fda_import_alert", "c3")

        recall_ids = state_manager.get_seen_ids("fda_recall")
        assert recall_ids == {"recall-1", "recall-2"}

        alert_ids = state_manager.get_seen_ids("fda_import_alert")
        assert alert_ids == {"alert-1"}


# ─── get_stats ───────────────────────────────────────────────────────────


class TestGetStats:
    def test_empty_stats(self, state_manager):
        stats = state_manager.get_stats()
        assert stats["total_items"] == 0
        assert stats["by_source_type"] == {}

    def test_counts_by_source_type(self, state_manager):
        state_manager.mark_seen("r1", "fda_recall", "c1")
        state_manager.mark_seen("r2", "fda_recall", "c2")
        state_manager.mark_seen("a1", "fda_import_alert", "c3")

        stats = state_manager.get_stats()
        assert stats["total_items"] == 3
        assert stats["by_source_type"]["fda_recall"] == 2
        assert stats["by_source_type"]["fda_import_alert"] == 1


# ─── cleanup_old_items ───────────────────────────────────────────────────


class TestCleanup:
    def test_removes_old_items(self, state_manager):
        state_manager.mark_seen("old-1", "fda_recall", "c1")

        # Manually backdate the last_seen_at
        session = state_manager._get_session()
        try:
            item = session.query(SeenItem).filter_by(source_id="old-1").first()
            item.last_seen_at = datetime.now(timezone.utc) - timedelta(days=100)
            session.commit()
        finally:
            session.close()

        removed = state_manager.cleanup_old_items(days=90)
        assert removed == 1
        assert state_manager.is_new("old-1", "c1") is True

    def test_keeps_recent_items(self, state_manager):
        state_manager.mark_seen("recent-1", "fda_recall", "c1")
        removed = state_manager.cleanup_old_items(days=90)
        assert removed == 0
        assert state_manager.is_new("recent-1", "c1") is False
