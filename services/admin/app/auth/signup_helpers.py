"""Tenant-slug helpers used by the self-serve signup flow.

Extracted from ``auth_routes.py`` (Phase 1 sub-split 3/N). Both helpers
are pure (no patched module-level dependencies), so they move cleanly
without needing to update test patches that target
``services.admin.app.auth_routes``.

``_cleanup_supabase_user`` stays in ``auth_routes.py`` for now —
``test_auth_hardening_wave2.py`` patches ``get_supabase`` via the
``auth_routes`` module namespace, and moving the function here would
break that patch. It will migrate when the signup handler itself
extracts.

``auth_routes.py`` re-exports both names so existing
``from services.admin.app.auth_routes import _slugify_tenant_name``
imports continue to resolve unchanged.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..sqlalchemy_models import TenantModel


def _slugify_tenant_name(name: str) -> str:
    """Turn an arbitrary tenant display name into a URL-safe slug.

    Returns ``"tenant"`` if the input produces an empty slug (e.g. the
    input was all non-alphanumeric characters). Callers that need a
    unique slug should pipe this through ``_ensure_unique_tenant_slug``.
    """
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return base or "tenant"


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
