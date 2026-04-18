"""Shared permission matching helpers.

Supports both dot and colon separators (e.g. ``fda.export`` and
``fda:export``), full wildcard (``*``), and namespace wildcard
(``fda.*`` / ``fda:*``).

Also defines a coarse role-rank hierarchy used by invite flows (#1387) to
prevent privilege escalation via invite role assignment: an Admin cannot
issue an invite that confers an Owner role.
"""

from __future__ import annotations

from typing import Iterable, Optional


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


# --- Role hierarchy (#1387) -------------------------------------------------
#
# Numerically higher = more privileged. Unknown roles default to the lowest
# rank so an unrecognized tenant-custom role can never out-rank an Owner.
#
# When new role names are added, extend this table. Matching is
# case-insensitive.
_ROLE_RANK_BY_NAME: dict[str, int] = {
    "owner": 100,
    "admin": 80,
    "manager": 60,
    "compliance_manager": 60,
    "editor": 40,
    "member": 30,
    "viewer": 20,
    "guest": 10,
}

# Any role whose permissions array contains "*" or "admin.*" is treated as
# Owner-tier regardless of its name — that's the de-facto privilege level.
_OWNER_TIER_PERMISSIONS = {"*", "admin.*"}


def role_rank(role_name: Optional[str], permissions: Optional[Iterable[str]] = None) -> int:
    """Return a numeric privilege tier for a role.

    The rank is derived from two signals:
      * The role name (case-insensitive), mapped via :data:`_ROLE_RANK_BY_NAME`.
      * Whether the role's permissions grant wildcard/root access.

    The higher of the two is returned. Unknown names without wildcards fall
    back to ``0`` — the lowest possible tier.
    """
    name = (role_name or "").strip().lower()
    name_rank = _ROLE_RANK_BY_NAME.get(name, 0)
    perm_rank = 0
    if permissions:
        for p in permissions:
            if _normalize(p) in _OWNER_TIER_PERMISSIONS:
                perm_rank = max(perm_rank, _ROLE_RANK_BY_NAME["owner"])
                break
    return max(name_rank, perm_rank)


def can_invite_role(
    caller_role_name: Optional[str],
    caller_permissions: Optional[Iterable[str]],
    target_role_name: Optional[str],
    target_permissions: Optional[Iterable[str]],
) -> bool:
    """Return True iff the caller may issue an invite that confers ``target``.

    #1387 — an inviter may only issue invites at or below their own tier.
    Owner-tier targets additionally require the explicit
    ``users.invite.grant_owner`` permission (or Owner rank). The explicit
    permission acts as an escape hatch for both the Owner-tier check AND
    the basic tier check.
    """
    # Materialize perm iterables once — has_permission consumes them.
    caller_perm_list = list(caller_permissions or [])
    target_perm_list = list(target_permissions or [])

    caller_rank = role_rank(caller_role_name, caller_perm_list)
    target_rank = role_rank(target_role_name, target_perm_list)
    owner_rank = _ROLE_RANK_BY_NAME["owner"]

    # Explicit escalation permission bypasses the rank check but only for
    # Owner-tier targets (that's the whole point — granting the precise
    # superset you could not otherwise assign).
    has_grant_owner = has_permission(caller_perm_list, "users.invite.grant_owner")

    if target_rank >= owner_rank:
        # Owner-tier target. Allowed iff caller is Owner-tier or holds
        # users.invite.grant_owner explicitly.
        if caller_rank >= owner_rank:
            return True
        return has_grant_owner

    # Sub-Owner target — standard "no escalation" rule.
    return target_rank <= caller_rank
