"""
Product Catalog Router.

Manages the FTL product catalog for a tenant — products on the
Food Traceability List that require FSMA 204 traceability.

Persists to `fsma.products` table when DATABASE_URL is set,
falls back to in-memory dict for local dev.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from shared.database import get_db_safe
from shared.pagination import PaginationParams
from shared.rate_limit import limiter
from shared.tenant_context import TenantContext
from sqlalchemy.exc import SQLAlchemyError

from .webhook_compat import require_tenant_context

logger = logging.getLogger("product-catalog")

# Rate limits for catalog mutations. Product catalog edits are low-frequency
# human actions (operators curating the FTL list), so a modest per-client
# budget is ample while still blocking scripted abuse. GET routes are left
# unthrottled here.
#
# The production default is always ``30/minute``. An elevated budget is used
# only when ``REGENGINE_E2E_RELAX_PRODUCT_MUTATION_LIMIT`` is explicitly set
# (the Passwordless Auth E2E job seeds 55 products in one minute). Never arm
# this from ``REGENGINE_E2E_MODE`` alone — production defaults must not change
# unless that dedicated env var is set.
_DEFAULT_PRODUCT_MUTATION_RATE_LIMIT = "30/minute"
_E2E_RELAXED_PRODUCT_MUTATION_RATE_LIMIT = "10000/minute"
_E2E_RELAX_PRODUCT_MUTATION_LIMIT_ENV = "REGENGINE_E2E_RELAX_PRODUCT_MUTATION_LIMIT"
_E2E_RELAX_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def resolve_product_mutation_rate_limit(
    environ: dict[str, str] | None = None,
) -> str:
    """Return the product-mutation rate-limit string.

    Unset / empty env → production default ``30/minute``. Truthy
    ``REGENGINE_E2E_RELAX_PRODUCT_MUTATION_LIMIT`` → elevated E2E budget.
    """
    env = os.environ if environ is None else environ
    raw = str(env.get(_E2E_RELAX_PRODUCT_MUTATION_LIMIT_ENV, "")).strip().lower()
    if raw in _E2E_RELAX_TRUE_VALUES:
        return _E2E_RELAXED_PRODUCT_MUTATION_RATE_LIMIT
    return _DEFAULT_PRODUCT_MUTATION_RATE_LIMIT


# slowapi accepts a callable that returns the limit string per request.
_ADD_PRODUCT_RATE_LIMIT = resolve_product_mutation_rate_limit
_UPDATE_PRODUCT_RATE_LIMIT = resolve_product_mutation_rate_limit
_DELETE_PRODUCT_RATE_LIMIT = resolve_product_mutation_rate_limit

# Bounded list-item type reused by request models.
_CatalogListItem = Annotated[str, StringConstraints(max_length=200)]

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

    # extra="forbid": the only callers (frontend products page and mobile
    # field-capture) send exactly these keys, so unknown fields are a client
    # bug or probe and should 422 rather than be silently dropped.
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    sku: str = Field(default="", max_length=100)
    gtin: str = Field(default="", max_length=14)
    description: str = Field(default="", max_length=2000)
    suppliers: list[_CatalogListItem] = Field(default_factory=list, max_length=100)
    facilities: list[_CatalogListItem] = Field(default_factory=list, max_length=100)


class UpdateProductRequest(BaseModel):
    """Request to update a product."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=100)
    sku: str = Field(default="", max_length=100)
    gtin: str = Field(default="", max_length=14)
    description: str = Field(default="", max_length=2000)
    suppliers: list[_CatalogListItem] = Field(default_factory=list, max_length=100)
    facilities: list[_CatalogListItem] = Field(default_factory=list, max_length=100)


FTL_CATEGORIES = [
    "Leafy Greens",
    "Herbs",
    "Fresh-Cut Fruits",
    "Fresh-Cut Vegetables",
    "Finfish",
    "Crustaceans",
    "Molluscan Shellfish",
    "Smoked Finfish",
    "Soft Cheeses",
    "Shell Eggs",
    "Nut Butters",
    "Ready-to-Eat Deli Salads",
    "Fresh Tomatoes",
    "Fresh Peppers",
    "Fresh Cucumbers",
    "Fresh Sprouts",
    "Tropical Tree Fruits",
    "Fresh Melons",
]


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


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


