"""
Centralised path resolution for RegEngine services.

Instead of fragile ``Path(__file__).parent.parent…`` chains scattered
across every service, import helpers from here.

Environment variables (set automatically in Docker via docker-compose.yml):
    SERVICE_ROOT  – absolute path to the service directory  (e.g. /app)
    PROJECT_ROOT  – absolute path to the repository root     (e.g. /code)

When neither is set the helpers fall back to heuristic detection so that
``python -m pytest`` still works on a developer laptop.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from functools import lru_cache


# ── Core resolvers ────────────────────────────────────────────────

@lru_cache(maxsize=1)
def project_root() -> Path:
    """Return the repository root (contains ``services/``, ``frontend/``, etc.)."""
    env = os.getenv("PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    # Heuristic: walk up from this file until we find ``docker-compose.yml``
    candidate = Path(__file__).resolve().parent  # shared/
    for _ in range(6):
        candidate = candidate.parent
        if (candidate / "docker-compose.yml").exists():
            return candidate
    # Ultimate fallback – assume shared/ lives at <root>/services/shared/
    return Path(__file__).resolve().parent.parent.parent


@lru_cache(maxsize=1)
def services_dir() -> Path:
    """Return ``<project_root>/services``."""
    return project_root() / "services"


@lru_cache(maxsize=1)
def shared_dir() -> Path:
    """Return ``<project_root>/services/shared``."""
    return project_root() / "services" / "shared"


@lru_cache(maxsize=1)
def data_schemas_dir() -> Path:
    """Return the ``data-schemas/`` directory at project root."""
    return project_root() / "data-schemas"


# ── sys.path helpers ──────────────────────────────────────────────

def ensure_shared_importable() -> None:
    """Add ``services/shared`` (and ``services/``) to ``sys.path`` if missing."""
    for p in (str(shared_dir()), str(services_dir())):
        if p not in sys.path:
            sys.path.insert(0, p)


def ensure_path(*extra: str | Path) -> None:
    """Add arbitrary paths to ``sys.path`` if not already present."""
    for p in extra:
        s = str(Path(p).resolve())
        if s not in sys.path:
            sys.path.insert(0, s)


# ── Resource resolution ──────────────────────────────────────────

def service_resource(service_name: str, *parts: str) -> Path:
    """Resolve a file inside a service directory.

    Example::

        service_resource("compliance", "plugins", "fsma.yaml")
        # → <project_root>/services/compliance/plugins/fsma.yaml
    """
    return services_dir() / service_name / Path(*parts)
