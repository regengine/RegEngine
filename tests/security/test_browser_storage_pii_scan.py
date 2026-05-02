from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCANNER_PATH = ROOT / "scripts/security/scan_browser_storage_pii.py"
spec = importlib.util.spec_from_file_location("scan_browser_storage_pii", SCANNER_PATH)
assert spec is not None
scanner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["scan_browser_storage_pii"] = scanner
spec.loader.exec_module(scanner)


def test_scan_flags_direct_lead_pii_storage(tmp_path: Path):
    component = tmp_path / "LeadForm.tsx"
    component.write_text(
        """
        export function LeadForm({ email, companyName }) {
          localStorage.setItem('retailer_supplier_lead', JSON.stringify({
            email,
            companyName,
          }));
        }
        """,
        encoding="utf-8",
    )

    violations = scanner.scan_paths([component])

    assert len(violations) == 1
    assert violations[0].line_no == 3
    assert "sensitive term 'lead'" in violations[0].reason


def test_scan_allows_non_pii_flags_and_retry_metadata(tmp_path: Path):
    component = tmp_path / "ReadinessPage.tsx"
    component.write_text(
        """
        export function ReadinessPage() {
          localStorage.setItem('retailer_supplier_lead_submitted', '1');
          localStorage.setItem('retailer_supplier_lead_retry', JSON.stringify({
            pending: true,
            lastAttemptAt: new Date().toISOString(),
            endpoint: '/api/v1/assessments/retailer-readiness',
          }));
        }
        """,
        encoding="utf-8",
    )

    assert scanner.scan_paths([component]) == []


def test_scan_flags_sensitive_value_expression_with_safe_looking_key(tmp_path: Path):
    component = tmp_path / "Retry.tsx"
    component.write_text(
        """
        export function Retry({ email }) {
          sessionStorage.setItem('assessment_retry', JSON.stringify({ email }));
        }
        """,
        encoding="utf-8",
    )

    violations = scanner.scan_paths([component])

    assert len(violations) == 1
    assert violations[0].storage == "sessionStorage"
    assert "sensitive term 'email'" in violations[0].reason


def test_cli_returns_nonzero_when_violations_exist(tmp_path: Path, capsys):
    component = tmp_path / "LeadForm.tsx"
    component.write_text(
        "localStorage.setItem('lead_payload', JSON.stringify(leadPayload));",
        encoding="utf-8",
    )

    exit_code = scanner.main([str(tmp_path)])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Browser storage PII scan failed" in output
    assert "lead_payload" in output
