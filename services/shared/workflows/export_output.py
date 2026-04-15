"""
Workflow: FDA Export / Regulator Output

Generates compliance export packages for FDA 24-hour traceability requests.
This is the revenue-critical output — the thing customers pay for.

Pipeline:
    1. Query canonical events (by TLC, date range, or recall filter)
    2. Format as FDA-expected CSV with KDE columns
    3. Compute content hash for integrity verification
    4. Log export to audit trail (fsma.export_log)
    5. Return CSV/PDF as streaming response

Export formats:
    - CSV v1: Legacy format from fsma.cte_events table
    - CSV v2: Canonical model format from fsma.traceability_events (preferred)
    - PDF: Formatted compliance report
    - Merkle proof: Cryptographic proof of event inclusion in hash chain

Entry point:
    services/ingestion/app/fda_export/router.py
        GET  /api/v1/fda/export         — single TLC export
        GET  /api/v1/fda/export/all     — all events (date-filtered)
        GET  /api/v1/fda/export/v2      — canonical model export
        GET  /api/v1/fda/export/recall  — recall-filtered export
        POST /api/v1/fda/export/verify  — verify previous export integrity
        GET  /api/v1/fda/export/merkle-root  — tenant hash chain root
        GET  /api/v1/fda/export/merkle-proof — event inclusion proof
        GET  /api/v1/fda/trace/{tlc}    — transformation graph trace

    Query layer:
        services/ingestion/app/fda_export/queries.py
            fetch_v2_events()        — read from canonical model
            fetch_recall_events()    — recall-filtered query
            fetch_trace_graph_data() — transformation graph
            log_v2_export()          — write export audit record

    Formatting:
        services/ingestion/app/fda_export/formatters.py
            generate_csv_v2_and_hash()  — CSV + content hash
            build_csv_response()        — streaming response builder
            build_package_response()    — multi-file package

    Verification:
        services/ingestion/app/fda_export/verification.py
            verify_export_handler()  — re-hash and compare

    Merkle proofs:
        services/ingestion/app/fda_export/merkle.py
            get_merkle_root_handler()
            get_merkle_proof_handler()

Side effects (explicit):
    - DB read: fsma.traceability_events, fsma.cte_events, fsma.hash_chain
    - DB write: fsma.export_log (audit record of what was exported, when)
    - No mutations to source data — exports are read-only

Known issues:
    - Export history endpoint reads from fsma.export_log which may not
      exist in all environments (created by migration v053).
    - v1 CSV format reads from legacy fsma.cte_events table. Will be
      removed after migration to canonical-only model.
"""
