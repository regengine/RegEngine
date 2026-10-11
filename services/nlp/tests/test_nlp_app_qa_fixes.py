"""QA deep-pass regression tests for services/nlp/app.

Covers four real defects found by reading the module (no issue numbers
assigned yet): "where did X go" intent misrouting, substring modal matching
in obligation inference, unparseable dates passing the KDE gate, and the
S3 fallback path ignoring size and decoding guards.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from services.nlp.app.consumer.conversion import _convert_entities_to_extraction
from services.nlp.app.extractor import infer_obligation_type
from services.nlp.app.extractors.fsma_extractor import FSMAExtractor
from services.nlp.app.query_planner import parse_query

TODAY = date(2026, 1, 15)
TENANT = "12345678-1234-5678-1234-567812345678"


class TestWhereDidDirection:
    def test_where_did_go_is_forward(self):
        plan = parse_query("Where did lot LOT-ABC-123 go?", today=TODAY)
        assert plan.intent == "trace_forward"
        assert plan.tlc == "LOT-ABC-123"

    def test_where_did_come_from_is_backward(self):
        plan = parse_query("Where did lot LOT-ABC-123 come from?", today=TODAY)
        assert plan.intent == "trace_backward"
        assert plan.tlc == "LOT-ABC-123"

    def test_bare_where_did_keeps_legacy_backward_default(self):
        plan = parse_query("Where did lot LOT-ABC-123 ship?", today=TODAY)
        assert plan.intent == "trace_backward"

    def test_downstream_still_forward(self):
        plan = parse_query("Show downstream facilities for lot LOT-ABC-123", today=TODAY)
        assert plan.intent == "trace_forward"


class TestObligationKeywordWordBoundaries:
    def test_mayonnaise_is_not_permitted(self):
        result = infer_obligation_type("The mayonnaise production line operates daily.")
        assert result["obligation"] == "MANDATORY"

    def test_american_is_not_permitted(self):
        result = infer_obligation_type("American cheese production follows standard procedures.")
        assert result["obligation"] == "MANDATORY"

    def test_candy_canes_are_not_permitted(self):
        result = infer_obligation_type("The facility processes candy canes daily.")
        assert result["obligation"] == "MANDATORY"

    def test_shallot_does_not_trigger_conditional(self):
        result = infer_obligation_type("The shallot crop was graded unless damaged.")
        assert result["obligation"] == "MANDATORY"

    def test_real_modals_still_fire(self):
        assert infer_obligation_type("The supplier shall submit records monthly.")["obligation"] == "MANDATORY"
        assert infer_obligation_type("The applicant may submit supporting evidence.")["obligation"] == "PERMITTED"
        assert infer_obligation_type("The handler shall not exceed limits.")["obligation"] == "PROHIBITED"

    def test_conversion_does_not_permit_mayonnaise_sentence(self):
        entity = [
            {
                "type": "OBLIGATION",
                "text": "The mayonnaise production line operates daily.",
                "start": 0,
                "end": 46,
            }
        ]
        extraction = _convert_entities_to_extraction(entity, doc_id="d", source_url="u")[0]
        assert extraction.obligation_type.value == "MUST"


class TestUnparseableDatesFailClosed:
    def test_normalize_date_returns_none_for_impossible_date(self):
        assert FSMAExtractor()._normalize_date("13/45/2024") is None

    def test_normalize_date_keeps_valid_dates(self):
        assert FSMAExtractor()._normalize_date("01/15/2026") == "2026-01-15"

    def test_impossible_date_routes_to_review(self):
        text = (
            "Bill of Lading\nShipper: Acme Foods\n"
            "Lot: LOT-ABC-123\nQuantity: 50 cases\n"
            "GLN: 1234567890123\nDate: 13/45/2024\n"
        )
        extractor = FSMAExtractor()
        result = extractor.extract(text, "doc-1", tenant_id=TENANT)
        assert result.review_required is True
        assert any("event date" in w.lower() for w in result.warnings)
        assert extractor.to_graph_event(result)["ctes"] == []


def _mock_s3_client(body: bytes):
    client = MagicMock()
    client.generate_presigned_url.side_effect = Exception("presign unavailable")
    client.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=body))}
    return client


class TestS3FallbackHardening:
    def test_fallback_rejects_oversized_body(self):
        from services.nlp.app import s3_loader
        from services.nlp.app.text_loader import MAX_DOC_BYTES

        with patch.object(s3_loader, "boto3") as boto:
            boto.client.return_value = _mock_s3_client(b"x" * (MAX_DOC_BYTES + 1))
            with pytest.raises(ValueError, match="TOO_LARGE"):
                s3_loader.load_s3_artifact("s3://my-bucket/some/key")

    def test_fallback_rejects_malformed_utf8(self):
        from services.nlp.app import s3_loader

        with patch.object(s3_loader, "boto3") as boto:
            boto.client.return_value = _mock_s3_client(b"\xff\xfe\x00bad bytes")
            with pytest.raises(ValueError, match="DECODE_FAILED"):
                s3_loader.load_s3_artifact("s3://my-bucket/some/key")

    def test_fallback_decodes_valid_text(self):
        from services.nlp.app import s3_loader

        with patch.object(s3_loader, "boto3") as boto:
            boto.client.return_value = _mock_s3_client(b"Lot: ABC-123")
            assert s3_loader.load_s3_artifact("s3://my-bucket/some/key") == "Lot: ABC-123"
