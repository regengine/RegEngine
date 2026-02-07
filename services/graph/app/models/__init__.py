"""Graph models for tenant overlay system.

Re-exports from shared.tenant_models for backward compatibility.
New code should import directly from shared.tenant_models.
"""

from shared.tenant_models import (
    ControlMapping,
    CustomerProduct,
    MappingType,
    ProductControlLink,
    ProductType,
    TenantControl,
)

__all__ = [
    "TenantControl",
    "ControlMapping",
    "CustomerProduct",
    "MappingType",
    "ProductControlLink",
    "ProductType",
]
