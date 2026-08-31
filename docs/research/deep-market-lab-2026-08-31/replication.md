# Independent replication: two integrity claims

Date: 2026-08-31. Role: `security_review`. Scope: local adjudication only; no production edits, external access, installs, real tenant data, or secrets. Inspected commit: `41aa11c5071713c45521b7772c11b5a5cc9872c8`. Runtime: Python 3.12.2, SQLAlchemy 2.0.49, existing `.venv`, in-memory SQLite.

**Both narrow code-behavior claims are corroborated independently. Neither experiment establishes an unauthenticated attack, a deployed incident, or live production configuration.**

## 1. Chain verification does not re-hash the current event payload or KDEs

**Adjudication: corroborated as a verification coverage gap.** Calling the actual `CTEPersistence.verify_chain()` against synthetic SQL tables returns `valid=True` after either quantity-only or KDE-only changes that demonstrably change `compute_event_hash()`. The chain and event count stay unchanged. A deliberately corrupted stored chain hash returns `valid=False`, confirming that the probe can detect the kind of corruption the verifier actually checks.

The relevant implementation is [verification.py:30](../../../services/shared/cte_persistence/verification.py#L30). Its query reads stored digests and event existence, not the event payload:

```sql
SELECT hc.sequence_num, hc.event_hash,
       hc.previous_chain_hash, hc.chain_hash,
       hc.cte_event_id, ce.id AS matched_event_id
FROM fsma.hash_chain hc
LEFT JOIN fsma.cte_events ce
    ON ce.id = hc.cte_event_id
   AND ce.tenant_id = hc.tenant_id
WHERE hc.tenant_id = :tid
ORDER BY hc.sequence_num ASC
```

The per-row digest check is:

```python
recomputed = compute_chain_hash(event_hash, stored_prev)
if recomputed != stored_chain:
    errors.append(...)
```

It also checks sequence continuity, previous-chain linkage, orphan references, and certain missing-chain cases. Those are useful checks; none binds a current quantity or KDE value back to the recorded event hash.

| Synthetic change | Current payload hash matches original | `verify_chain.valid` | Errors |
| --- | --- | --- | --- |
| Baseline | true | true | `[]` |
| Quantity `10.0` → `999.0` | false | true | `[]` |
| Quantity restored; `reference_document_number` changed | false | true | `[]` |
| Stored `chain_hash` replaced by 64 zeroes | false | false | `Tamper detected at seq=1...` |

The changes use fields that participate in [compute_event_hash](../../../services/shared/cte_persistence/hashing.py#L67). The experiment does not rely on changing `product_description`, which that helper intentionally excludes.

**FDA export implication, established by source tracing rather than an HTTP experiment:** [query_events_by_tlc](../../../services/shared/cte_persistence/queries.py#L197) reads the current event fields and [current KDE values](../../../services/shared/cte_persistence/queries.py#L313). The [export handler](../../../services/ingestion/app/fda_export/router.py#L271) generates CSV from those rows and calls `verify_chain`; its [CSV response](../../../services/ingestion/app/fda_export/router.py#L469) uses:

```python
"X-Chain-Integrity": "VERIFIED" if chain_verification.valid else "UNVERIFIED"
```

Thus the header can truthfully reflect the stored chain-link checks while failing to establish that the exported payload still matches the event originally hashed. The newly generated `X-Export-Hash` covers the export bytes; it does not by itself connect those bytes to the original event commitment. Other export gates, authorization, audit persistence, and transport were not exercised by this probe.

**Threat capability and mitigation:** the mutation probe assumes the ability to change an event or KDE record, or an equivalent inconsistency from migration/import/correction/storage corruption. It does not establish an HTTP route that grants that capability. Event quantity mutation can require stronger privileges than KDE mutation, depending on deployed protections.

The active migration source includes [_cte_append_only_triggers](../../../alembic/versions/20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py#L1338). It installs `BEFORE UPDATE OR DELETE` guards on `fsma.cte_events` and `fsma.hash_chain`, reducing ordinary event-mutation exposure if deployed. That function does not install a `cte_kdes` guard. The [base KDE schema](../../../alembic/sql/V002__fsma_cte_persistence.sql#L98) has foreign-key and uniqueness constraints plus [tenant RLS](../../../alembic/sql/V002__fsma_cte_persistence.sql#L223); these do not themselves enforce value immutability within an authorized tenant. Live table grants, all deployed triggers, tenant policies, and migration application are **not verified**.

The migration's `fsma.allow_mutation` branch returns `OLD`; do not assume that setting it allows an UPDATE to retain `NEW` values. No claim about exploiting that branch is made here. Comments and old tests referencing `cte_events_no_update_delete`/the former v073 filename are not proof of deployed protection; the forward-port implementation above is the source inspected.

**Recommended next step:** add focused payload/KDE-drift regression coverage and define the verification contract before changing the header or digest algorithm. Confirm production migration and KDE mutation protections. A repair must account for legacy and canonical hash formats: [TraceabilityEvent.compute_sha256_hash](../../../services/shared/canonical_event.py#L447) differs from the legacy helper, and the [dual writer](../../../services/shared/canonical_persistence/legacy_dual_write.py#L202) copies its digest into the legacy table. Blindly applying one hashing helper to every historical row can create false alarms.

## 2. Graph staging publishes on nested commit before outer commit

**Adjudication: corroborated as a conditional transaction-boundary defect.** A real SQLAlchemy `Session`, with an explicit SQL `BEGIN` and an inserted synthetic row, was used. The actual `stage_graph_sync()` and its registered listeners ran unchanged. Only `publish_graph_sync` was replaced with an in-memory collector so no Redis or Neo4j access could occur.

The [stage function](../../../services/shared/canonical_persistence/legacy_dual_write.py#L402) stores a session-wide list and registers:

```python
sa_event.listen(session, "after_commit", _drain_pending_graph_sync)
sa_event.listen(session, "after_rollback", _clear_pending_graph_sync)
sa_event.listen(session, "after_soft_rollback", _clear_pending_graph_sync_soft)
```

The [drain listener](../../../services/shared/canonical_persistence/legacy_dual_write.py#L351) unconditionally pops that list and calls the publisher. In the installed SQLAlchemy version, `nested.commit()` dispatches `after_commit` while the outer transaction remains open. The listener does not distinguish those transaction levels.

| Scenario | Publishes before boundary | Publishes immediately after nested boundary | Publishes at end | Durable synthetic rows at end |
| --- | --- | --- | --- | --- |
| Feature explicitly disabled; outer commit | 0 | n/a | 0 | 1 |
| Feature enabled; normal outer commit | 0 | n/a | 1 | 1 |
| Feature enabled; normal outer rollback | 0 | n/a | 0 | 0 |
| Stage outer event → nested commit → outer rollback | 0 | 1 | 1 | 0 |
| Stage outer event → unrelated nested rollback → outer commit | 0 | 0 | 0 | 1 |

In the fourth scenario, `session.in_transaction()` is still `True` immediately after the nested commit and publish. An explicit `BEGIN` avoids SQLite's legacy behavior in which a SAVEPOINT might accidentally become the outermost database transaction. Querying after the outer rollback confirms the row is gone. The fifth scenario independently demonstrates the inverse consequence of keeping all staged events in one session-wide list: a nested rollback discards the event staged outside that SAVEPOINT even though its row ultimately commits.

**Reach and limits:** [CanonicalEventStore.persist_event](../../../services/shared/canonical_persistence/writer.py#L353) calls this staging function. The [legacy KDE write](../../../services/shared/canonical_persistence/legacy_dual_write.py#L219) uses `begin_nested`, so nested transactions are not an invented foreign pattern. Nevertheless, the reproduction invokes the staging primitive, not a full PostgreSQL-backed ingestion route. The exact end-to-end caller sequence, production DB commit-failure behavior, graph consumer behavior, and deployed configuration remain **not verified**.

The producer is [off by default](../../../services/shared/canonical_persistence/legacy_dual_write.py#L114). Real downstream effects additionally require enabling graph sync, configuring a reachable Redis endpoint, and a consumer processing the message. Source comments say a consumer is not deployed by the referenced manifests; this review did not independently inspect live deployments. Do not characterize this as active production graph corruption.

**Recommended next step:** retain the default-off setting. Before enabling this path, make the staged events transaction-aware and publish only after successful outer commit; add nested commit/outer rollback and nested rollback/outer commit tests. A simple `in_nested_transaction()` guard addresses only part of the behavior: nested rollbacks must discard the correct scope without losing outer events, and tests must cover publishing once after a successful outer commit. A durable outbox is a separate reliability decision, not necessary to prove this defect.

## Reproduction and verification

Complete executable code: [replication_probe.py](../../../docs/research/deep-market-lab-2026-08-31/replication_probe.py). From the repository root:

```bash
.venv/bin/python3 docs/research/deep-market-lab-2026-08-31/replication_probe.py
```

Result: exit `0`; all control and reproduction assertions passed. It prints the full JSON observations summarized above. The CTE probe uses reduced SQLite tables sufficient for the actual verification queries, not a mock `verify_chain` result. The changed fields are re-hashed with the production helper and compared to the initial digest. The fixture schema intentionally omits PostgreSQL mutation guards/RLS, making mutation ability an explicit precondition rather than an alleged bypass. Fixed non-mutated event fields remain in the synthetic fixture dictionary. This is a verifier-coverage experiment, not a production migration or persistence integration test.

Existing nearby regression tests were also run unchanged:

```bash
PYTHONPATH=services .venv/bin/python3 -m pytest tests/shared/test_cte_persistence_verify_chain_1314.py tests/shared/test_canonical_graph_outbox_1276.py -q --no-cov -o addopts=''
```

Result: **24 passed in 0.31s**. Their success coexists with both reproduced gaps; it is not evidence that current-payload verification or nested commit behavior is covered.

## Work report

- **Files changed:** this report and the standalone `replication_probe.py`, both under `docs/research/deep-market-lab-2026-08-31/`. Production source, public APIs, auth, billing, schema, and deployment configuration were unchanged.
- **What changed:** independent claim adjudication, synthetic reproductions, controls, code evidence, threat preconditions, mitigation assessment, and limitations.
- **Tests run:** standalone probe; the two existing targeted suites shown above.
- **What passed:** all probe assertions and 24 existing tests.
- **What was not tested:** live PostgreSQL triggers/RLS/grants, production data or services, actual Redis/Neo4j traffic, a full authenticated FDA export request, and complete ingestion-route reproduction.
- **Remaining risks:** current payload/KDE integrity can exceed what the header's verifier establishes; enabled graph sync has unscoped nested-transaction side effects. Deployment exposure is not verified.
- **Recommended next step:** convert these bounded reproductions into regression tests alongside scoped fixes, with PostgreSQL integration coverage for storage protections and transaction semantics before claiming production assurance.
