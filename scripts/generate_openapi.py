#!/usr/bin/env python3
"""
Generate the curated public OpenAPI 3.0 spec for RegEngine.

WHY THIS EXISTS
---------------
In production every FastAPI service sets `openapi_url=None`, so there is no
live `/openapi.json` to scrape. Customers and integrators still need a stable,
machine-readable contract for the public REST surface (Inflow Lab connector,
future SDK codegen, OpenAPI viewers).

This script imports the ingestion FastAPI app at build time, runs the
`openapi()` introspection in-process, applies an allowlist + denylist to
strip anything internal, and writes the result to
`frontend/public/openapi.json` so it is served as a plain static asset from
`https://regengine.co/openapi.json`. The backend services stay closed: no
network gate is flipped.

WHAT IS PUBLIC
--------------
A path is included in the curated spec when it passes BOTH filters:

1. DENY (drop the route, regardless of opt-in):
   - Path starts with any prefix in `INTERNAL_PREFIXES`
     (`/internal/`, `/admin/`, `/debug/`, `/kernel/`, `/control/`,
      `/api/v1/regulatory/` — internal pipeline)
   - ANY operation under the path carries a tag in `INTERNAL_TAGS`
     (`internal`, `admin`, `debug`, `kernel`, `control`)

2. ALLOW (must opt in via at least one of):
   - The path prefix appears in `PUBLIC_PREFIX_ALLOWLIST`, OR
   - At least one operation on the path carries the `public` tag.

Routes that pass neither rule are excluded. This is intentional: the default
posture is "private until explicitly published". To expose a new route,
either add `tags=["public", ...]` on the FastAPI handler or add its prefix
to `PUBLIC_PREFIX_ALLOWLIST` below.

DRIFT CHECK
-----------
CI runs this script and `git diff --exit-code frontend/public/openapi.json`.
If the committed spec is stale, the job fails and the dev must regenerate +
commit. This keeps the published contract in lockstep with the code without
shipping a live `/openapi.json` endpoint.

USAGE
-----
    python scripts/generate_openapi.py                 # write + exit 0
    python scripts/generate_openapi.py --check         # exit 1 if stale
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
INGESTION_DIR = REPO_ROOT / "services" / "ingestion"
SERVICES_DIR = REPO_ROOT / "services"
OUTPUT_PATH = REPO_ROOT / "frontend" / "public" / "openapi.json"

# Default-deny: any path that starts with one of these is dropped before the
# allowlist even runs.
INTERNAL_PREFIXES: tuple[str, ...] = (
    "/internal/",
    "/admin/",
    "/debug/",
    "/kernel/",
    "/control/",
    "/api/v1/regulatory/",  # internal regulatory pipeline
)

# Operations carrying any of these tags are treated as internal and the whole
# path is dropped.
INTERNAL_TAGS: frozenset[str] = frozenset(
    {"internal", "admin", "debug", "kernel", "control"}
)

# Opt-in allowlist of public prefixes. Any path under one of these is
# eligible (subject to the deny filter above). New customer-facing routes
# should add their prefix here OR tag their handler with `public`.
PUBLIC_PREFIX_ALLOWLIST: tuple[str, ...] = (
    # Liveness — useful for status pages and integration smoke tests.
    "/health",
    "/healthz",
    # Public ingestion surface (versioned under /api/v1/ and /v1/).
    # NOTE: every prefix added here MUST be reviewed for tenant-scoping and
    # auth coverage before merge — once it lands in the public spec,
    # integrators will start calling it.
    "/api/v1/ingest",
    "/api/v1/epcis",
    "/api/v1/fda",
    "/api/v1/recall",
    "/api/v1/export",
    "/api/v1/monitoring",
    "/api/v1/readiness",
    "/api/v1/webhooks",
    "/api/v1/qr",
    "/v1/ingest/",
    "/v1/verify/",
)

# Single opt-in tag for routes that don't fit the prefix allowlist.
PUBLIC_TAG: str = "public"

# Public-facing metadata.
PUBLIC_TITLE: str = "RegEngine Public API"
PUBLIC_VERSION: str = "1.0.0"
PUBLIC_SERVER_URL: str = "https://regengine.co/api/ingestion"
PUBLIC_SERVER_DESCRIPTION: str = (
    "Production ingestion API (Vercel proxy → Railway backend)"
)


def _bootstrap_imports() -> None:
    """Mirror the bootstrap dance services/ingestion/main.py does on startup."""
    for p in (str(INGESTION_DIR), str(SERVICES_DIR), str(REPO_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)

    # Provide minimal env so `require_env` and friends don't blow up during
    # import. We never connect to anything — we only call `app.openapi()`.
    os.environ.setdefault(
        "DATABASE_URL", "postgresql://openapi:openapi@localhost:5432/openapi"
    )
    os.environ.setdefault("JWT_SECRET", "openapi-generator-dummy-secret")
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
    os.environ.setdefault("SUPABASE_KEY", "openapi-generator-dummy-key")
    os.environ.setdefault("ADMIN_MASTER_KEY", "openapi-generator-dummy-master")
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "openapi-generator-dummy")


def _load_ingestion_app() -> Any:
    _bootstrap_imports()
    # Local import only after bootstrap.
    from services.ingestion.main import app  # type: ignore[import-not-found]

    return app


def _is_internal_path(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in INTERNAL_PREFIXES)


def _operation_tags(operation: dict[str, Any]) -> set[str]:
    return {str(t).lower() for t in operation.get("tags", []) or []}


def _path_has_internal_tag(path_item: dict[str, Any]) -> bool:
    for method, op in path_item.items():
        if method.lower() not in {
            "get",
            "put",
            "post",
            "delete",
            "options",
            "head",
            "patch",
            "trace",
        }:
            continue
        if _operation_tags(op) & INTERNAL_TAGS:
            return True
    return False


def _path_has_public_optin(path: str, path_item: dict[str, Any]) -> bool:
    if any(path.startswith(prefix) for prefix in PUBLIC_PREFIX_ALLOWLIST):
        return True
    for method, op in path_item.items():
        if method.lower() not in {
            "get",
            "put",
            "post",
            "delete",
            "options",
            "head",
            "patch",
            "trace",
        }:
            continue
        if PUBLIC_TAG in _operation_tags(op):
            return True
    return False


def _filter_paths(paths: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path, path_item in paths.items():
        if _is_internal_path(path):
            continue
        if _path_has_internal_tag(path_item):
            continue
        if not _path_has_public_optin(path, path_item):
            continue
        out[path] = path_item
    return out


def _used_schema_refs(node: Any, found: set[str]) -> None:
    """Walk a JSON-like tree and collect every `#/components/schemas/X` ref."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "$ref" and isinstance(v, str) and v.startswith(
                "#/components/schemas/"
            ):
                found.add(v.rsplit("/", 1)[-1])
            else:
                _used_schema_refs(v, found)
    elif isinstance(node, list):
        for item in node:
            _used_schema_refs(item, found)


