"""Drift test for the rules-enforcement call-site manifest.

The limitations note in the project README says rule failures are not
universally blocking — enforcement is per-route opt-in. The manifest
``ENFORCEMENT_AWARE_CALL_SITES`` in ``services/shared/rules/enforcement``
documents which paths actually call ``should_reject()`` and therefore
respect ``RULES_ENGINE_ENFORCE``.

This test asserts the manifest matches the code: every file that
imports ``should_reject`` must be listed, and every listed file must
actually import it. A new ``should_reject()`` call without a manifest
update — or a stale manifest entry — fails here.

See ``docs/architecture/RULES_ENFORCEMENT.md`` for the full model.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from shared.rules.enforcement import ENFORCEMENT_AWARE_CALL_SITES

REPO_ROOT = Path(__file__).resolve().parents[3]


def _files_importing_should_reject() -> set[str]:
    """Return repo-relative paths of non-test files that import should_reject."""
    # Use ripgrep when available — faster and respects .gitignore. Fall back
    # to a Python walk so the test still works in stripped CI images.
    try:
        result = subprocess.run(
            [
                "rg",
                "--type=py",
                "-l",
                "--multiline",
                # Match single-line and parenthesized multi-line import forms.
                r"from (shared\.rules\.enforcement|\.enforcement) import (\([^)]*should_reject|[^\n]*should_reject)",
                str(REPO_ROOT / "services"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode in {0, 1}:  # 1 = no matches, still success
            paths = result.stdout.strip().splitlines()
        else:
            raise RuntimeError(result.stderr)
    except (FileNotFoundError, RuntimeError):
        paths = []
        for path in REPO_ROOT.glob("services/**/*.py"):
            try:
                text = path.read_text()
            except OSError:
                continue
            if (
                "from shared.rules.enforcement import" in text or "from .enforcement import" in text
            ) and "should_reject" in text:
                paths.append(str(path))

    rel = set()
    for raw in paths:
        p = Path(raw)
        try:
            r = p.resolve().relative_to(REPO_ROOT)
        except ValueError:
            continue
        # Drop tests + the enforcement module itself (which defines
        # should_reject, not imports it).
        parts = r.parts
        if "tests" in parts:
            continue
        if r.as_posix().endswith("services/shared/rules/enforcement.py"):
            continue
        rel.add(r.as_posix())
    return rel


def test_manifest_matches_actual_should_reject_callers():
    """If this test fails, either update ENFORCEMENT_AWARE_CALL_SITES
    or remove the orphaned import."""
    actual = _files_importing_should_reject()
    manifest = set(ENFORCEMENT_AWARE_CALL_SITES)

    extra_in_code = actual - manifest
    extra_in_manifest = manifest - actual

    assert not extra_in_code, (
        f"These files call should_reject() but are not in "
        f"ENFORCEMENT_AWARE_CALL_SITES: {sorted(extra_in_code)}. "
        f"Add them to the manifest in services/shared/rules/enforcement.py."
    )
    assert not extra_in_manifest, (
        f"These files are in ENFORCEMENT_AWARE_CALL_SITES but do not "
        f"import should_reject(): {sorted(extra_in_manifest)}. "
        f"Remove them or wire enforcement."
    )


def test_manifest_is_nonempty():
    """Sanity guard — an empty manifest would silently break the drift check."""
    assert len(ENFORCEMENT_AWARE_CALL_SITES) >= 3, (
        "Manifest unexpectedly small — at least the 3 documented call sites "
        "(webhook_compat, epcis/persistence, webhook_router_v2) must be present."
    )


# ---------------------------------------------------------------------------
# WS-9 / #1203 option 2 — /validate must derive verdicts from shared.rules
# ---------------------------------------------------------------------------


def test_compliance_validate_derives_from_rules_engine():
    """Drift guard for the #1203 option-2 rewire (WS-9).

    The compliance ``POST /validate`` endpoint must derive its verdicts
    from ``services/shared/rules`` — a regression to a local contract
    check (the pre-WS-9 ``_validate_fsma204_config``) would silently
    decouple the endpoint from the versioned rule definitions the
    ingestion paths enforce. This asserts the route module still imports
    the engine and evaluates through it.
    """
    routes_path = REPO_ROOT / "services" / "compliance" / "app" / "routes.py"
    text = routes_path.read_text()

    assert "from shared.rules.engine import RulesEngine" in text, (
        "services/compliance/app/routes.py no longer imports RulesEngine — "
        "the /validate endpoint must evaluate through services/shared/rules "
        "(#1203 option 2, WS-9), not a local validation stub."
    )
    assert "evaluate_event(" in text, (
        "services/compliance/app/routes.py imports RulesEngine but never "
        "calls evaluate_event() — /validate verdicts must come from the "
        "rules engine (#1203 option 2, WS-9)."
    )
    assert "def _validate_fsma204_config" not in text, (
        "The pre-WS-9 local contract check (_validate_fsma204_config) has "
        "reappeared in services/compliance/app/routes.py — /validate "
        "verdicts must derive from services/shared/rules, not a local stub."
    )