def _derive_products_from_events(db, tenant_id: str, category: str | None = None) -> list[Product]:
    """Derive product list from canonical fsma.traceability_events table.

    Used as a fallback when fsma.products is empty for a tenant — the
    canonical events store still has product_reference / lot data we can
    surface so the catalog is not blank.
    """
    from sqlalchemy import text

    try:
        rows = db.execute(
            text(
                "SELECT product_reference, "
                "       COUNT(*) AS cte_count, "
                "       MAX(event_timestamp) AS last_cte, "
                "       MIN(event_timestamp) AS first_seen, "
                "       array_agg(DISTINCT traceability_lot_code) "
                "           FILTER (WHERE traceability_lot_code IS NOT NULL) AS lot_codes "
                "FROM fsma.traceability_events "
                "WHERE tenant_id = CAST(:tid AS uuid) "
                "  AND product_reference IS NOT NULL "
                "  AND product_reference != '' "
                "GROUP BY product_reference "
                "ORDER BY product_reference"
            ),
            {"tid": tenant_id},
        ).fetchall()
    except SQLAlchemyError as e:
        logger.warning("derive_products_from_events_failed: %s", e)
        return []

    products: list[Product] = []
    for row in rows:
        r = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
        ref = r.get("product_reference", "")
        p = Product(
            id=f"{tenant_id}-ev-{abs(hash(ref)) % 10**8:08d}",
            name=ref,
            category="",  # not available from events
            ftl_covered=True,
            description=f"Derived from {r.get('cte_count', 0)} traceability events",
            cte_count=int(r.get("cte_count", 0)),
            last_cte=str(r["last_cte"]) if r.get("last_cte") else None,
            created_at=str(r["first_seen"]) if r.get("first_seen") else "",
        )
        products.append(p)

    # If a category filter was requested but events have no category, return
    # all derived products only when no filter, or empty when filtered (we
    # cannot match categories we don't have).
    if category:
        return []
    return products


def _db_get_catalog(tenant_id: str, category: str | None = None) -> list[Product] | None:
    """Fetch catalog from fsma.products table. Returns None if DB unavailable.

    Falls back to deriving products from fsma.traceability_events when the
    products table is empty for this tenant.
    """
    from sqlalchemy import text

    db = get_db_safe()
    if db is None:
        return None
    try:
        if category:
            rows = db.execute(
                text(
                    "SELECT id, name, description, gtin, sku, ftl_category, ftl_covered, "
                    "unit_of_measure, created_at "
                    "FROM fsma.products WHERE tenant_id = CAST(:tid AS uuid) AND ftl_category = :cat ORDER BY name"
                ),
                {"tid": tenant_id, "cat": category},
            ).fetchall()
        else:
            rows = db.execute(
                text(
                    "SELECT id, name, description, gtin, sku, ftl_category, ftl_covered, "
                    "unit_of_measure, created_at "
                    "FROM fsma.products WHERE tenant_id = CAST(:tid AS uuid) ORDER BY name"
                ),
                {"tid": tenant_id},
            ).fetchall()
        products = [_fsma_row_to_product(r) for r in rows]

        # Fallback: if dedicated products table is empty, derive from
        # canonical traceability_events so the catalog is not blank.
        if not products:
            logger.info("products_table_empty tenant=%s, deriving from traceability_events", tenant_id)
            products = _derive_products_from_events(db, tenant_id, category)

        return products
    except SQLAlchemyError as e:
        logger.warning("db_catalog_read_failed: %s", e)
        return None
    finally:
        db.close()


