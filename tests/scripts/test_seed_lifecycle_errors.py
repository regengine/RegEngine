"""seed_lifecycle_test.py must use synthetic contacts and surface HTTP errors.

Finding: the seeder wrote realistic-looking personal data into the target
tenant and swallowed HTTP failures into dicts that were logged as
successes, so a fully failed run still exited zero. These tests pin the
fix: fixture contacts are clearly synthetic, and every HTTP error is
aggregated into results["errors"] with a nonzero exit code.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(monkeypatch):
    monkeypatch.setenv("REGENGINE_API_KEY", "test-key")
    monkeypatch.delenv("REGENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    name = "seed_lifecycle_test_errors"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "seed_lifecycle_test.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _run_main(module, monkeypatch, tmp_path, post, get):
    """Run main() with stubbed HTTP layer and redirected results file."""
    monkeypatch.setattr(module, "api_post", post)
    monkeypatch.setattr(module, "api_get", get)
    monkeypatch.setattr("time.sleep", lambda _s: None)
    real_open = open

    def fake_open(path, *args, **kwargs):
        if str(path).endswith("lifecycle_test_results.json"):
            path = str(tmp_path / "lifecycle_test_results.json")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    return module.main([])


def _ok_post(url, payload):
    if "ingest" in url:
        return {"accepted": 21, "rejected": 0, "events": []}
    return {"id": "ok"}


def _ok_get(url):
    return {}


def _failing_post(url, payload):
    return {"error": 500, "body": "boom"}


def _failing_get(url):
    return {"error": 500, "body": "boom"}


# --- module stays importable without a key; main still requires one ---


def test_import_without_api_key_does_not_exit(monkeypatch):
    monkeypatch.delenv("REGENGINE_API_KEY", raising=False)
    monkeypatch.delenv("REGENGINE_BASE_URL", raising=False)
    monkeypatch.delenv("REGENGINE_ENV", raising=False)
    name = "seed_lifecycle_test_no_key"
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / "seed_lifecycle_test.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    with pytest.raises(SystemExit):
        module.main([])


# --- contacts are clearly synthetic, never realistic personal data ---


def test_contacts_are_clearly_synthetic(monkeypatch):
    module = _load(monkeypatch)
    assert len(module.SUPPLIERS) == 3
    for supplier in module.SUPPLIERS:
        assert "synthetic" in supplier["contact_name"].lower()
        assert supplier["contact_email"].endswith("@example.invalid")
        assert "555-01" in supplier["phone"]
    blob = " ".join(f"{s['contact_name']} {s['contact_email']} {s['phone']}" for s in module.SUPPLIERS).lower()
    for realistic in ("maria", "gonzalez", "david chen", "sarah park", "valleyfreshfarms.com"):
        assert realistic not in blob


# --- HTTP errors aggregate into results and the exit code ---


def test_all_http_errors_aggregate_into_failure(monkeypatch, tmp_path, capsys):
    module = _load(monkeypatch)
    results = _run_main(module, monkeypatch, tmp_path, _failing_post, _failing_get)
    assert results["suppliers"] == 0
    assert results["products"] == 0
    assert results["success"] is False
    assert len(results["errors"]) >= 9
    assert module._exit_code(results) == 1
    out = capsys.readouterr().out
    assert "ERRORS" in out


def test_rejected_ingest_events_count_as_errors(monkeypatch, tmp_path):
    module = _load(monkeypatch)

    def post(url, payload):
        if "ingest" in url:
            return {
                "accepted": 19,
                "rejected": 2,
                "events": [{"status": "rejected", "cte_type": "harvesting", "errors": ["bad"]}],
            }
        return {"id": "ok"}

    results = _run_main(module, monkeypatch, tmp_path, post, _ok_get)
    assert results["success"] is False
    assert any("rejected" in err for err in results["errors"])
    assert module._exit_code(results) == 1


def test_clean_run_reports_success_and_zero_exit(monkeypatch, tmp_path):
    module = _load(monkeypatch)
    results = _run_main(module, monkeypatch, tmp_path, _ok_post, _ok_get)
    assert results["suppliers"] == len(module.SUPPLIERS)
    assert results["products"] == len(module.PRODUCTS)
    assert results["errors"] == []
    assert results["success"] is True
    assert module._exit_code(results) == 0
    assert (tmp_path / "lifecycle_test_results.json").exists()


def test_exit_code_helper(monkeypatch):
    monkeypatch.setenv("REGENGINE_API_KEY", "test-key")
    module_name = "seed_lifecycle_exit_probe"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / "seed_lifecycle_test.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    assert module._exit_code({"errors": []}) == 0
    assert module._exit_code({}) == 0
    assert module._exit_code({"errors": ["ingest: HTTP 500"]}) == 1
