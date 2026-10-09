from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "utilities" / "fix_duplicate_headers.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fix_duplicate_headers", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["fix_duplicate_headers"] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()

SAMPLE = """import { MarketingHeader } from '@/components/layout/marketing-header';

export default function Page() {
  return (
    <>
      <MarketingHeader />
      <p>Hello</p>
    </>
  );
}
"""


def _write_page(directory: Path, name: str = "page.tsx") -> Path:
    target = directory / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SAMPLE, encoding="utf-8")
    return target


def test_default_frontend_dir_derives_from_repo_root() -> None:
    frontend_dir = _MODULE.resolve_frontend_dir(None)
    repo_root = Path(__file__).resolve().parents[2]
    assert frontend_dir == repo_root / "frontend" / "src" / "app"
    assert "Desktop/RegEngine" not in str(frontend_dir)


def test_dry_run_reports_change_without_writing(tmp_path: Path) -> None:
    page = _write_page(tmp_path)
    changed = _MODULE.remove_duplicate_headers(page, dry_run=True)
    assert changed is True
    assert "MarketingHeader" in page.read_text(encoding="utf-8")


def test_apply_mode_rewrites_file(tmp_path: Path, monkeypatch) -> None:
    page = _write_page(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "y")
    count = _MODULE.run(tmp_path, dry_run=False, assume_yes=True)
    assert count == 1
    assert "MarketingHeader" not in page.read_text(encoding="utf-8")


def test_confirmation_abort_leaves_files_untouched(tmp_path: Path, monkeypatch) -> None:
    page = _write_page(tmp_path)
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "n")
    count = _MODULE.run(tmp_path, dry_run=False, assume_yes=False)
    assert count == 0
    assert "MarketingHeader" in page.read_text(encoding="utf-8")


def test_main_dry_run_flag_writes_nothing(tmp_path: Path, capsys) -> None:
    page = _write_page(tmp_path / "frontend" / "src" / "app")
    rc = _MODULE.main(["--root", str(tmp_path), "--dry-run"])
    assert rc == 0
    assert "MarketingHeader" in page.read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "dry" in out.lower()
