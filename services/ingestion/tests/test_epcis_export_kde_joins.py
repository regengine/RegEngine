"""Shared _query_tenant_events KDE join expansion (Phase B prerequisite).

Synthetic fixtures only. Ensures reference_document, tlc_source_reference,
immediate_previous_source, and harvester KDEs are selected with tenant_id on
every cte_kdes join.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

_ingestion_dir = Path(__file__).resolve().parent.parent
if str(_ingestion_dir) not in sys.path:
    sys.path.insert(0, str(_ingestion_dir))
_services_dir = _ingestion_dir.parent
if str(_services_dir) not in sys.path:
    sys.path.insert(0, str(_services_dir))

pytest.importorskip("fastapi")

import app.epcis_export as epcis_export
from app.epcis_export import _query_tenant_events

REQUIRED_SELECT_ALIASES = (
    "reference_document",
    "tlc_source_reference",
    "immediate_previous_source",
    "field_id",
    "harvester_name",
    "harvester_business_name",
    "harvester_business_phone",
    "ship_from",
    "ship_to",
    "ship_from_gln",
    "ship_to_gln",
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self):
        self.sql = ""
        self.params = None
        self.closed = False

    def execute(self, stmt, params=None):
        self.sql = str(stmt)
        self.params = params
        return _FakeResult([])

    def close(self):
        self.closed = True


def test_query_selects_shipping_and_harvest_kde_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
    assert _query_tenant_events(str(uuid4()), None, None, None) == []
    sql = " ".join(session.sql.split())
    for alias in REQUIRED_SELECT_ALIASES:
        assert f"AS {alias}" in sql or f"as {alias}" in sql
    assert "kde_key = 'reference_document'" in sql
    assert "kde_key = 'tlc_source_reference'" in sql
    assert "kde_key = 'immediate_previous_source'" in sql
    assert "kde_key = 'harvester_name'" in sql
    assert "kde_key = 'field_id'" in sql


def test_every_tenant_kdes_join_has_tenant_predicate(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _FakeSession()
    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: session)
    _query_tenant_events(str(uuid4()), None, None, None)
    sql = session.sql
    # Each LEFT JOIN tenant_kdes alias must also filter tenant_id = e.tenant_id
    import re

    joins = re.findall(r"LEFT JOIN tenant_kdes (\w+) ON ([^\n]+)", sql)
    assert len(joins) >= 17
    for alias, cond in joins:
        assert f"{alias}.tenant_id = e.tenant_id" in cond, alias
    assert session.closed


def test_joined_row_mapping_exposes_new_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Row:
        def __init__(self, mapping):
            self._mapping = mapping

    class _Session:
        def execute(self, *_a, **_k):
            return _FakeResult(
                [
                    _Row(
                        {
                            "event_type": "shipping",
                            "traceability_lot_code": "LOT-ROM-2026-0312A",
                            "reference_document": "BM:BOL-9001",
                            "tlc_source_reference": "https://id.gs1.org/414/6141410000014",
                            "immediate_previous_source": None,
                            "field_id": None,
                            "harvester_name": None,
                            "harvester_business_name": None,
                            "harvester_business_phone": None,
                            "ship_from_gln": "6141410000014",
                            "ship_to_gln": "6141410000069",
                        }
                    )
                ]
            )

        def close(self):
            pass

    monkeypatch.setattr(epcis_export, "get_db_safe", lambda: _Session())
    rows = _query_tenant_events(str(uuid4()), None, None, None)
    assert rows[0]["reference_document"] == "BM:BOL-9001"
    assert rows[0]["tlc_source_reference"].startswith("https://id.gs1.org/414/")
    assert rows[0]["ship_from_gln"] == "6141410000014"
