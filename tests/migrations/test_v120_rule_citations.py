"""Run the real v120 data migration in a disposable PostgreSQL database."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests.migrations.scratch_db import scratch_database_engine

ROOT = Path(__file__).resolve().parents[2]


def test_citations_version_audit_idempotence_and_rollback(monkeypatch):
    path = ROOT / "alembic/versions/20260904_c6a120b4e901_v120_rule_citations.py"
    spec = importlib.util.spec_from_file_location("v120", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with scratch_database_engine("issue_v120_" + uuid4().hex[:12]) as engine:
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA fsma"))
            # Use the actual rule catalog/evaluation/audit DDL; RLS is tested
            # separately. No table from the borrowed database is touched.
            ddl = (ROOT / "alembic/sql/V044__versioned_rules_engine.sql").read_text()
            ddl = ddl.split("BEGIN;", 1)[1].split("-- Row-Level Security", 1)[0]
            conn.exec_driver_sql(ddl)
            monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: conn))
            ids = {}
            for title, (old, new) in migration.CITATION_CORRECTIONS.items():
                ids[title] = str(uuid4())
                conn.execute(
                    text("""INSERT INTO fsma.rule_definitions(rule_id,title,citation_reference)
                            VALUES (:id,:title,:citation)"""),
                    {"id": ids[title], "title": title, "citation": old},
                )
            phone_id = str(uuid4())
            old_phone = {
                "type": "multi_field_presence",
                "field": "kdes.harvester_business_phone",
                "params": {"fields": ["kdes.harvester_business_phone", "from_entity_reference"]},
            }
            conn.execute(
                text("""INSERT INTO fsma.rule_definitions(rule_id,title,evaluation_logic)
                VALUES (:id, 'Initial Packing: Harvester Phone Required', CAST(:logic AS jsonb))"""),
                {"id": phone_id, "logic": json.dumps(old_phone)},
            )
            # A custom latest version makes its historical seed immutable.
            custom_title = next(iter(ids))
            conn.execute(
                text("""INSERT INTO fsma.rule_definitions(title,rule_version,citation_reference)
                VALUES (:title,2,'Custom tenant-reviewed citation')"""),
                {"title": custom_title},
            )
            retired_title = list(ids)[1]
            conn.execute(
                text("""INSERT INTO fsma.rule_definitions(title,rule_version,citation_reference,retired_date)
                VALUES (:title,2,'Retired historical citation',CURRENT_DATE)"""),
                {"title": retired_title},
            )
            conn.execute(
                text("""INSERT INTO fsma.rule_definitions(title,rule_version,retired_date)
                VALUES ('Initial Packing: Harvester Phone Required',2,CURRENT_DATE)""")
            )
            evaluation_id = str(uuid4())
            conn.execute(
                text("""INSERT INTO fsma.rule_evaluations
                (evaluation_id,tenant_id,event_id,rule_id,rule_version,result,why_failed)
                VALUES (:id,:tenant,:event,:rule,1,'fail','Historical evidence')"""),
                {"id": evaluation_id, "tenant": str(uuid4()), "event": str(uuid4()), "rule": phone_id},
            )
            migration.upgrade()
            count = len(ids)  # all but custom + the phone rule
            assert conn.execute(text("SELECT COUNT(*) FROM fsma.rule_audit_log")).scalar() == count
            for title, (_, expected) in migration.CITATION_CORRECTIONS.items():
                row = conn.execute(
                    text("SELECT citation_reference,rule_version FROM fsma.rule_definitions WHERE rule_id=:id"),
                    {"id": ids[title]},
                ).one()
                if title != custom_title:
                    assert tuple(row) == (expected, 3 if title == retired_title else 2)
                else:
                    assert row.rule_version == 1
            assert (
                conn.execute(
                    text("SELECT evaluation_logic->>'type' FROM fsma.rule_definitions WHERE rule_id=:id"),
                    {"id": phone_id},
                ).scalar()
                == "field_presence"
            )
            audit = conn.execute(
                text("SELECT old_values,new_values FROM fsma.rule_audit_log WHERE rule_id=:id"), {"id": phone_id}
            ).one()
            assert audit.old_values["rule_version"] == 1
            assert audit.new_values["rule_version"] == 3
            assert (
                conn.execute(
                    text(
                        "SELECT citation_reference FROM fsma.rule_definitions WHERE title=:title AND retired_date IS NOT NULL"
                    ),
                    {"title": retired_title},
                ).scalar()
                == "Retired historical citation"
            )
            migration.upgrade()
            assert conn.execute(text("SELECT COUNT(*) FROM fsma.rule_audit_log")).scalar() == count
            migration.downgrade()
            assert conn.execute(text("SELECT COUNT(*) FROM fsma.rule_audit_log")).scalar() == count * 2
            for title, (expected, _) in migration.CITATION_CORRECTIONS.items():
                assert (
                    conn.execute(
                        text("SELECT citation_reference FROM fsma.rule_definitions WHERE rule_id=:id"),
                        {"id": ids[title]},
                    ).scalar()
                    == expected
                )
            assert (
                conn.execute(
                    text("SELECT evaluation_logic FROM fsma.rule_definitions WHERE rule_id=:id"), {"id": phone_id}
                ).scalar()
                == old_phone
            )
            historical = conn.execute(
                text("SELECT rule_version,why_failed FROM fsma.rule_evaluations WHERE evaluation_id=:id"),
                {"id": evaluation_id},
            ).one()
            assert tuple(historical) == (1, "Historical evidence")
            migration.downgrade()
            assert conn.execute(text("SELECT COUNT(*) FROM fsma.rule_audit_log")).scalar() == count * 2
