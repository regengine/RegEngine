"""External connectors for third-party integrations.

Provides base classes and concrete implementations for connecting
RegEngine to food safety platforms, ERPs, retailer networks, and
IoT sensor providers.
"""

from .base import ConnectionStatus, ConnectorConfig, IntegrationConnector, SyncResult

__all__ = [
    "IntegrationConnector",
    "ConnectorConfig",
    "SyncResult",
    "ConnectionStatus",
]
