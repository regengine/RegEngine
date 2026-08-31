# Security and evidence boundary review — 2026-08-31

Role: `security_review`. Scope: ingest/persist/export evidence semantics, with
controlled offline probes. Baseline commit:
`41aa11c5071713c45521b7772c11b5a5cc9872c8`. Review evidence only; this lane did
not edit application source. The parent task separately corrected public proof
wording during this review.

**Verdict: KEEP the verification promise limited to internal consistency.** At
the baseline revision, the public sample format differed from the real FDA
package. The integrated package contract now passes both public verifiers in
local synthetic tests. The verifier still has no external trust anchor, and the
chain verifier does not establish that stored event content still matches the
chain. These checks do not prove who issued an archive or that a supplier
reported the truth. No customer, production deployment, real export, or
regulatory submission was inspected.

## Evidence and reproduction

Run from the repository root; the interpreter below is the existing project virtual
environment, not a new dependency installation:

```sh
env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 \
  .venv/bin/python \
  docs/research/evidence-wave-2026-08-31/security_repro.py
```

The script uses synthetic records, temporary ZIPs, and in-memory SQLite. It
denies Python socket connections. It neither queries a production database nor
changes repository application code. Raw outputs are in
`security-results.jsonl` (original), `security-results-after.jsonl` (after
the backend status fix), and
[`security-results-integrated.jsonl`](security-results-integrated.jsonl) (after
the package-contract integration). The table below preserves the original
observations and states the integrated result where behavior changed.
The SQLite experiment deliberately models altered
storage; it does **not** claim a remote attacker can bypass deployed PostgreSQL
permissions or triggers. Those controls were not exercised.

| Probe | Observed result | Reality Level |
| --- | --- | --- |
| Synthetic original ZIP | SDK exit 0; public helper `verified=true` | 5 — controlled local experiment |
| Change CSV, retain original manifest | SDK exit 1; public helper `verified=false` | 5 |
| Change CSV and recompute its included manifest | SDK exit 0; public helper `verified=true` | 5 |
| Actual FDA package helper → SDK/public helper | Baseline: both reject. Integrated: SDK exit 0 and public helper `verified=true` for all four declared members. | 5 |
| Self-consistent generated package with `UNVERIFIED` persisted chain | Integrated hardening: SDK exit 1 with `bundle UNVERIFIED`; public helper fails `package_persisted_chain_acceptable`. | 5 |
| Change persisted quantity from 10 to 99, retain stored hashes | Quantity's recomputed hash changes; `verify_chain().valid` remains true | 5, SQLite storage model |
| Corrupt tenant A's stored chain hash | A fails; unrelated tenant B remains valid with one chain row | 5, SQL query-scope control, not PostgreSQL RLS proof |
| Invalid chain plus missing row hash | Baseline: contradictory `PARTIAL`. Integrated: `UNVERIFIED`, with nested chain validity false. | 5 |
| 64 nonhex characters, no declared root, JSON proof helper | `verified=true` | 5, supporting schema/meaning sentinel |

## SEC-01 — Public proof checks do not authenticate the issuer

Priority: **P1 for the original product claim; claim correction made in this
wave.** Behavioral evidence is Level 5. Real-world deception/exploitation is
unverified.

At baseline, `frontend/src/app/proof/page.tsx:61` said the bundle verified what
RegEngine "signed", and the SDK docstring repeated signing language. The
algorithm compares file bytes to hashes and a Merkle root supplied in the same
untrusted ZIP. There is no signature verification or independently trusted root
in this flow (`frontend/public/sdk/verify_chain.py:82`, `:94`, `:119`, `:123`;
`services/ingestion/app/proof_verify_router.py:295`, `:348`, `:367`).

Replacing both a synthetic CSV and its manifest passes both implementations.
The unchanged-manifest negative control fails as expected. Thus the experiment
confirms internal consistency checks, not issuer authenticity. Even an
authenticated issuer would not establish that real-world source data is true.

The parent task changed the public copy and SDK docstring to state this limit.
This is a useful small repair, not a cryptographic authentication feature.
Remaining wording, API `verified` consumers, and sales material must preserve
the same distinction. The JSON helper also accepts a 64-character nonhex value
and reports a missing declared root as a passing check
(`proof_verify_router.py:142`, `:227`), so `verified` must not be promoted into
an unqualified trust badge.

