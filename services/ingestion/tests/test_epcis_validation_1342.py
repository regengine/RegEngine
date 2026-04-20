"""Unit tests for ``app.epcis.validation`` — issue #1342.

Raises coverage from 41% to ~100% by exercising every non-GLN branch
the existing ``test_epcis_gln_check_digit.py`` does not reach:

  - ``_default_product_description`` — pure helper; both branches.
  - ``_validate_tlc_format`` — minimum-length guard with strip().
  - ``_validate_epcis`` — required-field, type-allowlist, and
    lot/TLC presence checks (pins the error messages callers surface
    to the auditor).
  - ``_validate_as_fsma_event`` — happy path + ValidationError + the
    late-ImportError fallback. The function also degrades to None on
    unknown event_type (maps to RECEIVING), missing event_time (maps
    to now()), and missing product_description (synthesized default).
  - ``_audit_log_validation_failure`` — no-running-loop branch, the
    running-loop + ``loop.create_task`` branch, and the outer blanket
    exception swallow. Pinned because this is fire-and-forget telemetry
    running in the request path: if it ever raises it corrupts the
    ingestion response.
  - ``_validate_gln_format`` ImportError fallback — the inline GS1
    mod-10 algorithm that runs when ``shared.fsma_validation`` is
    unavailable. The happy delegate path is already covered by
    ``test_epcis_gln_check_digit.py``.

Check-digit / strict-rejection / mandatory-GLN behavior stays in
``test_epcis_gln_check_digit.py``; this file does not duplicate it.
"""

from __future__ import annotations

import asyncio
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
    _default_product_description,
    _validate_as_fsma_event,
    _validate_epcis,
    _validate_gln_format,
    _validate_tlc_format,
)

# Production-pattern TLC: 14-digit GTIN prefix + alphanumeric lot
# suffix. Satisfies ``_TLC_PRODUCTION_RE`` and the 15-char min_length
# on ``FSMAEvent.tlc``. Reused in happy-path fixtures below.
_GOOD_TLC = "00012345678901-L2025-1105-A"


# ---------------------------------------------------------------------------
# _default_product_description
# ---------------------------------------------------------------------------


class TestDefaultProductDescription:
    def test_with_product_id_returns_formatted_string(self):
        assert (
            _default_product_description({"product_id": "urn:epc:id:gtin:123"})
            == "EPCIS Product urn:epc:id:gtin:123"
        )

    def test_without_product_id_returns_generic_fallback(self):
        assert _default_product_description({}) == "EPCIS Traceability Event"

    def test_with_none_product_id_returns_generic_fallback(self):
        # ``if product_id`` — None is falsy, fall to generic.
        assert (
            _default_product_description({"product_id": None})
            == "EPCIS Traceability Event"
        )

    def test_with_empty_product_id_returns_generic_fallback(self):
        # Defensive: EPCIS producers sometimes emit empty strings for
        # "field known but blank" — must not produce "EPCIS Product ".
        assert (
            _default_product_description({"product_id": ""})
            == "EPCIS Traceability Event"
        )


# ---------------------------------------------------------------------------
# _validate_tlc_format
# ---------------------------------------------------------------------------


class TestValidateTlcFormat:
    @pytest.mark.parametrize("tlc", ["ABC", "LOT-1", "  ABC  "])
    def test_valid_lengths_pass(self, tlc):
        # Surrounding whitespace is stripped before length check.
        assert _validate_tlc_format(tlc) is True

    @pytest.mark.parametrize("tlc", ["", "A", "AB", "   "])
    def test_short_or_whitespace_fails(self, tlc):
        assert _validate_tlc_format(tlc) is False

    def test_none_fails(self):
        # Not technically reachable through the type annotation, but
        # _validate_epcis occasionally passes through caller-supplied
        # values before sanitizing — guard against AttributeError.
        assert _validate_tlc_format(None) is False


# ---------------------------------------------------------------------------
# _validate_epcis
# ---------------------------------------------------------------------------


