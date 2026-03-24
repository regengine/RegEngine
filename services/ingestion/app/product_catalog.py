"""
Product Catalog Router.

Manages the FTL product catalog for a tenant — products on the
Food Traceability List that require FSMA 204 traceability.

Persists to Supabase `product_catalog` table when DATABASE_URL is set,
falls back to in-memory dict for local dev.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
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
    is_sample: bool = Field(
        default=False,
        description="True for auto-generated sample data. Replace with real product records.",
    )


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


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_db_session():
    """Get a DB session from shared module, or None."""
    try:
        from shared.database import SessionLocal
        return SessionLocal()
    except Exception:
        return None


def _row_to_product(row) -> Product:
    """Convert a DB row (dict or Row) to Product model."""
    r = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    return Product(
        id=str(r.get("id", "")),
        name=r.get("name", ""),
        category=r.get("category", ""),
        ftl_covered=bool(r.get("ftl_covered", True)),
        sku=r.get("sku", ""),
        gtin=r.get("gtin", ""),
        description=r.get("description", ""),
        suppliers=r.get("suppliers") or [],
        facilities=r.get("facilities") or [],
        cte_count=int(r.get("cte_count", 0)),
        last_cte=r.get("last_cte"),
        created_at=str(r.get("created_at", "")),
    )


def _fsma_row_to_product(row) -> Product:
    """Convert an fsma.products row to Product model."""
    r = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    return Product(
        id=str(r.get("id", "")),
        name=r.get("name", ""),
        category=r.get("ftl_category", "") or "",
        ftl_covered=bool(r.get("ftl_covered", False)),
        sku=r.get("sku", "") or "",
        gtin=r.get("gtin", "") or "",
        description=r.get("description", "") or "",
        suppliers=[],
        facilities=[],
        cte_count=0,
        last_cte=None,
        created_at=str(r.get("created_at", "")),
    )


def _db_get_catalog(tenant_id: str, category: str | None = None) -> list[Product] | None:
    """Fetch catalog from fsma.products table. Returns None if DB unavailable."""
    from sqlalchemy import text
    db = _get_db_session()
    if db is None:
        return None
    try:
        if category:
            rows = db.execute(
                text(
                    "SELECT id, name, description, gtin, sku, ftl_category, ftl_covered, "
                    "unit_of_measure, created_at "
                    "FROM fsma.products WHERE org_id = CAST(:tid AS uuid) AND ftl_category = :cat ORDER BY name"
                ),
                {"tid": tenant_id, "cat": category},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT id, name, description, gtin, sku, ftl_category, ftl_covered, "
                    "unit_of_measure, created_at "
                    "FROM fsma.products WHERE org_id = CAST(:tid AS uuid) ORDER BY name"
                ),
                {"tid": tenant_id},
            ).fetchall()
        return [_fsma_row_to_product(r) for r in rows]
    except Exception as e:
        logger.warning("db_catalog_read_failed: %s", e)
        return None
    finally:
        db.close()


def _db_add_product(tenant_id: str, product: Product) -> bool:
    """Insert a product into Supabase. Returns True on success."""
    from sqlalchemy import text
    db = _get_db_session()
    if db is None:
        return False
    try:
        db.execute(
            text("""
                INSERT INTO product_catalog
                    (tenant_id, name, category, ftl_covered, sku, gtin,
                     description, suppliers, facilities, cte_count, last_cte)
                VALUES
                    (:tid, :name, :cat, :ftl, :sku, :gtin,
                     :desc, :suppliers::jsonb, :facilities::jsonb, :cte, :last_cte)
                ON CONFLICT (tenant_id, gtin)
                    WHERE gtin != ''
                DO UPDATE SET
                    name = EXCLUDED.name,
                    category = EXCLUDED.category,
                    description = EXCLUDED.description,
                    suppliers = EXCLUDED.suppliers,
                    facilities = EXCLUDED.facilities,
                    updated_at = now()
            """),
            {
                "tid": tenant_id,
                "name": product.name,
                "cat": product.category,
                "ftl": product.ftl_covered,
                "sku": product.sku,
                "gtin": product.gtin,
                "desc": product.description,
                "suppliers": json.dumps(product.suppliers),
                "facilities": json.dumps(product.facilities),
                "cte": product.cte_count,
                "last_cte": product.last_cte,
            },
        )
        db.commit()
        return True
    except Exception as e:
        logger.warning("db_catalog_insert_failed: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


def _db_lookup_by_gtin(tenant_id: str, gtin: str) -> Product | None:
    """Look up a single product by GTIN from Supabase."""
    from sqlalchemy import text
    db = _get_db_session()
    if db is None:
        return None
    try:
        row = db.execute(
            text("SELECT * FROM product_catalog WHERE tenant_id = :tid AND gtin = :gtin LIMIT 1"),
            {"tid": tenant_id, "gtin": gtin},
        ).fetchone()
        return _row_to_product(row) if row else None
    except Exception as e:
        logger.warning("db_catalog_lookup_failed: %s", e)
        return None
    finally:
        db.close()


def learn_from_event(tenant_id: str, event: dict) -> None:
    """Auto-learn product from ingested CTE event. Upserts by GTIN."""
    gtin = (event.get("kdes") or {}).get("gtin") or event.get("gtin", "")
    if not gtin:
        return
    name = event.get("product_description", "")
    facility = event.get("location_name", "")
    now = datetime.now(timezone.utc).isoformat()

    from sqlalchemy import text
    db = _get_db_session()
    if db is None:
        # Fallback: update in-memory store
        _memory_learn(tenant_id, gtin, name, facility, now)
        return
    try:
        db.execute(
            text("""
                INSERT INTO product_catalog
                    (tenant_id, name, category, ftl_covered, gtin,
                     description, facilities, cte_count, last_cte)
                VALUES
                    (:tid, :name, '', true, :gtin,
                     :name, :facilities::jsonb, 1, :now)
                ON CONFLICT (tenant_id, gtin)
                    WHERE gtin != ''
                DO UPDATE SET
                    cte_count = product_catalog.cte_count + 1,
                    last_cte = EXCLUDED.last_cte,
                    facilities = (
                        SELECT jsonb_agg(DISTINCT v)
                        FROM jsonb_array_elements(
                            COALESCE(product_catalog.facilities, '[]'::jsonb) ||
                            EXCLUDED.facilities
                        ) AS v
                    ),
                    updated_at = now()
            """),
            {
                "tid": tenant_id,
                "name": name,
                "gtin": gtin,
                "facilities": json.dumps([facility] if facility else []),
                "now": now,
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("learn_from_event_db_failed: %s", e)
        db.rollback()
        _memory_learn(tenant_id, gtin, name, facility, now)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# In-memory fallback (dev / when DATABASE_URL is not set)
# ---------------------------------------------------------------------------

# TODO(V042): Replace with fsma.tenant_products table queries.
# Tables created in V042__tenant_feature_data_tables.sql — wire CRUD here.
_catalog_store: dict[str, list[Product]] = {}


def _generate_sample_products(tenant_id: str) -> list[Product]:
    now = datetime.now(timezone.utc)
    records = [
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
            suppliers=["Valley Fresh Farms", "Sunrise Produce Co."],
            facilities=["Salinas Packing Co."],
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
    for r in records:
        r.is_sample = True
    return records


def _memory_learn(tenant_id: str, gtin: str, name: str, facility: str, now: str):
    """In-memory fallback for learn_from_event."""
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)
    for p in _catalog_store[tenant_id]:
        if p.gtin == gtin:
            p.cte_count += 1
            p.last_cte = now
            if facility and facility not in p.facilities:
                p.facilities.append(facility)
            return
    _catalog_store[tenant_id].append(Product(
        id=f"{tenant_id}-learned-{gtin[-6:]}",
        name=name or f"Product {gtin}",
        category="", ftl_covered=True, gtin=gtin,
        description=name, facilities=[facility] if facility else [],
        cte_count=1, last_cte=now,
        created_at=now,
    ))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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
    """Get product catalog for a tenant. Uses Supabase, falls back to memory."""
    # Try Supabase first
    products = _db_get_catalog(tenant_id, category)
    if products is not None:
        all_products = _db_get_catalog(tenant_id) if category else products
        categories = sorted(set(p.category for p in (all_products or []) if p.category))
        ftl_count = sum(1 for p in (all_products or []) if p.ftl_covered)
        return ProductCatalogResponse(
            tenant_id=tenant_id,
            total=len(products),
            ftl_covered=ftl_count,
            categories=categories,
            products=products,
        )

    # Fallback: in-memory
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)
    mem_products = _catalog_store[tenant_id]
    if category:
        mem_products = [p for p in mem_products if p.category == category]
    categories = sorted(set(p.category for p in _catalog_store[tenant_id]))
    ftl_count = sum(1 for p in _catalog_store[tenant_id] if p.ftl_covered)
    return ProductCatalogResponse(
        tenant_id=tenant_id,
        total=len(mem_products),
        ftl_covered=ftl_count,
        categories=categories,
        products=mem_products,
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
    now = datetime.now(timezone.utc)
    is_ftl = request.category in FTL_CATEGORIES

    product = Product(
        id=f"{tenant_id}-prod-{now.timestamp():.0f}",
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

    # Try Supabase
    if _db_add_product(tenant_id, product):
        return {"created": True, "product": product.model_dump(), "ftl_covered": is_ftl}

    # Fallback: in-memory
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = _generate_sample_products(tenant_id)
    _catalog_store[tenant_id].append(product)
    return {"created": True, "product": product.model_dump(), "ftl_covered": is_ftl}


@router.get(
    "/{tenant_id}/lookup",
    summary="Look up product by GTIN",
)
async def lookup_by_gtin(
    tenant_id: str,
    gtin: str = Query(..., description="GTIN to look up"),
    _: None = Depends(_verify_api_key),
):
    """Look up a single product by GTIN for scanner auto-fill."""
    # Try Supabase
    product = _db_lookup_by_gtin(tenant_id, gtin)
    if product:
        return {"found": True, "product": product.model_dump()}

    # Fallback: in-memory
    if tenant_id in _catalog_store:
        for p in _catalog_store[tenant_id]:
            if p.gtin == gtin:
                return {"found": True, "product": p.model_dump()}
    return {"found": False, "product": None}


@router.get(
    "/categories/ftl",
    summary="Get FTL categories",
)
async def get_ftl_categories():
    """Get all FTL product categories."""
    return {"categories": FTL_CATEGORIES, "total": len(FTL_CATEGORIES)}
