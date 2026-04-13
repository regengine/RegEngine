#!/usr/bin/env python3
"""CI lint: ensure all FastAPI route handlers declare response_model.

Scans all *_routes.py and routes.py files across services/ and flags
any @router.{method}(...) decorator missing the response_model= parameter.

Exempt patterns:
  - /health, /ready, /metrics endpoints (return JSONResponse directly)
  - WebSocket routes
  - Routes that return StreamingResponse / FileResponse / JSONResponse

Exit code 0 = all routes have response_model (or are exempt).
Exit code 1 = violations found.

Usage:
    python scripts/lint_response_models.py          # check all services
    python scripts/lint_response_models.py --fix     # future: auto-add stubs
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Paths that are exempt from response_model requirement
EXEMPT_ROUTE_PATTERNS = {
    "/health",
    "/ready",
    "/metrics",
    "/health/consumer",
}

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def find_route_files() -> list[Path]:
    """Find all route files across services."""
    root = Path(__file__).resolve().parent.parent / "services"
    files = []
    for p in root.rglob("*.py"):
        if "routes" in p.name or p.name == "routes.py":
            files.append(p)
    return sorted(files)


def check_file(filepath: Path) -> list[dict]:
    """Check a single file for routes missing response_model."""
    violations = []
    try:
        source = filepath.read_text()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Look at decorators
        for deco in node.decorator_list:
            route_path = None
            has_response_model = False
            method = None

            # @router.get("/path", ...) or @v1_router.post("/path", ...)
            if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                attr_name = deco.func.attr
                if attr_name not in HTTP_METHODS:
                    continue

                method = attr_name.upper()

                # Extract route path from first positional arg
                if deco.args and isinstance(deco.args[0], ast.Constant):
                    route_path = deco.args[0].value

                # Check for response_model keyword
                for kw in deco.keywords:
                    if kw.arg == "response_model":
                        has_response_model = True
                        break

                # Check exemptions
                if route_path and any(route_path.rstrip("/") == ex.rstrip("/") for ex in EXEMPT_ROUTE_PATTERNS):
                    continue

                # Check if function body returns StreamingResponse/FileResponse/JSONResponse
                func_source = ast.get_source_segment(source, node)
                if func_source and re.search(r"\b(StreamingResponse|FileResponse|JSONResponse)\b", func_source):
                    continue

                if not has_response_model:
                    violations.append({
                        "file": str(filepath.relative_to(Path(__file__).resolve().parent.parent)),
                        "line": node.lineno,
                        "function": node.name,
                        "method": method,
                        "route": route_path or "unknown",
                    })

    return violations


def main():
    files = find_route_files()
    all_violations = []

    for f in files:
        violations = check_file(f)
        all_violations.extend(violations)

    if not all_violations:
        print(f"✅ All routes in {len(files)} files have response_model (or are exempt)")
        sys.exit(0)

    print(f"❌ {len(all_violations)} routes missing response_model:\n")
    for v in all_violations:
        print(f"  {v['file']}:{v['line']}  {v['method']} {v['route']}  ({v['function']})")

    print(f"\n  Total: {len(all_violations)} violations across {len(files)} files")
    sys.exit(1)


if __name__ == "__main__":
    main()
