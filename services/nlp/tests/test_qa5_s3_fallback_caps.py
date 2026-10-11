"""QA5: the S3 fallback download path must enforce the same envelope as the loader.

``load_s3_artifact`` first tries a presigned URL (which flows through
``load_artifact`` and its size/MIME/strict-decode guards). When presigning
fails it fell back to ``obj["Body"].read()`` with no size cap and
``data.decode(errors="ignore")``, silently truncating hostile objects into
memory and silently dropping malformed bytes (which can mutilate lot
codes downstream). The fallback now enforces ``MAX_DOC_BYTES`` and fails
loudly on malformed UTF-8, mirroring ``text_loader``.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from services.nlp.app import s3_loader
from services.nlp.app.s3_loader import load_s3_artifact


def _fake_s3(body_bytes: bytes, content_length=None):
    """A boto3 client stand-in whose presigning fails, forcing the fallback."""
    body = MagicMock()
    # Emulate StreamingBody chunked reads for the capped loop.
    stream = io.BytesIO(body_bytes)
    body.read.side_effect = lambda amt=-1: stream.read(amt) if amt != -1 else stream.read()
    client = MagicMock()
    client.generate_presigned_url.side_effect = RuntimeError("no presign in test")
    obj = {"Body": body}
    if content_length is not None:
        obj["ContentLength"] = content_length
    client.get_object.return_value = obj
    return client


def _run_with_fake_s3(body_bytes: bytes, content_length=None):
    client = _fake_s3(body_bytes, content_length)
    with patch.object(s3_loader.boto3, "client", return_value=client):
        return load_s3_artifact("s3://test-bucket/docs/reg.txt")


def test_fallback_returns_small_valid_text():
    text = _run_with_fake_s3(b"Lot LOT-2026-001 shipped.", content_length=24)
    assert "LOT-2026-001" in text


def test_fallback_rejects_oversized_body():
    big = b"x" * (s3_loader.MAX_DOC_BYTES + 1)
    with pytest.raises(ValueError, match="E_DOC_TOO_LARGE"):
        _run_with_fake_s3(big, content_length=len(big))


def test_fallback_rejects_oversized_body_without_content_length():
    big = b"y" * (s3_loader.MAX_DOC_BYTES + 1)
    with pytest.raises(ValueError, match="E_DOC_TOO_LARGE"):
        _run_with_fake_s3(big)


def test_fallback_rejects_malformed_utf8():
    bad = b"prefix \xff\xfe\xfd suffix"
    with pytest.raises(ValueError, match="E_DOC_DECODE_FAILED"):
        _run_with_fake_s3(bad, content_length=len(bad))
