"""Shared file upload size limits to prevent OOM on large uploads."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

# Default limits
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CSV_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_EDI_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


async def read_upload_with_limit(
    file: UploadFile,
    max_bytes: int = MAX_FILE_SIZE_BYTES,
    label: str = "file",
) -> bytes:
    """Read an uploaded file with a size cap to prevent OOM.

    Reads in chunks so we never buffer more than max_bytes.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64 KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{label} too large (max {max_bytes // (1024*1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)
