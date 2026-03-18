from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.supplier_cte_service import _next_merkle_hash, _sha256_json


# ── Auto-clean helpers ────────────────────────────────────────────
# Instead of rejecting rows with short/empty fields, we auto-fill
# with safe defaults and collect warnings for the user.

_AUTOFILL_WARNINGS: list[dict[str, Any]] = []


def _autofill_str(value: Any, *, field: str, row_hint: str = "", min_len: int = 2, default: str = "Unknown") -> str:
    """Ensure a string meets min_length, substituting a default if not."""
    cleaned = str(value or "").strip()
    if len(cleaned) < min_len:
        replacement = default
        _AUTOFILL_WARNINGS.append({
            "field": field,
            "original": cleaned or "(empty)",
            "replacement": replacement,
            "hint": row_hint,
        })
        return replacement
    return cleaned


CTE_ALIAS_MAP = {
    "transformation": "transforming",
    "first_land_based_receiving": "first_receiver",
    # Single-letter FSMA 204 event type codes
    "r": "receiving",
    "s": "shipping",
    "t": "transforming",
    "c": "cooling",
    "p": "initial_packing",
    "h": "harvesting",
    # Common full-word aliases
    "harvest": "harvesting",
    "packing": "initial_packing",
    "pack": "initial_packing",
    "receive": "receiving",
    "ship": "shipping",
    "transform": "transforming",
    "cool": "cooling",
    # Distribution / processing aliases
    "distribute": "shipping",
    "distribution": "shipping",
    "di": "shipping",
    "process": "transforming",
    "processing": "transforming",
}


def normalize_cte_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return CTE_ALIAS_MAP.get(normalized, normalized)


