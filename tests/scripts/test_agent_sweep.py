"""Guards for the manual agent-sweep workflow (audit re-platform-2-ops, low #97).

Two defects, both pinned here:

* Concurrent manual sweeps had no ``concurrency`` block, so overlapping runs
  could each file the same findings issue. The workflow must serialize
  dispatches on the ref; the group covers every ``sweep_type`` because
  ``full-audit`` runs the same jobs as the single-type sweeps.
* The secrets scan covered only ``.py/.ts/.tsx/.js`` under three directories
  and dropped every match mentioning ``test`` via a substring filter, which
  skipped test paths and also discarded production findings whose value
  merely contained those letters (as in ``"latest-..."``).
"""

import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/agent-sweep.yml"


def load_workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def secrets_scan_run():
    workflow = load_workflow()
    job = workflow["jobs"]["security-sweep"]
    return next(step["run"] for step in job["steps"] if step.get("name") == "Scan for hardcoded secrets")


def test_concurrency_serializes_manual_sweeps():
    workflow = load_workflow()
    concurrency = workflow.get("concurrency")
    assert concurrency is not None, "agent-sweep needs a concurrency block so overlapping sweeps cannot file twice"
    assert "github.ref" in concurrency.get("group", ""), "concurrency group must be scoped to the ref"
    assert concurrency.get("cancel-in-progress") is True


def test_secrets_scan_covers_widened_file_types_and_dirs():
    run = secrets_scan_run()
    for ext in ("*.py", "*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.sh"):
        assert ext in run, f"secrets scan must cover {ext}"
    for scanned_dir in ("services/", "shared/", "frontend/src/", "scripts/", "tests/"):
        assert scanned_dir in run, f"secrets scan must cover {scanned_dir}"


def test_secrets_scan_has_no_test_substring_filter():
    run = secrets_scan_run()
    assert '| grep -v "test"' not in run
    assert "| grep -v test" not in run


def test_secrets_scan_reports_test_paths_without_flagging():
    run = secrets_scan_run()
    assert "Test Fixture" in run, "test-path findings must still be reported for visibility"
    info_section = run.split("Test Fixture")[1]
    assert "⚠️" not in info_section, "test-fixture findings must never trip issue creation"


def _fixture_tree(root: Path):
    (root / "services/acme/tests").mkdir(parents=True)
    (root / "services/acme/tool").mkdir(parents=True)
    (root / "frontend/src").mkdir(parents=True)
    (root / "scripts").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)
    (root / "services/acme/tests/test_auth.py").write_text('password = "fixture-value"\n', encoding="utf-8")
    (root / "services/acme/tool/run.sh").write_text('secret = "sh-value"\n', encoding="utf-8")
    (root / "frontend/src/widget.jsx").write_text('api_key = "jsx-value"\n', encoding="utf-8")
    (root / "services/acme/tool/latest.py").write_text('password = "latest-value"\n', encoding="utf-8")


def _grep_span(run: str, start_marker: str):
    start = run.index(start_marker)
    end = run.index("|| true)", start) + len("|| true)")
    return run[start:end]


def test_secrets_scan_pipeline_finds_test_paths_and_new_types(tmp_path):
    """Run the workflow's own first grep pipeline against a fixture tree."""
    _fixture_tree(tmp_path)
    run = secrets_scan_run()
    pipeline = _grep_span(run, "$(grep -rn")
    script = f'FOUND={pipeline}\necho "$FOUND"\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    for needle in ("test_auth.py", "run.sh", "widget.jsx", "latest.py"):
        assert needle in result.stdout, f"widened scan must surface {needle}"


def test_secrets_scan_pipeline_splits_prod_from_test(tmp_path):
    """Production slice must keep prod files and exclude test files."""
    _fixture_tree(tmp_path)
    run = secrets_scan_run()
    head = run[: run.index("RAW=$(echo")]
    assignment = _grep_span(run, "RAW=$(echo")
    script = f'{head}\n{assignment}\necho "$RAW"\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    for needle in ("run.sh", "widget.jsx", "latest.py"):
        assert needle in result.stdout, f"production slice must keep {needle}"
    assert "test_auth.py" not in result.stdout, "production slice must exclude test paths"
