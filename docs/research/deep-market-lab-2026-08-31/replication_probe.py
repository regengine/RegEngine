"""Local adjudication probes; synthetic SQLite data, no external services.

Run from repo root: .venv/bin/python3 docs/research/deep-market-lab-2026-08-31/replication_probe.py
These are observations of current behavior, not passing regression tests for a fix.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services"))

import sqlalchemy
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared.canonical_persistence import legacy_dual_write
from shared.cte_persistence import CTEPersistence
from shared.cte_persistence.hashing import compute_chain_hash, compute_event_hash


def chain_probe() -> dict:
    engine = create_engine("sqlite:///:memory:")
    fixture = dict(
        event_id="synthetic-event", event_type="shipping", tlc="SYNTHETIC-LOT",
        product_description="Synthetic produce", quantity=10.0,
        unit_of_measure="kg", location_gln="1234567890128",
        location_name="Synthetic facility", timestamp="2026-08-31T12:00:00+00:00",
        kdes={"reference_document_number": "SYNTHETIC-DOC-1"},
    )
    event_hash = compute_event_hash(**fixture)
    chain_hash = compute_chain_hash(event_hash, None)
    with engine.begin() as connection:
        connection.execute(text("ATTACH DATABASE ':memory:' AS fsma"))
        connection.execute(text("""
            CREATE TABLE fsma.cte_events (
                id TEXT PRIMARY KEY, tenant_id TEXT, validation_status TEXT,
                quantity REAL, sha256_hash TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE fsma.cte_kdes (
                tenant_id TEXT, cte_event_id TEXT, kde_key TEXT, kde_value TEXT
            )
        """))
        connection.execute(text("""
            CREATE TABLE fsma.hash_chain (
                sequence_num INTEGER, tenant_id TEXT, event_hash TEXT,
                previous_chain_hash TEXT, chain_hash TEXT, cte_event_id TEXT
            )
        """))
        connection.execute(text("""
            INSERT INTO fsma.cte_events VALUES
                ('synthetic-event', 'synthetic-tenant', 'valid', 10.0, :hash)
        """), {"hash": event_hash})
        connection.execute(text("""
            INSERT INTO fsma.cte_kdes VALUES
                ('synthetic-tenant', 'synthetic-event',
                 'reference_document_number', 'SYNTHETIC-DOC-1')
        """))
        connection.execute(text("""
            INSERT INTO fsma.hash_chain VALUES
                (1, 'synthetic-tenant', :event_hash, NULL, :chain_hash, 'synthetic-event')
        """), {"event_hash": event_hash, "chain_hash": chain_hash})

    def observe(session: Session) -> dict:
        current_quantity = session.execute(text("SELECT quantity FROM fsma.cte_events")).scalar_one()
        current_kdes = dict(session.execute(text("SELECT kde_key, kde_value FROM fsma.cte_kdes")).all())
        current_hash = compute_event_hash(**{**fixture, "quantity": current_quantity, "kdes": current_kdes})
        result = CTEPersistence(session).verify_chain("synthetic-tenant")
        return {
            "verify_chain_valid": result.valid,
            "current_payload_hash_matches_original": current_hash == event_hash,
            "errors": result.errors,
        }

    with Session(engine) as session:
        baseline = observe(session)
        assert baseline["verify_chain_valid"] and baseline["current_payload_hash_matches_original"]
        session.execute(text("UPDATE fsma.cte_events SET quantity = 999.0"))
        quantity_changed = observe(session)
        assert quantity_changed["verify_chain_valid"] and not quantity_changed["current_payload_hash_matches_original"]
        session.execute(text("UPDATE fsma.cte_events SET quantity = 10.0"))
        session.execute(text("UPDATE fsma.cte_kdes SET kde_value = 'SYNTHETIC-DOC-CHANGED'"))
        kde_changed = observe(session)
        assert kde_changed["verify_chain_valid"] and not kde_changed["current_payload_hash_matches_original"]
        session.execute(text("UPDATE fsma.hash_chain SET chain_hash = :bad"), {"bad": "0" * 64})
        chain_corrupted = observe(session)
        assert not chain_corrupted["verify_chain_valid"]
    engine.dispose()
    return dict(baseline=baseline, quantity_changed=quantity_changed,
                kde_changed=kde_changed, chain_corrupted_control=chain_corrupted)


def graph_probe(mode: str) -> dict:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE synthetic_events (id TEXT PRIMARY KEY)"))
    published = []
    with patch.dict("os.environ", {"ENABLE_NEO4J_SYNC": "false" if mode == "disabled" else "true"}), \
         patch.object(legacy_dual_write, "publish_graph_sync", side_effect=lambda event: published.append(event.event_id)), \
         Session(engine) as session:
        # Explicit SQL BEGIN avoids SQLite legacy transaction behavior in which
        # a SAVEPOINT can accidentally be the outermost database transaction.
        session.execute(text("BEGIN"))
        session.execute(text("INSERT INTO synthetic_events VALUES ('synthetic-event')"))
        legacy_dual_write.stage_graph_sync(session, SimpleNamespace(event_id="synthetic-event"))
        published_before_boundary = len(published)
        if mode in {"nested_commit_outer_rollback", "nested_rollback_outer_commit"}:
            nested = session.begin_nested()
            session.execute(text("SELECT 1"))
            if mode == "nested_commit_outer_rollback":
                nested.commit()
            else:
                nested.rollback()
        published_after_nested_boundary = len(published)
        outer_transaction_still_open = session.in_transaction()
        if mode in {"rollback", "nested_commit_outer_rollback"}:
            session.rollback()
        else:
            session.commit()
        with engine.connect() as connection:
            durable_rows = connection.execute(text("SELECT COUNT(*) FROM synthetic_events")).scalar_one()
        result = dict(
            published_before_boundary=published_before_boundary,
            published_after_nested_boundary=published_after_nested_boundary,
            outer_transaction_still_open=outer_transaction_still_open,
            published_final=len(published), durable_rows=durable_rows,
        )
    engine.dispose()
    return result


def main() -> None:
    graphs = {mode: graph_probe(mode) for mode in (
        "disabled", "commit", "rollback", "nested_commit_outer_rollback", "nested_rollback_outer_commit",
    )}
    assert graphs["disabled"]["published_final"] == 0
    assert graphs["commit"]["published_final"] == 1
    assert graphs["rollback"]["published_final"] == 0
    assert graphs["nested_commit_outer_rollback"]["published_after_nested_boundary"] == 1
    assert graphs["nested_commit_outer_rollback"]["outer_transaction_still_open"]
    assert graphs["nested_commit_outer_rollback"]["durable_rows"] == 0
    assert graphs["nested_rollback_outer_commit"]["published_final"] == 0
    assert graphs["nested_rollback_outer_commit"]["durable_rows"] == 1
    print(json.dumps({"python": sys.version.split()[0], "sqlalchemy": sqlalchemy.__version__,
                      "chain": chain_probe(), "graph": graphs}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
