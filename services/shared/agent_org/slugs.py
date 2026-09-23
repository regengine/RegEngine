"""Shared name-to-slug helper for agent-org pods/agents (and tenant names).

Extracted from
``services/admin/app/tenant_slug_helpers.py::_slugify_tenant_name`` so
agent-org's pod/agent slugging and admin's tenant slugging share one
implementation instead of two copies of the same regex. This is a small
shared-code extraction, not new tenant-slug behavior — the regex and
lower/strip/hyphen-collapse semantics are unchanged; only the empty-input
fallback value is now caller-supplied instead of hardcoded to
``"tenant"``.
"""

from __future__ import annotations

import re

_NON_ALNUM_RUN = re.compile(r"[^a-z0-9]+")


def slugify(name: str, *, fallback: str) -> str:
    """Turn an arbitrary display name into a URL-safe, lowercase slug.

    Non-alphanumeric runs collapse to a single ``-``; leading/trailing
    ``-`` is stripped. Returns ``fallback`` if the input produces an empty
    slug (e.g. the input was all non-alphanumeric characters, or empty).
    """
    base = _NON_ALNUM_RUN.sub("-", (name or "").strip().lower()).strip("-")
    return base or fallback
