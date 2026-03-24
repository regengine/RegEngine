"""Shared permission matching helpers.

Supports both dot and colon separators (e.g. ``fda.export`` and
``fda:export``), full wildcard (``*``), and namespace wildcard
(``fda.*`` / ``fda:*``).
"""

from __future__ import annotations

from typing import Iterable


def _normalize(permission: str) -> str:
    return permission.strip().lower().replace(":", ".")


def permission_implies(granted_permission: str, required_permission: str) -> bool:
    """Return True when a granted permission covers the required permission."""
    granted = _normalize(granted_permission)
    required = _normalize(required_permission)

    if not granted or not required:
        return False

    if granted in {"*", "admin.*", "super_admin"}:
        return True

    if granted == required:
        return True

    if granted.endswith(".*"):
        namespace = granted[:-2]
        return required.startswith(f"{namespace}.")

    return False


def has_permission(granted_permissions: Iterable[str], required_permission: str) -> bool:
    """Check whether any granted permission satisfies a required permission."""
    for granted in granted_permissions:
        if permission_implies(granted, required_permission):
            return True
    return False
