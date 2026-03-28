"""API endpoints for content graph overlay system.

These endpoints allow tenants to manage their custom controls, products,
and mappings to regulatory provisions.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

# Add shared module to path
from shared.auth import APIKey, require_api_key
from shared.tenant_models import (
    ControlMapping,
    CustomerProduct,
    MappingType,
    ProductControlLink,
    ProductType,
    TenantControl,
)

# Try to import overlay utilities - may not be available in all environments
try:
    # Use standardized path helper for cross-service import
    from shared.paths import add_to_path
    add_to_path(Path(__file__).resolve().parents[2] / "graph" / "app")
    from overlay_resolver import OverlayResolver
    from overlay_writer import OverlayWriter
    OVERLAY_AVAILABLE = True
except ImportError:
    OVERLAY_AVAILABLE = False
    OverlayResolver = None
    OverlayWriter = None

logger = structlog.get_logger("admin-overlay-api")
router = APIRouter(prefix="/v1/overlay", tags=["overlay"])


# Request/Response Models


class CreateControlRequest(BaseModel):
    """Request to create a tenant control."""

    control_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(..., min_length=1)
    framework: str = Field(..., description="e.g., NIST CSF, SOC2, ISO27001")


class CreateProductRequest(BaseModel):
    """Request to create a customer product."""

    product_name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    product_type: ProductType
    jurisdictions: list[str] = Field(..., min_length=1)


class CreateMappingRequest(BaseModel):
    """Request to map a control to a provision."""

    control_id: UUID
    provision_hash: str
    mapping_type: MappingType
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: Optional[str] = None


class LinkControlToProductRequest(BaseModel):
    """Request to link a control to a product."""

    control_id: UUID
    product_id: UUID


# Helper Functions


def get_tenant_id_from_api_key(api_key: APIKey) -> UUID:
    """Extract tenant_id from validated API key.

    Args:
        api_key: Validated API key

    Returns:
        Tenant UUID

    Raises:
        HTTPException: If API key has no tenant_id
    """
    if not api_key.tenant_id:
        logger.warning("api_key_missing_tenant_id", key_id=api_key.key_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API key is not associated with a tenant",
        )
    return UUID(api_key.tenant_id)


# Control Endpoints


@router.post("/controls", status_code=status.HTTP_201_CREATED)
async def create_control(
    request: CreateControlRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Create a new tenant control.

    Args:
        request: Control creation request
        api_key: Validated API key with tenant_id

    Returns:
        Created control data
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    control = TenantControl(
        tenant_id=tenant_id,
        control_id=request.control_id,
        title=request.title,
        description=request.description,
        framework=request.framework,
    )

    try:
        writer = OverlayWriter(tenant_id)
        created = writer.create_tenant_control(control)

        return {
            "id": str(created.id),
            "tenant_id": str(created.tenant_id),
            "control_id": created.control_id,
            "title": created.title,
            "description": created.description,
            "framework": created.framework,
            "created_at": created.created_at.isoformat(),
        }
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("control_creation_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create control: {str(exc)}",
        )


@router.get("/controls")
async def list_controls(
    framework: Optional[str] = None,
    api_key: APIKey = Depends(require_api_key),
):
    """List all tenant controls, optionally filtered by framework.

    Args:
        framework: Optional framework filter
        api_key: Validated API key with tenant_id

    Returns:
        List of controls
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        writer = OverlayWriter(tenant_id)
        controls = writer.list_controls(framework=framework)
        return {"controls": controls, "count": len(controls)}
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("list_controls_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list controls: {str(exc)}",
        )


