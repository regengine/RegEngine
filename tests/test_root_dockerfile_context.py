from __future__ import annotations

import shlex
import subprocess
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

        paths = [
            part
            for part in parts[1:]
            if not part.startswith("--")
        ]
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

    assert missing == [], (
        "Root Dockerfile references paths that are not present in the clean "
        f"HEAD archive: {missing}"
    )
