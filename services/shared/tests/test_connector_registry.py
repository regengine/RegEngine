"""Tenant isolation and lifecycle for the connector registry.

The ingestion router scopes every connector lookup by tenant
(``get_or_create_connector(tenant_id, ...)``). These tests pin that
contract: one tenant's connector instances, credentials and statuses
must never leak into another tenant's view.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest

from services.shared.external_connectors import registry as reg
from services.shared.external_connectors.base import (
    ConnectionStatus,
    ConnectorConfig,
    IntegrationConnector,
    NormalizedCTEEvent,
)
from services.shared.external_connectors.register_all import register_all_connectors


class _DummyConnector(IntegrationConnector):
    async def test_connection(self) -> bool:
        self._status = ConnectionStatus.CONNECTED
        return True

    async def fetch_events(
        self,
        since: Optional[datetime] = None,
        cursor: Optional[str] = None,
        limit: int = 100,
    ) -> tuple[List[NormalizedCTEEvent], Optional[str]]:
        return [], None

    def normalize_event(self, raw_event: Dict[str, Any]) -> NormalizedCTEEvent:
        return NormalizedCTEEvent(
            cte_type="receiving",
            traceability_lot_code=raw_event.get("lot", ""),
            product_description=raw_event.get("product", ""),
            quantity=None,
            unit_of_measure=None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def get_connector_info(self) -> Dict[str, Any]:
        return {"id": self.config.connector_id, "name": "Dummy", "category": "developer"}


def _config(connector_id: str = "dummy") -> ConnectorConfig:
    return ConnectorConfig(
        connector_id=connector_id,
        display_name=connector_id,
        category="developer",
        tenant_id="t1",
    )


@pytest.fixture
def isolated_registry():
    """Snapshot and restore the global registry so tests never leak state."""
    saved_classes = dict(reg._CONNECTOR_CLASSES)
    saved_aliases = dict(reg._CONNECTOR_ALIASES)
    saved_active = {tenant: dict(items) for tenant, items in reg._ACTIVE_CONNECTORS.items()}
    yield reg
    reg._CONNECTOR_CLASSES.clear()
    reg._CONNECTOR_CLASSES.update(saved_classes)
    reg._CONNECTOR_ALIASES.clear()
    reg._CONNECTOR_ALIASES.update(saved_aliases)
    reg._ACTIVE_CONNECTORS.clear()
    for tenant, items in saved_active.items():
        reg._ACTIVE_CONNECTORS[tenant] = items


class TestRegistration:
    def test_unknown_connector_class_is_none(self, isolated_registry):
        assert isolated_registry.get_connector_class("no-such-connector") is None

    def test_register_and_resolve_alias(self, isolated_registry):
        isolated_registry.register_connector("dummy_canonical", _DummyConnector, aliases=("dummy-alias",))
        assert isolated_registry.resolve_connector_id("dummy-alias") == "dummy_canonical"
        assert isolated_registry.get_connector_class("dummy-alias") is _DummyConnector
        assert isolated_registry.get_connector_class("dummy_canonical") is _DummyConnector

class TestTenantIsolation:
    def test_instances_are_per_tenant(self, isolated_registry):
        isolated_registry.register_connector("dummy_iso", _DummyConnector)
        first = isolated_registry.get_or_create_connector("tenant-a", "dummy_iso", _config())
        second = isolated_registry.get_or_create_connector("tenant-b", "dummy_iso", _config())
        assert first is not second

    def test_tenant_connector_maps_do_not_leak(self, isolated_registry):
        isolated_registry.register_connector("dummy_leak", _DummyConnector)
        isolated_registry.get_or_create_connector("tenant-a", "dummy_leak", _config())
        assert "dummy_leak" not in isolated_registry.get_tenant_connectors("tenant-b")
        assert isolated_registry.get_tenant_connectors("never-seen-tenant") == {}

    def test_same_tenant_returns_same_instance(self, isolated_registry):
        """Repeated lookups reuse the cached instance (idempotent)."""
        isolated_registry.register_connector("dummy_reuse", _DummyConnector)
        first = isolated_registry.get_or_create_connector("tenant-a", "dummy_reuse", _config())
        second = isolated_registry.get_or_create_connector("tenant-a", "dummy_reuse", _config())
        assert first is second

    def test_unknown_connector_raises(self, isolated_registry):
        with pytest.raises(ValueError, match="Unknown connector"):
            isolated_registry.get_or_create_connector("tenant-a", "missing", _config())

class TestRemoval:
    def test_remove_only_affects_named_tenant(self, isolated_registry):
        isolated_registry.register_connector("dummy_rm", _DummyConnector)
        isolated_registry.get_or_create_connector("tenant-a", "dummy_rm", _config())
        isolated_registry.get_or_create_connector("tenant-b", "dummy_rm", _config())
        isolated_registry.remove_connector("tenant-a", "dummy_rm")
        assert "dummy_rm" not in isolated_registry.get_tenant_connectors("tenant-a")
        assert "dummy_rm" in isolated_registry.get_tenant_connectors("tenant-b")

    def test_remove_unknown_is_noop(self, isolated_registry):
        isolated_registry.remove_connector("ghost-tenant", "ghost-connector")


class TestStatuses:
    async def test_statuses_are_scoped_to_requesting_tenant(self, isolated_registry):
        isolated_registry.register_connector("dummy_st", _DummyConnector)
        connector = isolated_registry.get_or_create_connector(
            "tenant-a", "dummy_st", _config("dummy_st")
        )
        assert await connector.test_connection() is True
        active = {
            entry["id"]: entry
            for entry in isolated_registry.get_all_integration_statuses("tenant-a")
        }
        other = {
            entry["id"]: entry
            for entry in isolated_registry.get_all_integration_statuses("tenant-b")
        }
        assert active["dummy_st"]["status"] == ConnectionStatus.CONNECTED.value
        assert other["dummy_st"]["status"] == ConnectionStatus.DISCONNECTED.value
        assert other["dummy_st"]["last_sync"] is None

class TestRegisterAll:
    def test_all_builtin_connector_ids_resolve(self, isolated_registry):
        register_all_connectors()
        for connector_id in (
            "safetyculture",
            "foodready",
            "fooddocs",
            "tive",
            "walmart",
            "kroger",
            "whole_foods",
            "costco",
            "csv_sftp",
        ):
            assert isolated_registry.get_connector_class(connector_id) is not None, connector_id

    def test_inflow_lab_alias_resolves(self, isolated_registry):
        register_all_connectors()
        assert (
            isolated_registry.get_connector_class("inflow-lab")
            is isolated_registry.get_connector_class("inflow_lab")
        )