class TestValidateEpcis:
    @staticmethod
    def _base_event():
        return {
            "type": "ObjectEvent",
            "eventTime": "2025-11-05T14:30:00Z",
            "action": "OBSERVE",
            "bizStep": "urn:epcglobal:cbv:bizstep:shipping",
            "ilmd": {"fsma:traceabilityLotCode": "TLC-ABC"},
        }

    def test_fully_valid_event_returns_no_errors(self):
        assert _validate_epcis(self._base_event()) == []

    @pytest.mark.parametrize(
        "missing_field",
        ["type", "eventTime", "action", "bizStep"],
    )
    def test_missing_required_field_reports_error(self, missing_field):
        event = self._base_event()
        event.pop(missing_field)
        errors = _validate_epcis(event)
        # The field name is echoed quoted so operators can grep the
        # log without knowing the message format.
        assert any(f"'{missing_field}'" in e for e in errors)

    @pytest.mark.parametrize(
        "falsy_value",
        ["", None, 0],
    )
    def test_falsy_required_value_reported_like_missing(self, falsy_value):
        # ``not event.get(field)`` — any falsy value triggers the
        # "Missing required" error the same way absence does.
        event = self._base_event()
        event["type"] = falsy_value
        errors = _validate_epcis(event)
        assert any("Missing required" in e for e in errors)

    def test_unsupported_type_flagged(self):
        event = self._base_event()
        event["type"] = "MysteryEvent"
        errors = _validate_epcis(event)
        assert any("Unsupported EPCIS event type" in e for e in errors)

    @pytest.mark.parametrize("bad_type", [[], {}, ["ObjectEvent"], {"k": "v"}])
    def test_unhashable_type_flagged_not_raised(self, bad_type):
        # Issue #1342: previously ``event.get("type") in {set}`` raised
        # TypeError when the caller supplied a list or dict, surfacing
        # as a 500 instead of a clean validation error. The guard now
        # rejects any non-string ``type`` as "Unsupported".
        event = self._base_event()
        event["type"] = bad_type
        errors = _validate_epcis(event)
        assert any("Unsupported EPCIS event type" in e for e in errors)

    @pytest.mark.parametrize(
        "etype",
        [
            "ObjectEvent",
            "AggregationEvent",
            "TransactionEvent",
            "TransformationEvent",
        ],
    )
    def test_all_supported_types_accepted(self, etype):
        event = self._base_event()
        event["type"] = etype
        errors = _validate_epcis(event)
        assert not any("Unsupported" in e for e in errors)

    def test_missing_lot_and_tlc_flagged(self):
        event = self._base_event()
        event["ilmd"] = {}
        errors = _validate_epcis(event)
        assert any("traceability lot code" in e for e in errors)

    def test_short_tlc_flagged(self):
        event = self._base_event()
        event["ilmd"] = {"fsma:traceabilityLotCode": "AB"}
        errors = _validate_epcis(event)
        assert any("too short" in e for e in errors)
        # Echo the offending value so operators can trace the bad event.
        assert any("'AB'" in e for e in errors)

    def test_ilmd_can_come_from_extension_fallback(self):
        # EPCIS 2.0 sometimes nests ilmd under ``extension`` — the
        # validator must reach into both locations.
        event = self._base_event()
        event.pop("ilmd")
        event["extension"] = {"ilmd": {"fsma:traceabilityLotCode": "TLC-XYZ"}}
        errors = _validate_epcis(event)
        assert not any("lot code" in e for e in errors)

    def test_missing_ilmd_and_extension_flagged(self):
        # Neither location has ilmd → _extract_lot_data returns ("",
        # "") → "Missing traceability lot code".
        event = self._base_event()
        event.pop("ilmd")
        errors = _validate_epcis(event)
        assert any("traceability lot code" in e for e in errors)

    def test_lot_code_without_explicit_tlc_still_valid(self):
        # When fsma:traceabilityLotCode is absent _extract_lot_data
        # defaults tlc := lot_code, so this satisfies the presence check
        # AND the min-length gate (LOT-100 → 7 chars).
        event = self._base_event()
        event["ilmd"] = {"lotNumber": "LOT-100"}
        errors = _validate_epcis(event)
        assert errors == []


