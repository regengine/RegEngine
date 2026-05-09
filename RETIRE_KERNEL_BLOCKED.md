# Retire kernel/ — BLOCKED

The `epic-g-retire-kernel` task assumed `kernel/` was orphan (no
`services/` imports). It is not. Safety check found 8 live imports
across 6 service files, plus several test stubs.

## Live imports (services/)

| File | Line | Import |
| --- | --- | --- |
| services/ingestion/app/task_handlers_discovery.py | 17 | `from kernel.discovery import discovery` |
| services/ingestion/app/routes_ingest.py | 77 | `from kernel.obligation.regulation_loader import RegulationLoader` |
| services/ingestion/app/routes_scraping.py | 24 | `from kernel.discovery import discovery` |
| services/graph/app/routers/regulations.py | 188 | `from kernel.graph import MappingEngine` |
| services/graph/app/routers/fsma/traceability.py | 299, 324, 349 | `from kernel.graph_traceability import TraceabilityLinker` |
| services/graph/app/routers/fsma/wizard.py | 25 | `from kernel.reporting.fsma_engine import FSMAApplicabilityEngine` |

Tests under `services/ingestion/tests` and `services/graph/tests` also
`sys.modules[]`-stub `kernel.*` packages (test_task_handlers_discovery_1342,
test_fsma_wizard_routes, test_fsma_physics) — confirming the production
code paths really do reach into kernel.

## Implication

`kernel/` cannot be deleted in a single chore PR. Each consumer needs
a migration plan first:

1. **services/ingestion/app/routes_ingest.py** — `RegulationLoader`
   needs to move to `services/ingestion/` or `services/shared/` (or be
   deleted if dead).
2. **services/ingestion** discovery (`routes_scraping.py`,
   `task_handlers_discovery.py`) — `kernel.discovery.discovery.scrape`
   needs an in-service replacement.
3. **services/graph/app/routers/regulations.py** — `MappingEngine`
   import is inside a function; check whether the route is reachable
   and whether MappingEngine is actually used.
4. **services/graph/app/routers/fsma/traceability.py** — three
   function-local imports of `TraceabilityLinker`; same triage.
5. **services/graph/app/routers/fsma/wizard.py** — module-level import
   of `FSMAApplicabilityEngine`; this is on the FSMA wizard surface.

## Recommended next steps

- File a meta-issue under `epic-g-retire-kernel` to enumerate each
  kernel surface and its consumer, and decide per-surface: migrate,
  inline, or delete-and-fix-callers.
- The codegen RCE risk noted in `project_kernel_audit_2026_04_17`
  still applies; if the codegen path is unreachable from the live
  routes above, it may be deletable as a sub-PR even before full
  retirement.
- The `cli/regengine.py` `compile vertical` / `list-verticals` /
  `validate vertical` commands should still be safe to remove
  separately if they are the only callers of the codegen surface —
  worth a focused follow-up PR.

## What this PR does

Nothing functional. It exists only to surface the blocker so the
parent epic isn't tracked as "in flight" while actually stuck.
