"""Live-tree tenant-scope gate.

Runs scripts/security/scan_tenant_scope.py against the real services/,
server/, and regengine/ trees: any unscoped query, and any stale baseline
row, fails. This test stays out of the blocking suites (it runs in the
non-required test-suite-check shard) until the tree itself is green; the
owning teams fix or baseline each site. See FIX-REPORT.md for the current
finding list.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT / "scripts/security/scan_tenant_scope.py"
spec = importlib.util.spec_from_file_location("scan_tenant_scope_gate", SCANNER_PATH)
assert spec is not None
scanner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["scan_tenant_scope_gate"] = scanner
spec.loader.exec_module(scanner)

ALLOWLIST_PATH = ROOT / ".semgrep" / "tenant-scope-allowlist.yml"


def test_repo_gate_has_no_new_violations():
    fresh, _ = scanner.check([ROOT / "services", ROOT / "server", ROOT / "regengine"], ALLOWLIST_PATH)
    assert fresh == [], [f"{v.file}:{v.line} [{v.scope}] {v.rule}" for v in fresh]


def test_repo_gate_has_no_stale_baseline_entries():
    _, stale = scanner.check([ROOT / "services", ROOT / "server", ROOT / "regengine"], ALLOWLIST_PATH)
    assert stale == [], [f"{e.file} :: {e.scope} :: {e.rule}" for e in stale]