def _db_add_product(tenant_id: str, product: Product) -> bool:
    """Insert a product into fsma.products. Returns True on success."""
    from sqlalchemy import text

    db = get_db_safe()
    if db is None:
        return False
    try:
        db.execute(
            text("""
                INSERT INTO fsma.products
                    (id, tenant_id, org_id, name, ftl_category, ftl_covered, sku, gtin,
                     description, unit_of_measure)
                VALUES
                    (CAST(:id AS uuid), CAST(:tid AS uuid), CAST(:tid AS uuid), :name, :cat, :ftl, :sku, :gtin,
                     :desc, :uom)
                ON CONFLICT (tenant_id, gtin) WHERE gtin IS NOT NULL AND gtin != ''
                DO UPDATE SET
                    name = EXCLUDED.name,
                    ftl_category = EXCLUDED.ftl_category,
                    description = EXCLUDED.description,
                    updated_at = now()
            """),
            {
                "id": product.id,
                "tid": tenant_id,
                "name": product.name,
                "cat": product.category,
                "ftl": product.ftl_covered,
                "sku": product.sku,
                "gtin": product.gtin,
                "desc": product.description,
                "uom": "",
            },
        )
        db.commit()
        return True
    except SQLAlchemyError as e:
        logger.warning("db_catalog_insert_failed: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


def _db_get_product(tenant_id: str, product_id: str) -> Product | None:
    """Fetch a single product from fsma.products."""
    from sqlalchemy import text

    db = get_db_safe()
    if db is None:
        return None
    try:
        row = db.execute(
            text(
                "SELECT id, name, description, gtin, sku, ftl_category, ftl_covered, "
                "unit_of_measure, created_at "
                "FROM fsma.products WHERE tenant_id = CAST(:tid AS uuid) AND id = CAST(:id AS uuid) LIMIT 1"
            ),
            {"tid": tenant_id, "id": product_id},
        ).fetchone()
        return _fsma_row_to_product(row) if row else None
    except SQLAlchemyError as e:
        logger.warning("db_catalog_product_read_failed: %s", e)
        return None
    finally:
        db.close()


def _db_update_product(tenant_id: str, product_id: str, product: Product) -> Product | None:
    """Update a product in fsma.products."""
    from sqlalchemy import text

    db = get_db_safe()
    if db is None:
        return None
    try:
        row = db.execute(
            text("""
                UPDATE fsma.products
                SET name = :name,
                    ftl_category = :cat,
                    ftl_covered = :ftl,
                    sku = :sku,
                    gtin = :gtin,
                    description = :desc,
                    updated_at = now()
                WHERE tenant_id = CAST(:tid AS uuid)
                  AND id = CAST(:id AS uuid)
                RETURNING id, name, description, gtin, sku, ftl_category, ftl_covered,
                          unit_of_measure, created_at
            """),
            {
                "tid": tenant_id,
                "id": product_id,
                "name": product.name,
                "cat": product.category,
                "ftl": product.ftl_covered,
                "sku": product.sku,
                "gtin": product.gtin,
                "desc": product.description,
            },
        ).fetchone()
        db.commit()
        return _fsma_row_to_product(row) if row else None
    except SQLAlchemyError as e:
        logger.warning("db_catalog_product_update_failed: %s", e)
        db.rollback()
        return None
    finally:
        db.close()


def _db_delete_product(tenant_id: str, product_id: str) -> bool:
    """Delete a product from fsma.products."""
    from sqlalchemy import text

    db = get_db_safe()
    if db is None:
        return False
    try:
        result = db.execute(
            text("DELETE FROM fsma.products WHERE tenant_id = CAST(:tid AS uuid) AND id = CAST(:id AS uuid)"),
            {"tid": tenant_id, "id": product_id},
        )
        db.commit()
        return bool(result.rowcount)
    except SQLAlchemyError as e:
        logger.warning("db_catalog_product_delete_failed: %s", e)
        db.rollback()
        return False
    finally:
        db.close()


def _db_lookup_by_gtin(tenant_id: str, gtin: str) -> Product | None:
    """Look up a single product by GTIN from Supabase."""
    from sqlalchemy import text

    db = get_db_safe()
    if db is None:
        return None
    try:
        row = db.execute(
            text(
                "SELECT id, name, description, gtin, sku, ftl_category, ftl_covered, "
                "unit_of_measure, created_at "
                "FROM fsma.products WHERE tenant_id = CAST(:tid AS uuid) AND gtin = :gtin LIMIT 1"
            ),
            {"tid": tenant_id, "gtin": gtin},
        ).fetchone()
        return _fsma_row_to_product(row) if row else None
    except SQLAlchemyError as e:
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

    db = get_db_safe()
    if db is None:
        # Fallback: update in-memory store
        _memory_learn(tenant_id, gtin, name, facility, now)
        return
    try:
        db.execute(
            text("""
                INSERT INTO fsma.products
                    (tenant_id, org_id, name, description, gtin, ftl_covered, ftl_category)
                VALUES
                    (CAST(:tid AS uuid), CAST(:tid AS uuid), :name, :name, :gtin, true, '')
                ON CONFLICT (tenant_id, gtin) WHERE gtin IS NOT NULL AND gtin != ''
                DO UPDATE SET
                    name = COALESCE(NULLIF(EXCLUDED.name, ''), fsma.products.name),
                    updated_at = now()
            """),
            {
                "tid": tenant_id,
                "name": name,
                "gtin": gtin,
            },
        )
        db.commit()
    except SQLAlchemyError as e:
        logger.warning("learn_from_event_db_failed: %s", e)
        db.rollback()
        _memory_learn(tenant_id, gtin, name, facility, now)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# In-memory fallback (dev / when DATABASE_URL is not set)
# ---------------------------------------------------------------------------

# NOTE(V042): fsma.products is the primary store; when empty for a tenant,
# _db_get_catalog falls back to deriving products from fsma.traceability_events.
# Full CRUD for fsma.tenant_products can be wired here when needed.
_catalog_store: dict[str, list[Product]] = {}


def _memory_get_product(tenant_id: str, product_id: str) -> Product | None:
    for product in _catalog_store.get(tenant_id, []):
        if product.id == product_id:
            return product
    return None


def _memory_update_product(tenant_id: str, product_id: str, product: Product) -> Product | None:
    products = _catalog_store.get(tenant_id, [])
    for index, existing in enumerate(products):
        if existing.id == product_id:
            product.created_at = existing.created_at
            product.cte_count = existing.cte_count
            product.last_cte = existing.last_cte
            products[index] = product
            return product
    return None


def _memory_delete_product(tenant_id: str, product_id: str) -> bool:
    products = _catalog_store.get(tenant_id, [])
    before = len(products)
    _catalog_store[tenant_id] = [product for product in products if product.id != product_id]
    return len(_catalog_store[tenant_id]) != before


def _memory_learn(tenant_id: str, gtin: str, name: str, facility: str, now: str):
    """In-memory fallback for learn_from_event."""
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = []
    for p in _catalog_store[tenant_id]:
        if p.gtin == gtin:
            p.cte_count += 1
            p.last_cte = now
            if facility and facility not in p.facilities:
                p.facilities.append(facility)
            return
    _catalog_store[tenant_id].append(
        Product(
            id=f"{tenant_id}-learned-{gtin[-6:]}",
            name=name or f"Product {gtin}",
            category="",
            ftl_covered=True,
            gtin=gtin,
            description=name,
            facilities=[facility] if facility else [],
            cte_count=1,
            last_cte=now,
            created_at=now,
        )
    )


# ---------------------------------------------------------------------------
# Audit (best-effort, never blocks the request path)
# ---------------------------------------------------------------------------


def _audit_task_done(task) -> None:
    """Fail loud, not silent: a detached audit write that raised must log."""
    import asyncio

    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("product_catalog_audit_write_failed error=%s", exc)


def _audit_product_mutation(
    *,
    ctx: TenantContext,
    event_type_name: str,
    action: str,
    tenant_id: str,
    product_id: str,
    changed_fields: list[str],
) -> None:
    """Fire-and-forget audit log for a successful catalog mutation.

    Best-effort by design: a successful mutation never fails because the
    audit write could not be scheduled. The write is scheduled on the
    running loop and a failed write is logged via a done callback; it
    never raises into the request path.

    ``changed_fields`` carries field NAMES only — never field values — so no
    secret material or PII ends up in the audit details.
    """
    try:
        import asyncio

        from shared.audit_logging import (
            AuditActor,
            AuditEventCategory,
            AuditEventType,
            AuditLogger,
            AuditResource,
            AuditSeverity,
        )

        event_type = getattr(AuditEventType, event_type_name)
        audit = AuditLogger.get_instance()
        actor = AuditActor(
            actor_id=ctx.principal_id,
            actor_type=ctx.principal_kind,
            email=ctx.actor_email,
            tenant_id=tenant_id,
        )
        resource = AuditResource(
            resource_type="product",
            resource_id=product_id,
            tenant_id=tenant_id,
        )
        coro = audit.log(
            event_type=event_type,
            category=AuditEventCategory.DATA_MODIFICATION,
            severity=AuditSeverity.INFO,
            actor=actor,
            action=action,
            outcome="success",
            resource=resource,
            message=f"product catalog {action}",
            details={"tenant_id": tenant_id, "changed_fields": changed_fields},
            tags=["product", "catalog"],
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro).add_done_callback(_audit_task_done)
        except RuntimeError:
            # No running loop (e.g. sync context) — skip async audit.
            try:
                coro.close()
            except Exception:
                pass
    except Exception:  # pragma: no cover - defensive
        logger.debug("audit_product_mutation: could not emit audit event", exc_info=True)


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
    pagination: PaginationParams = Depends(),
    ctx: TenantContext = Depends(require_tenant_context),
) -> ProductCatalogResponse:
    """Get product catalog for a tenant. Uses Supabase, falls back to memory."""
    tenant_id = ctx.tenant_id
    # Try Supabase first
    products = _db_get_catalog(tenant_id, category)
    if products is not None:
        all_products = _db_get_catalog(tenant_id) if category else products
        categories = sorted(set(p.category for p in (all_products or []) if p.category))
        ftl_count = sum(1 for p in (all_products or []) if p.ftl_covered)
        total = len(products)
        products = products[pagination.skip : pagination.skip + pagination.limit]
        return ProductCatalogResponse(
            tenant_id=tenant_id,
            total=total,
            ftl_covered=ftl_count,
            categories=categories,
            products=products,
        )

    # Fallback: in-memory
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = []
    mem_products = _catalog_store[tenant_id]
    if category:
        mem_products = [p for p in mem_products if p.category == category]
    categories = sorted(set(p.category for p in _catalog_store[tenant_id]))
    ftl_count = sum(1 for p in _catalog_store[tenant_id] if p.ftl_covered)
    total = len(mem_products)
    mem_products = mem_products[pagination.skip : pagination.skip + pagination.limit]
    return ProductCatalogResponse(
        tenant_id=tenant_id,
        total=total,
        ftl_covered=ftl_count,
        categories=categories,
        products=mem_products,
    )


