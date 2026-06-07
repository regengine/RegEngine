"""Register all available connectors.

Import this module at app startup to make all connectors
available in the registry.
"""

from .csv_sftp import CSVSFTPConnector
from .food_safety import (
    FoodDocsConnector,
    FoodReadyConnector,
    TiveConnector,
)
from .inflow_lab import InflowLabConnector
from .registry import register_connector
from .retailers import (
    CostcoConnector,
    KrogerConnector,
    WalmartGDSNConnector,
    WholeFoodsConnector,
)
from .safetyculture import SafetyCultureConnector


def register_all_connectors() -> None:
    """Register all built-in connectors."""
    # Food Safety Platforms
    register_connector("safetyculture", SafetyCultureConnector)
    register_connector("foodready", FoodReadyConnector)
    register_connector("fooddocs", FoodDocsConnector)

    # IoT / Cold Chain
    register_connector("tive", TiveConnector)

    # Retailer Networks
    register_connector("walmart", WalmartGDSNConnector)
    register_connector("kroger", KrogerConnector)
    register_connector("whole_foods", WholeFoodsConnector)
    register_connector("costco", CostcoConnector)

    # Generic (covers SAP, NetSuite, Fishbowl, QuickBooks)
    register_connector("csv_sftp", CSVSFTPConnector)

    # Developer / simulator integrations
    register_connector("inflow_lab", InflowLabConnector, aliases=("inflow-lab",))
