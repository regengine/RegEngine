"""Tests for shared permission matching helpers."""

from shared.permissions import (
    can_invite_role,
    has_permission,
    permission_implies,
    role_rank,
)


def test_permission_implies_exact_and_separator_normalization() -> None:
    assert permission_implies("fda:export", "fda.export")
    assert permission_implies("exchange.write", "exchange:write")


def test_permission_implies_wildcards() -> None:
    assert permission_implies("*", "fda.export")
    assert permission_implies("fda.*", "fda.export")
    assert permission_implies("admin.*", "simulations.write")
    assert not permission_implies("admin", "simulations.write")


def test_has_permission_with_mixed_grants() -> None:
    grants = ["exchange.read", "simulations.*"]
    assert has_permission(grants, "simulations.export")
    assert not has_permission(grants, "exchange.write")


def test_role_rank_treats_super_admin_as_owner_tier() -> None:
    # permission_implies treats super_admin as every permission, so a
    # low-named role carrying it must rank as Owner-tier (100), or a
    # mid-rank holder could assign it and inherit those permissions.
    assert role_rank("viewer", ["super_admin"]) == 100
    assert role_rank("custom-thing", ["Super_Admin"]) == 100
    assert role_rank("viewer", ["users.manage_roles"]) == 20


def test_can_invite_role_denies_super_admin_target_to_mid_rank() -> None:
    assert not can_invite_role("Admin", ["users.manage_roles"], "viewer", ["super_admin"])
    assert can_invite_role("Owner", [], "viewer", ["super_admin"])


def test_grant_owner_hatch_invite_path_keeps_working() -> None:
    # Inviting a future Owner with the explicit hatch still works.
    assert can_invite_role("Admin", ["users.invite.grant_owner"], "Owner", ["*"])


def test_grant_owner_hatch_ignored_for_membership_rewrites() -> None:
    # Immediate membership rewrites must not honor the hatch: a non-Owner
    # holding users.invite.grant_owner cannot promote in place.
    assert not can_invite_role(
        "Admin",
        ["users.invite.grant_owner"],
        "Owner",
        ["*"],
        honor_grant_owner=False,
    )
    # Owner-tier callers are unaffected by the flag.
    assert can_invite_role("Owner", [], "Owner", ["*"], honor_grant_owner=False)
