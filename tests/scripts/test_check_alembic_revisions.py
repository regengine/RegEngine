"""Tests for scripts/check_alembic_revisions.py.

Each test creates a minimal fake migration file in a temp directory and
invokes the helper functions directly (not via subprocess) so the suite
stays fast and IDE-friendly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load the script as a module without requiring it to be installed as a
# package.  We reference the repo root relative to this test file.
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check_alembic_revisions.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_alembic_revisions", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()
_looks_sequential = _mod._looks_sequential
GRANDFATHERED_IDS = _mod.GRANDFATHERED_IDS
KNOWN_DUPLICATE_IDS = _mod.KNOWN_DUPLICATE_IDS


# ---------------------------------------------------------------------------
# Unit tests: _looks_sequential
# ---------------------------------------------------------------------------


class TestLooksSequential:
    def test_grandfathered_id_not_sequential(self):
        """A grandfathered ID must never be flagged as sequential."""
        for rev_id in GRANDFATHERED_IDS:
            assert not _looks_sequential(rev_id), f"grandfathered {rev_id!r} wrongly flagged"

    def test_truly_random_hex_not_sequential(self):
        """A randomly generated 12-char hex hash must not be flagged."""
        assert not _looks_sequential("3f7a1c9e2b84")
        assert not _looks_sequential("deadbeef1234")
        assert not _looks_sequential("c0ffee123456")

    def test_new_sequential_pattern_flagged(self):
        """A new nibble-shift ID that isn't grandfathered must be flagged."""
        # Pattern: each byte incremented by 0x11 relative to the previous.
        # Shift by 2 from the grandfathered series so it isn't in the set.
        new_seq = "c3d4e5f6a7b8"  # happens to be grandfathered — skip
        # Build one that is definitely not grandfathered:
        # bytes 0x10, 0x21, 0x32, 0x43, 0x54, 0x65 → "102132435465"  (diff=+0x11 each? no)
        # Simpler: bytes 0x20, 0x31, 0x42, 0x53, 0x64, 0x75 → diff=0x11 each
        candidate = "203142536475"
        assert candidate not in GRANDFATHERED_IDS
        assert _looks_sequential(candidate)

    def test_non_12_char_not_flagged(self):
        """IDs that aren't exactly 12 chars are not flagged as sequential."""
        assert not _looks_sequential("a1b2c3d4e5")    # 10 chars
        assert not _looks_sequential("a1b2c3d4e5f6a7")  # 14 chars

    def test_non_arithmetic_not_flagged(self):
        """IDs whose bytes don't form a constant-difference sequence are OK."""
        # bytes: 0xab, 0xcd, 0x12, 0x34, 0x56, 0x78 → diffs vary
        assert not _looks_sequential("abcd12345678")


# ---------------------------------------------------------------------------
# Integration tests: collect_revisions + main via temp directory
# ---------------------------------------------------------------------------


def _write_migration(tmp_path: Path, filename: str, rev_id: str) -> Path:
    """Write a minimal Alembic migration file with the given revision ID."""
    f = tmp_path / filename
    f.write_text(
        f'revision: str = "{rev_id}"\n'
        'down_revision = None\n'
        'branch_labels = None\n'
        'depends_on = None\n'
    )
    return f


class TestCollectRevisions:
    def test_grandfathered_id_produces_no_failure(self, tmp_path, monkeypatch):
        """A grandfathered ID in a migration file must not cause a failure."""
        monkeypatch.setattr(_mod, "VERSIONS_DIR", tmp_path)
        monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path.parent)
        _write_migration(tmp_path, "001_baseline.py", "a1b2c3d4e5f6")  # grandfathered
        rev_map = _mod.collect_revisions()
        # The ID is present in the map but should be in GRANDFATHERED_IDS
        assert "a1b2c3d4e5f6" in rev_map
        assert "a1b2c3d4e5f6" in GRANDFATHERED_IDS

    def _patch(self, monkeypatch, tmp_path):
        """Patch both VERSIONS_DIR and REPO_ROOT so rel() works in tmp dirs."""
        monkeypatch.setattr(_mod, "VERSIONS_DIR", tmp_path)
        monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path.parent)

    def test_random_hex_id_passes_main(self, tmp_path, monkeypatch, capsys):
        """A random 12-char hex ID must result in exit code 0."""
        self._patch(monkeypatch, tmp_path)
        _write_migration(tmp_path, "001_random.py", "3f7a1c9e2b84")
        result = _mod.main()
        assert result == 0
        out = capsys.readouterr().out
        assert "OK" in out

    def test_sequential_new_id_fails_main(self, tmp_path, monkeypatch, capsys):
        """A new sequential ID must cause main() to return 1."""
        self._patch(monkeypatch, tmp_path)
        # 203142536475 → bytes 0x20,0x31,0x42,0x53,0x64,0x75 → diff=0x11 each
        _write_migration(tmp_path, "001_bad.py", "203142536475")
        result = _mod.main()
        assert result == 1
        out = capsys.readouterr().out
        assert "SEQUENTIAL" in out or "FAIL" in out

    def test_duplicate_non_known_id_fails_main(self, tmp_path, monkeypatch, capsys):
        """Two files sharing a non-grandfathered, non-known-duplicate ID must fail."""
        self._patch(monkeypatch, tmp_path)
        _write_migration(tmp_path, "001_a.py", "deadbeef1234")
        _write_migration(tmp_path, "002_a.py", "deadbeef1234")
        result = _mod.main()
        assert result == 1
        out = capsys.readouterr().out
        assert "DUPLICATE" in out

    def test_known_duplicate_emits_warning_not_failure(self, tmp_path, monkeypatch, capsys):
        """Known-duplicate IDs (pre-existing) must emit a WARNING but not fail."""
        self._patch(monkeypatch, tmp_path)
        dup_id = next(iter(KNOWN_DUPLICATE_IDS))  # pick any known dup
        # It's also grandfathered, so mark it in GRANDFATHERED_IDS too
        assert dup_id in GRANDFATHERED_IDS
        _write_migration(tmp_path, "001_dup.py", dup_id)
        _write_migration(tmp_path, "002_dup.py", dup_id)
        result = _mod.main()
        assert result == 0
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "pre-existing" in out
