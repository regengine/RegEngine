from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

from fastapi import HTTPException, UploadFile


ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".json", ".pdf"}


def _normalize_key(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[_normalize_key(str(key))] = value
    return normalized


def _parse_json_field(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_list_field(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [token.strip() for token in text.split(",") if token.strip()]
    return []


def _extract_event_row(row: dict[str, Any]) -> dict[str, Any]:
    cte_type = row.get("cte_type") or row.get("event_type") or ""
    event_time = row.get("event_time") or row.get("timestamp")
    kde_data = _parse_json_field(row.get("kde_data"))

    passthrough_keys = {
        "record_type",
        "facility_name",
        "tlc_code",
        "cte_type",
        "event_type",
        "event_time",
        "timestamp",
        "kde_data",
        "obligation_ids",
    }
    for key, value in row.items():
        if key in passthrough_keys:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        kde_data[key] = value

    return {
        "facility_name": str(row.get("facility_name") or row.get("location_name") or "").strip(),
        "tlc_code": str(row.get("tlc_code") or "").strip(),
        "cte_type": str(cte_type).strip(),
        "event_time": str(event_time).strip() if event_time else None,
        "kde_data": kde_data,
        "obligation_ids": _parse_list_field(row.get("obligation_ids")),
    }


def _classify_row(parsed: dict[str, Any], row: dict[str, Any], *, warnings: list[str]) -> None:
    record_type = str(row.get("record_type") or "").strip().lower()
    if record_type in {"facility", "facilities"}:
        parsed["facilities"].append(
            {
                "name": str(row.get("name") or row.get("facility_name") or "").strip(),
                "street": str(row.get("street") or "").strip(),
                "city": str(row.get("city") or "").strip(),
                "state": str(row.get("state") or "").strip(),
                "postal_code": str(row.get("postal_code") or row.get("zip") or "").strip(),
                "fda_registration_number": str(row.get("fda_registration_number") or "").strip() or None,
                "roles": _parse_list_field(row.get("roles")),
            }
        )
        return
    if record_type in {"ftl", "ftl_scope", "scope"}:
        parsed["ftl_scopes"].append(
            {
                "facility_name": str(row.get("facility_name") or row.get("name") or "").strip(),
                "category_id": str(row.get("category_id") or "").strip(),
            }
        )
        return
    if record_type in {"tlc", "lot"}:
        parsed["tlcs"].append(
            {
                "tlc_code": str(row.get("tlc_code") or "").strip(),
                "facility_name": str(row.get("facility_name") or row.get("name") or "").strip(),
                "product_description": str(row.get("product_description") or "").strip() or None,
                "status": str(row.get("status") or "active").strip().lower(),
            }
        )
        return
    if record_type in {"event", "cte", "cte_event"}:
        parsed["events"].append(_extract_event_row(row))
        return

    if row.get("cte_type") or row.get("event_type"):
        parsed["events"].append(_extract_event_row(row))
        return
    if row.get("category_id"):
        parsed["ftl_scopes"].append(
            {
                "facility_name": str(row.get("facility_name") or row.get("name") or "").strip(),
                "category_id": str(row.get("category_id") or "").strip(),
            }
        )
        return
    if row.get("tlc_code"):
        parsed["tlcs"].append(
            {
                "tlc_code": str(row.get("tlc_code") or "").strip(),
                "facility_name": str(row.get("facility_name") or row.get("name") or "").strip(),
                "product_description": str(row.get("product_description") or "").strip() or None,
                "status": str(row.get("status") or "active").strip().lower(),
            }
        )
        return
    if row.get("name") or row.get("facility_name"):
        parsed["facilities"].append(
            {
                "name": str(row.get("name") or row.get("facility_name") or "").strip(),
                "street": str(row.get("street") or "").strip(),
                "city": str(row.get("city") or "").strip(),
                "state": str(row.get("state") or "").strip(),
                "postal_code": str(row.get("postal_code") or row.get("zip") or "").strip(),
                "fda_registration_number": str(row.get("fda_registration_number") or "").strip() or None,
                "roles": _parse_list_field(row.get("roles")),
            }
        )
        return

    warnings.append("Skipped unrecognized row in uploaded dataset")


def _parse_csv_bytes(content: bytes, parsed: dict[str, Any], warnings: list[str]) -> None:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        normalized_row = _normalize_row(row)
        if not any(str(value or "").strip() for value in normalized_row.values()):
            continue
        _classify_row(parsed, normalized_row, warnings=warnings)


def _parse_json_bytes(content: bytes, parsed: dict[str, Any], warnings: list[str]) -> None:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON file: {exc}") from exc

    if isinstance(payload, dict):
        facilities = payload.get("facilities") or []
        ftl_scopes = payload.get("ftl_scopes") or payload.get("ftl_scope") or []
        tlcs = payload.get("tlcs") or []
        events = payload.get("events") or []

        if isinstance(facilities, list):
            for row in facilities:
                _classify_row(parsed, _normalize_row({**(row or {}), "record_type": "facility"}), warnings=warnings)
        if isinstance(ftl_scopes, list):
            for row in ftl_scopes:
                _classify_row(parsed, _normalize_row({**(row or {}), "record_type": "ftl_scope"}), warnings=warnings)
        if isinstance(tlcs, list):
            for row in tlcs:
                _classify_row(parsed, _normalize_row({**(row or {}), "record_type": "tlc"}), warnings=warnings)
        if isinstance(events, list):
            for row in events:
                _classify_row(parsed, _normalize_row({**(row or {}), "record_type": "event"}), warnings=warnings)
        if not any(isinstance(section, list) and section for section in [facilities, ftl_scopes, tlcs, events]):
            _classify_row(parsed, _normalize_row(payload), warnings=warnings)
        return

    if isinstance(payload, list):
        for row in payload:
            if isinstance(row, dict):
                _classify_row(parsed, _normalize_row(row), warnings=warnings)
        return

    raise HTTPException(status_code=400, detail="JSON must be an object or array")


def _parse_xlsx_bytes(content: bytes, parsed: dict[str, Any], warnings: list[str]) -> None:
    try:
        from openpyxl import load_workbook
    except Exception as exc:  # pragma: no cover - dependency/env specific
        raise HTTPException(status_code=503, detail="XLSX parsing unavailable (openpyxl missing)") from exc

    workbook = load_workbook(io.BytesIO(content), data_only=True)
    for sheet in workbook.worksheets:
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            continue
        headers = [_normalize_key(str(cell or "")) for cell in rows[0]]
        if not any(headers):
            continue

        normalized_sheet_name = sheet.title.strip().lower()
        inferred_record_type: str | None = None
        if "facility" in normalized_sheet_name:
            inferred_record_type = "facility"
        elif "ftl" in normalized_sheet_name or "scope" in normalized_sheet_name:
            inferred_record_type = "ftl_scope"
        elif "tlc" in normalized_sheet_name or "lot" in normalized_sheet_name:
            inferred_record_type = "tlc"
        elif "event" in normalized_sheet_name or "cte" in normalized_sheet_name:
            inferred_record_type = "event"

        for values in rows[1:]:
            if values is None:
                continue
            row_data = {
                header: value
                for header, value in zip(headers, values)
                if header
            }
            if not any(str(value or "").strip() for value in row_data.values()):
                continue
            if inferred_record_type and "record_type" not in row_data:
                row_data["record_type"] = inferred_record_type
            _classify_row(parsed, row_data, warnings=warnings)


def _parse_pdf_bytes(content: bytes, parsed: dict[str, Any], warnings: list[str]) -> None:
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover - dependency/env specific
        raise HTTPException(status_code=503, detail="PDF parsing unavailable (pdfplumber missing)") from exc

    extracted_rows = 0
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                headers = [_normalize_key(str(cell or "")) for cell in table[0]]
                for row_values in table[1:]:
                    row = {
                        header: value
                        for header, value in zip(headers, row_values)
                        if header
                    }
                    if not any(str(value or "").strip() for value in row.values()):
                        continue
                    _classify_row(parsed, row, warnings=warnings)
                    extracted_rows += 1

        if extracted_rows == 0:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            start = full_text.find("{")
            end = full_text.rfind("}")
            if 0 <= start < end:
                blob = full_text[start : end + 1]
                try:
                    _parse_json_bytes(blob.encode("utf-8"), parsed, warnings)
                    extracted_rows = 1
                except Exception:
                    pass

    if extracted_rows == 0:
        warnings.append("PDF parsed but no structured rows detected; include tabular data or JSON block")


async def parse_incoming_file(file: UploadFile) -> dict[str, Any]:
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    parsed: dict[str, Any] = {
        "detected_format": extension.replace(".", ""),
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
        "warnings": [],
    }
    warnings = parsed["warnings"]

    if extension == ".csv":
        _parse_csv_bytes(content, parsed, warnings)
    elif extension == ".json":
        _parse_json_bytes(content, parsed, warnings)
    elif extension == ".xlsx":
        _parse_xlsx_bytes(content, parsed, warnings)
    elif extension == ".pdf":
        _parse_pdf_bytes(content, parsed, warnings)
    else:  # pragma: no cover
        raise HTTPException(status_code=400, detail="Unsupported file format")

    return parsed
