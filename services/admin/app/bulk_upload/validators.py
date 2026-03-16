from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.supplier_cte_service import _next_merkle_hash, _sha256_json


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
    name: str = Field(min_length=2)
    street: str = Field(default="")
    city: str = Field(default="")
    state: str = Field(default="")
    postal_code: str = Field(default="")
    fda_registration_number: str | None = None
    roles: list[str] = Field(default_factory=list)

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
    facility_name: str = Field(min_length=2)
    category_id: str = Field(min_length=1)


class BulkTLCRow(BaseModel):
    tlc_code: str = Field(min_length=3)
    facility_name: str = Field(min_length=2)
    product_description: str | None = None
    status: str = "active"


class BulkCTEEventRow(BaseModel):
    facility_name: str = Field(min_length=2)
    tlc_code: str = Field(min_length=3)
    cte_type: str = Field(min_length=2)
    event_time: str | None = None
    kde_data: dict[str, Any] = Field(default_factory=dict)
    obligation_ids: list[str] = Field(default_factory=list)

    @field_validator("cte_type", mode="before")
    @classmethod
    def _normalize_cte(cls, value: Any) -> str:
        return normalize_cte_type(str(value or ""))

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
                errors.append(
                    {
                        "section": section_name,
                        "row": index,
                        "message": "; ".join(err.get("msg", "invalid row") for err in exc.errors()),
                    }
                )
                continue

            payload = candidate.model_dump()
            if section_name == "event":
                cte_type = str(payload.get("cte_type") or "")
                if cte_type not in supported_cte_types:
                    errors.append(
                        {
                            "section": section_name,
                            "row": index,
                            "message": f"Unsupported cte_type: {cte_type}",
                        }
                    )
                    continue
            if section_name == "ftl_scope":
                category_id = str(payload.get("category_id") or "")
                if category_id not in valid_ftl_category_ids:
                    errors.append(
                        {
                            "section": section_name,
                            "row": index,
                            "message": f"Unknown FTL category_id: {category_id}",
                        }
                    )
                    continue

            normalized[source_key].append(payload)

    return normalized, errors
