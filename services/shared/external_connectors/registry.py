"""Integration connector registry.

Central registry for all available connectors. Used by:
  - Settings API to show available integrations
  - Sync scheduler to run periodic pulls
  - Webhook router to dispatch inbound webhooks
  - Integrations page to show what's available
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from .base import ConnectorConfig, ConnectionStatus, IntegrationConnector

logger = logging.getLogger("connector-registry")

# Global registry mapping connector_id → connector class
_CONNECTOR_CLASSES: Dict[str, Type[IntegrationConnector]] = {}

# Active connector instances per tenant
_ACTIVE_CONNECTORS: Dict[str, Dict[str, IntegrationConnector]] = {}


def register_connector(connector_id: str, cls: Type[IntegrationConnector]) -> None:
    """Register a connector class for a given ID."""
    _CONNECTOR_CLASSES[connector_id] = cls
    logger.info("registered_connector id=%s class=%s", connector_id, cls.__name__)


def get_connector_class(connector_id: str) -> Optional[Type[IntegrationConnector]]:
    """Get a registered connector class by ID."""
    return _CONNECTOR_CLASSES.get(connector_id)


def list_available_connectors() -> List[Dict]:
    """List all registered connector classes with their metadata."""
    result = []
    for connector_id, cls in _CONNECTOR_CLASSES.items():
        # Create a temporary instance with empty config to get info
        try:
            config = ConnectorConfig(
                connector_id=connector_id,
                display_name=connector_id,
                category="unknown",
            )
            instance = cls(config)
            info = instance.get_connector_info()
            result.append(info)
        except Exception as exc:
            logger.warning(
                "connector_info_failed id=%s error=%s",
                connector_id, str(exc),
            )
            result.append({"id": connector_id, "name": connector_id, "error": str(exc)})
    return result


def get_or_create_connector(
    tenant_id: str,
    connector_id: str,
    config: ConnectorConfig,
) -> IntegrationConnector:
    """Get an existing connector instance for a tenant, or create one."""
    if tenant_id not in _ACTIVE_CONNECTORS:
        _ACTIVE_CONNECTORS[tenant_id] = {}

    tenant_connectors = _ACTIVE_CONNECTORS[tenant_id]
    if connector_id not in tenant_connectors:
        cls = _CONNECTOR_CLASSES.get(connector_id)
        if cls is None:
            raise ValueError(f"Unknown connector: {connector_id}")
        tenant_connectors[connector_id] = cls(config)

    return tenant_connectors[connector_id]


def get_tenant_connectors(tenant_id: str) -> Dict[str, IntegrationConnector]:
    """Get all active connectors for a tenant."""
    return _ACTIVE_CONNECTORS.get(tenant_id, {})


def remove_connector(tenant_id: str, connector_id: str) -> None:
    """Remove a connector instance for a tenant."""
    if tenant_id in _ACTIVE_CONNECTORS:
        _ACTIVE_CONNECTORS[tenant_id].pop(connector_id, None)


def get_all_integration_statuses(tenant_id: str) -> List[Dict]:
    """Get status of all registered connectors for a tenant.

    Returns connected status for active connectors, disconnected for
    registered-but-not-configured ones.
    """
    active = get_tenant_connectors(tenant_id)
    statuses = []

    for connector_id, cls in _CONNECTOR_CLASSES.items():
        if connector_id in active:
            statuses.append(active[connector_id].to_integration_status())
        else:
            info = {}
            try:
                config = ConnectorConfig(
                    connector_id=connector_id,
                    display_name=connector_id,
                    category="unknown",
                )
                info = cls(config).get_connector_info()
            except Exception as exc:
                logger.warning(
                    "connector_status_info_failed id=%s error=%s",
                    connector_id, str(exc),
                )
            statuses.append({
                "id": connector_id,
                "name": info.get("name", connector_id),
                "category": info.get("category", "unknown"),
                "status": ConnectionStatus.DISCONNECTED.value,
                "last_sync": None,
                "docs_url": info.get("docs_url"),
            })

    return statuses
