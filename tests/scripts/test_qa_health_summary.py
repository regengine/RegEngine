from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "qa_health_summary.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("qa_health_summary", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_parse_junit_counts_pass_fail_skip_and_duration(tmp_path: Path) -> None:
    junit = tmp_path / "pytest.xml"
    junit.write_text(
        '<testsuite tests="5" failures="1" errors="1" skipped="1" time="2.5" />',
        encoding="utf-8",
    )

    counts = _MODULE.parse_junit(junit)

    assert counts == {
        "passed": 2,
        "failed": 1,
        "errors": 1,
        "skipped": 1,
        "duration_seconds": 2.5,
    }


def test_parse_eslint_counts_errors_and_warnings(tmp_path: Path) -> None:
    report = tmp_path / "eslint.json"
    report.write_text(
        json.dumps(
            [
                {"filePath": "a.ts", "errorCount": 0, "warningCount": 2},
                {"filePath": "b.ts", "errorCount": 1, "warningCount": 0},
            ]
        ),
        encoding="utf-8",
    )

    counts = _MODULE.parse_eslint(report)

    assert counts["failed"] == 1
    assert counts["skipped"] == 2


def test_parse_playwright_stats(tmp_path: Path) -> None:
    report = tmp_path / "playwright.json"
    report.write_text(
        json.dumps({"stats": {"expected": 13, "unexpected": 55, "skipped": 2, "duration": 44000}}),
        encoding="utf-8",
    )

    counts = _MODULE.parse_playwright(report)

    assert counts == {
        "passed": 13,
        "failed": 55,
        "errors": 0,
        "skipped": 2,
        "duration_seconds": 44.0,
    }


def test_parsers_tolerate_non_utf8_artifacts(tmp_path: Path) -> None:
    """A non-UTF8 / binary-garbage artifact must be treated as absent, not crash."""
    junk = b"\xff\xfe\x00\x01garbage\x80\x81"

    eslint = tmp_path / "eslint.json"
    eslint.write_bytes(junk)
    assert _MODULE.parse_eslint(eslint) is None

    playwright = tmp_path / "playwright.json"
    playwright.write_bytes(junk)
    assert _MODULE.parse_playwright(playwright) is None

    junit = tmp_path / "pytest.xml"
    junit.write_bytes(junk)
    assert _MODULE.parse_junit(junit) is None


def test_parsers_tolerate_zero_byte_artifacts(tmp_path: Path) -> None:
    """Zero-byte artifacts (touched-but-never-written) are treated as absent."""
    for name, parser in (
        ("eslint.json", _MODULE.parse_eslint),
        ("playwright.json", _MODULE.parse_playwright),
        ("pytest.xml", _MODULE.parse_junit),
    ):
        empty = tmp_path / name
        empty.write_bytes(b"")
        assert parser(empty) is None


def test_build_summary_tolerates_missing_outputs(tmp_path: Path) -> None:
    out = tmp_path / "latest.json"
    args = _MODULE.argparse.Namespace(
        out=out,
        pytest_xml=None,
        eslint_json=None,
        vitest_junit=None,
        playwright_json=None,
        npm_ci_exit_code=None,
        workflow="QA Health",
        run_id="1",
        commit="abc",
        branch="main",
    )

    summary = _MODULE.build_summary(args)

    assert summary["overall"]["status"] == "unavailable"
    assert all(suite["status"] == "unavailable" for suite in summary["suites"])
    assert summary["clusters"] == []


def test_build_summary_classifies_blocking_clusters(tmp_path: Path) -> None:
    pytest_xml = tmp_path / "pytest.xml"
    pytest_xml.write_text(
        '<testsuite tests="3" failures="1" errors="0" skipped="0" time="1" />',
        encoding="utf-8",
    )
    vitest_xml = tmp_path / "vitest.xml"
    vitest_xml.write_text(
        '<testsuite tests="2" failures="0" errors="0" skipped="0" time="1" />',
        encoding="utf-8",
    )
    playwright_json = tmp_path / "playwright.json"
    playwright_json.write_text(
        json.dumps({"stats": {"expected": 1, "unexpected": 1, "skipped": 0}}),
        encoding="utf-8",
    )
    eslint_json = tmp_path / "eslint.json"
    eslint_json.write_text(json.dumps([]), encoding="utf-8")
    args = _MODULE.argparse.Namespace(
        out=tmp_path / "latest.json",
        pytest_xml=pytest_xml,
        eslint_json=eslint_json,
        vitest_junit=vitest_xml,
        playwright_json=playwright_json,
        npm_ci_exit_code=1,
        workflow="QA Health",
        run_id="1",
        commit="abc",
        branch="main",
    )

    summary = _MODULE.build_summary(args)

    assert summary["overall"]["status"] == "failing"
    assert summary["overall"]["blocking_count"] == 3
    assert {cluster["title"] for cluster in summary["clusters"]} == {
        "Dependency lock drift",
        "E2E auth path failures",
        "Backend regression cluster",
    }
