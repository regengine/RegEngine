"""Deep QA for the RegEngine SDK surface: client auth/tenant/retry edges,
model kwargs constructors, exception hierarchy, and label batch output.

Style follows tests/sdk/test_client_retry_and_errors.py: the real
``_request`` code path is driven through ``httpx.MockTransport`` (no
network, no sleeps), and overview comments name the bug each class pins.
"""

from __future__ import annotations

import httpx
import pytest

from regengine import RegEngineClient
from regengine.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RegEngineError,
    ValidationError,
)
from regengine.models import (
    CTEType,
    FTLResult,
    ReadinessScore,
    RecallDrill,
    Record,
    TimelineEvent,
    TraceResult,
)


def make_client(handler, **kwargs) -> RegEngineClient:
    kwargs.setdefault("retry_backoff_factor", 0.0)
    client = RegEngineClient(api_key="rge_test", **kwargs)
    client._session = httpx.Client(transport=httpx.MockTransport(handler))
    return client


def close(client: RegEngineClient) -> None:
    client._session.close()


class TestApiKeyValidation:
    @pytest.mark.parametrize("key", ["", "wrong-prefix-key", "Bearer rge_x", "rge"])
    def test_rejects_keys_without_rge_prefix(self, key):
        with pytest.raises(ValidationError):
            RegEngineClient(api_key=key)

    def test_accepts_well_formed_key(self):
        client = RegEngineClient(api_key="rge_live_abc123")
        try:
            assert client.api_key == "rge_live_abc123"
        finally:
            close(client)


class TestBaseUrlAndTenantHeaders:
    def test_trailing_slash_is_stripped(self):
        client = RegEngineClient(api_key="rge_test", base_url="https://regengine.co///")
        try:
            assert client.base_url == "https://regengine.co"
        finally:
            close(client)

    def test_no_tenant_header_when_tenant_unset(self):
        seen = {}

        def handler(request):
            seen.update(dict(request.headers))
            return httpx.Response(200, json={})

        client = make_client(handler)
        try:
            client._request("GET", "/api/v1/thing")
            assert "x-tenant-id" not in seen
            assert seen.get("x-regengine-api-key") == "rge_test"
        finally:
            close(client)


class TestRetryEdges:
    def test_non_numeric_retry_after_falls_back_to_backoff(self, monkeypatch):
        sleeps = []
        monkeypatch.setattr("regengine.client.time.sleep", lambda s: sleeps.append(s))
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "not-a-number"})
            return httpx.Response(200, json={"ok": True})

        client = make_client(handler, retry_backoff_factor=2.0)
        try:
            assert client._request("GET", "/api/v1/thing") == {"ok": True}
            assert sleeps == [2.0]
        finally:
            close(client)

    def test_exhausted_500s_raise_and_stop_after_max_retries_plus_one(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(500, text="boom")

        client = make_client(handler, max_retries=2)
        try:
            with pytest.raises(RegEngineError):
                client._request("GET", "/api/v1/thing")
            assert len(calls) == 3
        finally:
            close(client)

    def test_422_with_non_json_body_reports_the_body(self):
        client = make_client(lambda request: httpx.Response(422, content=b"plain failure"))
        try:
            with pytest.raises(RegEngineError, match="plain failure"):
                client._request("GET", "/api/v1/thing")
        finally:
            close(client)


class TestRecordReadPaths:
    ROW = {
        "event_id": "evt-1",
        "event_type": "SHIPPING",
        "traceability_lot_code": "LOT-1",
        "product_reference": "Romaine",
        "quantity": 4.0,
        "unit_of_measure": "CASE",
        "from_facility_reference": "GLN-1",
        "to_facility_reference": "GLN-2",
        "event_timestamp": "2026-01-01T00:00:00+00:00",
        "created_at": "2026-01-01T01:00:00+00:00",
    }

    def test_get_record_with_no_events_raises_not_found(self):
        client = make_client(lambda request: httpx.Response(200, json={"events": [], "total": 0}))
        try:
            with pytest.raises(NotFoundError, match="LOT-EMPTY"):
                client.get_record("LOT-EMPTY")
        finally:
            close(client)

    def test_get_record_sends_tlc_and_limit_params(self):
        seen = {}

        def handler(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"events": [self.ROW], "total": 1})

        client = make_client(handler)
        try:
            record = client.get_record("LOT-1")
            assert record.tlc == "LOT-1"
            assert seen.get("tlc") == "LOT-1"
            assert seen.get("limit") == "1"
        finally:
            close(client)

    def test_query_records_maps_enum_cte_to_event_type_param(self):
        seen = {}

        def handler(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, json={"events": [], "total": 0})

        client = make_client(handler)
        try:
            assert client.query_records("2026-01-01", "2026-12-31", cte_type=CTEType.SHIPPING) == []
            assert seen.get("event_type") == "SHIPPING"
            assert seen.get("limit") == "100"
        finally:
            close(client)