# ---------------------------------------------------------------------------
# _validate_as_fsma_event
# ---------------------------------------------------------------------------


class TestValidateAsFsmaEvent:
    @staticmethod
    def _good_normalized():
        return {
            "event_type": "shipping",
            "tlc": _GOOD_TLC,
            "product_description": "Romaine Lettuce",
            "quantity": 10,
            "unit_of_measure": "cases",
            "location_id": "0614141999996",
            "event_time": "2025-11-05T14:30:00Z",
            "source_location_id": "0614141999996",
            "dest_location_id": "0614141999996",
        }

    def test_happy_path_returns_model_dump(self):
        result = _validate_as_fsma_event(self._good_normalized(), tenant_id="t1")
        assert result is not None
        # model_dump serializes the enum as its string value.
        assert result["event_type"] == "SHIPPING"
        assert result["tlc"] == _GOOD_TLC
        assert result["tenant_id"] == "t1"
        assert result["reference_document_type"] == "EPCIS"

    def test_tenant_id_defaults_to_none(self):
        # ``tenant_id=None`` kwarg default — must flow through to the
        # emitted event for consistent multi-tenant labeling.
        result = _validate_as_fsma_event(self._good_normalized())
        assert result is not None
        assert result["tenant_id"] is None

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("shipping", "SHIPPING"),
            ("SHIPPING", "SHIPPING"),  # mixed case handled via .lower()
            ("receiving", "RECEIVING"),
            ("transformation", "TRANSFORMATION"),
            ("initial_packing", "CREATION"),
            ("creation", "CREATION"),
        ],
    )
    def test_event_type_map_covers_all_entries(self, raw, expected):
        n = self._good_normalized()
        n["event_type"] = raw
        result = _validate_as_fsma_event(n)
        assert result is not None
        assert result["event_type"] == expected

    def test_unknown_event_type_defaults_to_receiving(self):
        # The `.get(raw_type, FSMAEventType.RECEIVING)` default — pins
        # the fallback so an unmapped event_type doesn't 500 the
        # pipeline mid-ingestion.
        n = self._good_normalized()
        n["event_type"] = "mystery"
        result = _validate_as_fsma_event(n)
        assert result is not None
        assert result["event_type"] == "RECEIVING"

    def test_none_event_type_defaults_to_receiving(self):
        # The ``or "receiving"`` on the .lower() line — None event_type
        # becomes the "receiving" literal which resolves to RECEIVING.
        n = self._good_normalized()
        n["event_type"] = None
        result = _validate_as_fsma_event(n)
        assert result is not None
        assert result["event_type"] == "RECEIVING"

    def test_missing_product_description_synthesizes_default(self):
        n = self._good_normalized()
        n.pop("product_description")
        n["product_id"] = "urn:epc:id:gtin:42"
        result = _validate_as_fsma_event(n)
        assert result is not None
        assert result["product_description"] == "EPCIS Product urn:epc:id:gtin:42"

    def test_missing_product_description_and_product_id(self):
        n = self._good_normalized()
        n.pop("product_description")
        result = _validate_as_fsma_event(n)
        assert result is not None
        assert result["product_description"] == "EPCIS Traceability Event"

    def test_missing_event_time_synthesizes_now(self):
        # ``or datetime.now(timezone.utc).isoformat()`` — not ideal
        # (event_time should be required), but the fallback keeps the
        # pipeline flowing rather than 500ing on a missing timestamp.
        n = self._good_normalized()
        n.pop("event_time")
        result = _validate_as_fsma_event(n)
        assert result is not None
        assert result["event_time"]  # non-empty ISO string
        assert "T" in result["event_time"]

    def test_missing_tlc_defaults_to_unknown_and_fails_validation(self):
        # tlc defaults to "UNKNOWN" (7 chars) — fails FSMAEvent's
        # min_length=15 + GTIN regex — ValidationError → None.
        n = self._good_normalized()
        n.pop("tlc")
        result = _validate_as_fsma_event(n)
        assert result is None

    def test_validation_error_returns_none(self):
        # Short tlc violates both min_length and the GTIN prefix regex.
        # The function logs + audit-trails but must not raise: ingestion
        # keeps flowing, the event is simply dropped from the FSMA feed.
        n = self._good_normalized()
        n["tlc"] = "SHORT"
        result = _validate_as_fsma_event(n, tenant_id="t-oops")
        assert result is None

    def test_validation_error_triggers_audit_trail(self, monkeypatch):
        # Pins the bridge between ValidationError and audit logging —
        # the audit call must fire on every rejected FSMAEvent.
        captured = {}

        def _spy(errors, tenant_id, normalized):
            captured["errors"] = errors
            captured["tenant_id"] = tenant_id
            captured["normalized"] = normalized

        monkeypatch.setattr(mod, "_audit_log_validation_failure", _spy)
        n = self._good_normalized()
        n["tlc"] = "SHORT"
        result = _validate_as_fsma_event(n, tenant_id="tenant-42")
        assert result is None
        assert captured["tenant_id"] == "tenant-42"
        assert captured["normalized"] is n
        assert captured["errors"]  # non-empty list of pydantic errors

    def test_late_import_error_returns_none(self, monkeypatch):
        # The ``except ImportError`` handler guards against pydantic or
        # shared.schemas going missing mid-deploy. Reached by making
        # FSMAEvent raise ImportError at construction — the preceding
        # ``from shared.schemas import FSMAEvent, FSMAEventType`` has
        # already bound ValidationError in local scope, so ``except
        # ValidationError`` can evaluate without NameError and the
        # ImportError branch is reachable.
        import shared.schemas as _schemas

        def _raise_import_error(**_kwargs):
            raise ImportError("simulated late import failure")

        monkeypatch.setattr(_schemas, "FSMAEvent", _raise_import_error)
        result = _validate_as_fsma_event(self._good_normalized())
        assert result is None