class BulkFacilityRow(BaseModel):
    name: str = Field(default="")
    street: str = Field(default="")
    city: str = Field(default="")
    state: str = Field(default="")
    postal_code: str = Field(default="")
    fda_registration_number: str | None = None
    roles: list[str] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, value: Any) -> str:
        return _autofill_str(value, field="facility_name", min_len=2, default="Unnamed Facility")

    @field_validator("roles", mode="before")
    @classmethod
    def _normalize_roles(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [token.strip() for token in value.split(",") if token.strip()]
        return []


class BulkFTLScopeRow(BaseModel):
    facility_name: str = Field(default="")
    category_id: str = Field(default="")

    @field_validator("facility_name", mode="before")
    @classmethod
    def _clean_facility(cls, value: Any) -> str:
        return _autofill_str(value, field="ftl_facility_name", min_len=2, default="Unnamed Facility")

    @field_validator("category_id", mode="before")
    @classmethod
    def _clean_category(cls, value: Any) -> str:
        return _autofill_str(value, field="ftl_category_id", min_len=1, default="unknown")


class BulkTLCRow(BaseModel):
    tlc_code: str = Field(default="")
    facility_name: str = Field(default="")
    product_description: str | None = None
    status: str = "active"

    @field_validator("tlc_code", mode="before")
    @classmethod
    def _clean_tlc(cls, value: Any) -> str:
        return _autofill_str(value, field="tlc_code", min_len=3, default="TLC-UNKNOWN")

    @field_validator("facility_name", mode="before")
    @classmethod
    def _clean_facility(cls, value: Any) -> str:
        return _autofill_str(value, field="tlc_facility_name", min_len=2, default="Unnamed Facility")


class BulkCTEEventRow(BaseModel):
    facility_name: str = Field(default="")
    tlc_code: str = Field(default="")
    cte_type: str = Field(default="")
    event_time: str | None = None
    kde_data: dict[str, Any] = Field(default_factory=dict)
    obligation_ids: list[str] = Field(default_factory=list)

    @field_validator("facility_name", mode="before")
    @classmethod
    def _clean_facility(cls, value: Any) -> str:
        return _autofill_str(value, field="event_facility_name", min_len=2, default="Unnamed Facility")

    @field_validator("tlc_code", mode="before")
    @classmethod
    def _clean_tlc(cls, value: Any) -> str:
        return _autofill_str(value, field="event_tlc_code", min_len=3, default="TLC-UNKNOWN")

    @field_validator("cte_type", mode="before")
    @classmethod
    def _normalize_cte(cls, value: Any) -> str:
        cleaned = normalize_cte_type(str(value or ""))
        if len(cleaned) < 2:
            return _autofill_str(cleaned, field="cte_type", min_len=2, default="receiving")
        return cleaned

    @field_validator("event_time", mode="before")
    @classmethod
    def _normalize_event_time(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("event_time must be ISO-8601") from exc
        return parsed.isoformat()

    @field_validator("obligation_ids", mode="before")
    @classmethod
    def _normalize_obligations(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [token.strip() for token in value.split(",") if token.strip()]
        return []


def compute_payload_sha256(payload: dict[str, Any]) -> str:
    return _sha256_json(payload)


def next_merkle_hash(prev_hash: str | None, payload_sha256: str) -> str:
    return _next_merkle_hash(prev_hash, payload_sha256)


def validate_and_normalize_payload(
    parsed_payload: dict[str, Any],
    *,
    supported_cte_types: set[str],
    valid_ftl_category_ids: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    normalized: dict[str, list[dict[str, Any]]] = {
        "facilities": [],
        "ftl_scopes": [],
        "tlcs": [],
        "events": [],
    }
    errors: list[dict[str, Any]] = []

    # Clear per-run autofill warnings
    _AUTOFILL_WARNINGS.clear()

    section_specs: list[tuple[str, type[BaseModel], str]] = [
        ("facilities", BulkFacilityRow, "facility"),
        ("ftl_scopes", BulkFTLScopeRow, "ftl_scope"),
        ("tlcs", BulkTLCRow, "tlc"),
        ("events", BulkCTEEventRow, "event"),
    ]

    for source_key, model_cls, section_name in section_specs:
        rows = parsed_payload.get(source_key) or []
        if not isinstance(rows, list):
            errors.append(
                {
                    "section": section_name,
                    "row": 0,
                    "message": "Section must be an array",
                }
            )
            continue

        for index, row in enumerate(rows, start=1):
            try:
                candidate = model_cls.model_validate(row)
            except ValidationError as exc:
                # Even with auto-cleaning, some rows may still be truly invalid
                # (e.g. wrong types). Demote to warning and skip the row.
                errors.append(
                    {
                        "section": section_name,
                        "row": index,
                        "message": "; ".join(err.get("msg", "invalid row") for err in exc.errors()),
                        "severity": "warning",
                    }
                )
                continue

            payload = candidate.model_dump()
            if section_name == "event":
                cte_type = str(payload.get("cte_type") or "")
                if cte_type not in supported_cte_types:
                    # Auto-default to "receiving" instead of rejecting
                    payload["cte_type"] = "receiving"
                    _AUTOFILL_WARNINGS.append({
                        "field": "cte_type",
                        "original": cte_type,
                        "replacement": "receiving",
                        "hint": f"event row {index}",
                    })
            if section_name == "ftl_scope":
                category_id = str(payload.get("category_id") or "")
                if category_id not in valid_ftl_category_ids:
                    errors.append(
                        {
                            "section": section_name,
                            "row": index,
                            "message": f"Unknown FTL category_id: {category_id}",
                            "severity": "warning",
                        }
                    )
                    continue

            normalized[source_key].append(payload)

    # Convert autofill warnings into the errors list as non-blocking warnings
    for warn in _AUTOFILL_WARNINGS:
        errors.append({
            "section": "autofill",
            "row": 0,
            "message": f"Auto-filled {warn['field']}: '{warn['original']}' → '{warn['replacement']}'"
                       + (f" ({warn['hint']})" if warn.get("hint") else ""),
            "severity": "warning",
        })

    return normalized, errors
