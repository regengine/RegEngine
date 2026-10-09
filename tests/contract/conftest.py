"""Shared fixtures for contract tests."""

import logging
import sys

import pytest

logger = logging.getLogger(__name__)


@pytest.fixture(autouse=True)
def _clear_admin_brute_force_state():
    """Clear privileged-auth counters in local Redis before each test.

    The admin contract ``client`` fixture sets
    ``REDIS_URL=redis://localhost:6379/0`` before importing the admin service,
    so the privileged-auth budget is Redis-backed whenever a local Redis is
    running. Failure counts for ip="testclient" then persist
    across pytest processes: two suite runs within the 60s window poison each
    other, and tests expecting 401/403 get 429 instead.

    Only localhost is flushed -- a remote REDIS_URL must never be touched, and
    production stays Redis-backed (#1392).
    """
    try:
        import redis
    except ImportError as exc:
        # The redis client is not installed, so the limiter always uses its
        # in-memory fallback; there is no Redis state to clear.
        logger.debug(
            "skipping privileged-auth Redis cleanup: client not installed (%s)",
            exc,
        )
    else:
        try:
            client = redis.Redis.from_url(
                "redis://localhost:6379/0",
                socket_connect_timeout=0.5,
                socket_timeout=0.5,
            )
            keys = list(client.scan_iter("privileged_auth:*"))
            if keys:
                client.delete(*keys)
        except (
            redis.exceptions.ConnectionError,
            redis.exceptions.TimeoutError,
        ) as exc:
            # No local Redis -> the limiter falls back to in-memory and each
            # pytest process starts clean; nothing to clear.
            logger.warning(
                "skipping privileged-auth Redis cleanup: local Redis unavailable (%s)",
                exc,
            )

    for module_name in ("app.privileged_auth", "services.admin.app.privileged_auth"):
        module = sys.modules.get(module_name)
        throttle = getattr(module, "_privileged_auth_throttle", None) if module else None
        if throttle is None:
            continue
        with throttle._memory_lock:
            throttle._memory.clear()


@pytest.fixture(scope="module")
def published_spec():
    """Load the authoritative TypeScript export, without a stale generated asset."""
    import json
    import subprocess
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[2] / "frontend"
    script = """
const fs = require('node:fs');
const ts = require('typescript');
const source = fs.readFileSync('src/lib/public-openapi.ts', 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS }
}).outputText;
const exported = { exports: {} };
new Function('exports', 'module', compiled)(exported.exports, exported);
process.stdout.write(JSON.stringify(exported.exports.publicOpenApiSpec));
"""

    def load(env=None):
        result = subprocess.run(
            ["node", "-e", script],
            cwd=frontend,
            env=env,
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        return json.loads(result.stdout)

    return load
