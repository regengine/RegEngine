# Engineering / QA investigation — 2026-08-31

Scope: planner inspection of the FSMA production spine at local revision `41aa11c5`, with offline controlled experiments. No production code, configuration, schema, credentials, services, or external accounts changed. The applicable global and repository `AGENTS.md` files were read; no closer instruction file applies to this output. Paths below are repository-relative, with source line references.

**Recommended verdict: conditional GO for a bounded, supervised validation pilot; NO-GO for an autonomous or production-proven compliance claim.** Working implementation and substantial negative-path tests exist. They do not establish that every accepted format reaches the same durable evidence, that corrections survive retry, or that an exported artifact is complete. Resolve evidence loss on the selected pilot path before trusting it as the sole record.

## Evidence level and mechanism

**VERIFIED FACT — implementation presence:** CSV builds typed webhook events and calls the compatibility ingestion function (`services/ingestion/app/csv_templates.py:574`, `:602`). Webhook V2 checks timestamp/KDE validity, partitions rule failures, persists legacy events, then requires canonical persistence and evaluation (`services/ingestion/app/webhook_router_v2.py:1302`, `:1338`, `:1373`, `:1429`, `:1077`). Canonical writes use tenant context, per-tenant advisory locking and conflict-safe insertion (`services/shared/canonical_persistence/writer.py:215`, `:225`, `:275`). Export still reads `fsma.cte_events` and `fsma.cte_kdes`, rather than only the declared canonical table (`services/shared/cte_persistence/core.py:1330`, `:1385`). Thus the product is a collection of functioning paths with materially different guarantees, not one uniform pipeline.

Reality Ladder: source inspection supports level **1 LOGICAL** implementation reasoning; the 143 passing local tests and the probes below are level **5 CONTROLLED EXPERIMENT**, restricted to in-process code, fakes, and SQLite transaction events. This does not imply level 5 validation of the whole business or product. No deployed level 6 sandbox exercise, level 7 limited real-world operation, repeated customer use, or scaled operation was verified in this lane.

## Consequential findings

### 1. Accepted EPCIS records need not contain canonical evidence; retry does not repair the gap

**VERIFIED FACT:** `_persist_prepared_event_in_session` starts a daemon thread for canonical writing, passes the request's same SQLAlchemy session into it, waits up to five seconds, and logs/swallow exceptions (`services/ingestion/app/epcis/persistence.py:783–862`). It returns 201 for a newly stored legacy event (`:864–874`). The owning wrapper subsequently commits and closes the session (`:921–932`). On an idempotent legacy result, it skips the canonical block entirely (`:787`). Existing tests expressly confirm the accepted response after a canonical exception and the skipped replay path (`services/ingestion/tests/test_epcis_persistence_1342.py:815–855`); all three targeted tests passed.

**INFERENCE:** a canonical failure can leave an accepted legacy/export record without corresponding normalized provenance or rule-evaluation evidence. Replaying the same event does not guarantee repair. A timed-out worker also overlaps the caller's session lifecycle; the actual PostgreSQL race and resulting persisted rows were not exercised. The timeout warning passes nonstandard keyword arguments to a standard `logging.Logger` (`persistence.py:38`, `:853`), another reason to test this branch rather than rely on its comment.

This is stronger evidence against uniform durability than the presence of a canonical model is evidence for it. The smallest remedy is to make canonical work mandatory within the same request transaction for the selected pilot path, or explicitly quarantine and reconcile incomplete writes. Do not build a new distributed workflow before proving that the existing synchronous path suffices.

### 2. Content-changing retries can be accepted as unchanged duplicates

**VERIFIED FACT:** canonical idempotency hashes omit top-level quantity, unit of measure and product reference (`services/shared/canonical_event.py:463–496`), while the event content hash includes them (`:447–461`). On an existing key, persistence returns successful/idempotent without comparing the incoming content hash (`services/shared/canonical_persistence/writer.py:234–249`). The legacy key also omits quantity/UoM (`services/shared/cte_persistence/hashing.py:123–168`), and legacy persistence similarly returns early (`core.py:471–503`). V2 batch deduplication is narrower still: type, lot, timestamp and location (`webhook_router_v2.py:1305–1315`).

**CONTROLLED EXPERIMENT:** changing a canonical event from 10 kg to 999 cases preserved its idempotency key and changed its content hash. This proves a conflicting-payload identity, not a live data-loss incident. **INFERENCE:** an ERP correction that preserves identity/KDEs can be acknowledged without persisting its changed quantity. Require an explicit conflict/amendment response and preserve the prior record; simply changing the dedup formula could create silent duplicates.

### 3. Optional graph synchronization still publishes before outer commit at a savepoint boundary

