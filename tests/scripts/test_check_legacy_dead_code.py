from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_legacy_dead_code.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_legacy_dead_code", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_legacy_dead_code"] = module
    spec.loader.exec_module(module)
    return module


_MODULE = _load_module()


def test_manual_agent_sweep_guard_allows_dispatch_only(tmp_path: Path) -> None:
    _write_agent_sweep(
        tmp_path,
        "on:\n  workflow_dispatch:\n    inputs:\n      sweep_type:\n        required: true\n",
    )

    assert _MODULE.check_manual_agent_sweep(tmp_path) == []


def test_manual_agent_sweep_guard_blocks_scheduled_sweeps(tmp_path: Path) -> None:
    _write_agent_sweep(
        tmp_path,
        "on:\n  schedule:\n    - cron: '0 9 * * 1'\n  workflow_dispatch:\n",
    )

    findings = _MODULE.check_manual_agent_sweep(tmp_path)

    assert len(findings) == 1
    assert findings[0].code == "scheduled-agent-sweep"


def _write_agent_sweep(tmp_path: Path, text: str) -> None:
    workflow = tmp_path / ".github" / "workflows" / "agent-sweep.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(text, encoding="utf-8")


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_bare_app_import_in_service_code_is_a_finding(tmp_path: Path) -> None:
    path = _write(tmp_path, "services/ingestion/app/thing.py", "from app.config import get_settings\n")

    findings = _MODULE.check_bare_app_imports([path], tmp_path)

    assert [f.code for f in findings] == ["bare-app-import"]
    assert findings[0].line == 1
    assert "services.ingestion.app" in findings[0].message


@pytest.mark.parametrize(
    "line",
    [
        "import app\n",
        "import app as application\n",
        "    from app import csv_templates as route\n",
        "from app.sandbox.router import router\n",
    ],
)
def test_bare_app_import_forms_are_caught(tmp_path: Path, line: str) -> None:
    path = _write(tmp_path, "services/admin/main.py", line)
    assert len(_MODULE.check_bare_app_imports([path], tmp_path)) == 1


@pytest.mark.parametrize(
    "relative,line",
    [
        ("services/ingestion/app/thing.py", "from services.ingestion.app.config import get_settings\n"),
        ("services/ingestion/app/thing.py", "from .config import get_settings\n"),
        ("services/ingestion/app/thing.py", "from application import x\n"),
        ("services/ingestion/app/thing.py", "from app_utils import x\n"),
        ("services/ingestion/tests/test_thing.py", "from app.config import get_settings\n"),
        ("services/ingestion/app/tests/helpers.py", "from app.config import get_settings\n"),
        ("services/ingestion/conftest.py", "from app.config import get_settings\n"),
        ("scripts/thing.py", "from app.config import get_settings\n"),
        ("docs/archive/retired-topology/x.py", "from app.config import get_settings\n"),
    ],
)
def test_bare_app_import_guard_ignores_other_forms_and_places(tmp_path: Path, relative: str, line: str) -> None:
    path = _write(tmp_path, relative, line)
    assert _MODULE.check_bare_app_imports([path], tmp_path) == []
