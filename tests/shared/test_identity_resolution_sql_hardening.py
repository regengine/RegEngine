"""Regression tests for identity_resolution SQL hardening (#1191).

``IdentityResolutionService.find_potential_matches`` previously
assembled its WHERE clause with ``text(f\"...{type_filter}...\"")`` —
an f-string around a whitelisted literal. There was no active CVE
(the whitelist gated all substitutions) but the pattern is a
**footgun**: a future edit that inlines ``entity_type`` directly into
the f-string would promote a hardcoded query to an injection vector.

These tests lock in three invariants:

1. **Source-level**: the module contains no ``text(f"..."``) calls —
   all SQL strings are static.
2. **Behavioural**: the produced SQL statement doesn't embed the
   entity_type as a literal — it binds it as a parameter.
3. **Injection-attempt safety**: a pathological ``entity_type`` value
   (e.g. ``'lot'; DROP TABLE ...``) is rejected by the whitelist
   *before* reaching SQLAlchemy, so even a mis-used call can't
   produce a second statement.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.shared.identity_resolution import (
    VALID_ENTITY_TYPES,
    IdentityResolutionService,
)


TENANT = "tenant-1191"


# ── 1. Source-level invariants ─────────────────────────────────────────────


def test_service_module_has_no_fstring_sql():
    """#1191: `text(f"…")` is the footgun. The module must never build
    a SQL string with Python f-string interpolation, even for values
    that happen to be whitelisted today. Static strings only — every
    user value flows through SQLAlchemy bindparams."""
    src = (
        Path(__file__).resolve().parents[2]
        / "services"
        / "shared"
        / "identity_resolution"
        / "service.py"
    ).read_text()

    # Any occurrence of `text(f"` or `text(f'` is a regression.
    offending = re.findall(r"text\(\s*f['\"]", src)
    assert not offending, (
        f"#1191 regression: service.py contains {len(offending)} `text(f...)` "
        "call(s); convert them to parameterized binds."
    )


def test_find_potential_matches_uses_parameter_not_literal():
    """#1191: the concrete SQL generated for find_potential_matches
    must contain ``:entity_type`` as a bindparam (not the literal
    value inlined into the string)."""
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    svc = IdentityResolutionService(session)

    svc.find_potential_matches(TENANT, "test-name", entity_type="facility")

    # The first arg to execute() is a TextClause. Convert to str.
    call = session.execute.call_args
    sql_obj = call.args[0]
    sql_text = str(sql_obj)

    # Must contain the bindparam placeholder
    assert ":entity_type" in sql_text, (
        f"#1191: entity_type must be a bindparam, got SQL:\n{sql_text}"
    )
    # Must NOT contain the literal value inlined
    assert "'facility'" not in sql_text and '"facility"' not in sql_text, (
        f"#1191: entity_type literal was inlined into SQL:\n{sql_text}"
    )

    # Params dict must carry the value
    params = call.args[1]
    assert params["entity_type"] == "facility"
    assert params["tenant_id"] == TENANT


def test_find_potential_matches_sql_identical_for_none_and_facility():
    """Parameterized forms produce the SAME SQL text regardless of the
    entity_type value — only the bound params differ. If we still
    branched on `entity_type` to rewrite the SQL string, the two calls
    would produce different query text."""
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    svc = IdentityResolutionService(session)

    svc.find_potential_matches(TENANT, "test-a", entity_type=None)
    sql_none = str(session.execute.call_args.args[0])

    svc.find_potential_matches(TENANT, "test-b", entity_type="facility")
    sql_facility = str(session.execute.call_args.args[0])

    assert sql_none == sql_facility, (
        "#1191: SQL text must be static; different entity_type values "
        "must produce identical SQL (only bound params change)."
    )


# ── 2. Whitelist still blocks injection attempts ───────────────────────────


class TestEntityTypeWhitelistRejection:
    """The existing whitelist must keep rejecting hostile values."""

    @pytest.mark.parametrize(
        "hostile_value",
        [
            "'; DROP TABLE fsma.canonical_entities; --",
            "facility OR 1=1",
            "facility'; DELETE FROM fsma.entity_aliases WHERE 'a'='a",
            "facility UNION SELECT * FROM auth.users",
            # Unicode confusables
            "facilitу",  # Cyrillic 'у'
            # Case manipulation
            "FACILITY",  # uppercase — we store exact strings in VALID_ENTITY_TYPES
        ],
    )
    def test_hostile_entity_type_rejected_before_sql(self, hostile_value):
        """Even though SQL is now parameterized, the whitelist check
        runs first and should raise on anything not in VALID_ENTITY_TYPES."""
        if hostile_value in VALID_ENTITY_TYPES:
            pytest.skip(
                f"Test payload {hostile_value!r} accidentally matches the "
                "whitelist — adjust the test"
            )

        session = MagicMock()
        svc = IdentityResolutionService(session)

        with pytest.raises(ValueError, match="Invalid entity_type"):
            svc.find_potential_matches(
                TENANT, "search", entity_type=hostile_value
            )

        # Critical: execute() must NEVER have been called — the
        # whitelist raised before we hit the DB.
        session.execute.assert_not_called()

    def test_none_entity_type_allowed_no_raise(self):
        """None is the "no filter" sentinel and must still work."""
        session = MagicMock()
        session.execute.return_value.fetchall.return_value = []
        svc = IdentityResolutionService(session)

        svc.find_potential_matches(TENANT, "search", entity_type=None)

        # The SQL should have been executed with entity_type=None in params.
        assert session.execute.called
        params = session.execute.call_args.args[1]
        assert params["entity_type"] is None
        assert params["tenant_id"] == TENANT


# ── 3. Defense-in-depth: param binding stays consistent across calls ───────


def test_params_dict_always_contains_entity_type_key():
    """#1191: callers must always bind entity_type (either a valid
    whitelisted value or None). If the param was only conditionally
    added — as it was before the fix — then a future caller passing
    raw input could get it inlined into the SQL by mistake. Always-
    binding guarantees the value never touches the SQL string."""
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = []
    svc = IdentityResolutionService(session)

    for entity_type in (None, "facility", "lot", "product"):
        if entity_type is not None and entity_type not in VALID_ENTITY_TYPES:
            continue
        session.execute.reset_mock()
        svc.find_potential_matches(TENANT, "search", entity_type=entity_type)
        params = session.execute.call_args.args[1]
        assert "entity_type" in params, (
            f"entity_type kwarg missing from params dict for {entity_type!r}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
