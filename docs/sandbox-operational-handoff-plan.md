# Sandbox Operational Handoff Plan

Branch: `codex/sandbox-operational-handoff`

## Goal

Make the free sandbox and Inflow Lab feel like one operational workflow:

1. Diagnose free CSV data.
2. Save the result as a test run.
3. Carry detected headers, rows, and fixes into import mapping.
4. Monitor a live/authenticated feed separately from sandbox data.
5. Generate evidence only from authenticated, persisted records.

## Shared Rules

- No sandbox result may claim FDA-ready, FDA submission-ready, or production evidence-ready status.
- Primary copy should say diagnose, correct, save test run, map source, monitor feed, generate evidence.
- Keep mock, sandbox, authenticated feed, and production evidence visually and semantically distinct.
- Prefer existing Next.js dashboard, ingestion, sandbox, and Inflow Lab routes. Do not create speculative services.
- Agents are not alone in the codebase. Do not revert or overwrite unrelated edits.

## Agent Ownership

- Agent A, Test Run Persistence: `frontend/src/components/marketing/SandboxUpload.tsx`, `frontend/src/app/sandbox/results/**`, local handoff helpers only.
- Agent B, Row-Level Correction Worklist: `frontend/src/components/marketing/sandbox-grid/**`, diagnosis helpers/tests.
- Agent C, Import Mapping Handoff: `/ingest` frontend files and client-side handoff parsing. Coordinate any shared helper shape with Agent A.
- Agent D, Environment Boundary: Inflow Lab UI and dashboard copy/state boundaries only.
- Agent E, Validation Coverage: tests and browser validation. Avoid product implementation except tiny testability hooks.

## Interface Contract

Use a client-side handoff object until a real saved-run API exists:

```ts
type SandboxOperationalHandoff = {
  version: 1;
  source: "free-sandbox" | "inflow-lab-feeder";
  createdAt: string;
  summary: {
    totalEvents: number;
    passedChecks: number;
    needsWork: number;
    blockers: number;
  };
  csv?: string;
  detectedColumns?: string[];
  diagnosis?: unknown;
  corrections?: unknown;
};
```

Store it under `sessionStorage["regengine:sandbox-handoff"]` and navigate with `?from=sandbox-handoff`.

## Definition of Done

- Free sandbox gives an operational diagnosis and row/cell correction guidance.
- A user can save a sandbox result as a test run handoff.
- Ingest/import mapping page recognizes the handoff and shows what will be mapped.
- Inflow Lab makes sandbox vs authenticated feed vs evidence boundaries unmistakable.
- Tests cover diagnosis, handoff creation, handoff consumption, and boundary copy.
- Browser checks cover public sandbox, `/ingest?from=sandbox-handoff`, and `/tools/inflow-lab`.
