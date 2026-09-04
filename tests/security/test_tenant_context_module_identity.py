"""Production must load one authoritative tenant-context module and hook."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_SOURCE_ROOTS = (
    REPO_ROOT / "regengine",
    REPO_ROOT / "server",
    REPO_ROOT / "services",
)
FORBIDDEN_PREFIX = "services.shared"


def _is_forbidden_module(module_name: str) -> bool:
    return module_name == FORBIDDEN_PREFIX or module_name.startswith(f"{FORBIDDEN_PREFIX}.")


def _forbidden_imports(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and _is_forbidden_module(node.module):
            violations.append(node.lineno)
        elif isinstance(node, ast.Import):
            if any(_is_forbidden_module(alias.name) for alias in node.names):
                violations.append(node.lineno)
    return violations


def test_production_source_uses_only_canonical_shared_imports() -> None:
    violations: list[str] = []
    for source_root in PRODUCTION_SOURCE_ROOTS:
        for path in source_root.rglob("*.py"):
            if "tests" in path.parts:
                continue
            for line in _forbidden_imports(path):
                violations.append(f"{path.relative_to(REPO_ROOT)}:{line}")

    assert violations == [], (
        "Production code must import shared.* through its canonical package so "
        f"classes, singletons, hooks, and ContextVars have one identity; found: {violations}"
    )


def test_production_pythonpath_loads_one_module_contextvar_and_listener() -> None:
    """Exercise the lazy persistence imports that previously registered twice."""

    script = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path
        from types import SimpleNamespace

        from sqlalchemy import create_engine
        import shared.tenant_context as tenant_context
        from shared.canonical_persistence.writer import CanonicalEventStore
        from shared.cte_persistence.core import CTEPersistence
        from shared.exception_queue import ExceptionQueueService

        tenant_id = "11111111-1111-1111-1111-111111111111"
        session = SimpleNamespace(
            bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
            execute=lambda *args, **kwargs: None,
        )

        # These methods used lazy services.shared.tenant_context imports. Calling
        # them is the realistic trigger for the duplicate module/listener bug.
        CTEPersistence(session).set_tenant_context(tenant_id)
        CanonicalEventStore(session).set_tenant_context(tenant_id)
        ExceptionQueueService(session).set_tenant_context(tenant_id)

        canonical_file = Path(tenant_context.__file__).resolve()
        loaded_names = sorted(
            name
            for name, module in sys.modules.items()
            if getattr(module, "__file__", None)
            and Path(module.__file__).resolve() == canonical_file
        )

        calls = []
        fake_connection = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
            execute=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        engine = create_engine("sqlite:///:memory:")
        try:
            engine.dispatch.begin(fake_connection)
        finally:
            engine.dispose()

        assert loaded_names == ["shared.tenant_context"], loaded_names
        assert len(calls) == 1, f"expected one begin hook baseline; observed {len(calls)}"
        assert tenant_context._rls_tenant_id is sys.modules[loaded_names[0]]._rls_tenant_id
        print(json.dumps({"loaded_names": loaded_names, "listener_calls": len(calls)}))
        """
    )

    env = os.environ.copy()
    production_paths = (
        REPO_ROOT,
        REPO_ROOT / "services",
        REPO_ROOT / "services" / "ingestion",
        REPO_ROOT / "services" / "admin",
        REPO_ROOT / "services" / "graph",
        REPO_ROOT / "services" / "nlp",
        REPO_ROOT / "services" / "compliance",
    )
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in production_paths)
    env["REGENGINE_ENV"] = "test"

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, (
        f"isolated production import failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
