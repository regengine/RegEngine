"""``EPCIS_BATCH_TRANSACTIONAL`` gate and router mode dispatch.

Mid-batch rollback of real events needs a structurally valid EPCIS record.
Mode dispatch is stubbed and the request body is an empty dict.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app.epcis import persistence as persistence_mod  # noqa: E402

router_mod = importlib.import_module("app.epcis.router")


class TestBatchTransactionalEnvGate:
    def test_default_unset_is_atomic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("EPCIS_BATCH_TRANSACTIONAL", raising=False)
        assert persistence_mod._batch_transactional() is True

    @pytest.mark.parametrize("val", ["1", "true", "yes", "on", "atomic"])
    def test_truthy_variants_are_atomic(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("EPCIS_BATCH_TRANSACTIONAL", val)
        assert persistence_mod._batch_transactional() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "off", "partial"])
    def test_falsy_variants_opt_out(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("EPCIS_BATCH_TRANSACTIONAL", val)
        assert persistence_mod._batch_transactional() is False


class TestRouterModeDefaultsRespectEnvGate:
    def test_no_mode_with_env_true_dispatches_to_atomic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"atomic": 0, "partial": 0}

        def _fake_atomic(tenant: str, events: list[dict]) -> list:
            calls["atomic"] += 1
            return [({"status": 201, "cte_id": "x"}, 201) for _ in events]

        def _fake_single(tenant: str, event: dict):
            calls["partial"] += 1
            return ({"status": 201, "cte_id": "x"}, 201)

        monkeypatch.setattr(router_mod, "_ingest_batch_events_db_atomic", _fake_atomic)
        monkeypatch.setattr(router_mod, "_ingest_single_event", _fake_single)
        monkeypatch.setattr(router_mod, "_batch_transactional", lambda: True)
        monkeypatch.setattr(
            router_mod,
            "_resolve_authenticated_tenant",
            lambda request, x, y: "tenant-router",
        )

        body = router_mod.BatchIngestRequest(events=[{}])
        resp = asyncio.run(
            router_mod.ingest_epcis_batch(
                request=MagicMock(),
                body=body,
                mode=None,
                x_tenant_id="tenant-router",
                x_regengine_api_key="k",
                _=None,
            )
        )
        assert resp.status_code == 201
        assert calls == {"atomic": 1, "partial": 0}

    def test_no_mode_with_env_false_dispatches_to_partial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = {"atomic": 0, "partial": 0}

        def _fake_atomic(tenant: str, events: list[dict]) -> list:
            calls["atomic"] += 1
            return [({"status": 201, "cte_id": "x"}, 201) for _ in events]

        def _fake_single(tenant: str, event: dict):
            calls["partial"] += 1
            return ({"status": 201, "cte_id": "x"}, 201)

        monkeypatch.setattr(router_mod, "_ingest_batch_events_db_atomic", _fake_atomic)
        monkeypatch.setattr(router_mod, "_ingest_single_event", _fake_single)
        monkeypatch.setattr(router_mod, "_batch_transactional", lambda: False)
        monkeypatch.setattr(
            router_mod,
            "_resolve_authenticated_tenant",
            lambda request, x, y: "tenant-router",
        )

        body = router_mod.BatchIngestRequest(events=[{}])
        resp = asyncio.run(
            router_mod.ingest_epcis_batch(
                request=MagicMock(),
                body=body,
                mode=None,
                x_tenant_id="tenant-router",
                x_regengine_api_key="k",
                _=None,
            )
        )
        assert resp.status_code == 201
        assert calls == {"atomic": 0, "partial": 1}
