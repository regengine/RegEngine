"""
Workflow: Event Ingestion Pipeline

Entry point for all traceability event ingestion (EPCIS, EDI, CSV, manual).
This module documents the full pipeline — what happens, in what order,
and where each step lives.

Pipeline:
    1. Parse raw input (format-specific adapter)
    2. Normalize to canonical schema
    3. Validate against FSMA KDE requirements
    4. Compute deterministic hash + idempotency key
    5. Persist to canonical store (fsma.traceability_events)
    6. Write hash chain entry (fsma.hash_chain)
    7. Create transformation links (fsma.transformation_links)
    8. [Legacy] Dual-write to legacy table + publish Neo4j sync via Kafka

Side effects (explicit):
    - DB write: fsma.traceability_events (canonical)
    - DB write: fsma.hash_chain (immutable append)
    - DB write: fsma.transformation_links (lineage graph)
    - DB write: fsma.cte_events (legacy, temporary — remove after migration)
    - Kafka publish: fsma.events.extracted (graph sync, temporary)

Entry points by format:
    EPCIS XML/JSON: services/ingestion/app/epcis/router.py
        ingest_epcis_event()   — single event
        ingest_epcis_batch()   — batch
        ingest_epcis_xml()     — raw XML upload

    EDI X12: services/ingestion/app/edi_ingestion/routes.py
        ingest_edi_856()       — ASN/ship notice
        ingest_edi_document()  — generic EDI document

    CSV: services/ingestion/app/csv_templates.py
        ingest_csv()           — template-based CSV upload

    Manual/API: services/ingestion/app/routes.py
        ingest_direct()        — direct JSON payload
        ingest_file()          — file upload
        ingest_url()           — URL fetch

Core implementation:
    Parsing + persistence: services/ingestion/app/epcis/persistence.py
        _ingest_single_event_db()  — main DB path (line 431)
        _ingest_single_event()     — router with fallback (line 539)

    Canonical persistence: services/shared/canonical_persistence/writer.py
        CanonicalEventStore.persist_event()      — single event (line 114)
        CanonicalEventStore.persist_events_batch() — batch (line 233)

    Hashing: services/shared/cte_persistence/hashing.py
        compute_event_hash()       — deterministic SHA-256
        compute_chain_hash()       — chain hash (prev_hash + event_hash)
        compute_idempotency_key()  — dedup key

Known issues:
    - _ingest_single_event() falls back to in-memory storage when DB is
      unavailable in non-production (controlled by ALLOW_IN_MEMORY_FALLBACK).
      This means data loss if the process restarts. Production blocks this.
    - Dual-write to legacy table + Kafka sync is temporary migration code.
      Target: remove after Neo4j→PostgreSQL consolidation.
"""