def _prune_components(spec: dict[str, Any]) -> None:
    """Drop schemas no longer referenced after path filtering. Iterative —
    schemas may reference other schemas transitively."""
    schemas = spec.get("components", {}).get("schemas", {})
    if not schemas:
        return

    used: set[str] = set()
    _used_schema_refs(spec.get("paths", {}), used)

    # Transitive closure
    changed = True
    while changed:
        changed = False
        for name in list(used):
            schema = schemas.get(name)
            if schema is None:
                continue
            before = len(used)
            _used_schema_refs(schema, used)
            if len(used) != before:
                changed = True

    spec["components"]["schemas"] = {
        name: schema for name, schema in schemas.items() if name in used
    }


def build_public_spec() -> dict[str, Any]:
    app = _load_ingestion_app()
    spec = app.openapi()

    # Deep copy by JSON round-trip so we don't mutate FastAPI's cached spec.
    spec = json.loads(json.dumps(spec))

    spec["info"] = {
        "title": PUBLIC_TITLE,
        "version": PUBLIC_VERSION,
        "description": (
            "Curated public REST API for the RegEngine FSMA 204 platform. "
            "Generated at build time from the ingestion service; internal, "
            "admin, and control-plane routes are excluded. Source of truth: "
            "`scripts/generate_openapi.py` in the RegEngine repo."
        ),
        "contact": {
            "name": "RegEngine Support",
            "url": "https://regengine.co/contact",
        },
        "license": {"name": "Proprietary"},
    }
    spec["servers"] = [
        {"url": PUBLIC_SERVER_URL, "description": PUBLIC_SERVER_DESCRIPTION}
    ]

    spec["paths"] = _filter_paths(spec.get("paths", {}))
    _prune_components(spec)

    # Sort top-level keys for stable diffs.
    return {k: spec[k] for k in sorted(spec.keys())}


def _serialize(spec: dict[str, Any]) -> str:
    # Deterministic: sorted keys + trailing newline.
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if frontend/public/openapi.json is stale.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Output path (default: frontend/public/openapi.json).",
    )
    args = parser.parse_args()

    spec = build_public_spec()
    serialized = _serialize(spec)

    if args.check:
        if not args.output.exists():
            print(
                f"::error::{args.output} does not exist. "
                "Run `python scripts/generate_openapi.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        current = args.output.read_text()
        if current != serialized:
            print(
                f"::error::{args.output} is out of date. "
                "Run `python scripts/generate_openapi.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {args.output} matches generated spec.")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialized)
    print(
        f"Wrote {args.output} "
        f"({len(spec.get('paths', {}))} public paths, "
        f"{len(spec.get('components', {}).get('schemas', {}))} schemas)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