# ---------------------------------------------------------------------------
# _audit_log_validation_failure
# ---------------------------------------------------------------------------


class _FakeAuditLogger:
    def __init__(self):
        self.calls: list[dict] = []

    def log(self, **kwargs):
        self.calls.append(kwargs)

        async def _dummy():
            return None

        return _dummy()


def _install_fake_audit(
    monkeypatch: pytest.MonkeyPatch, raise_on_get_instance: bool = False
) -> _FakeAuditLogger:
    """Install a stub ``shared.audit_logging`` that records ``.log()`` calls.

    The real module reaches into a writer singleton that can talk to a
    database; swap it out so the test doesn't require any infra.
    """
    fake_logger = _FakeAuditLogger()

    class _AuditLogger:
        @classmethod
        def get_instance(cls):
            if raise_on_get_instance:
                raise RuntimeError("boom from test stub")
            return fake_logger

    class _E:  # enum-lite stand-in — passed straight through to .log()
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
    # ``_FakeAuditLogger.log()`` returns a coroutine that the no-loop
    # branch of the production code intentionally never awaits. That's
    # the documented "no running loop, skip async audit" behavior, but
    # it does emit a RuntimeWarning when the coroutine is GC'd. Filter
    # at the class level rather than per-test so the test surface
    # stays clean.
    def test_no_running_loop_is_silent(self, monkeypatch):
        # Synchronous call path — ``asyncio.get_running_loop()`` raises
        # RuntimeError, which is the documented "no loop, skip async
        # audit" branch. Must build the coroutine (so .log() is still
        # called) but must not raise.
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure(
            [{"loc": ("body", "tlc"), "msg": "bad"}],
            tenant_id="t",
            normalized={"idempotency_key": "k", "tlc": "T", "event_time": "2025"},
        )
        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["outcome"] == "failure"
        assert call["action"] == "fsma_event_validation"
        assert call["resource"]["resource_id"] == "k"
        assert call["resource"]["attributes"]["tlc"] == "T"

    def test_running_loop_schedules_task(self, monkeypatch):
        # Under a running event loop, the coroutine must be scheduled
        # via ``loop.create_task`` so the audit fires concurrently with
        # ingestion rather than blocking it.
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
                # Drain the scheduled task so we don't leak a warning.
                await asyncio.sleep(0)
            finally:
                loop.create_task = orig

        asyncio.run(_runner())

        assert len(fake.calls) == 1
        assert len(created) == 1

    def test_idempotency_key_defaults_to_literal_unknown(self, monkeypatch):
        # ``.get("idempotency_key") or "unknown"`` — handles both the
        # missing-key and explicit-None cases.
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure([{"loc": ("tlc",)}], tenant_id="t", normalized={})
        assert fake.calls[0]["resource"]["resource_id"] == "unknown"

    def test_failed_fields_extracted_from_errors(self, monkeypatch):
        fake = _install_fake_audit(monkeypatch)
        _audit_log_validation_failure(
            [
                {"loc": ("body", "tlc"), "msg": "bad"},
                {"loc": ("body", "event_time"), "msg": "bad"},
                {"msg": "error without loc"},  # .get("loc", ["unknown"])
            ],
            tenant_id=None,
            normalized={"idempotency_key": "k"},
        )
        msg = fake.calls[0]["message"]
        # Last element of each loc tuple becomes the reported field;
        # errors without loc fall back to the "unknown" default.
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
        # AuditLogger.get_instance() raises RuntimeError — this escapes
        # the inner get_running_loop try/except and lands in the outer
        # ``except Exception`` handler. The function is fire-and-forget
        # telemetry in the request path; a broken audit writer must
        # never corrupt the ingestion response.
        _install_fake_audit(monkeypatch, raise_on_get_instance=True)
        _audit_log_validation_failure(
            [{"loc": ("tlc",)}],
            tenant_id=None,
            normalized={},
        )

    def test_missing_audit_module_is_swallowed(self, monkeypatch):
        # ``from shared.audit_logging import ...`` raises ImportError
        # when the entry is None — caught by the outer handler too.
        monkeypatch.setitem(sys.modules, "shared.audit_logging", None)
        _audit_log_validation_failure(
            [{"loc": ("tlc",)}],
            tenant_id=None,
            normalized={},
        )


