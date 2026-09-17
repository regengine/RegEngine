# Golden Path

The RegEngine golden path is the narrow story we expect demos, tests, and production hardening to reinforce.

```text
simulate data -> ingest -> validate -> show failures -> export evidence
```

## Fast Verification

Run the deterministic local simulation:

```bash
python3 scripts/run_full_fsma_simulation.py
```

The runner writes artifacts to `/tmp/regengine-golden-path` by default:

- `summary.json` records the simulated lifecycle, detected failure point, remediation replay, evidence hashes, and export metadata.
- `fda_export.csv` is generated through the ingestion service's FDA CSV formatter.

This check is intentionally database-free. It proves that the production spine primitives still line up:

- deterministic Inflow-style source events
- canonical `TraceabilityEvent` normalization
- stateless FSMA rule evaluation
- SHA-256 record hashes and ordered chain hashes
- FDA export columns, including `System Entry Timestamp`

## Recall Reconstruction Fixture

The recall fixture proves one narrower claim: that a lot can be followed through pallets, splits, relabels, a DC, and a 3PL, and that missing evidence is reported as `unresolved` rather than read as exclusion.

```bash
python3 scripts/run_recall_fixture.py --case all --output-dir /tmp/regengine-recall-fixture
```

It runs the same synthetic scenario three ways (complete records, a withheld 3PL pallet-content record, and an unreachable ERP served from its retained snapshot), writes an evidence package per case, and reconciles each against `sample_data/recall_fixture/answer_key.json`. It is DB-free and reuses the canonical event model and hash chain. See `sample_data/recall_fixture/README.md`.

For the heavier live-service scenario, use:

```bash
python3 scripts/e2e_brutal_scenario.py
```

## 1. Simulate FSMA Data

Use `inflow-lab` to generate deterministic FSMA lifecycle events.

Expected output:

- Harvesting, cooling, packing, shipping, receiving, and transformation events
- Stable event identifiers
- Traceable lot lineage
- Payloads compatible with the RegEngine ingestion contract

## 2. Ingest Into RegEngine

Send generated CTE/KDE events into the RegEngine ingestion surface.

Expected behavior:

- Tenant context is established before persistence.
- Payload shape is validated.
- Invalid records are rejected or routed through the configured remediation flow.
- Accepted records enter the canonical FSMA pipeline.

## 3. Validate Compliance

Run validation and readiness scoring against stored evidence.

Expected behavior:

- Missing or malformed KDEs are surfaced.
- Rule outcomes are tied to persisted tenant-scoped records.
- Failure points are actionable for an operator or supplier.

## 4. Show Failure Points

Expose the compliance gaps that matter for FSMA 204.

Examples:

- Missing required KDE fields
- Broken lot lineage
- Invalid event relationships
- Late or incomplete traceability data
- Records that cannot support an FDA request

## 5. Generate FDA Export

Generate FDA export material from stored tenant-scoped evidence.

Expected behavior:

- Export output is derived from canonical persisted data.
- Export operations are tenant-scoped.
- Export history is observable and auditable.

## Demo Contract

A useful demo should answer four questions:

1. What data did the supplier provide?
2. What failed FSMA validation?
3. What evidence did RegEngine persist?
4. What can be exported for an FDA request?

If a demo step does not help answer those questions, it is outside the golden path.
