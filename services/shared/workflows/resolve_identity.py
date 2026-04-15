"""
Workflow: Identity Resolution Pipeline

Matches and merges entity records when ingested events reference the same
real-world entity with different identifiers (e.g., GLN variants, name
typos, lot code aliases).

Pipeline:
    1. Generate candidates — fuzzy match against existing entities
    2. Score candidates — confidence scoring per match pair
    3. Auto-resolve high-confidence matches (above AMBIGUOUS_THRESHOLD_HIGH)
    4. Queue ambiguous matches for human review (between LOW and HIGH)
    5. Execute merge/split actions on confirmed matches
    6. Persist resolution history for audit trail

Trigger:
    Called synchronously during ingestion when entity collisions are detected.
    NOT a background process — runs inline within the ingestion request.

Entry point:
    services/shared/identity_resolution/service.py
        IdentityResolutionService  — main orchestrator class

    Thresholds: services/shared/identity_resolution/constants.py
        AMBIGUOUS_THRESHOLD_LOW   — below this: no match
        AMBIGUOUS_THRESHOLD_HIGH  — above this: auto-merge

Side effects (explicit):
    - DB read: entity lookup for candidate generation
    - DB write: merge/split records
    - DB write: resolution history (audit)

Known issues:
    - Identity resolution is tightly coupled to Neo4j graph queries
      in the current implementation. Target: PostgreSQL-only after
      graph consolidation.
    - Review workflow (human-in-the-loop) routes through admin service
      but the trigger path is not fully wired end-to-end.
"""
