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
INTERNAL_TAGS: frozenset[str] = frozenset({"internal", "admin", "debug", "kernel", "control"})

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
PUBLIC_SERVER_DESCRIPTION: str = "Production ingestion API (Vercel proxy → Railway backend)"


def _bootstrap_imports() -> None:
    """Mirror the bootstrap dance services/ingestion/main.py does on startup."""
    for p in (str(INGESTION_DIR), str(SERVICES_DIR), str(REPO_ROOT)):
        if p not in sys.path:
            sys.path.insert(0, p)

    # Provide minimal env so `require_env` and friends don't blow up during
    # import. We never connect to anything — we only call `app.openapi()`.
    os.environ.setdefault("DATABASE_URL", "postgresql://openapi:openapi@localhost:5432/openapi")
    os.environ.setdefault("JWT_SECRET", "openapi-generator-dummy-secret")
    os.environ.setdefault("ENVIRONMENT", "development")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("SUPABASE_URL", "http://localhost:54321")
    os.environ.setdefault("SUPABASE_KEY", "openapi-generator-dummy-key")
    os.environ.setdefault("ADMIN_MASTER_KEY", "openapi-generator-dummy-master")
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USER", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "openapi-generator-dummy")


# Placeholder secrets for the import below (#2861). `server.main` validates
# secret material at import time, so these must be long and non-obvious enough
# to survive that check — including if `REGENGINE_REQUIRE_SECURE_SECRETS` is
# ever enabled, which #2808 argues it should be. They are used to build a
# schema and nothing else: this process never serves a request or opens a
# socket, and the values never leave it.
_IMPORT_ONLY_ENV: dict[str, str] = {
    # Reproduces the production router gate. `_router_enabled` consults
    # `_is_prod`, derived from REGENGINE_ENV, and there is no narrower switch.
    "REGENGINE_ENV": "production",
    "ENV": "production",
    "DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_DATABASE_URL": "sqlite:///:memory:",
    "ADMIN_FALLBACK_SQLITE": "1",
    "AUTH_SECRET_KEY": "openapi-generator-import-only-not-a-real-secret-4f2b",
    "JWT_SECRET": "openapi-generator-import-only-not-a-real-jwt-secret-9c7e",
    "REGENGINE_API_KEY": "openapi-generator-import-only-not-a-real-api-key-1a3d",
    "TOOL_ACCESS_SECRET": "openapi-generator-import-only-not-a-real-tool-secret-8e5c",
}


def _load_production_app() -> Any:
    """Build the app the production monolith actually serves (#2861).

    This used to import ``services/ingestion/main.py``. That entrypoint has no
    experimental-router gate, so the published spec advertised 9 paths that are
    not mounted in production — 20% of the public contract, 404 for every
    integrator and every SDK generated from it. Worse, the
    ``openapi-public-spec`` workflow enforces that the committed file matches
    the generator, so the drift was locked in and looked verified.

    Deriving the spec from ``server.main`` under the production environment
    removes the class of drift rather than patching this instance: a router
    that becomes experimental drops out of the published contract on the next
    regeneration, with no list here to maintain.

    Note the two apps cannot both be loaded in one process. The ingestion
    entrypoint calls ``assert_legacy_entrypoint_not_in_production`` and raises
    under ``REGENGINE_ENV=production``, which is exactly the environment this
    needs — so this is a replacement, not an addition.
    """
    import os

    _bootstrap_imports()
    # ASSIGNED, not setdefault. The published contract must be a function of
    # the code alone, never of whoever ran the generator. `setdefault` looks
    # equivalent and is not: under pytest, or for any developer with
    # REGENGINE_ENV=development exported, the inherited value wins and the
    # generator silently builds the NON-production app — mounting every
    # experimental router and reproducing exactly the #2861 drift this
    # function exists to remove.
    for key, value in _IMPORT_ONLY_ENV.items():
        os.environ[key] = value
    # Test-only variables that the production config validator rejects. A
    # developer or CI job with these exported would otherwise see the generator
    # fail with an auth-config error that has nothing to do with the schema.
    for _test_only in ("AUTH_TEST_BYPASS_TOKEN", "ALLOW_LEGACY_ENTRYPOINT_IN_PROD"):
        os.environ.pop(_test_only, None)

    # Deployment knobs that legitimately vary per environment but MUST NOT
    # reach a published contract. `ENABLE_EXPERIMENTAL_ROUTERS=1` re-mounts
    # every experimental router, putting all 9 paths #2861 removed straight
    # back into the spec; `DISABLED_ROUTERS` drops arbitrary live ones. Either
    # would make the committed spec a function of whoever ran the generator,
    # and the drift-check workflow would then enforce that accident.
    #
    # The published contract is defined as: default production posture, no
    # per-deploy overrides. Anyone needing an experimental route documented
    # should promote it out of _EXPERIMENTAL_ROUTERS, not export a flag.
    for _override in ("ENABLE_EXPERIMENTAL_ROUTERS", "DISABLED_ROUTERS"):
        os.environ.pop(_override, None)

    # Local import only after bootstrap and env setup.
    from server.main import app  # type: ignore[import-not-found]

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
            if k == "$ref" and isinstance(v, str) and v.startswith("#/components/schemas/"):
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

    spec["components"]["schemas"] = {name: schema for name, schema in schemas.items() if name in used}


