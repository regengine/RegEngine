#!/usr/bin/env python3
"""Generate or verify the route-complete production security manifest."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "docs" / "security" / "route-security-manifest.json"
PRODUCTION_RESULT_MARKER = "ROUTE_SECURITY_PRODUCTION_RESULT="

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _configure_inventory_import() -> None:
    """Force a deterministic local/test import that mounts every router."""

    for key in (
        "ADMIN_DATABASE_URL",
        "DATABASE_URL",
        "DISABLED_ROUTERS",
        "ENABLED_ROUTERS",
        "ENABLE_EXPERIMENTAL_ROUTERS",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_ENVIRONMENT_ID",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
    ):
        os.environ.pop(key, None)
    os.environ.update(
        {
            "ADMIN_FALLBACK_SQLITE": "sqlite:///:memory:",
            "AUTH_SECRET_KEY": "route-manifest-local-generation-secret",  # pragma: allowlist secret
            "ENV": "test",
            "METRICS_API_KEY": "route-manifest-local-metrics",  # pragma: allowlist secret
            "RATE_LIMIT_FAIL_MODE": "closed",
            "REGENGINE_ENV": "test",
        }
    )


def _load_inventory_app():
    _configure_inventory_import()
    from server.main import app

    return app


def _generate_manifest() -> dict[str, Any]:
    from server.route_security_manifest import build_route_security_manifest

    return build_route_security_manifest(_load_inventory_app())


def _manifest_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"


def _production_environment() -> dict[str, str]:
    from cryptography.fernet import Fernet

    from server.router_policy import PRODUCTION_ENABLED_ROUTERS

    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RAILWAY_")
        and key
        not in {
            "ADMIN_FALLBACK_SQLITE",
            "AUTH_ALLOW_LEGACY_JTI_FREE",
            "AUTH_TEST_BYPASS_TOKEN",
            "DISABLED_ROUTERS",
            "ENABLED_ROUTERS",
            "ENABLE_EXPERIMENTAL_ROUTERS",
            "ENV",
            "REGENGINE_ENV",
        }
    }
    database_url = "postgresql://regengine_route_manifest:local-only@localhost:5432/regengine_route_manifest"  # pragma: allowlist secret
    env.update(
        {
            "ADMIN_DATABASE_URL": database_url,
            "AUTH_SECRET_KEY": "route-manifest-production-check-secret",  # pragma: allowlist secret
            "DATABASE_URL": database_url,
            "ENABLED_ROUTERS": ",".join(sorted(PRODUCTION_ENABLED_ROUTERS)),
            "METRICS_API_KEY": "route-manifest-production-metrics",  # pragma: allowlist secret
            # Strict auth refuses to boot without a valid Fernet key (#3238);
            # generated per run so no key material lives in this file.
            "MFA_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "RATE_LIMIT_FAIL_MODE": "closed",
            "REDIS_URL": "redis://localhost:6379/15",
            "REGENGINE_ENV": "production",
            "RAILWAY_ENVIRONMENT_NAME": "production",
            "SESSION_STORE_BACKEND": "database",
            "TOOL_ACCESS_SECRET": "route-manifest-production-tool-access",  # pragma: allowlist secret
        }
    )
    return env


def _expected_snapshot(manifest: dict[str, Any]) -> list[dict[str, str]]:
    fields = ("operation", "owner", "method", "path")
    return sorted(
        [{field: item[field] for field in fields} for item in manifest["enabled_operations"]],
        key=lambda item: (item["path"], item["method"], item["owner"]),
    )


def _verify_actual_production_import(manifest: dict[str, Any]) -> dict[str, int]:
    command = [sys.executable, str(Path(__file__).resolve()), "--production-child"]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=_production_environment(),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Production route verification failed.\n"
            f"stdout tail:\n{result.stdout[-4000:]}\n"
            f"stderr tail:\n{result.stderr[-4000:]}"
        )
    marker_line = next(
        (line for line in result.stdout.splitlines() if line.startswith(PRODUCTION_RESULT_MARKER)),
        None,
    )
    if marker_line is None:
        raise RuntimeError("Production route verification returned no result marker")
    payload = json.loads(marker_line.removeprefix(PRODUCTION_RESULT_MARKER))
    if payload.get("snapshot") != _expected_snapshot(manifest):
        raise RuntimeError("Actual production route table differs from the checked-in enabled operation manifest")
    return {
        "enabled_operations": len(payload["snapshot"]),
        "omitted_operations_probed": int(payload["omitted_operations_probed"]),
    }


def _production_child() -> int:
    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"Manifest not found: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    from server.main import app
    from server.route_security_manifest import probe_omitted_paths_exact_404, production_operation_snapshot

    snapshot = production_operation_snapshot(app)
    omitted_operations_probed = probe_omitted_paths_exact_404(app, manifest)
    print(
        PRODUCTION_RESULT_MARKER
        + json.dumps(
            {
                "snapshot": snapshot,
                "omitted_operations_probed": omitted_operations_probed,
            },
            separators=(",", ":"),
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--write", action="store_true", help="Write the deterministic manifest")
    action.add_argument("--check", action="store_true", help="Fail if the checked-in manifest is stale")
    parser.add_argument("--production-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.production_child:
        return _production_child()

    manifest = _generate_manifest()
    rendered = _manifest_text(manifest)
    if args.write:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST_PATH.write_text(rendered, encoding="utf-8")
    else:
        if not MANIFEST_PATH.exists():
            print(f"Route security manifest is missing: {MANIFEST_PATH}", file=sys.stderr)
            return 1
        checked_in = MANIFEST_PATH.read_text(encoding="utf-8")
        if checked_in != rendered:
            print(
                "Route security manifest is stale. Run: python scripts/generate_route_security_manifest.py --write",
                file=sys.stderr,
            )
            return 1

    verification = _verify_actual_production_import(manifest)
    print(
        "Route security manifest verified: "
        f"{verification['enabled_operations']} enabled operations; "
        f"{verification['omitted_operations_probed']} omitted operations returned exact 404."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
