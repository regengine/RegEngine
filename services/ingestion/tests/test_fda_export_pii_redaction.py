"""Data-free FDA export redaction and permission checks."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.authz import IngestionPrincipal  # noqa: E402
from app.fda_export.router import _authorize_pii_access  # noqa: E402
from app.fda_export_service import (  # noqa: E402
    FDA_COLUMNS,
    FDA_COLUMNS_V2,
    PII_REDACTION_PLACEHOLDER,
    _event_to_fda_row,
    _generate_csv,
    _generate_csv_v2,
    _redact_extra_kde_pii,
    _redact_location_value,
)


def test_redact_location_value_redacts_pii_columns_by_default() -> None:
    for column in ("Location Name", "Ship From Name", "Ship To Name", "Immediate Previous Source", "Receiving Location"):
        assert _redact_location_value(" ", column, False) == PII_REDACTION_PLACEHOLDER


def test_redact_location_value_passes_through_when_include_pii_true() -> None:
    assert _redact_location_value(" ", "Location Name", True) == " "


def test_redact_location_value_does_not_touch_non_pii_columns() -> None:
    assert _redact_location_value(" ", "Location GLN", False) == " "


def test_redact_location_value_preserves_empty_strings() -> None:
    assert _redact_location_value("", "Location Name", False) == ""


def test_redact_extra_kde_pii_redacts_address_and_contact_keys() -> None:
    assert _redact_extra_kde_pii({"facility_address": " "}) == {
        "facility_address": PII_REDACTION_PLACEHOLDER
    }


def test_redact_extra_kde_pii_preserves_keys_for_audit_visibility() -> None:
    assert _redact_extra_kde_pii({"driver_name": ""}) == {"driver_name": ""}


def test_empty_event_row_has_no_identity_values() -> None:
    row = _event_to_fda_row({})
    assert set(row) == set(FDA_COLUMNS)
    assert all(value == "" for value in row.values())


@pytest.mark.parametrize("generator,columns", [(_generate_csv, FDA_COLUMNS), (_generate_csv_v2, FDA_COLUMNS_V2)])
def test_empty_csv_has_only_the_header(generator, columns) -> None:
    rows = list(csv.reader(io.StringIO(generator([]))))
    assert rows == [columns]


def test_endpoint_include_pii_without_permission_returns_403() -> None:
    principal = IngestionPrincipal(key_id="", scopes=["fda.export"])
    with pytest.raises(HTTPException) as exc:
        _authorize_pii_access(
            include_pii=True,
            principal=principal,
            identity={"user_id": "", "request_id": ""},
            tenant_id="",
            export_scope="",
        )
    assert exc.value.status_code == 403


def test_endpoint_default_pii_access_is_noop() -> None:
    _authorize_pii_access(
        include_pii=False,
        principal=IngestionPrincipal(key_id="", scopes=[]),
        identity={},
        tenant_id="",
        export_scope="",
    )
