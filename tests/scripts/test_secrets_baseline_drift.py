"""The exit-3 exception must never hide a changed secret finding."""

import runpy
from pathlib import Path

without_scan_metadata = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/check_secrets_baseline_drift.py")
)["without_scan_metadata"]


def test_line_number_and_generated_at_drift_only():
    original = {
        "version": "1.5.0",
        "plugins_used": [{"name": "KeywordDetector"}],
        "results": {
            "sample.py": [
                {
                    "type": "Secret Keyword",
                    "hashed_secret": "synthetic",  # pragma: allowlist secret
                    "line_number": 1,
                }
            ]
        },
        "generated_at": "before",
    }
    drifted = {
        **original,
        "generated_at": "after",
        "results": {"sample.py": [{**original["results"]["sample.py"][0], "line_number": 2}]},
    }
    assert without_scan_metadata(original) == without_scan_metadata(drifted)


def test_changed_finding_and_scanner_settings_fail_comparison():
    original = {
        "results": {
            "sample.py": [
                {
                    "hashed_secret": "synthetic",  # pragma: allowlist secret
                    "line_number": 1,
                }
            ]
        },
        "plugins_used": [{"name": "KeywordDetector"}],
    }
    changed_finding = {
        **original,
        "results": {
            "sample.py": [
                {
                    "hashed_secret": "different",  # pragma: allowlist secret
                    "line_number": 2,
                }
            ]
        },
    }
    added_finding = {
        **original,
        "results": {
            "sample.py": original["results"]["sample.py"]
            + [
                {
                    "hashed_secret": "added",  # pragma: allowlist secret
                    "line_number": 3,
                }
            ]
        },
    }
    changed_scanner = {**original, "plugins_used": []}
    for changed in (changed_finding, added_finding, changed_scanner):
        assert without_scan_metadata(original) != without_scan_metadata(changed)
