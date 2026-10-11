"""QA5: permission-boundary edge cases for shared/permissions.py.

Covers bare-string permission inputs, the vacuous namespace permission,
and the documented scope of the invite escape hatch.
"""

from shared.permissions import can_invite_role, has_permission, permission_implies, role_rank


def test_bare_string_wildcard_does_not_bypass_invite_rank() -> None:
    # A single permission string instead of a list must still confer
    # Owner tier, so a low-tier caller cannot grant it.
    assert role_rank("guest", "*") == 100
    assert not can_invite_role("viewer", [], "custom", "*")


def test_bare_string_admin_wildcard_matches() -> None:
    assert role_rank("member", "admin.*") == 100
    assert has_permission("admin.*", "fda.export")


def test_namespace_wildcard_does_not_imply_vacuous_permission() -> None:
    assert not permission_implies("fda.*", "fda.")
    assert permission_implies("fda.*", "fda.export")


def test_grant_owner_escape_hatch_only_covers_owner_tier_targets() -> None:
    # The users.invite.grant_owner permission lets a non-Owner invite an
    # Owner-tier target, but it does not waive the basic no-escalation
    # rule for sub-Owner targets.
    assert can_invite_role("member", ["users.invite.grant_owner"], "owner", ["*"])
    assert not can_invite_role("member", ["users.invite.grant_owner"], "manager", [])
