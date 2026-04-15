"""Backward-compatibility shim — code moved to epcis/ package."""
from services.ingestion.app.epcis.router import router  # noqa: F401
from services.ingestion.app.epcis.persistence import (  # noqa: F401
    _epcis_store,
    _epcis_idempotency_index,
)
