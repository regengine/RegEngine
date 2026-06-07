# Inflow Workbench Design-Partner Demo

Purpose: a 3-4 minute Loom that shows RegEngine turning messy supplier data into explainable readiness, remediation work, and protected evidence handoff.

## Setup

- Open the verified staging app at `/tools/inflow-lab`.
- Use the built-in scenarios deliberately:
  - `Complete romaine lettuce flow` proves the corrected data shape reaches readiness 100 in preflight.
  - `Missing shipping destination` proves a shipping KDE block still creates fix work.
  - `Transformation-style broken lineage` proves missing source-lot lineage still creates remediation work.
- Keep the dashboard tabs ready in a second browser tab: `/dashboard/compliance` and `/dashboard/suppliers`.
- Keep the supplier portal tab ready if the buyer asks how external partners submit data.

Preflight and Workbench saves are not production evidence by themselves. They show readiness, fix queue, and commit-gate state. Production evidence requires authenticated ingest into Postgres, hash-chain verification, compliance scoring, and export audit/package generation.

## Talk Track

1. Start with the problem.
   "Most FSMA 204 teams do not start with clean APIs. They start with supplier CSVs, screenshots, spreadsheets, EDI extracts, and partial shipment records."

2. Load the clean supplier feed.
   Show the Inflow Lab scenario library, choose `Complete romaine lettuce flow`, and run preflight. Call out readiness 100, zero fix items, and the staging gate.

3. Load the messy supplier feed.
   Choose `Missing shipping destination`, and load it into Data Feeder.

4. Run preflight.
   Click evaluate. Call out the readiness score, blocked/warning states, and the exact failed KDEs. Use this line:
   "Inflow prepares the data before it becomes permanent evidence."

5. Open the fix queue.
   Show the generated task for the missing shipping destination and any blocking rule reasons.
   "The product does not stop at pass/fail. It creates operational work with owner, severity, impact, and replay path."

6. Show the broken-lineage case.
   Choose `Transformation-style broken lineage` and show that the transformation row is blocked until input TLCs are supplied.

7. Show the commit gate.
   Move through simulation/preflight/staging/production evidence language.
   "Simulation and preflight are safe. Production evidence requires authentication, persistence, provenance, and no unresolved fixes."

8. Save the run and switch to dashboards.
   Open `/dashboard/compliance` and point to `Inflow Workbench` readiness. Then open `/dashboard/suppliers` and show the same readiness signal beside supplier management.

9. Close with the system-of-record point.
   "The Engine proves whether records are complete and trustworthy. Inflow is now the operational front door that gets supplier data into that shape."

## Strongest Before/After

- Before: a supplier CSV with a shipment that cannot support FDA export.
- After: exact missing KDE, fix queue item, blocked commit gate, unified readiness score, and a path to replay corrected records.

## One-Liner

Inflow prepares the data. The Engine proves it.

## Local Persisted Evidence Proof

Use the fast simulator for quick golden-contract checks; it is DB-free and does not prove persisted evidence:

```bash
./venv/bin/python scripts/run_full_fsma_simulation.py --json
```

Use the full verifier when you need real local Postgres-backed evidence:

```bash
POSTGRES_PASSWORD=regengine docker compose -f docker-compose.dev.yml up -d postgres
DATABASE_URL=postgresql://regengine:regengine@localhost:5432/regengine ./venv/bin/alembic upgrade head
DATABASE_URL=postgresql://regengine:regengine@localhost:5432/regengine \
  ./venv/bin/python scripts/verify_inflow_to_regengine_e2e.py \
  --output-dir /tmp/regengine-inflow-e2e
```

The verifier fails nonzero if Postgres or migrations are unavailable, the clean Inflow fixture is rejected, workbench save is not persisted, hash-chain verification fails, compliance score sees no events, or the FDA ZIP package lacks the manifest, CSV, chain payload, five data rows, and `System Entry Timestamp`.
