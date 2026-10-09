"""Fallback decode in s3_loader must not silently drop bytes.

Before the fix, the presigned-URL fallback decoded the raw S3 body with
``errors="ignore"``, quietly deleting every undecodable byte. The fallback
now decodes strict UTF-8 and, only on failure, logs a warning and decodes
with visible replacement characters so the gap shows downstream.
"""

import io
import logging
from unittest.mock import MagicMock, patch

from services.nlp.app.s3_loader import load_s3_artifact


def _s3_client_with_body(body: bytes, presign_ok: bool = False) -> MagicMock:
    s3 = MagicMock()
    if presign_ok:
        s3.generate_presigned_url.return_value = "https://example.test/presigned"
    else:
        s3.generate_presigned_url.side_effect = Exception("presign unavailable")
    s3.get_object.return_value = {"Body": io.BytesIO(body)}
    return s3


def test_fallback_decodes_valid_utf8_exactly():
    body = "Fresh Farms recall notice".encode("utf-8")
    with patch("services.nlp.app.s3_loader.boto3") as mock_boto:
        mock_boto.client.return_value = _s3_client_with_body(body)
        assert load_s3_artifact("s3://bucket/key") == "Fresh Farms recall notice"


def test_fallback_invalid_utf8_warns_and_marks_loss(caplog):
    body = b"Lot A \xff\xfe end"
    with patch("services.nlp.app.s3_loader.boto3") as mock_boto:
        mock_boto.client.return_value = _s3_client_with_body(body)
        with caplog.at_level(logging.WARNING, logger="s3_loader"):
            result = load_s3_artifact("s3://bucket/key")

    assert result == body.decode("utf-8", errors="replace")
    assert "\ufffd" in result
    assert "s3_fallback_body_not_utf8_using_replace" in caplog.text
