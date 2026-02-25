"""
Product Catalog Router.

Manages the FTL product catalog for a tenant — products on the
Food Traceability List that require FSMA 204 traceability.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.webhook_router import _verify_api_key

logger = logging.getLogger("product-catalog")

router = APIRouter(prefix="/api/v1/products", tags=["Product Catalog"])


class Product(BaseModel):
    """A product in the FTL catalog."""
    id: str
    name: str
    category: str  # FTL category
    ftl_covered: bool = True
    sku: str = ""
    gtin: str = ""
    description: str = ""
    suppliers: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)
    cte_count: int = 0
    last_cte: str | None = None
    created_at: str = ""


class ProductCatalogResponse(BaseModel):
    """Product catalog response."""
    tenant_id: str
    total: int
    ftl_covered: int
    categories: list[str]
    products: list[Product]


class CreateProductRequest(BaseModel):
    """Request to add a product."""
    name: str
    category: str
    sku: str = ""
    gtin: str = ""
    description: str = ""
    suppliers: list[str] = Field(default_factory=list)
    facilities: list[str] = Field(default_factory=list)


FTL_CATEGORIES = [
    "Leafy Greens", "Herbs", "Fresh-Cut Fruits", "Fresh-Cut Vegetables",
    "Finfish", "Crustaceans", "Molluscan Shellfish", "Smoked Finfish",
    "Soft Cheeses", "Shell Eggs", "Nut Butters", "Ready-to-Eat Deli Salads",
    "Fresh Tomatoes", "Fresh Peppers", "Fresh Cucumbers", "Fresh Sprouts",
    "Tropical Tree Fruits", "Fresh Melons",
]


def _generate_sample_products(tenant_id: str) -> list[Product]:
    now = datetime.now(timezone.utc)
    return [
        Product(
            id=f"{tenant_id}-prod-001", name="Romaine Lettuce", category="Leafy Greens",
            ftl_covered=True, sku="ROM-001", gtin="00612345678901",
            description="Whole head romaine lettuce, California grown",
            suppliers=["Valley Fresh Farms"], facilities=["Salinas Packing Co."],
            cte_count=47, last_cte=now.isoformat(), created_at=now.isoformat(),
        ),
        Product(
            id=f"{tenant_id}-prod-002", name="Roma Tomatoes", category="Fresh Tomatoes",
            ftl_covered=True, sku="TOM-002", gtin="00612345678902",
            description="Vine-ripened Roma tomatoes",
            suppliers=["Valley Fresh Farms", "Sunrise Produce Co."], facilities=["Salinas Packing Co."],
            cte_count=32, last_cte=now.isoformat(), created_at=now.isoformat(),
        ),
        Product(
            id=f"{tenant_id}-prod-003", name="Atlantic Salmon Fillets", category="Finfish",
            ftl_covered=True, sku="SAL-003", gtin="00612345678903",
            description="Fresh Atlantic salmon fillets",
            suppliers=["Pacific Seafood Inc."], facilities=["Seattle Cold Storage"],
            cte_count=28, last_cte=now.isoformat(), created_at=now.isoformat(),
        ),
        Product(
            id=f"{tenant_id}-prod-004", name="English Cucumbers", category="Fresh Cucumbers",
            ftl_covered=True, sku="CUC-004", gtin="00612345678904",
            description="Greenhouse English cucumbers",
            suppliers=["Sunrise Produce Co."], facilities=["Portland Distribution"],
            cte_count=11, last_cte=now.isoformat(), created_at=now.isoformat(),
        ),
        Product(
            id=f"{tenant_id}-prod-005", name="Mixed Salad Greens", category="Leafy Greens",
            ftl_covered=True, sku="SAL-005", gtin="00612345678905",
            description="Spring mix salad blend",
            suppliers=["Green Valley Organics"], facilities=["Salinas Packing Co."],
            cte_count=5, last_cte=now.isoformat(), created_at=now.isoformat(),
        ),
    ]


_catalog_store: dict[str, list[Product]] = {}


@router.get(
    "/{tenant_id}",
    response_model=ProductCatalogResponse,
    summary="Get product catalog",
)
async def get_catalog(
    tenant_id: str,
    category: str | None = None,
    _: None = Depends(_verify_api_key),
) -> ProductCatalogResponse:
    """Get product catalog for a tenant."""
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)

    products = _catalog_store[tenant_id]
    if category:
        products = [p for p in products if p.category == category]

    categories = sorted(set(p.category for p in _catalog_store[tenant_id]))
    ftl_count = sum(1 for p in _catalog_store[tenant_id] if p.ftl_covered)

    return ProductCatalogResponse(
        tenant_id=tenant_id,
        total=len(products),
        ftl_covered=ftl_count,
        categories=categories,
        products=products,
    )


@router.post(
    "/{tenant_id}",
    summary="Add a product",
)
async def add_product(
    tenant_id: str,
    request: CreateProductRequest,
    _: None = Depends(_verify_api_key),
):
    """Add a product to the catalog."""
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)

    now = datetime.now(timezone.utc)
    is_ftl = request.category in FTL_CATEGORIES

    product = Product(
        id=f"{tenant_id}-prod-{len(_catalog_store[tenant_id]) + 1:03d}",
        name=request.name,
        category=request.category,
        ftl_covered=is_ftl,
        sku=request.sku,
        gtin=request.gtin,
        description=request.description,
        suppliers=request.suppliers,
        facilities=request.facilities,
        created_at=now.isoformat(),
    )

    _catalog_store[tenant_id].append(product)

    return {"created": True, "product": product.model_dump(), "ftl_covered": is_ftl}


@router.get(
    "/categories/ftl",
    summary="Get FTL categories",
)
async def get_ftl_categories():
    """Get all FTL product categories."""
    return {"categories": FTL_CATEGORIES, "total": len(FTL_CATEGORIES)}
