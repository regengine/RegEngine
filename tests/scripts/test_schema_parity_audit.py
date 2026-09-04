"""Unit tests for scripts/schema_parity_audit.py FK recording (#2881)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "schema_parity_audit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("schema_parity_audit", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_dump_schema_records_foreign_keys(tmp_path):
    db_path = tmp_path / "schema.db"
    url = f"sqlite:///{db_path}"
    engine = create_engine(url)
    metadata = MetaData()
    Table("parents", metadata, Column("id", Integer, primary_key=True))
    Table(
        "children",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("label", String(32)),
        Column("parent_id", Integer, ForeignKey("parents.id", name="fk_children_parent")),
    )
    metadata.create_all(engine)
    engine.dispose()

    mod = _load_module()
    snapshot = mod.dump_schema(url)

    child_key = next(key for key in snapshot if key.endswith(".children"))
    fks = snapshot[child_key]["foreign_keys"]
    assert fks, "dump_schema must record inspector.get_foreign_keys"
    match = next(fk for fk in fks if fk["name"] == "fk_children_parent")
    assert match["referred_table"] == "parents"
    assert match["constrained_columns"] == ["parent_id"]
    assert match["referred_columns"] == ["id"]

    parent_key = next(key for key in snapshot if key.endswith(".parents"))
    assert snapshot[parent_key]["foreign_keys"] == []


def test_fk_identity_ignores_ondelete_options():
    mod = _load_module()
    left = {
        "name": "fk_children_parent",
        "referred_schema": "main",
        "referred_table": "parents",
        "constrained_columns": ["parent_id"],
        "referred_columns": ["id"],
    }
    right = dict(left)
    # Option churn must not create a distinct identity.
    assert mod._fk_identity(left) == mod._fk_identity(right)
