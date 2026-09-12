"""Tenant-slug helpers used by admin tenant creation."""

from __future__ import annotations

from shared.agent_org.slugs import slugify
from sqlalchemy import select
from sqlalchemy.orm import Session

from .sqlalchemy_models import TenantModel


def _slugify_tenant_name(name: str) -> str:
    """Turn an arbitrary tenant display name into a URL-safe slug.

    Returns ``"tenant"`` if the input produces an empty slug (e.g. the
    input was all non-alphanumeric characters). Callers that need a
    unique slug should pipe this through ``_ensure_unique_tenant_slug``.

    Thin wrapper over the shared ``slugify`` helper (also used by
    agent_org's pod/agent slugging) so this function's existing call
    sites and tests are untouched.
    """
    return slugify(name, fallback="tenant")


def _ensure_unique_tenant_slug(db: Session, tenant_name: str) -> str:
    """Return a slug guaranteed not to collide with an existing tenant.

    Appends ``-2``, ``-3``, ... to the base slug until a free one is
    found. Callers own the transaction — this function reads but never
    writes.
    """
    base_slug = _slugify_tenant_name(tenant_name)
    slug = base_slug
    suffix = 2
    while db.execute(select(TenantModel).where(TenantModel.slug == slug)).scalar_one_or_none():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    return slug