class TestExportFdaParams:
    CSV_HEADERS = {"Content-Type": "text/csv"}

    def test_export_sends_tlc_and_date_range(self):
        seen = {}

        def handler(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, content=b"a,b\n", headers=self.CSV_HEADERS)

        client = make_client(handler)
        try:
            client.export_fda("LOT-A", "2026-01-01", "2026-01-31")
            assert seen.get("tlc") == "LOT-A"
            assert seen.get("start_date") == "2026-01-01"
            assert seen.get("end_date") == "2026-01-31"
        finally:
            close(client)


class TestKwargsConstructors:
    """TraceResult/RecallDrill/ReadinessScore/FTLResult read every field
    through kwargs.get, so unknown keys are ignored and nothing is unset."""

    def test_trace_result_defaults_and_unknown_keys_ignored(self):
        result = TraceResult(facilities=[{"gln": "G"}], nonsense_key=123)
        assert result.lot_id == ""
        assert result.hop_count == 0
        assert result.facilities == [{"gln": "G"}]
        assert result.trace_duration_ms is None

    def test_recall_drill_honours_id_and_type_aliases(self):
        drill = RecallDrill(id="D-1", type="backward_trace", status="done", unknown=1)
        assert drill.drill_id == "D-1"
        assert drill.drill_type == "backward_trace"
        assert drill.target_tlc == ""
        assert drill.facilities_affected == 0

    def test_readiness_score_honours_server_key_aliases(self):
        score = ReadinessScore(
            readiness_score=82,
            last_drill="2026-01-01",
            average_completion_seconds=900,
            sla_met_percentage=99.0,
        )
        assert score.last_drill_date == "2026-01-01"
        assert score.average_drill_seconds == 900
        assert score.sla_compliance_percentage == 99.0
        assert score.recommendations == []

    def test_ftl_result_ignores_unknown_keys(self):
        # FTLResult has no client read path (check_ftl was removed in WS-11);
        # pin only that unknown keys never break construction.
        assert FTLResult(category="leafy", covered=True, risk_level="high", extra="ignored").covered is True


class TestFromApiEdgeCases:
    def test_record_ignores_unknown_keys_and_defaults_quantity(self):
        record = Record.from_api({"id": "E1", "tlc": "LOT-9", "something_new": "x"})
        assert record.quantity == 0.0
        assert record.tlc == "LOT-9"

    def test_timeline_explicit_location_wins_over_facility(self):
        event = TimelineEvent.from_api(
            {"type": "SHIPPING", "event_date": "2026-02-01", "location": "Dock 7", "facility": {"name": "Other Name"}},
        )
        assert event.location == "Dock 7"


class TestExceptionHierarchy:
    @pytest.mark.parametrize(
        "exc",
        [AuthenticationError, RateLimitError, NotFoundError, ValidationError],
    )
    def test_sdk_errors_are_regengine_errors_with_message(self, exc):
        err = exc("boom")
        assert isinstance(err, RegEngineError)
        assert str(err) == "boom"
        assert err.message == "boom"


class TestLabelBatchOutput:
    """generate_batch_labels is pure string output for fmt=zpl, so these run
    without the optional qrcode/Pillow/fpdf2 packages."""

    def _label(self, tlc="LOT-A"):
        from regengine.labels import LabelData

        return LabelData(
            traceability_lot_code=tlc,
            product_description="Romaine",
            quantity=10,
            unit_of_measure="cases",
            location_gln="0614141000001",
            location_name="Salinas, CA",
            lot_date="2026-02-06",
        )

    def test_zpl_output_carries_tlc_and_closes_block(self):
        from regengine.labels import generate_label_zpl

        zpl = generate_label_zpl(self._label("LOT-9"))
        assert "LOT-9" in zpl
        assert zpl.startswith("^XA")
        assert zpl.rstrip().endswith("^XZ")

    def test_unknown_format_raises_instead_of_returning_empty(self):
        """Before the fix an unsupported fmt silently returned [], so a
        caller writing the results to disk produced nothing and exited 0."""
        from regengine.labels import generate_batch_labels

        with pytest.raises(ValueError, match="unsupported label format"):
            generate_batch_labels([self._label()], fmt="docx")

    def test_filenames_are_sanitized_like_the_cli(self):
        """The CLI sanitizes every non [A-Za-z0-9_.-] char, but the batch
        helper only replaced '/'. A TLC such as 'LOT:A/B C' must map to the
        same safe filename in both paths."""
        from regengine.labels import generate_batch_labels

        (filename, content) = generate_batch_labels([self._label("LOT:A/B C")], fmt="zpl")[0]
        assert filename == "label_LOT_A_B_C.zpl"
        assert content.startswith(b"^XA")