Small next experiment: ask one actual audit/export recipient to explain what
they believe a passing verification proves, then compare that interpretation
with the documented checks. This requires an authorized recipient; none was
contacted here. If issuer authentication is required, specify the trusted
channel/key and rotation/revocation owner first. Do not add a large signing
system before establishing that requirement.

## SEC-02 — Baseline FDA packages could not pass the advertised public verifiers

Priority at baseline: **P1 workflow blocker for the advertised handoff**.
Disposition after integration: **closed for the tested local package contract**.
Evidence is **Level 5** for helper interoperability; authenticated HTTP export,
deployed behavior, issuer identity, and source-data truth remain unverified.

At baseline, `_build_fda_package` emitted `manifest.files` entries with `name`
and `sha256`, and no `manifest.merkle`. The public verifier required each
entry's `path` and a `merkle.root`; the offline SDK also required that root.

The baseline experiment called the actual package helper with synthetic events
and passed its bytes directly to both actual verifiers. The SDK reported
`manifest.merkle.root missing` and labeled the package `TAMPERED`. The public
helper returned false. This was a format interoperability failure, independent
of database validity.

After integration, the generator emits `name`, `path`, `size`, and `sha256` for
each declared file plus Merkle metadata. The unchanged reproduction now reports
SDK exit 0 and public `verified=true`, with four of four declared hashes and the
recomputed root matching. The generated-package contract tests also exercise a
changed-member negative path. This closes the local format mismatch for the
supported contract. Synthetic chain metadata was explicitly supplied as valid;
the result does not establish persistence, completeness, issuer authenticity,
or source-data accuracy.

An integration review found that the first format repair still accepted a
self-consistent package whose persisted-chain status was `UNVERIFIED`. The
verifiers now cross-check the manifest summary against the hashed chain artifact
and reject an invalid persisted chain. The final reproduction records SDK exit 1
with `bundle UNVERIFIED` and public `verified=false`. A manifest summary that
disagrees with the hashed chain artifact also fails in the focused contract
tests. `VERIFIED` and internally consistent `PARTIAL` packages remain accepted.

The local repair chose one package contract and added generator-to-verifier
coverage. The next contract test should preserve safe handling of older
packages and distinguish "unsupported format" from "content changed". This is
a public artifact contract and should be versioned explicitly. A passing result
must still be described as internal consistency unless there is an external
trust anchor.

Covered negative cases now include changed, missing, duplicate, undeclared and
unsafe members, a failed persisted chain, and manifest/chain-artifact
disagreement. Remaining cases include predictable malformed-manifest handling,
unsupported versions distinct from tampering, and proving that package
generation never copies another tenant's events. Test the latter with PostgreSQL
RLS and two tenants.

## SEC-03 — Stored content and failure status are weaker than the integrity label

Priority: **P2 security diagnostic gap**, and a launch prerequisite if full
stored-content integrity is promised. Evidence: **Level 5** for local verifier
behavior; a production mutation path or external exploit is **UNVERIFIED**.

`CTEPersistence.verify_chain` selects the ledger's `event_hash` plus the
matching event ID, not event fields or KDEs
(`services/shared/cte_persistence/core.py:1543`). It recomputes each chain link
from that already-stored hash (`:1632`), and checks row existence/counts. It
does not recompute event content or compare event-table and ledger digests.

Using its real SQL against an in-memory SQLite storage model, an event whose
quantity changed from 10 to 99 remains `valid=true`, although
`compute_event_hash` produces a different digest for the changed quantity.
Corrupting the chain link itself fails, so the experiment is not merely a
stub returning success. The other tenant remains unaffected. There are
append-only SQL guards in the repository (`alembic/sql/V053__cte_append_only_triggers.sql:24`),
but this experiment does not load PostgreSQL migrations, validate active
database roles, or bypass those guards. It shows a verification blind spot if
storage diverges through an authorized correction, defect, or another failure
of the storage boundary; it does not show unauthorized production writes.