**CONTROLLED EXPERIMENT — newly reproduced:** with a real SQLAlchemy SQLite `Session`, real `stage_graph_sync`, a mocked publish sink, and `ENABLE_NEO4J_SYNC=true`, releasing a nested savepoint published the event before the outer transaction committed. Rolling back the outer transaction could not retract it. Output:

```text
before savepoint commit: []
after savepoint commit, before outer commit: ['probe-event']
after outer rollback: ['probe-event']
```

The helper drains pending events on every `after_commit`, without distinguishing nested transactions (`services/shared/canonical_persistence/legacy_dual_write.py:351–368`, `:435`). Compatibility ingestion commits `canon_sp` and can subsequently roll back the outer savepoint on rejection (`services/ingestion/app/webhook_compat.py:220`, `:277`). Existing outbox tests passed but do not cover nested savepoint commits (`tests/shared/test_canonical_graph_outbox_1276.py`).

Scope matters: graph sync defaults **off** (`legacy_dual_write.py:111–120`). This is not evidence the deployed system currently emits ghost graph nodes. Keep it off unless needed. Even after correcting savepoint handling, pending events live only in `session.info`, transport errors are swallowed, and queue trimming drops oldest entries (`:305–317`, `:359`, `:427`). This is best-effort derived-state sync, not a durable transactional outbox.

### 4. “Allowed,” “accepted,” and “verified” are different, limited claims

**VERIFIED FACT:** missing or misspelled `RULES_ENGINE_ENFORCE` resolves to `off`; a no-verdict summary is accepted in all modes (`services/shared/rules/enforcement.py:64–103`). Basic required-KDE rejection still exists, so this does **not** mean all invalid input is accepted. Compatibility ingestion tolerates canonical/rule exceptions in off mode (`webhook_compat.py:189–231`). Workbench `/commit-gate` evaluates request-provided `authenticated`, `persisted` and `provenance_attached` flags; it is not itself a database commit or an independent proof of those facts (`services/ingestion/app/inflow_workbench.py:835–850`, `:924–931`).

Legacy `verify_chain` recomputes chain linkage using stored `hash_chain.event_hash` and checks event existence/count, but does not recompute the underlying event/KDE content hash (`services/shared/cte_persistence/core.py:1541–1569`, `:1605–1636`). Moreover, legacy event hashing intentionally excludes product descriptions and omits `location_name` (`hashing.py:64–109`). **INFERENCE:** a `VERIFIED` chain badge is insufficient proof of unchanged exported content, complete business records, or factual source authenticity. The database's mutation defenses are a separate security question, not evidence this verifier hashes those fields.

### 5. “Export all” retains selection and completeness limits

**VERIFIED FACT:** `/export/all` fetches at most 10,000 seed rows and then expands each seed TLC, deduplicating the expanded result (`services/ingestion/app/fda_export/router.py:564–595`). The second query does not carry the requested `event_type` filter. It can therefore include other event types for those lots; the limit is not a reliable final-output cap. Excess seed rows generate a successful response with `X-Truncated`, not a complete paginated export (`:692–696`). Shared pagination code exists but this route does not use it (`services/shared/fda_export/pagination.py:32`).

The export coverage gate permits ≥80% required-field coverage, or a caller-acknowledged incomplete export below it (`services/ingestion/app/fda_export/coverage.py:13–64`). Coverage of returned rows cannot demonstrate the absence of missing lots/events. **INFERENCE:** an artifact retained without its HTTP headers could be mistaken for complete evidence. Test downloadable manifests and row-set reconciliation, not just whether the CSV opens. This is a software observation, not a statement that 80% is a regulatory threshold.

## Tests and exact reproduction

Python `.venv/bin/python` resolves to Python 3.12.2; pytest 9.0.3 is installed. No installation was necessary. Test processes were started with the following environment and launcher. `FILES` below denotes each exact list passed as trailing `pytest.main` arguments, in three separate runs:

```sh
env -i PATH=/usr/bin:/bin ENVIRONMENT=test DATABASE_URL=sqlite:///:memory: \
  AWS_EC2_METADATA_DISABLED=true ENABLE_NEO4J_SYNC=false SENTRY_DSN= \
  .venv/bin/python - <<'PY'
import socket
import pytest
def deny_network(*args, **kwargs):
    raise RuntimeError('Deep Market Lab: live network disabled during local evidence run')
socket.socket.connect = deny_network
socket.create_connection = deny_network
FILES = [...]  # Substitute one exact list below.
raise SystemExit(pytest.main(['-o', 'addopts=', '-q', '--import-mode=importlib',
    '--asyncio-mode=auto', '--no-cov', *FILES]))
PY
```

Run 1 — **89 passed in 0.61s**, exit 0:

