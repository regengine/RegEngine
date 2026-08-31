#!/usr/bin/env python3
"""Reject raw HTTP clients in release-enabled outbound-fetch paths.

The listed modules are reachable from the consolidated production process and
either consume a caller/configured URL or perform an enabled regulatory fetch.
All network I/O in them must be routed through ``shared.safe_http`` so DNS is
validated and the connection is IP-pinned for every redirect/request.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

ENABLED_OUTBOUND_HTTP_PATHS = (
    Path("services/admin/app/tool_verification_routes.py"),
    Path("services/admin/app/webhook_outbox.py"),
    Path("services/ingestion/app/routes_ingest.py"),
    Path("services/ingestion/app/task_handlers_regulation.py"),
    Path("services/scheduler/app/notifications.py"),
    Path("services/scheduler/app/scrapers/base.py"),
    Path("services/scheduler/app/scrapers/fda_import_alerts.py"),
    Path("services/scheduler/app/scrapers/fda_recalls.py"),
    Path("services/scheduler/app/scrapers/fda_warning_letters.py"),
)

_RAW_MODULE_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "request",
    "stream",
    "Client",
    "AsyncClient",
    "Session",
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    call: str


def _qualified_name(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, ast.Attribute):
        return (*_qualified_name(node.value), node.attr)
    return ()


def scan_source(path: Path, source: str) -> list[Violation]:
    """Return direct ``httpx``/``requests`` call sites in ``source``."""
    tree = ast.parse(source, filename=str(path))
    module_aliases: dict[str, str] = {}
    direct_aliases: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in {"httpx", "requests"}:
                    module_aliases[alias.asname or alias.name] = root
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            if root in {"httpx", "requests"}:
                for alias in node.names:
                    if alias.name in _RAW_MODULE_METHODS:
                        direct_aliases[alias.asname or alias.name] = f"{root}.{alias.name}"
                    else:
                        module_aliases[alias.asname or alias.name] = root

    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _qualified_name(node.func)
        rendered: str | None = None
        if len(name) == 1 and name[0] in direct_aliases:
            rendered = direct_aliases[name[0]]
        elif len(name) == 2 and name[0] in module_aliases and name[1] in _RAW_MODULE_METHODS:
            rendered = f"{module_aliases[name[0]]}.{name[1]}"
        if rendered is not None:
            violations.append(Violation(path=path, line=node.lineno, call=rendered))

    return sorted(violations, key=lambda item: (str(item.path), item.line, item.call))


def validate_paths(root: Path = REPO_ROOT, paths: Iterable[Path] = ENABLED_OUTBOUND_HTTP_PATHS) -> list[Violation]:
    violations: list[Violation] = []
    for relative_path in paths:
        absolute_path = root / relative_path
        if not absolute_path.is_file():
            violations.append(Violation(relative_path, 0, "missing security-inventory path"))
            continue
        violations.extend(scan_source(relative_path, absolute_path.read_text(encoding="utf-8")))
    return sorted(violations, key=lambda item: (str(item.path), item.line, item.call))


def main() -> int:
    violations = validate_paths()
    if violations:
        for violation in violations:
            print(f"{violation.path}:{violation.line}: direct outbound call {violation.call}")
        print("Route enabled outbound HTTP through services/shared/safe_http.py")
        return 1
    print(f"Enabled outbound HTTP guard passed for {len(ENABLED_OUTBOUND_HTTP_PATHS)} paths.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
