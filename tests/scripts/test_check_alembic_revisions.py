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
        assert not _looks_sequential("3f7a1c9e2b84")  # pragma: allowlist secret
        assert not _looks_sequential("deadbeef1234")  # pragma: allowlist secret
        assert not _looks_sequential("c0ffee123456")  # pragma: allowlist secret

    def test_new_sequential_pattern_flagged(self):
        """A new nibble-shift ID that isn't grandfathered must be flagged."""
        # Pattern: each byte incremented by 0x11 relative to the previous.
        # Shift by 2 from the grandfathered series so it isn't in the set.
        new_seq = "c3d4e5f6a7b8"  # happens to be grandfathered — skip  # pragma: allowlist secret
        # Build one that is definitely not grandfathered:
        # bytes 0x10, 0x21, 0x32, 0x43, 0x54, 0x65 → "102132435465"  (diff=+0x11 each? no)
        # Simpler: bytes 0x20, 0x31, 0x42, 0x53, 0x64, 0x75 → diff=0x11 each
        candidate = "203142536475"
        assert candidate not in GRANDFATHERED_IDS
        assert _looks_sequential(candidate)

    def test_non_12_char_not_flagged(self):
        """IDs that aren't exactly 12 chars are not flagged as sequential."""
        assert not _looks_sequential("a1b2c3d4e5")  # 10 chars  # pragma: allowlist secret
        assert not _looks_sequential("a1b2c3d4e5f6a7")  # 14 chars  # pragma: allowlist secret

    def test_non_arithmetic_not_flagged(self):
        """IDs whose bytes don't form a constant-difference sequence are OK."""
        # bytes: 0xab, 0xcd, 0x12, 0x34, 0x56, 0x78 → diffs vary
        assert not _looks_sequential("abcd12345678")  # pragma: allowlist secret


# ---------------------------------------------------------------------------
# Integration tests: collect_revisions + main via temp directory
# ---------------------------------------------------------------------------


