"""
Standardized Ingestion Adapters.

Each adapter handles one input format: parse raw input, normalize to
canonical schema, validate, and map to canonical events.

Implementing a new adapter:
    1. Subclass IngestAdapter
    2. Implement parse(), normalize(), validate(), map_to_canonical()
    3. Register in ADAPTER_REGISTRY
    4. Wire to a route in routes.py

Existing adapters:
    epcis   — EPCIS 2.0 XML/JSON (services/ingestion/app/epcis/)
    edi     — EDI X12 856/850/810/861 (services/ingestion/app/edi_ingestion/)
    csv     — Template-based CSV upload (services/ingestion/app/csv_templates.py)
    manual  — Direct JSON payload (services/ingestion/app/routes.py:ingest_direct)
"""

from .base import IngestAdapter, AdapterResult, ADAPTER_REGISTRY

__all__ = ["IngestAdapter", "AdapterResult", "ADAPTER_REGISTRY"]
