"""
Workflow orchestration entry points.

Each module in this package represents one production-critical workflow.
These are the ONLY entry points for major business flows — if you need
to understand what happens when an event is ingested, evaluated, or
exported, start here.

Production spine (in order):
    ingest_event → canonicalize → resolve_identity → evaluate_compliance → produce_audit → export_output
"""
