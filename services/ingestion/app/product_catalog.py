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

from app.webhook_compat import _verify_api_key

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


def learn_from_event(
    tenant_id: str,
    product_description: str,
    gtin: str | None = None,
    kdes: dict | None = None,
) -> Product | None:
    """
    Auto-learn: upsert a product into the catalog from an ingested CTE event.

    If a product with the same GTIN already exists, update its CTE count and
    last_cte timestamp. Otherwise create a new entry. This makes the scanner
    smarter with every confirmed scan — second time you scan a GTIN it pre-fills
    everything instantly, zero AI cost.
    """
    if not product_description and not gtin:
        return None

    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)

    now = datetime.now(timezone.utc)
    catalog = _catalog_store[tenant_id]

    # Check if product already exists by GTIN
    if gtin:
        for product in catalog:
            if product.gtin == gtin:
                product.cte_count += 1
                product.last_cte = now.isoformat()
                # Enrich if we have new info
                if kdes:
                    if kdes.get("facility_name") and kdes["facility_name"] not in product.facilities:
                        product.facilities.append(kdes["facility_name"])
                logger.info("product_catalog_updated gtin=%s cte_count=%d", gtin, product.cte_count)
                return product

    # Check by exact name match
    for product in catalog:
        if product.name.lower() == product_description.lower():
            product.cte_count += 1
            product.last_cte = now.isoformat()
            if gtin and not product.gtin:
                product.gtin = gtin
            return product

    # Create new product
    new_product = Product(
        id=f"{tenant_id}-prod-{len(catalog) + 1:03d}",
        name=product_description,
        category="",  # Will be categorized later or manually
        ftl_covered=False,
        sku="",
        gtin=gtin or "",
        description=product_description,
        suppliers=[],
        facilities=[kdes["facility_name"]] if kdes and kdes.get("facility_name") else [],
        cte_count=1,
        last_cte=now.isoformat(),
        created_at=now.isoformat(),
    )
    catalog.append(new_product)
    logger.info("product_catalog_learned name=%s gtin=%s", product_description, gtin)
    return new_product


@router.get(
    "/{tenant_id}/lookup",
    summary="Lookup product by GTIN",
)
async def lookup_by_gtin(
    tenant_id: str,
    gtin: str,
    _: None = Depends(_verify_api_key),
):
    """Fast lookup for scanner auto-fill — returns product if GTIN known."""
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)

    for product in _catalog_store[tenant_id]:
        if product.gtin == gtin:
            return {"found": True, "product": product.model_dump()}

    return {"found": False, "product": None}


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
