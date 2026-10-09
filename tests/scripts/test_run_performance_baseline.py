"""Guards for scripts/run-performance-baseline.sh (audit medium finding).

The Linux k6 install must not download and sudo-install an unverified
tarball. It installs a pinned k6 through the system package manager so
artifact signatures are verified, and the supply-chain gate agrees.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run-performance-baseline.sh"
_CHECKER = ROOT / "scripts" / "ci" / "check_supply_chain.py"

# Exact shape removed from the script by this fix. Kept here so the
# tests prove they would have caught the old code.
OLD_LINUX_BLOCK = """\
        wget https://github.com/grafana/k6/releases/download/v0.47.0/k6-v0.47.0-linux-amd64.tar.gz
        tar -xzf k6-v0.47.0-linux-amd64.tar.gz
        sudo cp k6-v0.47.0-linux-amd64/k6 /usr/local/bin/
        rm -rf k6-v0.47.0-linux-amd64*
"""


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_supply_chain", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_supply_chain"] = module
    spec.loader.exec_module(module)
    return module


mod = _load_checker()


def test_no_unverified_tarball_install() -> None:
    text = SCRIPT.read_text()
    assert "k6-v0.47.0-linux-amd64.tar.gz" not in text
    assert "sudo cp" not in text


def test_k6_version_is_pinned() -> None:
    text = SCRIPT.read_text()
    assert 'K6_VERSION="0.47.0"' in text
    assert "k6=${K6_VERSION}" in text


def test_gate_flags_old_block_and_passes_fixed_script(tmp_path: Path) -> None:
    old = tmp_path / "old.sh"
    old.write_text(OLD_LINUX_BLOCK)
    old_rules = {v.rule for v in mod.check_download_checksum(old, "old.sh")}
    assert "download-checksum" in old_rules
    assert mod.check_download_checksum(SCRIPT, "scripts/run-performance-baseline.sh") == []
