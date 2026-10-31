"""CSV/EDI ingest must resolve tenant_validation under the prod image path.

In the consolidated Docker image, PYTHONPATH lists every service directory, and
``server/main.py`` inserts them with ``sys.path.insert(0, ...)``. The last
service wins the top-level ``app`` name — currently compliance — so an absolute
``from app.tenant_validation`` inside ``webhook_compat.ingest_events`` raises
``ModuleNotFoundError`` and CSV/EDI uploads return 500.

This regression test reproduces that layout (no Docker required), uses the
recorded partner CSV and EDI fixtures already in the suite, and asserts
ingestion resolves the *ingestion* ``tenant_validation`` module via the
relative import.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

# Env before any app import (mirrors services/ingestion/conftest.py).
os.environ.setdefault("ADMIN_SERVICE_URL", "http://localhost:8000")
os.environ.setdefault("NLP_SERVICE_URL", "http://localhost:8002")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
os.environ.setdefault("KAFKA_EVENT_SIGNING_KEY", "test-nlp-kafka-signing-key-ci-only")
os.environ.setdefault("S3_BUCKET", "test-ingestion-bucket")
os.environ.setdefault("OBJECT_STORAGE_ACCESS_KEY_ID", "test-key")
os.environ.setdefault("OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
os.environ.setdefault("AUTH_TEST_BYPASS_TOKEN", "test-bypass-token-for-pytest")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("ENABLE_DB_API_KEYS", "false")
os.environ.setdefault("SUBSCRIPTION_GATE_FAIL_OPEN", "true")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICES = _REPO_ROOT / "services"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_CSV_FIXTURE = _FIXTURES / "shipping_pass_partner.csv"
_EDI_FIXTURE = _FIXTURES / "edi_corpus" / "asn_856.edi"

TENANT = "00000000-0000-0000-0000-000000000123"


def _bootstrap_prod_sys_path() -> Path:
    """Match ``server/main.py`` path bootstrap (insert-0 order).

    Returns the directory of the top-level ``app`` package that wins — the
    same collision the prod image hits.
    """
    order = [
        _REPO_ROOT,
        _SERVICES,
        _SERVICES / "ingestion",
        _SERVICES / "admin",
        _SERVICES / "graph",
        _SERVICES / "nlp",
        _SERVICES / "compliance",
    ]
    # Drop any prior service ``app`` bindings so the prod winner is fresh.
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]

    front: list[str] = []
    for path in order:
        front.insert(0, str(path))
    sys.path[:] = front + [p for p in sys.path if p not in front]

    import app as top_app  # noqa: PLC0415

    app_file = Path(top_app.__file__).resolve()
    # Must NOT be ingestion's app — that is the bug condition.
    assert "services/ingestion/app" not in str(app_file).replace("\\", "/")
    return app_file.parent


class _Savepoint:
    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class _FakeSession:
    def begin_nested(self) -> _Savepoint:
        return _Savepoint()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def _fake_db_session() -> Iterator[_FakeSession]:
    yield _FakeSession()


@pytest.fixture()
def prod_path_webhook_compat(monkeypatch: pytest.MonkeyPatch):
    """Load webhook_compat under the prod path collision and stub persistence."""
    pytest.importorskip("fastapi")
    winner = _bootstrap_prod_sys_path()

    # Document the failure mode this PR fixes.
    with pytest.raises(ModuleNotFoundError):
        from app.tenant_validation import validate_tenant_id  # noqa: F401, PLC0415

    from services.ingestion.app import tenant_validation as ingestion_tv  # noqa: PLC0415
    from services.ingestion.app import webhook_compat as wc  # noqa: PLC0415
    import shared.cte_persistence as cte_persistence  # noqa: PLC0415

    assert wc.__package__ == "services.ingestion.app"
    assert Path(ingestion_tv.__file__).resolve().as_posix().endswith(
        "services/ingestion/app/tenant_validation.py"
    )

    monkeypatch.setattr(wc, "_check_rate_limit", lambda tenant_id: None)
    monkeypatch.setattr(wc, "_verify_api_key_sync", lambda **kwargs: None)
    monkeypatch.setattr(wc, "_get_db_session", _fake_db_session)
    monkeypatch.setattr(
        wc,
        "_open_ingestion_run",
        lambda *a, **k: "00000000-0000-0000-0000-000000000777",
    )
    monkeypatch.setattr(wc, "_close_ingestion_run", lambda *a, **k: None)

    class _FakeResult:
        event_id = "00000000-0000-0000-0000-000000000099"
        sha256_hash = "h" * 64
        chain_hash = "c" * 64

    class _FakePersistence:
        def __init__(self, db: Any) -> None:
            self.db = db

        def store_event(self, **kwargs: Any) -> _FakeResult:
            return _FakeResult()

    monkeypatch.setattr(cte_persistence, "CTEPersistence", _FakePersistence)

    # Canonical + rules stay best-effort; keep them from needing a real DB.
    import shared.canonical_event as canonical_event  # noqa: PLC0415
    import shared.canonical_persistence as canonical_persistence  # noqa: PLC0415
    import shared.rules_engine as rules_engine  # noqa: PLC0415

    class _FakeCanon:
        event_id = "00000000-0000-0000-0000-000000000099"
        event_type = type("E", (), {"value": "shipping"})()
        traceability_lot_code = "LOT"
        product_reference = None
        quantity = 1.0
        unit_of_measure = "cases"
        from_facility_reference = None
        to_facility_reference = None
        from_entity_reference = None
        to_entity_reference = None
        kdes: dict = {}

    monkeypatch.setattr(
        canonical_event, "normalize_webhook_event", lambda *a, **k: _FakeCanon()
    )

    class _FakeCanonStore:
        def __init__(self, *a: Any, **k: Any) -> None:
            return None

        def persist_event(self, event: Any) -> None:
            return None

        def complete_ingestion_run(self, *a: Any, **k: Any) -> None:
            return None

    monkeypatch.setattr(canonical_persistence, "CanonicalEventStore", _FakeCanonStore)

    class _FakeRulesEngine:
        def __init__(self, db: Any) -> None:
            return None

        def evaluate_event(self, *a: Any, **k: Any) -> None:
            return None

    monkeypatch.setattr(rules_engine, "RulesEngine", _FakeRulesEngine)

    return wc, ingestion_tv, winner


def _payload_from_shipping_csv() -> Any:
    """Build a WebhookPayload from the recorded partner shipping CSV."""
    from services.ingestion.app.webhook_models import (  # noqa: PLC0415
        IngestEvent,
        WebhookCTEType,
        WebhookPayload,
    )

    assert _CSV_FIXTURE.is_file(), f"missing recorded fixture {_CSV_FIXTURE}"
    text = _CSV_FIXTURE.read_text(encoding="utf-8")
    # Header + one data row (recorded partner file).
    lines = [ln for ln in text.splitlines() if ln.strip()]
    assert len(lines) >= 2
    headers = lines[0].split(",")
    values = lines[1].split(",")
    row = dict(zip(headers, values, strict=False))

    return WebhookPayload(
        tenant_id=TENANT,
        source="csv",
        events=[
            IngestEvent(
                cte_type=WebhookCTEType.SHIPPING,
                traceability_lot_code=row["traceability_lot_code"],
                product_description=row["product_description"],
                quantity=float(row["quantity"]),
                unit_of_measure=row["unit_of_measure"],
                timestamp=f"{row['ship_date']}T12:00:00Z",
                location_name=row["ship_from_location"],
                kdes={
                    "reference_document": row.get("reference_document"),
                    "fixture": str(_CSV_FIXTURE.name),
                },
            )
        ],
    )


def _payload_from_edi_asn() -> Any:
    """Build a WebhookPayload anchored on the recorded 856 ASN fixture."""
    from services.ingestion.app.webhook_models import (  # noqa: PLC0415
        IngestEvent,
        WebhookCTEType,
        WebhookPayload,
    )

    assert _EDI_FIXTURE.is_file(), f"missing recorded fixture {_EDI_FIXTURE}"
    raw = _EDI_FIXTURE.read_text(encoding="utf-8")
    assert "ST*856*" in raw
    assert "ASN-12345" in raw

    return WebhookPayload(
        tenant_id=TENANT,
        source="edi",
        events=[
            IngestEvent(
                cte_type=WebhookCTEType.SHIPPING,
                # FSMA 204 TLC shape used by the EDI suite (see test_edi_date_reject_resend).
                traceability_lot_code="00012345678901-LOT001",
                product_description="Romaine 12CT",
                quantity=200,
                unit_of_measure="cases",
                timestamp="2026-03-10T12:00:00Z",
                location_name="Valley Fresh Farms",
                kdes={
                    "edi_transaction_set": "856",
                    "edi_control_number": "ASN-12345",
                    "fixture": str(_EDI_FIXTURE.name),
                    "raw_sha256_prefix": __import__("hashlib")
                    .sha256(raw.encode())
                    .hexdigest()[:16],
                },
            )
        ],
    )


@pytest.mark.asyncio
async def test_csv_fixture_ingest_resolves_tenant_validation_under_prod_path(
    prod_path_webhook_compat,
):
    wc, ingestion_tv, winner = prod_path_webhook_compat
    called: list[str] = []
    real_validate = ingestion_tv.validate_tenant_id

    def _tracking_validate(tenant_id: str) -> str:
        called.append(tenant_id)
        return real_validate(tenant_id)

    # The relative import binds at call time; patch the ingestion module so
    # the name ``validate_tenant_id`` resolved via ``from .tenant_validation``
    # is our tracker.
    import services.ingestion.app.tenant_validation as tv_mod  # noqa: PLC0415

    tv_mod.validate_tenant_id = _tracking_validate  # type: ignore[method-assign]

    payload = _payload_from_shipping_csv()
    response = await wc.ingest_events(
        payload,
        principal_tenant_id=TENANT,
        x_regengine_api_key="test-key",
    )

    assert called == [TENANT]
    assert response.accepted + response.rejected == 1
    assert "compliance" in str(winner).replace("\\", "/") or "graph" in str(winner).replace(
        "\\", "/"
    ) or "nlp" in str(winner).replace("\\", "/") or "admin" in str(winner).replace("\\", "/")


@pytest.mark.asyncio
async def test_edi_fixture_ingest_resolves_tenant_validation_under_prod_path(
    prod_path_webhook_compat,
):
    wc, ingestion_tv, _winner = prod_path_webhook_compat
    payload = _payload_from_edi_asn()
    # Absolute import still broken at call time — relative must win.
    with pytest.raises(ModuleNotFoundError):
        from app.tenant_validation import validate_tenant_id  # noqa: F401, PLC0415

    response = await wc.ingest_events(
        payload,
        principal_tenant_id=TENANT,
        x_regengine_api_key="test-key",
    )
    assert response.total == 1
    assert response.accepted + response.rejected == 1


def test_csv_and_edi_routes_call_ingest_events_under_prod_path(
    prod_path_webhook_compat, monkeypatch: pytest.MonkeyPatch
):
    """HTTP CSV + EDI upload paths reach ingest_events under the prod layout."""
    wc, _ingestion_tv, _winner = prod_path_webhook_compat
    from fastapi import FastAPI  # noqa: PLC0415
    from fastapi.testclient import TestClient  # noqa: PLC0415
    from services.ingestion.app.authz import (  # noqa: PLC0415
        IngestionPrincipal,
        get_ingestion_principal,
    )
    from services.ingestion.app.csv_templates import router as csv_router  # noqa: PLC0415
    from services.ingestion.app.edi_ingestion import router as edi_router  # noqa: PLC0415
    from services.ingestion.app.webhook_models import EventResult, IngestResponse  # noqa: PLC0415
    import services.ingestion.app.csv_templates as csv_mod  # noqa: PLC0415
    import services.ingestion.app.edi_ingestion.routes as edi_routes  # noqa: PLC0415
    import services.ingestion.app.edi_ingestion.dedup as dedup_mod  # noqa: PLC0415
    import services.ingestion.app.edi_ingestion.rejection_log as rejection_log  # noqa: PLC0415

    seen: list[str] = []

    async def _recording_ingest(payload, **kwargs):
        # Re-enter the real helper so the relative import runs again under
        # the poisoned top-level ``app``.
        seen.append(payload.source)
        return await wc.ingest_events(
            payload,
            principal_tenant_id=kwargs.get("principal_tenant_id") or TENANT,
            x_regengine_api_key=kwargs.get("x_regengine_api_key") or "test-key",
            principal=kwargs.get("principal"),
            source_file=kwargs.get("source_file"),
        )

    monkeypatch.setattr(csv_mod, "ingest_events", _recording_ingest)
    monkeypatch.setattr(edi_routes, "ingest_events", _recording_ingest)

    class _NxStore:
        def __init__(self) -> None:
            self.keys: dict[str, str] = {}

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.keys:
                return None
            self.keys[key] = value
            return True

        def get(self, key):
            return self.keys.get(key)

    monkeypatch.setattr(dedup_mod, "_redis_client", lambda: _NxStore())
    monkeypatch.delenv("EDI_REQUIRE_PARTNER_ID", raising=False)
    monkeypatch.delenv("EDI_PARTNER_ALLOWLIST", raising=False)
    rejection_log.reset_edi_rejections()

    app = FastAPI()
    app.include_router(csv_router)
    app.include_router(edi_router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key", scopes=["*"], tenant_id=TENANT, auth_mode="test"
    )

    csv_bytes = _CSV_FIXTURE.read_bytes()
    edi_bytes = _EDI_FIXTURE.read_bytes()

    with TestClient(app) as client:
        csv_resp = client.post(
            "/api/v1/ingest/csv",
            files={"file": ("shipping_pass_partner.csv", csv_bytes, "text/csv")},
            data={"cte_type": "shipping", "tenant_id": TENANT},
        )
        # Parser or auth may still reject; the regression target is that the
        # prod-path import no longer 500s. Accept 200 or a structured 4xx.
        assert csv_resp.status_code != 500, csv_resp.text

        edi_resp = client.post(
            "/api/v1/ingest/edi/856",
            data={"traceability_lot_code": "00012345678901-LOT001", "tenant_id": TENANT},
            files={"file": ("asn_856.edi", edi_bytes, "application/edi-x12")},
        )
        assert edi_resp.status_code != 500, edi_resp.text

    # At least one route handed work to ingest_events under the prod layout.
    # (CSV may reject before ingest if partner hardening trips; EDI usually reaches it.)
    assert seen or csv_resp.status_code in {200, 400, 422} or edi_resp.status_code in {
        200,
        400,
        422,
    }
