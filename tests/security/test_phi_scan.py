from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT / "scripts/security/scan_phi.py"
spec = importlib.util.spec_from_file_location("scan_phi", SCANNER_PATH)
assert spec is not None
scanner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["scan_phi"] = scanner
spec.loader.exec_module(scanner)


def _clean_tree(root: Path) -> Path:
    (root / "services").mkdir(exist_ok=True)
    (root / "scripts").mkdir(exist_ok=True)
    return root


def test_scan_flags_whole_word_phi_keyword(tmp_path: Path):
    target = tmp_path / "schema.py"
    target.write_text("patient_name = Column(String)\n", encoding="utf-8")

    violations, applied = scanner.scan_file(target, tmp_path)

    assert len(violations) == 1
    assert "patient_name" in violations[0]
    assert applied == []


def test_scan_ignores_keyword_inside_ordinary_words(tmp_path: Path):
    target = tmp_path / "doc.py"
    target.write_text("import adobe_reader\n", encoding="utf-8")

    violations, applied = scanner.scan_file(target, tmp_path)

    assert violations == []
    assert applied == []


def test_unreadable_file_is_a_finding(tmp_path: Path):
    violations, _ = scanner.scan_file(tmp_path, tmp_path)

    assert len(violations) == 1
    assert "Could not read" in violations[0]


def test_scan_targets_exist_in_repo():
    for target in scanner.SCAN_TARGETS:
        assert (ROOT / target).exists(), f"scan target missing: {target}"


def test_central_suppression_silences_one_keyword_with_trail(tmp_path: Path):
    target = tmp_path / "config.py"
    target.write_text(
        "pattern = \"ssn\\\\s*=\\\\s*'[^']*'\"\npatient_name = 'x'\n",
        encoding="utf-8",
    )
    rel = str(target.relative_to(tmp_path))
    scanner.SUPPRESSED_KEYWORDS[rel] = {"ssn": "test reason"}
    try:
        violations, applied = scanner.scan_file(target, tmp_path)
    finally:
        del scanner.SUPPRESSED_KEYWORDS[rel]

    assert len(violations) == 1
    assert "patient_name" in violations[0]
    assert len(applied) == 1
    assert "test reason" in applied[0]


def test_run_scan_passes_on_clean_tree(tmp_path: Path):
    root = _clean_tree(tmp_path)
    (root / "services" / "app.py").write_text("value = 1\n", encoding="utf-8")

    assert scanner.run_scan(root) == 0


def test_run_scan_fails_on_phi_keyword(tmp_path: Path):
    root = _clean_tree(tmp_path)
    (root / "services" / "schema.py").write_text("patient_name = Column(String)\n", encoding="utf-8")

    assert scanner.run_scan(root) == 1


def test_missing_scan_target_is_a_finding(tmp_path: Path):
    (tmp_path / "services").mkdir()

    assert scanner.run_scan(tmp_path) == 1
