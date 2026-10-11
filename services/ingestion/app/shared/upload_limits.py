"""Shared file upload size and content validation helpers."""

from __future__ import annotations

import contextlib
import io
import re
import zipfile
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, Request, UploadFile

# Default limits
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_CSV_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_EDI_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_REGULATION_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB

UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024
_MAX_FILENAME_CHARS = 120
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]+")
_IMAGE_CONTENT_TYPES = {
    "BMP": "image/bmp",
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "TIFF": "image/tiff",
    "WEBP": "image/webp",
}


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
        chunk = await file.read(UPLOAD_CHUNK_SIZE_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{label} too large (max {max_bytes // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def read_request_body_with_limit(
    request: Request,
    max_bytes: int = MAX_FILE_SIZE_BYTES,
    label: str = "request body",
) -> bytes:
    """Read a raw request body with a streaming size cap.

    Unlike ``request.body()``, this never buffers more than ``max_bytes`` in
    memory. It closes the chunked/streaming-upload gap left by
    ``RequestSizeLimitMiddleware``, which only enforces the ``Content-Length``
    header and lets bodies without it (``Transfer-Encoding: chunked``) through.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"{label} too large (max {max_bytes // (1024 * 1024)} MB)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def stream_upload_to_file_with_limit(
    file: UploadFile,
    destination: str | Path | BinaryIO,
    max_bytes: int = MAX_FILE_SIZE_BYTES,
    label: str = "file",
    prefix_bytes: int = 8192,
) -> tuple[int, bytes]:
    """Stream an upload to disk while enforcing the byte cap.

    Returns the total bytes written and an initial byte prefix callers can
    validate without first buffering the full upload in memory.

    When ``destination`` is a path opened by this helper, a failure partway
    through (oversize upload, write error) removes the partial file so
    aborted uploads cannot accumulate in the staging directory. When it is
    a caller-provided file object, bytes written before the failure stay in
    it and cleanup is the caller's job.
    """
    total = 0
    prefix = bytearray()
    close_destination = False
    if hasattr(destination, "write"):
        out = destination  # type: ignore[assignment]
    else:
        out = open(destination, "wb")
        close_destination = True

    failed = False
    try:
        while True:
            chunk = await file.read(UPLOAD_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"{label} too large (max {max_bytes // (1024 * 1024)} MB)",
                )
            if len(prefix) < prefix_bytes:
                prefix.extend(chunk[: prefix_bytes - len(prefix)])
            out.write(chunk)
    except Exception:
        failed = True
        raise
    finally:
        if close_destination:
            with contextlib.suppress(OSError):
                out.close()
            if failed:
                with contextlib.suppress(OSError):
                    Path(destination).unlink(missing_ok=True)
    return total, bytes(prefix)


def sanitize_upload_filename(
    filename: str | None,
    *,
    fallback: str = "upload",
    max_length: int = _MAX_FILENAME_CHARS,
) -> str:
    """Return a basename safe for logs, metadata, and internal URLs."""
    raw = _CONTROL_CHARS_RE.sub("", str(filename or ""))
    name = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = _SAFE_FILENAME_RE.sub("_", name)
    name = re.sub(r"_+", "_", name)
    name = re.sub(r"\.+", ".", name)
    name = name.strip(" ._-")
    if not name or name in {".", ".."}:
        name = fallback
    if len(name) > max_length:
        stem, dot, suffix = name.rpartition(".")
        if dot and suffix:
            suffix = suffix[:20]
            available = max(1, max_length - len(suffix) - 1)
            name = f"{stem[:available]}.{suffix}"
        else:
            name = name[:max_length]
    return name or fallback


def regulation_upload_type(filename: str | None) -> str:
    """Validate the filename extension and return ``pdf`` or ``docx``."""
    safe_name = sanitize_upload_filename(filename)
    suffix = Path(safe_name).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")


def validate_regulation_upload_content(
    file_type: str,
    prefix: bytes,
    *,
    path: str | Path | None = None,
) -> None:
    """Validate regulation bytes by parser-friendly signatures."""
    if file_type == "pdf":
        if not prefix.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Uploaded PDF content is invalid")
        return

    if file_type == "docx":
        if not prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
            raise HTTPException(status_code=400, detail="Uploaded DOCX content is invalid")
        if path is None:
            return
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Uploaded DOCX content is invalid") from exc
        if "[Content_Types].xml" not in names or "word/document.xml" not in names:
            raise HTTPException(status_code=400, detail="Uploaded DOCX content is invalid")
        return

    raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")


def validated_image_content_type(
    image_bytes: bytes,
    declared_content_type: str | None = None,
) -> str:
    """Validate raster image bytes with Pillow and return the actual MIME type."""
    # Media types are case-insensitive (RFC 2045) and may carry parameters,
    # so normalize before checking the declared type. The bytes are still
    # verified with Pillow below; this gate only rejects obvious non-images.
    normalized_declared = (declared_content_type or "").split(";")[0].strip().lower()
    if not normalized_declared.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload must be an image")
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover - dependency is present in tests/prod images
        raise HTTPException(status_code=500, detail="Pillow is required for image validation") from exc

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image.verify()
            image_format = image.format
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image payload") from exc

    content_type = _IMAGE_CONTENT_TYPES.get(str(image_format or "").upper())
    if not content_type:
        raise HTTPException(status_code=400, detail="Unsupported image format")
    return content_type