@router.post(
    "/{tenant_id}",
    summary="Add a product",
)
@limiter.limit(_ADD_PRODUCT_RATE_LIMIT)
async def add_product(
    request: Request,
    tenant_id: str,
    payload: CreateProductRequest,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Add a product to the catalog."""
    # The authenticated tenant is authoritative: the write lands under
    # ctx.tenant_id, never the client-supplied path tenant id.
    tenant_id = ctx.tenant_id
    now = datetime.now(timezone.utc)
    is_ftl = payload.category in FTL_CATEGORIES

    product = Product(
        id=str(uuid.uuid4()),
        name=payload.name,
        category=payload.category,
        ftl_covered=is_ftl,
        sku=payload.sku,
        gtin=payload.gtin,
        description=payload.description,
        suppliers=payload.suppliers,
        facilities=payload.facilities,
        created_at=now.isoformat(),
    )

    created_fields = ["name", "category", "sku", "gtin", "description", "suppliers", "facilities"]

    # Try Supabase
    if _db_add_product(tenant_id, product):
        _audit_product_mutation(
            ctx=ctx,
            event_type_name="DATA_CREATE",
            action="product_create",
            tenant_id=tenant_id,
            product_id=product.id,
            changed_fields=created_fields,
        )
        return {"created": True, "product": product.model_dump(), "ftl_covered": is_ftl}

    # Fallback: in-memory
    if tenant_id not in _catalog_store:
        _catalog_store[tenant_id] = []
    _catalog_store[tenant_id].append(product)
    _audit_product_mutation(
        ctx=ctx,
        event_type_name="DATA_CREATE",
        action="product_create",
        tenant_id=tenant_id,
        product_id=product.id,
        changed_fields=created_fields,
    )
    return {"created": True, "product": product.model_dump(), "ftl_covered": is_ftl}


@router.get(
    "/{tenant_id}/lookup",
    summary="Look up product by GTIN",
)
async def lookup_by_gtin(
    tenant_id: str,
    gtin: str = Query(..., description="GTIN to look up"),
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Look up a single product by GTIN for scanner auto-fill."""
    tenant_id = ctx.tenant_id
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


@router.get(
    "/{tenant_id}/{product_id}",
    summary="Get product",
)
async def get_product(
    tenant_id: str,
    product_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Get one product from the catalog."""
    tenant_id = ctx.tenant_id
    product = _db_get_product(tenant_id, product_id) or _memory_get_product(tenant_id, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"product": product.model_dump()}


@router.put(
    "/{tenant_id}/{product_id}",
    summary="Update product",
)
@limiter.limit(_UPDATE_PRODUCT_RATE_LIMIT)
async def update_product(
    request: Request,
    tenant_id: str,
    product_id: str,
    payload: UpdateProductRequest,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Update one product in the catalog."""
    tenant_id = ctx.tenant_id
    now = datetime.now(timezone.utc)
    is_ftl = payload.category in FTL_CATEGORIES
    existing = _db_get_product(tenant_id, product_id) or _memory_get_product(tenant_id, product_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Product not found")

    product = Product(
        id=product_id,
        name=payload.name,
        category=payload.category,
        ftl_covered=is_ftl,
        sku=payload.sku,
        gtin=payload.gtin,
        description=payload.description,
        suppliers=payload.suppliers,
        facilities=payload.facilities,
        cte_count=existing.cte_count,
        last_cte=existing.last_cte,
        created_at=existing.created_at or now.isoformat(),
    )

    updated = _db_update_product(tenant_id, product_id, product) or _memory_update_product(
        tenant_id, product_id, product
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")
    _audit_product_mutation(
        ctx=ctx,
        event_type_name="DATA_UPDATE",
        action="product_update",
        tenant_id=tenant_id,
        product_id=product_id,
        changed_fields=["name", "category", "sku", "gtin", "description", "suppliers", "facilities"],
    )
    return {"updated": True, "product": updated.model_dump(), "ftl_covered": is_ftl}


@router.delete(
    "/{tenant_id}/{product_id}",
    status_code=204,
    summary="Delete product",
)
@limiter.limit(_DELETE_PRODUCT_RATE_LIMIT)
async def delete_product(
    request: Request,
    tenant_id: str,
    product_id: str,
    ctx: TenantContext = Depends(require_tenant_context),
):
    """Delete one product from the catalog."""
    tenant_id = ctx.tenant_id
    if _db_delete_product(tenant_id, product_id) or _memory_delete_product(tenant_id, product_id):
        _audit_product_mutation(
            ctx=ctx,
            event_type_name="DATA_DELETE",
            action="product_delete",
            tenant_id=tenant_id,
            product_id=product_id,
            changed_fields=[],
        )
        return Response(status_code=204)
    raise HTTPException(status_code=404, detail="Product not found")
