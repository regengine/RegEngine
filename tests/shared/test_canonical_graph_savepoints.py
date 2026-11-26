"""Canonical graph notifications follow the outer transaction and its savepoints."""

from types import SimpleNamespace

import pytest
from shared.canonical_persistence import legacy_dual_write as graph_sync
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.fixture
def graph_transaction(monkeypatch):
    published = []
    monkeypatch.setenv("ENABLE_NEO4J_SYNC", "true")
    monkeypatch.setattr(graph_sync, "publish_graph_sync", lambda event: published.append(event.event_id))
    engine = create_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text("SELECT 1"))
        yield session, published
    engine.dispose()


def stage(session, name):
    graph_sync.stage_graph_sync(session, SimpleNamespace(event_id=name))


def test_nested_commits_wait_for_outer_commit(graph_transaction):
    session, published = graph_transaction
    batch = session.begin_nested()
    event = session.begin_nested()
    canonical = session.begin_nested()
    stage(session, "accepted")
    canonical.commit()
    event.commit()
    batch.commit()
    assert published == []
    session.commit()
    assert published == ["accepted"]
    session.commit()
    assert published == ["accepted"]


def test_rejected_batch_discards_committed_child_notifications(graph_transaction):
    session, published = graph_transaction
    batch = session.begin_nested()
    with session.begin_nested():
        with session.begin_nested():
            stage(session, "rolled-back-batch")
    assert published == []
    batch.rollback()
    session.commit()
    assert published == []


def test_sibling_rollback_preserves_accepted_notifications(graph_transaction):
    session, published = graph_transaction
    stage(session, "outer")
    with session.begin_nested():
        stage(session, "accepted-sibling")
    rejected = session.begin_nested()
    stage(session, "rejected-sibling")
    rejected.rollback()
    with session.begin_nested():
        stage(session, "later-sibling")
    assert published == []
    session.commit()
    assert published == ["outer", "accepted-sibling", "later-sibling"]


def test_ancestor_rollback_drops_children_but_keeps_outer_work(graph_transaction):
    session, published = graph_transaction
    stage(session, "outer")
    parent = session.begin_nested()
    with session.begin_nested():
        stage(session, "committed-child")
    parent.rollback()
    session.commit()
    assert published == ["outer"]


def test_outer_rollback_after_nested_commit_never_publishes(graph_transaction):
    session, published = graph_transaction
    with session.begin_nested():
        stage(session, "aborted")
    session.rollback()
    session.commit()
    assert published == []


def test_closing_and_reusing_session_does_not_publish_abandoned_work(graph_transaction):
    session, published = graph_transaction
    stage(session, "abandoned")
    session.close()
    session.execute(text("SELECT 1"))
    stage(session, "replacement")
    session.commit()
    assert published == ["replacement"]
