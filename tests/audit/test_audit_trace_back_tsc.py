"""Regression tests for run_tsc in the trace-back audit script.

Audit finding (medium): run_tsc stripped tsc output lines mentioning "e2e/"
or "security-audit" before grading, so new type errors in those files still
scored as clean. These tests fake the `npx tsc --noEmit` subprocess result
and prove run_tsc grades the full output.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path


def load_audit_module():
    path = Path(__file__).resolve().parent / "audit_trace_back.py"
    spec = importlib.util.spec_from_file_location("audit_trace_back_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_tsc(returncode, stdout, stderr=""):
    def _run(*args, **kwargs):
        cmd = args[0] if args else []
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=stdout, stderr=stderr)

    return _run


def test_e2e_type_error_fails_the_check(monkeypatch):
    audit = load_audit_module()
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        fake_tsc(1, "src/e2e/trace.spec.ts(12,5): error TS2322: Type 'string' is not assignable to type 'number'.\n"),
    )
    ok, output = audit.run_tsc()
    assert ok is False
    assert "e2e" in output


def test_security_audit_type_error_fails_the_check(monkeypatch):
    audit = load_audit_module()
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        fake_tsc(1, "src/security-audit/check.ts(3,7): error TS2304: Cannot find name 'foo'.\n"),
    )
    ok, output = audit.run_tsc()
    assert ok is False
    assert "security-audit" in output


def test_type_error_outside_excluded_paths_fails_the_check(monkeypatch):
    audit = load_audit_module()
    monkeypatch.setattr(
        audit.subprocess,
        "run",
        fake_tsc(
            1, "src/components/TracePanel.tsx(8,3): error TS2322: Type 'string' is not assignable to type 'number'.\n"
        ),
    )
    ok, _output = audit.run_tsc()
    assert ok is False


def test_clean_output_passes_the_check(monkeypatch):
    audit = load_audit_module()
    monkeypatch.setattr(audit.subprocess, "run", fake_tsc(0, ""))
    ok, output = audit.run_tsc()
    assert ok is True
    assert output == "Clean"