@router.get("/controls/{control_id}")
async def get_control_details(
    control_id: UUID,
    api_key: APIKey = Depends(require_api_key),
):
    """Get detailed information about a control.

    Args:
        control_id: Control UUID
        api_key: Validated API key with tenant_id

    Returns:
        Control details with mappings and products
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        resolver = OverlayResolver(tenant_id)
        details = resolver.get_control_details(control_id)

        if "error" in details:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=details["error"])

        return details
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as exc:
        logger.exception("get_control_details_failed", control_id=str(control_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get control details: {str(exc)}",
        )


@router.put("/controls/{control_id}")
async def update_control(
    control_id: UUID,
    request: CreateControlRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Update an existing tenant control.

    Args:
        control_id: Control UUID to update
        request: Updated control data
        api_key: Validated API key with tenant_id

    Returns:
        Updated control data
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        writer = OverlayWriter(tenant_id)

        # Update control properties
        updated = writer.update_control(
            control_id=control_id,
            title=request.title,
            description=request.description,
            framework=request.framework,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Control {control_id} not found or not owned by tenant"
            )

        return {
            "id": str(control_id),
            "tenant_id": str(tenant_id),
            "title": request.title,
            "description": request.description,
            "framework": request.framework,
            "updated": True
        }
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("control_update_failed", control_id=str(control_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update control: {str(exc)}",
        )


@router.delete("/controls/{control_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_control(
    control_id: UUID,
    api_key: APIKey = Depends(require_api_key),
):
    """Delete a tenant control and all its mappings.

    Args:
        control_id: Control UUID to delete
        api_key: Validated API key with tenant_id

    Returns:
        No content on success
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        writer = OverlayWriter(tenant_id)
        deleted = writer.delete_control(control_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Control {control_id} not found or not owned by tenant"
            )

        logger.info("control_deleted", control_id=str(control_id), tenant_id=str(tenant_id))
        return None
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("control_deletion_failed", control_id=str(control_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete control: {str(exc)}",
        )


# Product Endpoints


@router.post("/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    request: CreateProductRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Create a new customer product.

    Args:
        request: Product creation request
        api_key: Validated API key with tenant_id

    Returns:
        Created product data
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    product = CustomerProduct(
        tenant_id=tenant_id,
        product_name=request.product_name,
        description=request.description,
        product_type=request.product_type,
        jurisdictions=request.jurisdictions,
    )

    try:
        writer = OverlayWriter(tenant_id)
        created = writer.create_customer_product(product)

        return {
            "id": str(created.id),
            "tenant_id": str(created.tenant_id),
            "product_name": created.product_name,
            "description": created.description,
            "product_type": created.product_type.value,
            "jurisdictions": created.jurisdictions,
            "created_at": created.created_at.isoformat(),
        }
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("product_creation_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create product: {str(exc)}",
        )


@router.get("/products")
async def list_products(
    product_type: Optional[str] = None,
    api_key: APIKey = Depends(require_api_key),
):
    """List all customer products, optionally filtered by type.

    Args:
        product_type: Optional product type filter
        api_key: Validated API key with tenant_id

    Returns:
        List of products
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        writer = OverlayWriter(tenant_id)
        products = writer.list_products(product_type=product_type)
        return {"products": products, "count": len(products)}
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("list_products_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list products: {str(exc)}",
        )


@router.get("/products/{product_id}/requirements")
async def get_product_requirements(
    product_id: UUID,
    api_key: APIKey = Depends(require_api_key),
):
    """Get all regulatory requirements for a customer product.

    This endpoint merges tenant controls with global regulatory provisions.

    Args:
        product_id: Product UUID
        api_key: Validated API key with tenant_id

    Returns:
        Product requirements with controls and provisions
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        resolver = OverlayResolver(tenant_id)
        requirements = resolver.get_regulatory_requirements(product_id)

        if "error" in requirements:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=requirements["error"])

        return requirements
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as exc:
        logger.exception("get_product_requirements_failed", product_id=str(product_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get product requirements: {str(exc)}",
        )


@router.get("/products/{product_id}/compliance-gaps")
async def get_compliance_gaps(
    product_id: UUID,
    jurisdiction: str,
    api_key: APIKey = Depends(require_api_key),
):
    """Identify regulatory provisions not yet mapped for a product.

    Args:
        product_id: Product UUID
        jurisdiction: Jurisdiction to check (e.g., "US", "EU")
        api_key: Validated API key with tenant_id

    Returns:
        Compliance gap analysis
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        resolver = OverlayResolver(tenant_id)
        gaps = resolver.get_compliance_gaps(product_id, jurisdiction)
        return gaps
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as exc:
        logger.exception(
            "get_compliance_gaps_failed",
            product_id=str(product_id),
            jurisdiction=jurisdiction,
            error=str(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get compliance gaps: {str(exc)}",
        )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    api_key: APIKey = Depends(require_api_key),
):
    """Delete a customer product and all its control links.

    Args:
        product_id: Product UUID to delete
        api_key: Validated API key with tenant_id

    Returns:
        No content on success
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        writer = OverlayWriter(tenant_id)
        deleted = writer.delete_product(product_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {product_id} not found or not owned by tenant"
            )

        logger.info("product_deleted", product_id=str(product_id), tenant_id=str(tenant_id))
        return None
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("product_deletion_failed", product_id=str(product_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete product: {str(exc)}",
        )


# Mapping Endpoints


@router.post("/mappings", status_code=status.HTTP_201_CREATED)
async def create_mapping(
    request: CreateMappingRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Map a tenant control to a regulatory provision.

    Args:
        request: Mapping creation request
        api_key: Validated API key with tenant_id

    Returns:
        Created mapping data
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    # Use API key owner as created_by (could be enhanced with user management)
    created_by = UUID(api_key.key_id.replace("rge_", "").replace("-", "")[:32].ljust(32, "0"))

    mapping = ControlMapping(
        tenant_id=tenant_id,
        control_id=request.control_id,
        provision_hash=request.provision_hash,
        mapping_type=request.mapping_type,
        confidence=request.confidence,
        notes=request.notes,
        created_by=created_by,
    )

    try:
        writer = OverlayWriter(tenant_id)
        created = writer.map_control_to_provision(mapping)

        return {
            "id": str(created.id),
            "tenant_id": str(created.tenant_id),
            "control_id": str(created.control_id),
            "provision_hash": created.provision_hash,
            "mapping_type": created.mapping_type.value,
            "confidence": created.confidence,
            "notes": created.notes,
            "created_at": created.created_at.isoformat(),
        }
    except ValueError as exc:
        logger.warning("mapping_creation_validation_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (AttributeError, TypeError, RuntimeError, OSError) as exc:
        logger.exception("mapping_creation_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create mapping: {str(exc)}",
        )


@router.post("/products/link-control", status_code=status.HTTP_201_CREATED)
async def link_control_to_product(
    request: LinkControlToProductRequest,
    api_key: APIKey = Depends(require_api_key),
):
    """Link a tenant control to a customer product.

    Args:
        request: Link creation request
        api_key: Validated API key with tenant_id

    Returns:
        Link confirmation
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    link = ProductControlLink(
        product_id=request.product_id,
        control_id=request.control_id,
        tenant_id=tenant_id,
    )

    try:
        writer = OverlayWriter(tenant_id)
        created = writer.link_control_to_product(link)

        return {
            "product_id": str(created.product_id),
            "control_id": str(created.control_id),
            "tenant_id": str(created.tenant_id),
            "created_at": created.created_at.isoformat(),
        }
    except ValueError as exc:
        logger.warning("link_creation_validation_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (AttributeError, TypeError, RuntimeError, OSError) as exc:
        logger.exception("link_creation_failed", tenant_id=str(tenant_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to link control to product: {str(exc)}",
        )


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mapping(
    mapping_id: UUID,
    api_key: APIKey = Depends(require_api_key),
):
    """Delete a control-to-provision mapping.

    Args:
        mapping_id: Mapping UUID to delete
        api_key: Validated API key with tenant_id

    Returns:
        No content on success
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        writer = OverlayWriter(tenant_id)
        deleted = writer.delete_mapping(mapping_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Mapping {mapping_id} not found or not owned by tenant"
            )

        logger.info("mapping_deleted", mapping_id=str(mapping_id), tenant_id=str(tenant_id))
        return None
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError) as exc:
        logger.exception("mapping_deletion_failed", mapping_id=str(mapping_id), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete mapping: {str(exc)}",
        )


# Provision Query Endpoints


@router.get("/provisions/{provision_hash}/overlays")
async def get_provision_overlays(
    provision_hash: str,
    api_key: APIKey = Depends(require_api_key),
):
    """Get a provision with tenant-specific control mappings.

    Args:
        provision_hash: Hash of the provision
        api_key: Validated API key with tenant_id

    Returns:
        Provision with tenant overlays
    """
    tenant_id = get_tenant_id_from_api_key(api_key)

    try:
        resolver = OverlayResolver(tenant_id)
        overlays = resolver.get_provision_with_overlays(provision_hash)

        if "error" in overlays:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=overlays["error"])

        return overlays
    except HTTPException:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError, OSError, KeyError) as exc:
        logger.exception("get_provision_overlays_failed", provision_hash=provision_hash, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provision overlays: {str(exc)}",
        )
