# NOTE: This router is NOT mounted in the application. It is retained as
# legacy/reference code and may be integrated in a future release.

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from shared.auth import APIKey, require_api_key
from shared.rate_limit import rate_limit_headers_dependency, rate_limit_middleware

router = APIRouter(prefix="/api", tags=["domain"])

DISCLAIMER = (
    "Outputs are regulatory references and citations only, not legal advice. "
    "Customer remains responsible for compliance decisions."
)


# ---- KYC ----
class KYCValidationRequest(BaseModel):
    id_type: Literal["SSN", "EIN", "VAT", "TIN", "Passport", "NationalID"]
    id_value: str = Field(min_length=3, max_length=64)
    country_code: str = Field(
        min_length=2, max_length=2, description="ISO 3166-1 alpha-2"
    )


class KYCValidationResponse(BaseModel):
    valid_format: bool
    issuer_pattern_match: bool
    confidence: float = Field(ge=0.0, le=1.0)
    disclaimer: str = DISCLAIMER


def _free_tier_limit(request: Request):
    # Apply tighter free-tier limits (e.g., 60/minute) by API key/IP
    rate_limit_middleware(request, limit_per_minute=60, use_api_key=True)


def _free_tier_limit_dependency(request: Request):
    # Thin wrapper so tests can monkeypatch `_free_tier_limit`
    return _free_tier_limit(request)


@router.post(
    "/kyc/basic",
    response_model=KYCValidationResponse,
    dependencies=[
        Depends(_free_tier_limit_dependency),
        Depends(rate_limit_headers_dependency),
    ],
)
def kyc_basic_validate(
    payload: KYCValidationRequest, api_key: APIKey = Depends(require_api_key)
):
    # Stateless format/pattern validation only
    country = payload.country_code.upper()
    value = payload.id_value.strip()
    # Simple heuristics (placeholder): format length checks by id_type
    length_rules = {
        "SSN": 9,
        "EIN": 9,
        "VAT": 8,
        "TIN": 9,
        "Passport": 8,
        "NationalID": 8,
    }
    expected_len = length_rules.get(payload.id_type)
    valid_format = (
        expected_len is None or len([c for c in value if c.isalnum()]) >= expected_len
    )
    issuer_pattern_match = country in {"US", "GB", "DE", "FR", "CA"}
    confidence = 0.6 if valid_format else 0.2
    return KYCValidationResponse(
        valid_format=bool(valid_format),
        issuer_pattern_match=bool(issuer_pattern_match),
        confidence=confidence,
    )


# ---- AML ----
class AMLWatchlistRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    country_hint: Optional[str] = Field(default=None, min_length=2, max_length=2)


class AMLWatchlistResponse(BaseModel):
    candidate_count: int
    max_confidence: float = Field(ge=0.0, le=1.0)
    disclaimer: str = DISCLAIMER


@router.post(
    "/aml/watchlist",
    response_model=AMLWatchlistResponse,
    dependencies=[
        Depends(_free_tier_limit_dependency),
        Depends(rate_limit_headers_dependency),
    ],
)
def aml_watchlist_check(
    payload: AMLWatchlistRequest, api_key: APIKey = Depends(require_api_key)
):
    # Placeholder: do not perform actual matching; return structured response with disclaimers
    name = payload.name.strip()
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Invalid name")
    # Return zero candidates for now to avoid false positives in free tier
    return AMLWatchlistResponse(candidate_count=0, max_confidence=0.0)


# ---- Privacy ----
class PrivacyRuleLookupRequest(BaseModel):
    data_category: Literal["PII", "SensitivePII", "Financial", "Health", "Biometric"]
    subject_region: str = Field(min_length=2, max_length=2)
    processing_purpose: Literal[
        "Marketing", "Analytics", "Identity", "Fraud", "Operations"
    ]
    jurisdiction_code: Optional[str] = Field(
        default=None, description="e.g., US-CA, EU"
    )


class PrivacyRuleReference(BaseModel):
    citation: str
    rule_version: Optional[str] = None
    effective_date: Optional[str] = None
    source_uri: Optional[str] = None
    jurisdiction_code: Optional[str] = None


class PrivacyRuleLookupResponse(BaseModel):
    references: list[PrivacyRuleReference]
    disclaimer: str = DISCLAIMER


@router.post(
    "/privacy/rule-lookup",
    response_model=PrivacyRuleLookupResponse,
    dependencies=[
        Depends(_free_tier_limit_dependency),
        Depends(rate_limit_headers_dependency),
    ],
)
def privacy_rule_lookup(
    payload: PrivacyRuleLookupRequest, api_key: APIKey = Depends(require_api_key)
):
    # Return neutral references only; no prescriptive advice
    refs = [
        PrivacyRuleReference(
            citation="GDPR Art. 6 — Lawfulness of processing",
            rule_version="EU-2016/679",
            effective_date="2018-05-25",
            source_uri="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
            jurisdiction_code=payload.jurisdiction_code or "EU",
        )
    ]
    return PrivacyRuleLookupResponse(references=refs)


# ---- Filings ----
class FilingsSchemaCheckRequest(BaseModel):
    form_type: Literal["SAR", "STR", "CTR", "Custom"]
    payload_schema: dict


class FilingsSchemaCheckResponse(BaseModel):
    conforms: bool
    issues: list[str]
    disclaimer: str = DISCLAIMER


@router.post(
    "/filings/schema-check",
    response_model=FilingsSchemaCheckResponse,
    dependencies=[
        Depends(_free_tier_limit_dependency),
        Depends(rate_limit_headers_dependency),
    ],
)
def filings_schema_check(
    payload: FilingsSchemaCheckRequest, api_key: APIKey = Depends(require_api_key)
):
    # Placeholder: accept only non-empty schemas; detailed validation to be added
    conforms = bool(payload.payload_schema)
    issues = [] if conforms else ["Empty or invalid schema"]
    return FilingsSchemaCheckResponse(conforms=conforms, issues=issues)
