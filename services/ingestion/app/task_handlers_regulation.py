"""Task-queue handler for regulation ingestion (ADR-002 PR-E).

Registers one task type:
  - ``regulation_ingest`` — processes a regulation file staged at a local
    path, replacing the Redis-as-blob-store pattern from the old
    BackgroundTasks path.

Staging contract:
  The route writes the uploaded file to ``{INGEST_STAGING_DIR}/{job_id}.{ext}``
  before enqueuing.  This handler reads from that path, processes the file,
  and removes the staging file on completion (success or failure).

  INGEST_STAGING_DIR defaults to /tmp/regengine_ingest.  In production this
  should be set to a volume mount that outlives the request process but does
  NOT need to outlive a container restart — durability for the binary blob is
  a follow-up (S3 or fsma.ingest_blob bytea) tracked in ADR-002 §deferred.
  The critical durability property — that the *task row* survives SIGTERM —
  is already satisfied by fsma.task_queue in Postgres.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any

import redis
import structlog
from shared.task_queue import register_task_handler

logger = structlog.get_logger("ingestion.regulation")

INGEST_STAGING_DIR = os.getenv("INGEST_STAGING_DIR", "/tmp/regengine_ingest")


def _resolve_staging_path(file_path: str) -> str:
    """Resolve ``file_path`` and require it to live inside the staging dir.

    Both sides are resolved with ``os.path.realpath`` so ``..`` segments
    and symlinks (including a symlink placed inside the staging dir that
    points outside it) cannot escape. Raises ``ValueError`` when the
    resolved path is outside the staging directory.
    """
    if not isinstance(file_path, str) or not file_path:
        raise ValueError("staging path must be a non-empty string")
    staging = os.path.realpath(INGEST_STAGING_DIR)
    resolved = os.path.realpath(file_path)
    if resolved != staging and not resolved.startswith(staging + os.sep):
        raise ValueError(f"staging path escapes staging directory: {file_path!r}")
    return resolved


def _remove_staging_file_quietly(file_path: str) -> None:
    """Delete ``file_path`` only when it resolves inside the staging dir.

    Re-resolves immediately before deleting so a path that was never
    validated (or that changed since validation) can never cause a file
    outside the staging directory to be removed. Never raises.
    """
    try:
        resolved = _resolve_staging_path(file_path)
    except (OSError, ValueError, TypeError):
        logger.error("regulation_staging_path_rejected", file_path=file_path)
        return
    try:
        os.remove(resolved)
    except OSError:
        pass


async def _process_regulation_from_file(
    job_id: str,
    name: str,
    filename: str,
    tenant_id: str,
    file_path: str,
    webhook: str | None = None,
) -> None:
    """Process a staged regulation file and update Redis status keys.

    Mirrors process_regulation_ingestion from routes.py but reads from a
    local staging file instead of from a Redis blob key.
    """
    import httpx

    from .config import get_settings
    from .regulation_loader import RegulationLoader  # type: ignore[import]

    settings = get_settings()
    r = redis.from_url(settings.redis_url)

    # Tenant-isolation marker read by routes_status to scope status/result
    # lookups to the owning tenant (audit/ingestion-service-audit.md).
    if tenant_id:
        r.setex(f"ingest:owner:{job_id}", 7200, tenant_id)

    try:
        resolved_path = _resolve_staging_path(file_path)
    except (OSError, ValueError, TypeError) as exc:
        logger.error("regulation_staging_path_rejected", job_id=job_id, file_path=file_path, error=str(exc))
        r.setex(f"ingest:status:{job_id}", 7200, "failed: invalid staging path")
        return

    content = None
    try:
        with open(resolved_path, "rb") as fh:
            content = fh.read()
    except (OSError, IOError) as exc:
        logger.error("regulation_staging_file_missing", job_id=job_id, file_path=file_path, error=str(exc))
        r.setex(f"ingest:status:{job_id}", 7200, "failed: staging file not found")
        return

    suffix = ".pdf" if filename.endswith(".pdf") else ".docx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        r.setex(f"ingest:status:{job_id}", 7200, "processing")
        loader = RegulationLoader(
            uri=settings.neo4j_uri,
            user=settings.neo4j_user,
            password=settings.neo4j_password,
        )
        count = await loader.load(
            tmp_path,
            "pdf" if filename.endswith(".pdf") else "docx",
            name,
        )
        loader.close()

        r.setex(f"ingest:status:{job_id}", 7200, "completed")
        r.setex(
            f"ingest:result:{job_id}",
            7200,
            json.dumps({"sections": count, "name": name, "tenant_id": tenant_id}),
        )
        logger.info("regulation_ingested_task_queue", name=name, sections=count, job_id=job_id)

        if webhook:
            try:
                # SSRF-safe: re-validates URL + pins to validated IP.
                from shared.safe_http import safe_httpx_post_async

                await safe_httpx_post_async(
                    webhook,
                    json={"job_id": job_id, "status": "completed", "regulation": name, "sections": count},
                )
            except (httpx.HTTPError, OSError, ValueError) as exc:
                logger.error("ingestion_webhook_failed", job_id=job_id, error=str(exc))

    except (redis.RedisError, ConnectionError, OSError, ValueError) as exc:
        logger.error("regulation_ingestion_task_failed", job_id=job_id, error=str(exc))
        r.setex(f"ingest:status:{job_id}", 7200, f"failed: {exc}")
        if webhook:
            try:
                from shared.safe_http import safe_httpx_post_async

                await safe_httpx_post_async(
                    webhook,
                    json={"job_id": job_id, "status": "failed", "error": str(exc)},
                )
            except (httpx.HTTPError, OSError, ValueError):
                pass
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        # Clean up the staging file regardless of outcome, but only when
        # it resolves inside the staging directory.
        _remove_staging_file_quietly(file_path)


def _handle_regulation_ingest(
    *,
    job_id: str,
    name: str,
    filename: str,
    tenant_id: str,
    file_path: str,
    webhook: str | None = None,
    **_: Any,
) -> None:
    asyncio.run(
        _process_regulation_from_file(
            job_id=job_id,
            name=name,
            filename=filename,
            tenant_id=tenant_id,
            file_path=file_path,
            webhook=webhook,
        )
    )


def register_regulation_handlers() -> None:
    """Call once at startup to wire handlers into TASK_HANDLERS."""
    register_task_handler("regulation_ingest", _handle_regulation_ingest)


def get_staging_path(job_id: str, filename: str) -> str:
    """Return the canonical staging path for a given job/file, creating the dir."""
    os.makedirs(INGEST_STAGING_DIR, exist_ok=True)
    ext = ".pdf" if filename.endswith(".pdf") else ".docx"
    return os.path.join(INGEST_STAGING_DIR, f"{job_id}{ext}")