def _write_migration(
    tmp_path: Path,
    filename: str,
    rev_id: str,
    down_revision: str = "None",
) -> Path:
    """Write a minimal Alembic migration file with the given revision ID."""
    f = tmp_path / filename
    f.write_text(
        f'revision: str = "{rev_id}"\ndown_revision = {down_revision}\nbranch_labels = None\ndepends_on = None\n'
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

    def test_merge_revision_tuple_parents_are_not_reported_as_heads(self, tmp_path, monkeypatch, capsys):
        """A merge migration points at both parents even when down_revision is a tuple."""
        self._patch(monkeypatch, tmp_path)
        base = "3f7a1c9e2b84"  # pragma: allowlist secret
        left = "4a8c2f91d0b3"  # pragma: allowlist secret
        right = "5b9d3a02c1e4"  # pragma: allowlist secret
        merge = "6c0e4b13d2f5"  # pragma: allowlist secret

        _write_migration(tmp_path, "001_base.py", base)
        _write_migration(tmp_path, "002_left.py", left, f'"{base}"')
        _write_migration(tmp_path, "003_right.py", right, f'"{base}"')
        _write_migration(
            tmp_path,
            "004_merge.py",
            merge,
            f'("{left}", "{right}")',
        )

        result = _mod.main()
        assert result == 0
        out = capsys.readouterr().out
        assert f"Head(s): {merge}" in out


class TestMultipleHeadsGuard:
    """Proof fixtures for the second-head guard (Phase 3 CI governance).

    Three head-forks landed on main inside 48h (v099/v100, v101/v102, and
    the v101/v102 -> v103 reparent). The MULTIPLE HEADS check already
    existed; these fixtures prove it actually fails CI, so the guard
    cannot silently rot.
    """

    def _patch(self, monkeypatch, tmp_path):
        monkeypatch.setattr(_mod, "VERSIONS_DIR", tmp_path)
        monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path.parent)

    def test_second_head_fails_main(self, tmp_path, monkeypatch, capsys):
        """The exact v099/v100 shape: two migrations sharing one parent and
        neither pointed at — two heads, ambiguous `alembic upgrade head`."""
        self._patch(monkeypatch, tmp_path)
        base = "3f7a1c9e2b84"  # pragma: allowlist secret
        fork_a = "4a8c2f91d0b3"  # pragma: allowlist secret
        fork_b = "5b9d3a02c1e4"  # pragma: allowlist secret

        _write_migration(tmp_path, "001_base.py", base)
        _write_migration(tmp_path, "002_fork_a.py", fork_a, f'"{base}"')
        _write_migration(tmp_path, "003_fork_b.py", fork_b, f'"{base}"')

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "MULTIPLE HEADS (2)" in out
        # Both offending revisions are named so the fix is actionable.
        assert fork_a in out
        assert fork_b in out
        assert "alembic merge" in out

    def test_three_heads_fails_main(self, tmp_path, monkeypatch, capsys):
        self._patch(monkeypatch, tmp_path)
        base = "3f7a1c9e2b84"  # pragma: allowlist secret
        for i, fork in enumerate(
            ("4a8c2f91d0b3", "5b9d3a02c1e4", "6c0e4b13d2f5"),  # pragma: allowlist secret
            start=2,
        ):
            _write_migration(tmp_path, f"00{i}_fork.py", fork, f'"{base}"')
        _write_migration(tmp_path, "001_base.py", base)

        assert _mod.main() == 1
        assert "MULTIPLE HEADS (3)" in capsys.readouterr().out

    def test_merging_the_fork_restores_single_head(self, tmp_path, monkeypatch, capsys):
        """The documented remedy (`alembic merge`) makes the guard pass —
        proving the failure is actionable, not a dead end."""
        self._patch(monkeypatch, tmp_path)
        base = "3f7a1c9e2b84"  # pragma: allowlist secret
        fork_a = "4a8c2f91d0b3"  # pragma: allowlist secret
        fork_b = "5b9d3a02c1e4"  # pragma: allowlist secret
        merge = "6c0e4b13d2f5"  # pragma: allowlist secret

        _write_migration(tmp_path, "001_base.py", base)
        _write_migration(tmp_path, "002_fork_a.py", fork_a, f'"{base}"')
        _write_migration(tmp_path, "003_fork_b.py", fork_b, f'"{base}"')
        _write_migration(tmp_path, "004_merge.py", merge, f'("{fork_a}", "{fork_b}")')

        assert _mod.main() == 0
        assert f"Head(s): {merge}" in capsys.readouterr().out

    def test_reparent_leaving_two_heads_fails(self, tmp_path, monkeypatch, capsys):
        """The v101/v102 -> v103 reparent shape: a later migration is
        re-pointed at one fork, leaving the other fork still a head."""
        self._patch(monkeypatch, tmp_path)
        base = "3f7a1c9e2b84"  # pragma: allowlist secret
        fork_a = "4a8c2f91d0b3"  # pragma: allowlist secret
        fork_b = "5b9d3a02c1e4"  # pragma: allowlist secret
        later = "6c0e4b13d2f5"  # pragma: allowlist secret

        _write_migration(tmp_path, "001_base.py", base)
        _write_migration(tmp_path, "002_fork_a.py", fork_a, f'"{base}"')
        _write_migration(tmp_path, "003_fork_b.py", fork_b, f'"{base}"')
        # Reparented onto fork_a only — fork_b is still an unmerged head.
        _write_migration(tmp_path, "004_later.py", later, f'"{fork_a}"')

        assert _mod.main() == 1
        out = capsys.readouterr().out
        assert "MULTIPLE HEADS (2)" in out
        assert fork_b in out

    def test_real_repo_dag_has_exactly_one_head(self, capsys):
        """The live alembic/versions/ tree must have a single head. Runs
        against the REAL directory (no monkeypatch), so a merged PR that
        forks the DAG fails this test as well as the CI script."""
        assert _mod.main() == 0
        assert "single head" in capsys.readouterr().out