# --- Real error envelope (#2863) ------------------------------------------
#
# FastAPI auto-documents 422 as HTTPValidationError -> {"detail": [...]}, but
# this application installs its own handlers (shared/error_handling.py:
# install_exception_handlers), so NOTHING ever returns a top-level `detail`.
# Publishing FastAPI's default meant every generated SDK parsed a field that
# is never present, and error handling silently degraded to "unknown error"
# on the most common 4xx.
#
# Three producers reach a client error, and after #2863's normalization they
# share one envelope -- `error.type` and `error.message` are always present:
#
#   RequestValidationError handler  -> type "validation_error", plus `details`
#   HTTPException(422, "text")      -> type "http_422"
#   HTTPException(422, {...})       -> the dict's own `type`/`code`, preserved
#
# `additionalProperties: true` on the inner object is deliberate: dict-detail
# call sites keep their bespoke fields (`code`, `errors`, ...), and a schema
# that forbade them would be a second inaccurate spec.

_ERROR_ENVELOPE_SCHEMA_NAME = "ErrorEnvelope"

_ERROR_ENVELOPE_SCHEMA: dict[str, Any] = {
    "title": "ErrorEnvelope",
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["type", "message"],
            "additionalProperties": True,
            "properties": {
                "type": {
                    "type": "string",
                    "description": (
                        "Machine-readable error class. 'validation_error' for request "
                        "validation failures, 'http_<status>' for unclassified errors, "
                        "or a domain code such as 'E_NO_TENANT'."
                    ),
                },
                "message": {"type": "string", "description": "Human-readable summary."},
                "details": {
                    "type": "array",
                    "description": "Per-field validation errors. Present for 'validation_error'.",
                    "items": {"type": "object", "additionalProperties": True},
                },
            },
        }
    },
}


def _apply_real_error_envelope(spec: dict[str, Any]) -> None:
    """Point every documented 4xx/5xx response at the envelope actually returned."""
    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    schemas[_ERROR_ENVELOPE_SCHEMA_NAME] = _ERROR_ENVELOPE_SCHEMA
    ref = {"$ref": f"#/components/schemas/{_ERROR_ENVELOPE_SCHEMA_NAME}"}

    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for status, response in (operation.get("responses") or {}).items():
                if not (isinstance(status, str) and status[:1] in {"4", "5"}):
                    continue
                if not isinstance(response, dict):
                    continue
                response["content"] = {"application/json": {"schema": dict(ref)}}


def build_public_spec() -> dict[str, Any]:
    app = _load_production_app()
    spec = app.openapi()

    # Deep copy by JSON round-trip so we don't mutate FastAPI's cached spec.
    spec = json.loads(json.dumps(spec))

    spec["info"] = {
        "title": PUBLIC_TITLE,
        "version": PUBLIC_VERSION,
        "description": (
            "Curated public REST API for the RegEngine FSMA 204 platform. "
            "Generated at build time from the production monolith; internal, "
            "admin, and control-plane routes are excluded. Source of truth: "
            "`scripts/generate_openapi.py` in the RegEngine repo."
        ),
        "contact": {
            "name": "RegEngine Support",
            "url": "https://regengine.co/contact",
        },
        "license": {"name": "Proprietary"},
    }
    spec["servers"] = [{"url": PUBLIC_SERVER_URL, "description": PUBLIC_SERVER_DESCRIPTION}]

    spec["paths"] = _filter_paths(spec.get("paths", {}))
    _apply_real_error_envelope(spec)
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
