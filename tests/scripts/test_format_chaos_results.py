from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "format_chaos_results.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("format_chaos_results", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def _run_main(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["format_chaos_results.py", *args])
    return _MODULE.main()


def test_missing_results_file_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A missing results file must not read as clean: exit nonzero with explicit failure."""
    missing = tmp_path / "does_not_exist.json"

    exit_code = _run_main(monkeypatch, ["--input", str(missing)])

    assert exit_code != 0
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_empty_results_file_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An empty results list is also not a clean run."""
    empty = tmp_path / "chaos_results.json"
    empty.write_text("[]", encoding="utf-8")

    exit_code = _run_main(monkeypatch, ["--input", str(empty)])

    assert exit_code != 0
    out = capsys.readouterr().out
    assert "FAIL" in out


def test_passing_results_exit_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = tmp_path / "chaos_results.json"
    results.write_text(
        json.dumps([{"name": "neo4j-failure", "status": "passed", "duration": 120}]),
        encoding="utf-8",
    )

    assert _run_main(monkeypatch, ["--input", str(results)]) == 0


def test_failing_results_exit_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = tmp_path / "chaos_results.json"
    results.write_text(
        json.dumps([{"name": "kafka-failure", "status": "failed", "duration": 45}]),
        encoding="utf-8",
    )

    assert _run_main(monkeypatch, ["--input", str(results)]) != 0