# ---------------------------------------------------------------------------
# _validate_gln_format — ImportError fallback path
# ---------------------------------------------------------------------------


class TestValidateGlnFormatInlineFallback:
    """Exercises the legacy inline GS1 mod-10 check when
    ``shared.fsma_validation`` is unavailable. The happy delegate path
    is covered by ``test_epcis_gln_check_digit.py``; this class is
    about the *should-never-happen-in-prod* fallback.

    The valid-GLN fixture (``0614141999996``) is the same reference
    value the other test file uses; both paths must agree on it.
    """

    def test_fallback_accepts_valid_gln(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        assert _validate_gln_format("0614141999996") is True

    def test_fallback_rejects_bad_check_digit(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        # Same 12-digit body as the valid GLN above but with the check
        # digit flipped from 6 → 0.
        assert _validate_gln_format("0614141999990") is False

    def test_fallback_rejects_wrong_length(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        # 5 digits — not 13, so the length gate rejects before the
        # checksum runs.
        assert _validate_gln_format("12345") is False

    def test_fallback_rejects_non_digit(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        # Mostly digits + one letter — fails isdigit() regardless of
        # length, so the checksum never runs.
        assert _validate_gln_format("061414199999X") is False

    def test_fallback_rejects_empty(self, monkeypatch):
        # The ``if not gln`` short-circuit fires BEFORE the import, so
        # the ImportError branch isn't exercised here — but the return
        # is still False. Included so the branch remains pinned.
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", None)
        assert _validate_gln_format("") is False

    def test_empty_short_circuits_without_importing(self, monkeypatch):
        # Tighter version of the above: if we could observe the import,
        # we'd see it's never attempted. We observe indirectly by
        # checking that the function returns False even with a stub
        # that would raise on import.
        raiser = types.ModuleType("shared.fsma_validation")

        def _boom(*a, **kw):
            raise RuntimeError("should not be called")

        raiser.validate_gln = _boom  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "shared.fsma_validation", raiser)
        assert _validate_gln_format("") is False
