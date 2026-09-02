"""`ROUTER_SURFACE.md` must not drift from the routers `server/main.py` knows — #2838.

`docs/engineering/ROUTER_SURFACE.md` publishes a copy-pasteable
``ENABLED_ROUTERS=`` string, and `ARCHITECTURE.md` points operators at it as
"the current surface audit". Because ``ENABLED_ROUTERS`` is allow-by-
configuration, **omission means disabled** — so a stale doc does not read as
stale. It produces a working-looking deployment with features silently missing.

That is what #2838 found: the published allowlist omitted `remediation` plus
both public proof routers, so an operator following the doc would have taken
down `regengine.co/proof` and `/verify` — endpoints the README advertises and
that third-party verifier tooling depends on.

Fixing the doc alone does not stop it recurring; a hand-maintained list in
Markdown drifts again the next time a router is added. This is the CI guard the
issue asked for, modelled on the existing `scripts/check_workflow_inventory.py`
pattern.

Three invariants, each catching a different direction of drift:

1. Every name in the doc's allowlist is a real router. A typo or a removed
   router here is worse than useless — `server/main.py` rejects unknown flags,
   so the documented string would fail the boot it is meant to configure.
2. No name in the allowlist is experimental. Experimental routers are
   auto-disabled in production; recommending one in a production config would
   be misleading.
3. **Every non-experimental router appears somewhere in the document.** This is
   the direction that actually broke — a router registered in code and absent
   from the audit. Membership in the *document* rather than the allowlist is
   deliberate: a production router may legitimately be discussed as
   disable-by-default without being in the recommended string, but it must not
   be invisible.

Parsing is done with ``ast``, not with grep over the source: the set literals
run to dozens of entries and a line-based scan silently mismatches when one is
reformatted.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_POLICY = _REPO_ROOT / "server" / "router_policy.py"
_DOC = _REPO_ROOT / "docs" / "engineering" / "ROUTER_SURFACE.md"

_ALLOWLIST_LINE = re.compile(r"^ENABLED_ROUTERS=(.+)$", re.MULTILINE)


def _collection_elts(node: ast.AST) -> list[ast.AST] | None:
    if isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        return list(node.elts)
    if isinstance(node, ast.Call) and node.args:
        inner = node.args[0]
        if isinstance(inner, (ast.Set, ast.List, ast.Tuple)):
            return list(inner.elts)
    return None


def _set_literal(module: ast.Module, name: str) -> set[str]:
    """Return the string members of a module-level ``name = frozenset({...})``."""
    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            continue
        elts = _collection_elts(node.value)
        if elts is None:
            pytest.fail(f"{name} in server/router_policy.py is no longer a literal collection")
        return {e.value for e in elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    pytest.fail(f"{name} not found in server/router_policy.py — has it been renamed? (#2838)")


@pytest.fixture(scope="module")
def policy_module() -> ast.Module:
    return ast.parse(_POLICY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def valid_routers(policy_module) -> set[str]:
    return _set_literal(policy_module, "VALID_ROUTER_NAMES")


@pytest.fixture(scope="module")
def experimental_routers(policy_module) -> set[str]:
    return _set_literal(policy_module, "EXPERIMENTAL_ROUTERS")


@pytest.fixture(scope="module")
def doc_text() -> str:
    return _DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def doc_allowlist(doc_text) -> set[str]:
    match = _ALLOWLIST_LINE.search(doc_text)
    assert match, (
        f"No 'ENABLED_ROUTERS=' line found in {_DOC.relative_to(_REPO_ROOT)}. That string "
        f"is what operators copy; without it the checks below verify nothing (#2838)."
    )
    return {name.strip() for name in match.group(1).split(",") if name.strip()}


class TestGuardIsNotVacuous:
    """Each check below iterates a parsed set. An empty one passes silently."""

    def test_router_sets_are_populated(self, valid_routers, experimental_routers):
        assert len(valid_routers) > 20, f"only {len(valid_routers)} valid routers parsed — parser drift?"
        assert experimental_routers, "no experimental routers parsed — parser drift?"
        assert experimental_routers < valid_routers, (
            "_EXPERIMENTAL_ROUTERS contains names absent from _VALID_ROUTER_NAMES: "
            f"{sorted(experimental_routers - valid_routers)}"
        )

    def test_doc_allowlist_is_populated(self, doc_allowlist):
        assert len(doc_allowlist) > 5, f"doc allowlist parsed as only {sorted(doc_allowlist)} — regex drift?"


class TestDocAllowlistIsApplicable:
    def test_every_documented_router_is_a_real_router(self, doc_allowlist, valid_routers):
        """A name here that main.py does not recognise fails the boot it configures."""
        unknown = sorted(doc_allowlist - valid_routers)
        assert not unknown, (
            f"ROUTER_SURFACE.md's ENABLED_ROUTERS names routers that are not in "
            f"_VALID_ROUTER_NAMES: {unknown}. server/main.py rejects unknown flags, so "
            f"copy-pasting the documented string would fail to boot (#2838)."
        )

    def test_no_experimental_router_is_recommended_for_production(self, doc_allowlist, experimental_routers):
        leaked = sorted(doc_allowlist & experimental_routers)
        assert not leaked, (
            f"ROUTER_SURFACE.md recommends experimental routers for production: {leaked}. "
            f"These are auto-disabled in production regardless, so the documented "
            f"configuration would not do what it says (#2838)."
        )


class TestNoProductionRouterIsUndocumented:
    """The direction #2838 actually broke."""

    def test_every_production_router_appears_in_the_audit(self, valid_routers, experimental_routers, doc_text):
        production = valid_routers - experimental_routers
        missing = sorted(r for r in production if r not in doc_text)
        assert not missing, (
            f"{len(missing)} non-experimental router(s) are registered in server/main.py but "
            f"appear nowhere in ROUTER_SURFACE.md: {missing}.\n"
            f"ENABLED_ROUTERS is allow-by-configuration, so a router missing from the audit "
            f"reads as 'disabled' to anyone applying it — which is how the public /proof and "
            f"/verify endpoints were nearly taken down (#2838). Add each to the relevant "
            f"section, and to the ENABLED_ROUTERS string if it belongs in production."
        )
