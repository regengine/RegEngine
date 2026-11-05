"""Ingestion code must import its own modules relatively.

The consolidated server (``server/main.py``) puts every service directory on
``sys.path``, and each service ships a top-level package named ``app``. Only
one of them wins (currently ``services/graph/app``), so inside the production
image an absolute ``from app.X import ...`` in ingestion either raises
``ModuleNotFoundError`` or, worse, silently loads another service's ``app.X``
(``app.config`` resolved to graph's ``Settings``, which has no ``redis_url``).
Unit tests put ``services/ingestion`` first on the path and never see it.
"""

from __future__ import annotations

import ast
from pathlib import Path

INGESTION_APP = Path(__file__).resolve().parent.parent / "app"

# Absolute imports that open PRs already remove. Delete an entry once its fix
# lands; never add one.
PENDING_ELSEWHERE = {
    ("webhook_compat.py", "app.tenant_validation"),  # PR #3774
    ("edi_ingestion/routes.py", "app.edi_ingestion.rejection_log"),  # fix/csv-edi-ingest-monolith-imports
}


def _absolute_app_imports(path: Path) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif (
            isinstance(node, ast.Call)
            and getattr(node.func, "attr", getattr(node.func, "id", None)) == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names = [node.args[0].value]
        else:
            continue
        found.extend((node.lineno, name) for name in names if name == "app" or name.startswith("app."))
    return found


def test_ingestion_app_has_no_new_absolute_app_imports() -> None:
    offenders = [
        f"{path.relative_to(INGESTION_APP).as_posix()}:{lineno} imports {module}"
        for path in sorted(INGESTION_APP.rglob("*.py"))
        for lineno, module in _absolute_app_imports(path)
        if (path.relative_to(INGESTION_APP).as_posix(), module) not in PENDING_ELSEWHERE
    ]
    assert offenders == [], "use a relative import (from .x / from ..x):\n" + "\n".join(offenders)
