"""Unit tests for ``app.epcis.validation`` on empty and malformed input.

A passing FSMAEvent, a real TLC, and the GLN check-digit accept/reject
paths need a real record. They are not exercised here.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

from app.epcis import validation as mod  # noqa: E402
from app.epcis.validation import (  # noqa: E402
    _audit_log_validation_failure,
    _epcis_product_description,
    _validate_as_fsma_event,
    _validate_epcis,
    _validate_gln_format,
    _validate_tlc_format,
)


class TestEpcisProductDescription:
    def test_nothing_recorded_is_an_empty_cell(self):
        assert _epcis_product_description({}, {}) == ""
        assert _epcis_product_description({"productDescription": "   "}, None) == ""
        assert _epcis_product_description({}, {"productDescription": "   "}) == ""


class TestValidateTlcFormat:
    def test_minimum_length_passes(self):
        assert _validate_tlc_format("abc") is True

    @pytest.mark.parametrize("tlc", ["", "A", "AB", "   "])
    def test_short_or_whitespace_fails(self, tlc):
        assert _validate_tlc_format(tlc) is False

    def test_none_fails(self):
        assert _validate_tlc_format(None) is False


class TestValidateEpcis:
    def test_empty_dict_reports_missing_fields_type_and_lot(self):
        errors = _validate_epcis({})
        for field in ("type", "eventTime", "action", "bizStep"):
            assert any(f"'{field}'" in e for e in errors)
        assert any("Unsupported EPCIS event type" in e for e in errors)
        assert any("traceability lot code" in e for e in errors)
        assert not any("Traceback" in e for e in errors)

    @pytest.mark.parametrize("falsy_value", ["", None, 0])
    def test_falsy_required_value_reported_like_missing(self, falsy_value):
        errors = _validate_epcis({"type": falsy_value})
        assert any("Missing required" in e for e in errors)

    def test_unsupported_type_flagged(self):
        errors = _validate_epcis({"type": "MysteryEvent"})
        assert any("Unsupported EPCIS event type" in e for e in errors)

    @pytest.mark.parametrize("bad_type", [[], {}, ["not-a-type"], {"k": "v"}])
    def test_unhashable_type_flagged_not_raised(self, bad_type):
        errors = _validate_epcis({"type": bad_type})
        assert any("Unsupported EPCIS event type" in e for e in errors)


class TestValidateAsFsmaEvent:
    def test_unknown_event_type_fails_validation(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(mod, "_audit_log_validation_failure", lambda e, t, n: captured.update(errors=e))
        assert _validate_as_fsma_event({"event_type": "mystery"}, tenant_id="t1") is None
        assert captured["errors"][0]["loc"] == ["event_type"]

    def test_none_event_type_fails_validation(self):
        assert _validate_as_fsma_event({}) is None
        assert _validate_as_fsma_event({"event_type": None}) is None

    def test_missing_event_time_fails_validation(self):
        assert _validate_as_fsma_event({"event_type": "shipping"}) is None

    def test_validation_error_returns_none(self):
        assert _validate_as_fsma_event({"event_type": "shipping"}, tenant_id="t-oops") is None

    def test_validation_error_triggers_audit_trail(self, monkeypatch):
        captured = {}

        def _spy(errors, tenant_id, normalized):
            captured["errors"] = errors
            captured["tenant_id"] = tenant_id
            captured["normalized"] = normalized

        monkeypatch.setattr(mod, "_audit_log_validation_failure", _spy)
        normalized = {"event_type": "shipping"}
        result = _validate_as_fsma_event(normalized, tenant_id="tenant-42")
        assert result is None
        assert captured["tenant_id"] == "tenant-42"
        assert captured["normalized"] is normalized
        assert captured["errors"]

    def test_late_import_error_returns_none(self, monkeypatch):
        import shared.schemas as _schemas

        def _raise_import_error(**_kwargs):
            raise ImportError("simulated late import failure")

        monkeypatch.setattr(_schemas, "FSMAEvent", _raise_import_error)
        assert _validate_as_fsma_event({"event_type": "shipping"}) is None


class _FakeAuditLogger:
    def __init__(self):
        self.calls: list[dict] = []

    def log(self, **kwargs):
        self.calls.append(kwargs)

        async def _dummy():
            return None

        return _dummy()


def _install_fake_audit(monkeypatch: pytest.MonkeyPatch, raise_on_get_instance: bool = False) -> _FakeAuditLogger:
    fake_logger = _FakeAuditLogger()

    class _AuditLogger:
        @classmethod
        def get_instance(cls):
            if raise_on_get_instance:
                raise RuntimeError("boom from test stub")
            return fake_logger

    class _E:
        DATA_CREATE = "DATA_CREATE"
        DATA_MODIFICATION = "DATA_MODIFICATION"

    fake_mod = types.SimpleNamespace(
        AuditLogger=_AuditLogger,
        AuditActor=lambda **kw: kw,
        AuditResource=lambda **kw: kw,
        AuditEventType=_E,
        AuditEventCategory=_E,
        AuditSeverity=types.SimpleNamespace(WARNING="WARNING"),
    )
    monkeypatch.setitem(sys.modules, "shared.audit_logging", fake_mod)
    return fake_logger


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
class TestAuditLogValidationFailure:
    def test_no_running_loop_is_silent(self, monkeypatch):
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure(
            [{"loc": ("body", "tlc"), "msg": "bad"}],
            tenant_id="t",
            normalized={},
        )
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["outcome"] == "failure"
        assert call["action"] == "fsma_event_validation"
        assert call["resource"]["resource_id"] == "unknown"
        assert call["resource"]["attributes"]["tlc"] is None

    def test_running_loop_schedules_task(self, monkeypatch):
        fake = _install_fake_audit(monkeypatch)
        created: list[object] = []

        async def _runner():
            loop = asyncio.get_running_loop()
            orig = loop.create_task

            def _spy(coro, **kw):
                created.append(coro)
                return orig(coro, **kw)

            loop.create_task = _spy  # type: ignore[assignment]
            try:
                _audit_log_validation_failure(
                    [{"loc": ("tlc",)}],
                    tenant_id="t",
                    normalized={"idempotency_key": "k"},
                )
                await asyncio.sleep(0)
            finally:
                loop.create_task = orig

        asyncio.run(_runner())

        assert len(fake.calls) == 1
        assert len(created) == 1

    def test_failed_audit_task_logs_at_error(self, monkeypatch, caplog):
        fake = _install_fake_audit(monkeypatch)

        def _failing_log(**kwargs):
            async def _boom():
                raise RuntimeError("audit database unreachable")

            return _boom()

        fake.log = _failing_log

        async def _runner():
            _audit_log_validation_failure(
                [{"loc": ("tlc",)}],
                tenant_id="t",
                normalized={"idempotency_key": "k"},
            )
            for _ in range(10):
                await asyncio.sleep(0)

        with caplog.at_level(logging.ERROR, logger="epcis-ingestion"):
            asyncio.run(_runner())

        assert any(
            record.levelno >= logging.ERROR and "fsma_validation_audit_write_failed" in record.getMessage()
            for record in caplog.records
        )

    def test_idempotency_key_defaults_to_literal_unknown(self, monkeypatch):
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure([{"loc": ("tlc",)}], tenant_id="t", normalized={})
        assert fake.calls[0]["resource"]["resource_id"] == "unknown"

    def test_failed_fields_extracted_from_errors(self, monkeypatch):
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure(
            [
                {"loc": ("body", "tlc"), "msg": "bad"},
                {"loc": ("body", "event_time"), "msg": "bad"},
                {"msg": "error without loc"},
            ],
            tenant_id=None,
            normalized={"idempotency_key": "k"},
        )
        msg = fake.calls[0]["message"]
        assert "tlc" in msg
        assert "event_time" in msg
        assert "unknown" in msg

    def test_tenant_id_flows_to_actor_and_resource(self, monkeypatch):
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure(
            [{"loc": ("tlc",)}],
            tenant_id="acme-prod",
            normalized={"idempotency_key": "k"},
        )
        call = fake.calls[0]
        assert call["actor"]["tenant_id"] == "acme-prod"
        assert call["resource"]["tenant_id"] == "acme-prod"
        assert call["details"]["tenant_id"] == "acme-prod"

    def test_outer_exception_is_swallowed(self, monkeypatch):
        _install_fake_audit(monkeypatch, raise_on_get_instance=True)
        _audit_log_validation_failure(
            [{"loc": ("tlc",)}],
            tenant_id=None,
            normalized={},
        )

    def test_missing_audit_module_is_swallowed(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.audit_logging", None)
        _audit_log_validation_failure(
            [{"loc": ("tlc",)}],
            tenant_id=None,
            normalized={},
        )


class TestValidateGlnFormatInlineFallback:
    def test_fallback_rejects_wrong_length(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        assert _validate_gln_format("12345") is False

    def test_fallback_rejects_non_digit(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        assert _validate_gln_format("not-a-gln") is False

    def test_fallback_rejects_empty(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        assert _validate_gln_format("") is False

    def test_empty_short_circuits_without_importing(self, monkeypatch):
        raiser = types.ModuleType("shared.fsma_validation")

        def _boom(*a, **kw):
            raise RuntimeError("should not be called")

        raiser.validate_gln = _boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", raiser)
        assert _validate_gln_format("") is False
