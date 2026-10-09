"""Regression test for the audit finding on the deprecated bootstrap script.

The old services/admin/scripts/bootstrap_auth.py printed a freshly minted
API key to stdout and created the key with no expiry. The fix was to delete
the script, so these tests assert it stays gone and that no remaining admin
script handles raw API keys in its source.
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def test_bootstrap_auth_script_is_deleted():
    assert not (SCRIPTS_DIR / "bootstrap_auth.py").exists(), (
        "services/admin/scripts/bootstrap_auth.py must stay deleted: "
        "it printed raw API keys and minted keys with no expiry"
    )


def test_no_admin_script_references_raw_keys():
    offenders = sorted(path.name for path in SCRIPTS_DIR.glob("*.py") if "raw_key" in path.read_text(encoding="utf-8"))
    assert offenders == [], f"admin scripts must not handle raw API keys, found in: {offenders}"
