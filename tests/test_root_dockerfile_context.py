from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile"


def _copy_sources_from_root_dockerfile() -> list[str]:
    sources: list[str] = []

    for raw_line in DOCKERFILE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or not line.startswith("COPY "):
            continue

        parts = shlex.split(line)
        if len(parts) < 3:
            continue

        # Build-stage copies are internal to Docker and do not depend on the
        # Git archive used by Railway uploads.
        if any(part.startswith("--from=") for part in parts[1:]):
            continue

        paths = [part for part in parts[1:] if not part.startswith("--")]
        sources.extend(paths[:-1])

    return sources


def test_root_dockerfile_copy_sources_exist_in_head_archive():
    missing: list[str] = []

    for source in _copy_sources_from_root_dockerfile():
        result = subprocess.run(
            ["git", "cat-file", "-e", f"HEAD:{source}"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            missing.append(source)

    assert missing == [], f"Root Dockerfile references paths that are not present in the clean HEAD archive: {missing}"


def test_migration_owner_credential_is_removed_before_runtime_starts():
    dockerfile = DOCKERFILE.read_text()

    migration = "bash /app/scripts/run-migrations.sh"
    credential_removal = "exec env -u MIGRATIONS_DATABASE_URL"
    runtime = "gunicorn server.main:app"
    assert migration in dockerfile
    assert credential_removal in dockerfile
    assert runtime in dockerfile
    assert dockerfile.index(migration) < dockerfile.index(credential_removal) < dockerfile.index(runtime)


def test_exec_boundary_removes_migration_credential_from_runtime_process():
    env = os.environ.copy()
    env["MIGRATIONS_DATABASE_URL"] = "schema-owner-secret"
    result = subprocess.run(
        [
            "env",
            "-u",
            "MIGRATIONS_DATABASE_URL",
            sys.executable,
            "-c",
            "import os; raise SystemExit("
            "1 if 'MIGRATIONS_DATABASE_URL' in os.environ else 0)",
        ],
        env=env,
        check=False,
    )
    assert result.returncode == 0
