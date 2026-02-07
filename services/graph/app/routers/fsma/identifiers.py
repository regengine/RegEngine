from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from shared.auth import require_api_key
from shared.fsma_validation import (
    IdentifierType,
    ValidationResult,
    validate_batch,
    validate_gln,
    validate_gtin,
    validate_identifier,
    validate_sscc,
    validate_tlc,
)

router = APIRouter(tags=["Validation"])


# ============================================================================
# IDENTIFIER VALIDATION ENDPOINTS
# ============================================================================


@router.post("/validate/tlc")
def validate_tlc_endpoint(
    tlc: str = Query(..., description="Traceability Lot Code to validate"),
    strict: bool = Query(False, description="Apply strict pattern matching"),
    api_key=Depends(require_api_key),
):
    """
    Validate a Traceability Lot Code (TLC).

    FSMA 204 allows flexible TLC formats. This validates:
    - Minimum/maximum length
    - No dangerous characters (security)
    - Pattern matching (optional in strict mode)

    Returns validation result with any warnings or errors.
    """
    result = validate_tlc(tlc, strict=strict)

    return {
        "is_valid": result.is_valid,
        "identifier_type": result.identifier_type.value,
        "original_value": result.original_value,
        "normalized_value": result.normalized_value,
        "errors": result.errors,
        "warnings": result.warnings,
    }


@router.post("/validate/gtin")
def validate_gtin_endpoint(
    gtin: str = Query(..., description="GTIN to validate (8, 12, 13, or 14 digits)"),
    api_key=Depends(require_api_key),
):
    """
    Validate a Global Trade Item Number (GTIN).

    Validates:
    - Correct length (8, 12, 13, or 14 digits)
    - Valid GS1 check digit

    Returns validation result with any errors.
    """
    result = validate_gtin(gtin)

    return {
        "is_valid": result.is_valid,
        "identifier_type": result.identifier_type.value,
        "original_value": result.original_value,
        "normalized_value": result.normalized_value,
        "errors": result.errors,
        "warnings": result.warnings,
    }


@router.post("/validate/gln")
def validate_gln_endpoint(
    gln: str = Query(..., description="GLN to validate (13 digits)"),
    api_key=Depends(require_api_key),
):
    """
    Validate a Global Location Number (GLN).

    Validates:
    - Exactly 13 digits
    - Valid GS1 check digit

    Returns validation result with any errors.
    """
    result = validate_gln(gln)

    return {
        "is_valid": result.is_valid,
        "identifier_type": result.identifier_type.value,
        "original_value": result.original_value,
        "normalized_value": result.normalized_value,
        "errors": result.errors,
        "warnings": result.warnings,
    }


@router.post("/validate/identifier")
def validate_identifier_endpoint(
    value: str = Query(..., description="Identifier value to validate"),
    identifier_type: Optional[str] = Query(
        None,
        description="Expected type: TLC, GTIN, GLN, SSCC (auto-detect if not provided)",
    ),
    strict: bool = Query(False, description="Apply strict validation"),
    api_key=Depends(require_api_key),
):
    """
    Validate any identifier with optional auto-detection.

    If identifier_type is not provided, the system will attempt to
    auto-detect based on the format (numeric vs alphanumeric, length).

    Supported types:
    - TLC: Traceability Lot Code (flexible alphanumeric)
    - GTIN: Global Trade Item Number (8, 12, 13, or 14 digits)
    - GLN: Global Location Number (13 digits)
    - SSCC: Serial Shipping Container Code (18 digits)
    """
    expected_type = None
    if identifier_type:
        try:
            expected_type = IdentifierType(identifier_type.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid identifier_type: {identifier_type}. "
                f"Valid types: TLC, GTIN, GLN, SSCC",
            )

    result = validate_identifier(value, expected_type=expected_type, strict=strict)

    return {
        "is_valid": result.is_valid,
        "identifier_type": result.identifier_type.value,
        "original_value": result.original_value,
        "normalized_value": result.normalized_value,
        "errors": result.errors,
        "warnings": result.warnings,
    }


class BatchValidationItem(BaseModel):
    value: str
    identifier_type: Optional[str] = None


class BatchValidationRequest(BaseModel):
    identifiers: List[BatchValidationItem]
    strict: bool = False


@router.post("/validate/batch")
def validate_batch_endpoint(
    request: BatchValidationRequest,
    api_key=Depends(require_api_key),
):
    """
    Validate multiple identifiers in a single request.

    Useful for validating all identifiers in a document or shipment
    before ingestion into the traceability system.

    Returns validation results for each identifier with summary statistics.
    """
    # Convert to internal format
    identifiers = []
    for item in request.identifiers:
        expected_type = None
        if item.identifier_type:
            try:
                expected_type = IdentifierType(item.identifier_type.upper())
            except ValueError:
                pass  # Will auto-detect
        identifiers.append((item.value, expected_type))

    results = validate_batch(identifiers, strict=request.strict)

    valid_count = sum(1 for r in results if r.is_valid)

    return {
        "summary": {
            "total": len(results),
            "valid": valid_count,
            "invalid": len(results) - valid_count,
        },
        "results": [
            {
                "is_valid": r.is_valid,
                "identifier_type": r.identifier_type.value,
                "original_value": r.original_value,
                "normalized_value": r.normalized_value,
                "errors": r.errors,
                "warnings": r.warnings,
            }
            for r in results
        ],
    }