A second local failure in the same evidence-status boundary was deterministic
at baseline: `_build_chain_verification_payload` first marked an invalid chain
`UNVERIFIED`, then overwrote it with `PARTIAL` if any event hash was missing
(`fda_export_service.py:593`). The original README told recipients to accept
`VERIFIED or PARTIAL` (`:695`). A nested `valid=false` was retained, and the
route's `X-Chain-Integrity` remained `UNVERIFIED` (`fda_export/router.py:432`),
so the evidence was contradictory, not entirely erased. **The backend lane
fixed this status precedence and README guidance during this wave; independent
verification is recorded below.** The stored-content verification gap remains.

Next repair experiment: design bounded content reconciliation for each existing
hash format. Canonical and
legacy writers intentionally use different formulas
(`services/shared/canonical_event.py:447` and
`services/shared/cte_persistence/hashing.py:65`). Blindly rehashing every record
with only one formula risks falsely declaring historical evidence corrupt.
Include wrong-tenant joins, missing/extra chain rows, changed KDEs, changed
quantities, amendments, and both writer formats in the follow-up test set.

## Independent post-fix review

Disposition: **no blocking finding in the reviewed patch**. This review read
the exact changes in `fda_export_service.py` and
`test_fda_export_service_1342.py`, then independently reran the original two
focused suites in a scrubbed environment with socket connections denied:
**87 tests passed in 1.57 seconds**. The added coverage includes the eight
chain-validity × missing-record-hash × missing-chain-hash combinations and a
generated ZIP test that inspects the chain JSON, manifest, and README.

The original reproduction was rerun unchanged. Comparing all eight JSONL
records found exactly one changed result:

```text
invalid_chain_and_missing_hash:
  before: chain_valid=false, status=PARTIAL
  after:  chain_valid=false, status=UNVERIFIED
```

At that intermediate stage, the other seven result records were unchanged, so
the generator-to-verifier incompatibility and stored-content hash blind spot
both remained reproducible. Original and intermediate results were preserved in
`security-results.jsonl` and `security-results-after.jsonl`.

The public proof page and SDK docstring changes were also reviewed: both now
say the checks establish internal consistency and neither authenticate the
issuer nor establish source-data accuracy. No verifier logic was changed by
that copy patch. Two adjacent absolute statements on the page (`:168`, `:202`)
were flagged to the parent for tighter wording about the unchanged-manifest
negative control; they are outside the two edited text passages.

## Post-integration review

The unchanged reproduction was run again after the package-contract merge.
[`security-results-integrated.jsonl`](security-results-integrated.jsonl) shows
the valid-chain FDA package passing both public verifiers, the self-consistent
`UNVERIFIED` package failing both, and invalid chain plus missing row hash
remaining `UNVERIFIED`. The stored-content mutation remains valid under
`verify_chain()`, and a changed generic file still passes when its untrusted
in-archive manifest is recomputed. These are Level 5 local experiments, not
proof of a deployed fix or successful customer export.

## Verification and handoff

- Files changed in this lane: `security.md`, `security_repro.py`, and the three
  `security-results*.jsonl` artifacts under this evidence directory.
- What changed: durable review evidence and reproducible synthetic probes;
  no auth, schema, API, billing, deployment, or application source changes.
- Tests run: the two existing focused suites
  `services/ingestion/tests/test_proof_verify_router.py` and
  `services/ingestion/tests/test_fda_export_service_1342.py`, using the existing
  Python environment, an empty inherited environment, denied socket
  connections, `-o addopts= --no-cov -p no:cacheprovider`.
- What passed: baseline **78 tests in 1.51 seconds**; independent post-fix
  **87 tests in 1.57 seconds**. The standalone probe completed at baseline,
  after the status fix, and after final package hardening. Focused contract tests
  cover valid `VERIFIED`/`PARTIAL`, failed `UNVERIFIED`, manifest/chain
  disagreement, undeclared/duplicate members, and changed content. Unsafe
  acceptance results that remain are findings, not security passes.
- What was not tested: production HTTP routing, credentials, active PostgreSQL
  migrations/RLS, real supplier data, operator behavior, regulatory acceptance,
  live traffic, or customer willingness to pay.
- Remaining risks: misleading integrity interpretation, stored-content blind
  spots, unversioned/legacy-package behavior, and deployed tenant isolation.
  Package interoperability and failure status are repaired and independently
  tested locally, not deployment-verified.
- Recommended next step: preserve truthful public wording; add explicit
  unsupported-version and archive-member boundary tests; then run an isolated
  two-tenant PostgreSQL reconciliation experiment.