```python
FILES = [
 'tests/shared/test_rules_enforcement.py',
 'tests/shared/test_canonical_graph_outbox_1276.py',
 'tests/shared/test_canonical_dual_write_strict_1277.py',
 'tests/shared/test_canonical_event_idempotency_key.py',
 'tests/shared/test_cte_persistence_verify_chain_1314.py',
 'services/shared/tests/test_cte_persistence_1323_1324.py',
 'services/shared/tests/test_rules_enforcement_manifest.py']
```

Run 2 — **51 passed in 1.41s**, exit 0:

```python
FILES = [
 'services/ingestion/tests/test_webhook_router_v2_enforcement.py',
 'services/ingestion/tests/test_webhook_compat_enforcement.py',
 'services/ingestion/tests/test_epcis_persistence_enforcement.py',
 'services/ingestion/tests/test_fda_export_epic_l_1655.py',
 'services/ingestion/tests/test_fda_export_timezone.py']
```

Run 3 — **3 passed in 0.64s**, exit 0. The final visible run also added `-s`; `os.write` printed the pytest return code after an earlier successful invocation returned no captured summary:

```python
FILES = ['services/ingestion/tests/test_epcis_persistence_1342.py::TestPersistPreparedEventInSession']
```

The savepoint probe used this exact command, replacing external publishing with an in-memory list:

```sh
env -i PATH=/usr/bin:/bin ENVIRONMENT=test DATABASE_URL=sqlite:///:memory: \
  ENABLE_NEO4J_SYNC=true PYTHONPATH=services .venv/bin/python - <<'PY'
from types import SimpleNamespace
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from shared.canonical_persistence import legacy_dual_write as sync
published = []
sync.publish_graph_sync = lambda event: published.append(event.event_id)
with Session(create_engine('sqlite:///:memory:')) as session:
    session.execute(text('SELECT 1'))
    savepoint = session.begin_nested()
    sync.stage_graph_sync(session, SimpleNamespace(event_id='probe-event'))
    print('before savepoint commit:', published)
    savepoint.commit()
    print('after savepoint commit, before outer commit:', published)
    session.rollback()
    print('after outer rollback:', published)
PY
```

The quantity probe used `env -i PATH=/usr/bin:/bin ENVIRONMENT=test PYTHONPATH=services .venv/bin/python -`, then:

```python
from uuid import UUID
from shared.canonical_event import TraceabilityEvent
base=TraceabilityEvent(tenant_id=UUID('00000000-0000-0000-0000-000000000111'),event_type='shipping',traceability_lot_code='PROBE-LOT',event_timestamp='2026-08-01T12:00:00Z',quantity=10,unit_of_measure='kg',source_system='webhook_api',kdes={})
changed=base.model_copy(update={'quantity':999,'unit_of_measure':'cases'})
print('quantity/uom change keeps idempotency key:', base.compute_idempotency_key()==changed.compute_idempotency_key())
print('quantity/uom change changes event hash:', base.compute_sha256_hash()!=changed.compute_sha256_hash())
```

Both comparisons printed `True`. An initial probe incorrectly supplied enum value `source_system='api'`; Pydantic rejected it before hashing. The corrected probe above used the supported `webhook_api` value.

## Highest-value falsification experiments

1. **Durable acceptance:** on disposable PostgreSQL, inject failure/timeout between legacy and canonical EPCIS persistence, restart, replay, and reconcile events, KDEs, rule evaluations and export rows. Pass only if accepted records have durable evidence or explicit recoverable quarantine, with no shared-session activity after close.
2. **Correction and retry:** send the same event unchanged, then alter quantity/UoM with the same identity, across CSV/EPCIS/webhook paths. Pass only with exact replay deduplication plus an explicit conflict or auditable amendment for changed content.
3. **Export set equality:** load 10,001 distinct lots, mixed event types, transformations beyond five hops, and events late on the end date. Compare requested source IDs with artifact IDs; incomplete outputs must carry persistent manifest warnings or fail closed.
4. **Integrity semantics:** change a stored KDE in a disposable fixture while preserving chain rows, and check every advertised verifier. Require content-hash verification where “unchanged records” is claimed, separately from chain-link verification.

Files changed: this report only. What changed: documented code evidence, two probes and verification limits. Tests run/passed: 143 existing selected tests in three independent processes; no test failures in those sets. Not tested: real PostgreSQL transactions, Docker/infrastructure, full suites, deployment, frontend, real supplier data, network integration, crash recovery or throughput. Those are deliberate scope limits; infrastructure availability was not tested and is not claimed as a blocker. Remaining risk: mocks cannot validate SQL/RLS behavior or field completeness. Recommended next step: one disposable-database accepted-event reconciliation test on the exact proposed pilot ingestion path, before additional features or broad marketing claims.
