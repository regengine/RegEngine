# WS-1 read-path cutover — compressed (~12 h) operator runbook

> **Scope:** WS-1b read-flag cutover, WS-1c backfill. WS-1d (retiring the dual
> write) is **reference only** in this document — it is not a 12-hour action.
> **Companion doc:** [`dual-write-cutover.md`](dual-write-cutover.md) (read-path
> inventory + never-do list). This runbook does not replace it.
>
> Written to be executed by one tired human with a second person on call.
> Every step states: command → expected output → pass/fail → abort trigger →
> rollback. If a step has no clean pass, **stop**; do not improvise forward.

---

## READ THIS BEFORE YOU TOUCH ANYTHING

### 1. The recorded "soak" did not happen. Treat it as fiction.

`docs/persistence/dual-write-cutover.md` and `README.md` both currently state
that `FDA_EXPORT_V1_READ_CANONICAL=1` was set on Railway on 2026-07-17 and
`CHAIN_VERIFY_READ_CANONICAL=1` on 2026-07-24, each "soaking". `queries.py`
even carries the inline claim that the canonical reader is *"live in production
since 2026-07-17"*.

**Production is running commit `48d5f641` and has never executed the canonical
read path. Both flags are effectively OFF.**

Both facts can be true at once: the env vars were set on a Railway service whose
running image does not contain (or never exercised) the flagged code. Setting an
env var that no deployed code reads produces exactly this — a confident
changelog entry and zero canonical reads.

Consequences you must internalise:

- **Elapsed calendar time buys you nothing.** The soak clock starts when you
  finish Step 2/3 and *prove* the read happened, not on 2026-07-17.
- **Never again accept "the variable is set" as evidence.** Every flag step
  below requires a positive oracle (Appendix A) showing which *table* was read.
  That check is the whole reason this document exists.
- Do not "correct" the stale claims in `dual-write-cutover.md` mid-incident.
  Record what you observe here; reconcile the docs afterwards.

### 2. What makes a 12-hour compression defensible — and what does not

| | Reversibility | Blast radius | Compressible? |
|---|---|---|---|
| Read flags (Steps 2–3) | env var + restart, seconds | read path only; **dual write still on, so legacy remains a complete, current fallback** | **Yes** |
| Backfill (Step 5) | writes rows; reversible only by targeted delete | canonical store gains rows | Partly — dry-run is not compressible |
| Retire dual write (Step 6 / WS-1d) | **not reversible on this timescale** — legacy stops receiving data the moment it ships; every minute after is unrecoverable divergence | permanent | **No** |

The asymmetry is the entire argument. Steps 2–3 are cheap to undo *because the
legacy store keeps being written*. The moment that stops being true, so does the
argument.

### 3. Facts about this repo that contradict common assumptions

| Assumption you may arrive with | Reality (verified in-repo) |
|---|---|
| Alembic head is `v093` / `16cb29a3938c` | **False.** Single head is **`51701aedee57` (v109)**, `alembic/versions/20260802_51701aedee57_v109_team_roster_security_definer.py`. Verified by `scripts/check_alembic_revisions.py` → *"OK — revision DAG is clean: unique IDs, single head, no orphans."* `16cb29a3938c` is v093, sixteen revisions back. |
| Flipping a flag writes a log line | **False.** `export_v1_reads_canonical()` and `chain_verify_reads_canonical()` are bare `os.getenv` reads with no logging. There is **no** log signal. Use Appendix A. |
| `/health` or `/readiness` reports the deployed SHA | **False.** Neither exposes a commit SHA or the alembic revision. Confirm via Railway CLI/dashboard and a SQL query. |
| The runtime DB role can scan all tenants | **False.** Runtime `DATABASE_URL` is the RLS-enforced `regengine` role; `get_tenant_context()` **raises** when `app.tenant_id` is unset. An all-tenant parity scan needs the owner role (`MIGRATIONS_DATABASE_URL`). See Step 4. |
| The canonical store is indexed on `sha256_hash` | **False.** `v081` (`a7b8c9d0e1f2`) indexed `fsma.cte_events (tenant_id, sha256_hash)` **only**. `fsma.traceability_events` has no such index; the parity scan's twin lookup degrades toward a table scan. Budget for it (Step 4). |
| Merging this runbook will deploy something | **False, and deliberately so.** `docs/**` is in neither `backend-ci.yml` nor `deploy.yml` push paths. A docs-only merge triggers no CI and no deploy. |
| `legacy_orphans == 0` is reachable today | **Probably false.** See "The Step 4/5 deadlock" below — a whole class of legacy rows *cannot* join canonical by hash, by construction. Know this before the scan returns exit 1 at 3am. |

### 5. The Step 4 / Step 5 deadlock — read this before the scan returns

The two sibling scripts disagree, and the disagreement lands exactly on the
Step 4 gate. Resolve it *now*, not when a red verdict is on screen.

`scripts/verify_canonical_parity_live.py`'s docstring claims a `webhook_compat`
pair "still joins on `sha256_hash`". **That is not correct**, and the hash
preimages prove it:

| | Preimage (pipe-joined) |
|---|---|
| legacy `cte_persistence.hashing.compute_event_hash` | `event_id · event_type · tlc · quantity · unit_of_measure · location_gln · timestamp · json(kdes minus description keys)` — **8 fields**; `product_description` excluded (#1323), `location_name` accepted but **not hashed**, no `to_facility` |
| canonical `TraceabilityEvent.compute_sha256_hash` | `event_id · event_type · tlc · product_reference · quantity · unit_of_measure · from_facility_reference · to_facility_reference · timestamp · json(kdes)` — **10 fields** |

Different field sets, different arity. They cannot agree except by accident.

**Therefore:** every legacy row written by the legacy-native path
(`CTEPersistence.store_event`, still live via `webhook_compat.ingest_events`)
carries a legacy-formula hash and **can never join a canonical row by
`sha256_hash`** — even though the same real-world event *was* written
canonically by the sibling canonical-only store call in the same request.

The consequences chain badly:

1. Step 4 counts those rows as **`legacy_orphans`** → verdict `DO-NOT-PROCEED`,
   exit `1`, criterion **S3 fails**.
2. Step 5 is the designated repair — but it **correctly refuses** these exact
   rows, reporting them under `skipped_by_reason.legacy_native_hash_formula`,
   because backfilling them would (a) duplicate an event already present
   canonically and (b) inject a hash the canonical verifier cannot reproduce,
   creating a permanent chain-verification failure.
3. So the gate cannot be cleared by the tool built to clear it.

**What you must NOT do when this happens** (these are the 3am failure modes):
- Do not conclude data was lost. A `legacy_native_hash_formula` orphan is **not**
  a #1277 violation — the canonical row exists, just under a different hash.
- Do not add `--ignore-field` flags. They filter *field divergence* on matched
  pairs; they do nothing to orphans, and reaching for them here means you have
  misread the failure.
- Do not hand-write rows, backdate, or "fix" hashes to force a join.
- Do not proceed to WS-1d on the theory that it is "only a hashing artifact".

**What you MUST do:**

```bash
# classify the orphans — do the two tools agree on the count?
jq '.legacy_orphans.count' /tmp/ws1-parity-full.json
jq -r '.skipped_by_reason.legacy_native_hash_formula // 0' /tmp/ws1c-dryrun.json
```

- **If the counts match** (every parity orphan is a legacy-native-hash row):
  this is the **known structural class**, not corruption. Proceeding is a
  **daylight decision requiring the owner of #1335** — it is explicitly *not*
  authorised by this runbook and not a 3am judgement call. Steps 2 and 3 may
  remain flipped (they are independently evidenced and reversible); Steps 5
  and 6 stop.
- **If parity orphans EXCEED the backfill's legacy-native count:** the excess is
  the real thing — lost canonical writes, a genuine #1277 violation. **Roll back
  Steps 2 and 3 immediately** and treat it as a data-integrity incident.

The honest read: this repo cannot reach `legacy_orphans == 0` while
`webhook_compat.ingest_events` remains a live ingest route writing legacy-formula
hashes. Closing that gap is design work (retire the legacy-native write path, or
teach the parity scan to recognise and separately classify legacy-formula hashes)
— not something to discover and solve inside a 12-hour window.

### 4. Hard prohibitions for this window

- Do **not** change any code default. `FDA_EXPORT_V1_READ_CANONICAL` and
  `CHAIN_VERIFY_READ_CANONICAL` stay `default OFF` in source. This window flips
  *environment variables*, nothing else.
- Do **not** remove or disable the dual write.
- Do **not** delete or truncate `fsma.cte_events` / `fsma.cte_kdes`.
- Do **not** let `scripts/verify_canonical_parity_live.py` run with `--execute`-
  like intent; it is structurally read-only and must stay that way.
- Do **not** add `--ignore-field` to make a scan green without the sign-off in
  GO/NO-GO item **G6**.

---

## Preconditions

Gather these **before** the window opens. Missing any one of them turns a
12-hour window into a 14-hour window.

| Need | Why | Verify now |
|---|---|---|
| GitHub org billing admin | Step 0 is account-level; a repo admin cannot clear it | Can you load the org billing page? |
| `gh` CLI authenticated | Step 0/1 verification | `gh auth status` |
| Railway access (dashboard + `railway` CLI) | Steps 1–3 | `railway whoami` |
| `MIGRATIONS_DATABASE_URL` (owner role) — read-only use | Step 4 all-tenant scan, Appendix A | value present in Railway service vars |
| Runtime `DATABASE_URL` (`regengine` role) | Step 1 head check | as above |
| Repo checkout at the SHA you intend to deploy | Steps 4–5 run scripts from it | `python3 -m pytest tests/invariants -q` passes locally |
| A named second person with authority to say "roll back" | Step 2/3 judgement calls | they are awake |

Local validation baseline (run it now; CI cannot do this for you):

```bash
source venv/bin/activate
python3 -m pytest tests/invariants/test_fda_export_v1_golden.py \
                  tests/invariants/test_chain_verify_golden.py \
                  tests/invariants/test_dual_write_parity.py -q
```

**Expected:** `12 passed`. **This was confirmed green locally while writing this
runbook.** If it is not green, the cutover does not start — the goldens are the
only proof that legacy and canonical readers agree.

---

## Step 0 — Clear the Actions spending limit (BLOCKS EVERYTHING)

GitHub Actions is down repo-wide: runner allocation failure, 0 billable ms,
account-level billing. `deploy.yml` will not run without a green
`Backend CI Status Gate` check, and that check comes from Actions. There is no
supported bypass. **Nothing in Steps 1–6 can proceed until this is fixed.**

**0.1 — Clear the limit.**

Click path: GitHub → organisation → **Settings** → **Billing and licensing** →
**Spending limits** → **Actions** → raise the limit (or enable
"Unlimited spending") → **Update limit**. Also confirm the payment method on
file is not expired/declined — a valid limit with a dead card fails identically.

- **Expected:** the Actions spending limit shows the new value and no red
  payment banner remains.
- **Abort trigger:** you are not a billing admin, or the payment method is
  rejected. → Escalate to whoever owns the account. Do not proceed. Do not
  attempt to self-host a runner as a workaround during this window.

**0.2 — Prove runners actually run and consume billable time.**

"Queued" is not "working". A billing-blocked run can sit queued, or complete
instantly with a billing error and **0 billable ms** — the exact signature of
the current outage.

```bash
export REPO=regengine/RegEngine          # confirm your actual owner/repo

gh workflow run backend-ci.yml --repo "$REPO" --ref main
sleep 60
gh run list --repo "$REPO" --workflow backend-ci.yml --limit 1
RUN_ID=$(gh run list --repo "$REPO" --workflow backend-ci.yml --limit 1 --json databaseId -q '.[0].databaseId')
gh run watch "$RUN_ID" --repo "$REPO"

# THE decisive check — billable milliseconds, not status:
gh api "repos/$REPO/actions/runs/$RUN_ID/timing"
```

- **Expected:** the timing payload reports
  `{"billable":{"UBUNTU":{"total_ms":<large>,"jobs":<n>}},"run_duration_ms":<large>}`
  with `total_ms` in the **millions** (backend-ci is a long suite).
- **PASS:** `billable.*.total_ms > 0` **and** jobs progressed past `queued` into
  `in_progress`. This is the only accepted proof.
- **FAIL / abort trigger:** `total_ms == 0`, or the run sits `queued` for
  > 15 minutes, or any job annotation mentions billing/spending/payment. →
  Billing is not actually cleared. Return to 0.1. **Do not proceed to Step 1.**
- **Rollback:** none needed — this step changes no product state. If you raised
  the spending limit and now want it lowered, do that after the window, not
  during it.

> **Not compressible.** There is no path around this. See "12-hour triage".

---

## Step 1 — Green CI on `main`, deploy, verify SHA and migrations

**1.1 — Confirm the backend gate is green on the SHA you will ship.**

```bash
gh run list --repo "$REPO" --workflow backend-ci.yml --branch main --limit 5
gh api "repos/$REPO/commits/$(gh api repos/$REPO/commits/main -q .sha)/check-runs" \
  -q '.check_runs[] | select(.name=="Backend CI Status Gate") | {name,status,conclusion}'
```

- **Expected:** exactly one `Backend CI Status Gate` with
  `status: completed`, `conclusion: success`.
- **PASS:** conclusion is `success`.
- **FAIL / abort trigger:** `failure`, `skipped`, or **absent**. `deploy.yml`
  sets `allowed-conclusions: success` and `fail-on-no-checks: true`, so a
  `skipped` gate or a missing gate cannot green-light a deploy — it will hang
  for the full `checks-discovery-timeout: 2700` (45 min) and then fail. Fix CI
  first; a 45-minute silent stall will eat your window.
- **Rollback:** n/a.

**1.2 — Deploy.**

A push to `main` touching backend paths deploys automatically. To deploy an
existing SHA deliberately, use the dispatch — it is the same gate:

```bash
gh workflow run deploy.yml --repo "$REPO" --ref main
gh run watch "$(gh run list --repo "$REPO" --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')" --repo "$REPO"
```

- **Expected:** `wait-for-ci` passes, then `railway up --ci ...` succeeds.
- **PASS:** deploy job green **and** Railway reports the new deployment
  `SUCCESS` with `/readiness` healthy (`railway.toml`:
  `healthcheckPath=/readiness`, `healthcheckTimeout=300`).
- **FAIL / abort trigger:** healthcheck fails 3× (`restartPolicyMaxRetries=3`),
  or the migration runner errors (see 1.3).
- **Rollback:** Railway dashboard → service → **Deployments** →
  previous deployment → **Redeploy**. Production returns to `48d5f641`, which is
  a known-working state with both flags inert.

**1.3 — Confirm the deployed SHA.**

Neither `/health` nor `/readiness` reports a commit. Use Railway:

```bash
railway status --json                    # or: Railway dashboard → Deployments
curl -fsS https://<prod-host>/readiness | jq '.status, .checks.postgres'
curl -fsS https://<prod-host>/health     | jq
```

- **Expected:** Railway's active deployment references the intended commit;
  `/readiness` returns `"ok"` or `"degraded"` with `checks.postgres.status: "ok"`.
- **PASS:** active deployment SHA **≠ `48d5f641`** and equals your target SHA.
- **FAIL / abort trigger:** SHA still `48d5f641`, or `postgres` is `error`
  (that is the only component that can 503). → Roll back per 1.2. **A flag flip
  on the old image is precisely the failure that produced the fictitious soak in
  the first place. Do not flip anything until this check passes.**
- **Rollback:** redeploy previous.

**1.4 — Confirm migrations reached head.**

Migrations run automatically at container boot (`Dockerfile` CMD →
`bash /app/scripts/run-migrations.sh && gunicorn ...`) under a Postgres advisory
lock with a 90 s timeout, using `MIGRATIONS_DATABASE_URL` (owner role) when set.

```bash
psql "$DATABASE_URL" -c "SELECT version_num FROM alembic_version;"
```

- **Expected:** `51701aedee57`
- **PASS:** the value equals the single head reported by
  `python3 scripts/check_alembic_revisions.py` **for the SHA you deployed** —
  derive it, do not trust this document's copy of it:
  ```bash
  python3 scripts/check_alembic_revisions.py    # → "Head(s): <rev>"
  ```
- **FAIL / abort trigger:** more than one row in `alembic_version` (multi-head —
  `alembic upgrade head` is ambiguous), a value behind head, or boot logs showing
  `MIGRATION_LOCK_TIMEOUT_S` exhaustion. → Roll back; resolve migrations outside
  this window.
- **Rollback:** redeploy previous. Note that **rolling the app back does not roll
  migrations back**; forward-only is the repo's model. Nothing in WS-1b/1c
  requires a new migration, so this should not arise.

---

## Step 2 — Flip `FDA_EXPORT_V1_READ_CANONICAL`

Affects: `services/ingestion/app/fda_export/queries.py` —
`export_v1_reads_canonical()` selects `fetch_recall_events_canonical()` /
`build_recall_where_clause_canonical()` instead of the `fsma.cte_events` +
`fsma.cte_kdes` readers. Proven byte-identical across 7 filter combinations by
`tests/invariants/test_fda_export_v1_golden.py`.

**2.1 — Baseline before the flip.** Capture Appendix A counters and run one
representative v1 recall export, saving the CSV. You need a *before* artifact to
diff against; without it "it looks fine" is not evidence.

**2.2 — Flip.**

Railway → service → **Variables** → set `FDA_EXPORT_V1_READ_CANONICAL=1` → the
service restarts. (Accepted truthy values: `1`, `true`, `yes`, `on`;
case-insensitive, whitespace-stripped.)

- **Expected:** service restarts, `/readiness` healthy within the 300 s window.
- **PASS:** healthy restart.
- **FAIL / abort trigger:** restart loop. → Rollback 2.5.

**2.3 — PROVE IT IS BEING READ (mandatory).**

Run **Oracle A** (Appendix A). `fsma.cte_kdes` is the clean discriminator: the
legacy export reader joins it via a correlated subquery; the canonical reader
never touches it, and **neither** chain verifier touches it. So its counters are
not contaminated by Step 3.

- **PASS:** across a v1 recall export, `fsma.cte_kdes` counters **do not move**
  and `fsma.traceability_events` counters **do** move.
- **FAIL / abort trigger:** `cte_kdes` still moving → the flag is set but not
  read (wrong service, wrong environment, stale image, or a worker process that
  did not restart). → Rollback 2.5, re-verify Step 1.3, and treat any claim of
  success as false.

Where a canonical-only row exists for an exportable tenant, corroborate with
**Oracle B** (Appendix A) — it is hermetic and beats the counter delta.

**2.4 — Watch (soak).** Minimum **60 minutes** of real export traffic, and at
least one export per filter shape you actually serve.

Watch for:
- `X-Chain-Integrity` flipping `VERIFIED` → `UNVERIFIED` on exports that were
  previously `VERIFIED`.
- Row-count changes vs the 2.1 baseline CSV for the same filters. Expected delta
  is **zero** on dual-written data; a *positive* delta is canonical-only rows
  becoming visible (explainable, but must be explained, not shrugged at).
- 5xx on `/api/v1/fda/*`.
- Export latency: the canonical reader has no `sha256_hash` index backing it, and
  its `LEFT JOIN fsma.hash_chain` is on `event_hash`. Watch p95.

- **PASS:** zero 5xx attributable to export; row counts match baseline (or every
  difference is traced to a specific canonical-only row); no new `UNVERIFIED`.
- **Abort trigger (any one):** any export 5xx; any row-count difference you
  cannot explain within 10 minutes; any customer-visible export discrepancy;
  p95 latency regression > 2×.

**2.5 — Rollback.** Railway → Variables → **delete** `FDA_EXPORT_V1_READ_CANONICAL`
(or set `0`) → restart. Confirm with Oracle A that `cte_kdes` counters move
again. Recovery time: one restart. The legacy store is still being dual-written,
so it is current — there is no data to reconcile on rollback.

---

## Step 3 — Flip `CHAIN_VERIFY_READ_CANONICAL`

Affects: `services/shared/canonical_persistence/verification.py` —
`chain_verify_reads_canonical()`; consumed by
`services/ingestion/app/compliance_score.py` and the three FDA export handlers
via `_verify_chain_for_export()`. Proven by
`tests/invariants/test_chain_verify_golden.py`.

**Known limitation, stated plainly.** The golden's corpus is written by
`CanonicalEventStore(dual_write=True)`, which appends **one** chain row per
event. The real ingest route (`webhook_compat.ingest_events` = legacy
`store_event` **plus** a separate canonical-only store) appends **two**. The
golden therefore does not exercise the shape production actually has;
`tests/shared/test_chain_verify_dual_write_live.py` does. The canonical verifier
handles this via the #2506 combine rule (a row is a true orphan only when *both*
stores miss it). **This is the weakest proof in the sequence — do not compress
Step 3's soak below Step 2's.**

Also note: the chain-verification *job* (`chain_verification_job.py`)
deliberately walks **both** stores and does **not** consult this flag. Flipping
this does not change the job.

**3.1 — Baseline.** Capture Appendix A counters. Record `chain_verified` for a
handful of known tenants via the compliance-score path, and the
`X-Chain-Integrity` header on a v1 export.

**3.2 — Flip.** Railway → Variables → `CHAIN_VERIFY_READ_CANONICAL=1` → restart.

- **PASS:** healthy restart. **FAIL:** restart loop → rollback 3.5.

**3.3 — PROVE IT IS BEING READ (mandatory).**

Use **Oracle C** (Appendix A) against the **compliance-score** path, not the
export path. Rationale: `compliance_score.py` reads *only* legacy tables
(`fsma.cte_events`, `fsma.cte_kdes`, `fsma.hash_chain`) — verified by grep — and
touches `fsma.traceability_events` **exclusively** through the flagged verifier.
The legacy `verify_chain` never reads `traceability_events` at all. So movement
on `fsma.traceability_events` during a compliance-score request is unambiguous.

Do **not** use the export path here: if Step 2 is already on, exports touch
`traceability_events` for a different reason and the signal is contaminated.

- **PASS:** `fsma.traceability_events` counters move during a compliance-score
  request.
- **FAIL / abort trigger:** they do not → flag set, not read. Rollback 3.5.

**3.4 — Watch (soak).** Minimum **60 minutes**.

Watch for:
- Tenants whose `chain_verified` flips `true` → `false`. **This is the highest-
  severity signal in the entire cutover.** A tenant that was verifying and now
  does not means the two verifiers disagree on real production data — exactly
  what the golden's corpus gap could hide.
- Compliance scores moving. Chain integrity is 30% of the score;
  `chain_verified: false` collapses that dimension.
- `chain_verification_error: true` / `chain_verified: null` appearing (the
  fail-closed branch — verification failed to *run*).
- `X-Chain-Integrity: UNVERIFIED` on exports that were `VERIFIED` at 3.1.

- **PASS:** no tenant regresses `true → false`; no new `null`/error; compliance
  scores stable.
- **Abort trigger (any one):** **any** tenant regressing `true → false` — roll
  back immediately, do not investigate first; any new `chain_verification_error`;
  any export dropping to `UNVERIFIED`.

**3.5 — Rollback.** Delete `CHAIN_VERIFY_READ_CANONICAL` → restart. Confirm with
Oracle C that `traceability_events` counters stop moving on compliance-score
requests. One restart. Nothing to reconcile.

---

## Step 4 — Evidence-based soak gate (`verify_canonical_parity_live.py`)

This is what replaces a calendar soak with a measurement. It is **strictly
read-only** — three independent layers (statement allowlist,
`default_transaction_read_only=on` on the connection, re-asserted via
`set_config`) — so it is safe to point at production.

**4.1 — Role and RLS.** `fsma.cte_events` / `fsma.traceability_events` are
`FORCE ROW LEVEL SECURITY` with a `tenant_id = get_tenant_context()` policy, and
`get_tenant_context()` **raises** when `app.tenant_id` is unset.

- All-tenant scan → requires the **owner** role (`MIGRATIONS_DATABASE_URL`).
- Single-tenant scan → works under either role; the script sets the
  `app.tenant_id` GUC itself **only when exactly one `--tenant` is given**.
- Two or more `--tenant` values under the runtime role will fail or silently
  under-cover. Prefer one all-tenant scan as owner, or loop one tenant at a time.

**4.2 — Smoke pass first** (bounded; protects production from a cold scan):

```bash
export DATABASE_URL="$MIGRATIONS_DATABASE_URL"    # owner role, read-only use
python3 scripts/verify_canonical_parity_live.py --limit 1000 --json \
  | tee /tmp/ws1-parity-smoke.json
```

- **Expected:** exit 0, `"verdict": "SMOKE PASS CLEAN — NOT A CUTOVER DECISION"`.
- **PASS:** exit 0 and `legacy_orphans.count == 0` and
  `field_divergence.rows == 0`.
- **This is explicitly NOT the gate.** The script says so itself.

**4.3 — Full scan (the actual gate):**

```bash
python3 scripts/verify_canonical_parity_live.py --json \
  --statement-timeout-ms 60000 --batch-size 1000 \
  | tee /tmp/ws1-parity-full.json
echo "exit=$?"
```

Note `--settle-seconds` (default applied when `--until` is omitted) excludes the
most recent seconds, because cross-transaction writers commit the legacy and
canonical rows separately and scanning up to `now()` reports phantom orphans.
**Do not set `--settle-seconds 0`** to "get more coverage."

**Exit codes:** `0` safe · `1` parity violations · `2` could not complete ·
`3` zero coverage (false-green guard).

**4.4 — SAFE-TO-PROCEED criteria. All must hold simultaneously:**

| # | JSON path | Required value | Why |
|---|---|---|---|
| S1 | `exit_code` | `0` | any other value is DO-NOT-PROCEED by construction |
| S2 | `verdict` | `"SAFE-TO-PROCEED"` | **not** `"SMOKE PASS CLEAN"` — that string means `--limit` truncated the scan |
| S3 | `legacy_orphans.count` | `0`, **or** every orphan classified as `legacy_native_hash_formula` per the deadlock procedure | a legacy row with no canonical twin normally means a canonical write was lost (#1277). But legacy-native-hash rows can never join by construction — classify before you conclude. **Any orphan not accounted for by that class is a hard stop.** See "The Step 4 / Step 5 deadlock" |
| S4 | `field_divergence.rows` | `0` | the `dual_write_legacy` mapping is not being reproduced |
| S5 | `field_divergence.rows_same_transaction` | `0` | **non-negotiable.** Same-transaction pairs came from `dual_write_legacy` itself; divergence here means the dual write is broken. No `--ignore-field` may ever be used to clear this |
| S6 | `coverage.rows_compared` | `> 0` and ≥ 95% of `coverage.legacy_total_in_window` | guards the classic false-green; a large shortfall means RLS or the window is hiding rows |
| S7 | `coverage.truncated_by_limit` | `false` | a truncated scan is not a release decision |
| S8 | `coverage.ambiguous_matches` | `0` | duplicate `sha256_hash` within a tenant makes the join non-unique; the mapping is unverifiable for those rows |
| S9 | `options.ignore_fields` | `[]` | unless G6 sign-off exists (below) |
| S10 | `connection.canonical_sha_index` | record it | expected `null` — no index on `traceability_events(sha256_hash)`. Not a blocker; it is a **performance** warning. If the scan is unacceptably slow, narrow with `--since`, do **not** raise `--limit` and call it done |

**Conditional exception (S9 / G6):** `field_divergence.by_field.id > 0` confined
entirely to `rows_cross_transaction` is *structural*, not corruption — those
pairs were written by two different writers (`webhook_compat`'s legacy
`store_event` + a separate canonical-only store), so `cte_events.id` legitimately
differs from `traceability_events.event_id`. **But it means the `id` column of
the regulator-facing v1 export changes value at cutover for those rows.** That is
a real, externally visible change to an FDA traceability record identifier.

If you use `--ignore-field id`, then **all** of the following must hold:
- `field_divergence.rows_same_transaction == 0` with no ignores at all;
- every ignored divergence is `id` and only in cross-transaction pairs;
- a named human signs off in the GO/NO-GO record that the exported `id` value
  changing is accepted.

The script echoes `ignore_fields` in its verdict block specifically so this
cannot be smuggled past a reviewer. Do not defeat that.

- **Abort trigger:** exit `1`, `2`, or `3`; or any of S1–S9 failing. Exit `3`
  (zero coverage) especially: it means you proved nothing. Fix the window/role
  and re-run.
- **Rollback:** none — the script writes nothing. But a failed gate means Steps 5
  and 6 do not happen, and you should seriously consider rolling the Step 2/3
  flags back rather than sitting on unexplained divergence.

---

## Step 5 — WS-1c backfill (`backfill_canonical_from_legacy.py`)

Only run this if Step 4 reported `legacy_orphans.count > 0` — those orphans are
exactly what this repairs. If Step 4 is clean, **skip Step 5 entirely**; there is
nothing to backfill.

> **Run the dry run (5.1) even when you do not intend to execute.** It is
> read-only, and its `skipped_by_reason.legacy_native_hash_formula` count is the
> classifier the deadlock procedure needs. Executing (5.3) requires G3.0 — the
> daylight sign-off — not merely a non-zero orphan count.

Safety properties (verified in-script): `--dry-run` is the **default**, writing
requires explicit `--execute`; `fsma.hash_chain` is **never** written; each row
insert runs inside a SAVEPOINT so one bad row cannot poison its batch;
tenant-scoped with `app.tenant_id` set per tenant so RLS is *enforced*, not
bypassed; idempotent and resumable.

It reconstructs the ambiguous `location_gln` → (`from_facility_reference`,
`to_facility_reference`) split by enumerating the closed set of hypotheses and
accepting one **only when it reproduces the stored `sha256_hash` bit for bit**.
A match is proof, not a guess. Rows where no hypothesis matches are **refused**,
never synthesised.

**5.1 — Dry run (default; mutates nothing):**

```bash
DATABASE_URL="$MIGRATIONS_DATABASE_URL" \
python3 scripts/backfill_canonical_from_legacy.py \
  --report-path /tmp/ws1c-dryrun.jsonl --json | tee /tmp/ws1c-dryrun.txt
```

- **Expected:** banner `DRY RUN — no writes will be issued. Pass --execute to
  apply.` and a summary ending `Nothing was written.`
- **PASS:** exit `0` (exit `1` = unexpected row errors, `2` = could not connect /
  no tenants resolved).

**5.2 — Review the dry run. Do not skip this; it is the whole safety margin.**

| Summary field | Interpretation | Action |
|---|---|---|
| `orphans_found` | should equal Step 4's `legacy_orphans.count` | **material disagreement ⇒ stop.** Two independent tools disagree about reality |
| `backfilled` (would-backfill) | rows whose hash oracle matched | should be `orphans_found` − `skipped` |
| `skipped_by_reason.legacy_native_hash_formula` | rows written by the legacy-native path (`webhook_compat` → `store_event`), which uses a *different* hash formula and can never join canonically | **Expected and correct.** Backfilling these would duplicate an event that already exists canonically and inject a hash the canonical verifier cannot reproduce. Non-zero here is normal |
| other `skipped_by_reason.*` | refusals (e.g. no hypothesis reproduced the hash — often a dropped `None`-valued KDE) | Read `REFUSAL_HELP` text printed inline. Refusals are a **normal, reportable outcome**, not a failure |
| `facility_hypotheses` | which from/to split the hash proved, per row class | a wildly skewed distribution deserves a second look |
| `status_assumed_active` | `validation_status='valid'` is lossy (`active`/`superseded`/`draft` all map to `valid`); no canonical superseder found | if this is large and matters to you, re-run with `--status-ambiguous=skip` and backfill those separately |
| `chain_entry_missing` | backfilled rows with no `fsma.hash_chain` row | **informational only — the script will not fix it.** Every non-zero value needs a named human owner and a follow-up issue. Do not let this scroll past |
| `errors` | unexpected exceptions | **must be `0`** before `--execute` |

- **Abort trigger:** `errors > 0`; `orphans_found` materially ≠ Step 4's count;
  refusal reasons you do not understand.

**5.3 — Execute (bounded first, then full):**

```bash
# bounded first pass — prove the write path on a small batch
DATABASE_URL="$MIGRATIONS_DATABASE_URL" \
python3 scripts/backfill_canonical_from_legacy.py --execute \
  --limit 100 --batch-size 100 \
  --report-path /tmp/ws1c-exec.jsonl --state-file /tmp/ws1c-state.json --json

# re-verify before widening
python3 scripts/verify_canonical_parity_live.py --json | jq '.legacy_orphans.count'

# full run
DATABASE_URL="$MIGRATIONS_DATABASE_URL" \
python3 scripts/backfill_canonical_from_legacy.py --execute \
  --batch-size 200 \
  --report-path /tmp/ws1c-exec.jsonl --state-file /tmp/ws1c-state.json --json
```

- **Expected:** header `EXECUTE (rows written)`; `backfilled` matches the dry
  run's projection; `errors: 0`.
- **PASS:** exit `0`, `errors == 0`, and a re-run of Step 4 now reports
  `legacy_orphans.count == 0` with S1–S8 still holding.
- **FAIL / abort trigger:** `errors > 0`; parity does not improve; any new
  `field_divergence`.
- **Rollback:** there is no undo command. Backfilled rows are identifiable —
  they carry `provenance_metadata.backfill` with mapper
  `backfill_canonical_from_legacy` v`1.0.0` and issue `#1335 WS-1c`, and
  `/tmp/ws1c-exec.jsonl` is a per-row audit trail. Removal is a hand-written,
  reviewed `DELETE` scoped by that provenance marker — **not** a 3am action.
  Bound the exposure by keeping the first pass at `--limit 100`.
- **Retain** `/tmp/ws1c-dryrun.jsonl`, `/tmp/ws1c-exec.jsonl` and both parity
  JSONs as compliance evidence. Move them off the ephemeral box.

---

## Step 6 — WS-1d retirement (REFERENCE ONLY — not in this window)

Listed so nobody improvises it at hour 11.

WS-1d drops `dual_write` from `CanonicalEventStore`, applies a read-only trigger
to the legacy tables for one release, then archives them. It also removes the
canonical verifier's existence-only `cte_events` probe, retires
`scripts/validate_data_integrity.py`'s reconciliation check from the ops runbook,
and deletes `DUAL_WRITE_RECONCILIATION_NEEDED`.

> **Until then, when you run `scripts/validate_data_integrity.py` (#2934):**
> exit 0 counts as evidence only if the output shows a `[PASS]` line for all
> four named checks — Hash Chain Continuity, Orphaned Records, Dual-Write
> Reconciliation, Tenant Isolation. Paste the printed check table into the
> evidence log, not just the exit status. No database means no verification:
> the script exits `2` (or `64` when `DATABASE_URL` is unset) and prints the
> connection error — treat that as NO-GO, not as a pass.

**Entry gate — all of:**
1. Steps 2 and 3 soaked with **no** rollback, on evidence (Appendix A), for a
   full release cycle — not 12 hours.
2. Step 4 full scan `SAFE-TO-PROCEED` with `ignore_fields: []`, repeated on at
   least two separate days.
3. Step 5 complete: `legacy_orphans.count == 0`, `chain_entry_missing` resolved
   and closed out.
4. Code defaults flipped to canonical and shipped **before** the dual write is
   removed — never in the same release.
5. The never-do list in `dual-write-cutover.md` re-read and still satisfied.

**Why it cannot be compressed:** every earlier step's rollback works *because the
legacy store is still being written and is therefore current*. WS-1d ends that.
From the moment it ships, legacy is frozen and diverging, and "flip it back" no
longer restores a usable fallback — it restores a stale one. There is no
12-hour version of this step, and the existence of a fictitious soak in the
project record (see the top of this document) is a direct argument for *more*
caution here, not less.

---

## GO / NO-GO checklist

Sign each line with a name and a timestamp. An unchecked box is a NO-GO.

**Gate 0 — may the window start?**

- [ ] **G0.1** Actions spending limit cleared; payment method valid.
- [ ] **G0.2** A dispatched run reported `billable.*.total_ms > 0`
      (`gh api repos/$REPO/actions/runs/<id>/timing`). *Queued ≠ working.*
- [ ] **G0.3** `pytest tests/invariants/{test_fda_export_v1_golden,test_chain_verify_golden,test_dual_write_parity}.py` green locally (12 passed).
- [ ] **G0.4** Rollback authority named and awake.
- [ ] **G0.5** Owner-role DB URL available for read-only use.

**Gate 1 — may flags be flipped?**

- [ ] **G1.1** `Backend CI Status Gate` = `success` on the deployed SHA.
- [ ] **G1.2** Railway active deployment SHA **≠ `48d5f641`** and equals target.
- [ ] **G1.3** `SELECT version_num FROM alembic_version` equals the single head
      from `scripts/check_alembic_revisions.py` (expected `51701aedee57`), one
      row only.
- [ ] **G1.4** `/readiness` → `checks.postgres.status == "ok"`.

**Gate 2 — per flag (complete twice: Step 2, then Step 3)**

- [ ] **G2.1** Pre-flip baseline captured (counters + export CSV / chain states).
- [ ] **G2.2** Service restarted healthy after the variable change.
- [ ] **G2.3** **Oracle proves the correct table was read** — Oracle A/B for
      `FDA_EXPORT_V1_READ_CANONICAL`, Oracle C for `CHAIN_VERIFY_READ_CANONICAL`.
      *"The variable is set" is not acceptable evidence.*
- [ ] **G2.4** ≥ 60 min soak, zero abort triggers fired.
- [ ] **G2.5** Rollback rehearsed at least once for one flag (unset → restart →
      oracle confirms the legacy table is read again).

**Gate 3 — may the backfill run?**

- [ ] **G3.0** If `legacy_orphans.count > 0`: every orphan is accounted for by
      the backfill dry run's `legacy_native_hash_formula` count, **and** the
      owner of #1335 has signed off in daylight. Any unaccounted orphan ⇒
      **NO-GO and roll back Steps 2–3.** (Deadlock procedure, top of document.)
- [ ] **G3.1** Full parity scan: S1–S8 all satisfied.
- [ ] **G3.2** `coverage.rows_compared ≥ 0.95 × coverage.legacy_total_in_window`.
- [ ] **G3.3** `field_divergence.rows_same_transaction == 0` with **no** ignores.
- [ ] **G3.4 (conditional)** If `--ignore-field id` is used: every ignored
      divergence is `id`, cross-transaction only, **and** ______________ (name)
      accepts that the v1 export's `id` column changes for those rows.
- [ ] **G3.5** Dry run reviewed line by line; `errors == 0`;
      `orphans_found` agrees with the parity scan.
- [ ] **G3.6** `chain_entry_missing` has a named owner and a filed issue.
- [ ] **G3.7** Bounded `--limit 100` execute pass verified before the full run.

**Gate 4 — WS-1d**

- [ ] **G4.x** NO-GO for this window. Unconditionally. Do not check these boxes
      tonight.

---

## If you only have 12 hours

### You MAY compress

| What | Reasoning |
|---|---|
| **Running Steps 2 and 3 in the same window** instead of separate releases | The flags are independent (different modules, different consumers) and each is individually reversible in one restart. Contamination between their oracles is handled by using `cte_kdes` for Step 2 and the compliance-score path for Step 3. |
| **The calendar soak → a 60-minute evidenced soak** | The soak's purpose is to detect legacy/canonical divergence. Step 4 *measures* that divergence directly across the whole store. A measurement over all rows beats an hour of hoping the right query shape arrives. Time still buys traffic-shape diversity — which is why 60 min is a floor, not a formality. |
| **Skipping the smoke pass** if the full scan completes quickly | The smoke pass exists to protect production from an unindexed cold scan. If a `--since`-narrowed full scan returns fast, the smoke pass adds nothing. |
| **Skipping Step 5 entirely** when Step 4 reports zero legacy orphans | There is nothing to backfill. Running a writer with no work is pure risk. |
| **Deferring documentation reconciliation** (fixing the stale claims in `dual-write-cutover.md`, `README.md`, `queries.py`) | Nothing depends on it during the window. Do it the next working day — but *do* it. |

### You MAY NOT compress

| What | Reasoning |
|---|---|
| **Step 0 (billing)** | Structural, not procedural. `deploy.yml`'s `wait-for-ci` requires a `Backend CI Status Gate` with `allowed-conclusions: success` and `fail-on-no-checks: true`. No gate → no deploy, and it stalls 45 minutes before telling you. There is no workaround and attempting one at 3am invents a new untested deploy path. |
| **The oracle check after each flip (G2.3)** | This is the single defect that already occurred: env vars were set, the project recorded a soak, and zero canonical reads happened. Skipping this reproduces a *known* failure. It costs about 5 minutes. |
| **Confirming the deployed SHA (G1.2)** | Same root cause. A flag flip against `48d5f641` is a no-op that reads as success. |
| **The full, non-truncated parity scan before Step 5 (S7)** | `truncated_by_limit: true` yields the verdict string `"SMOKE PASS CLEAN — NOT A CUTOVER DECISION"`. The tool refuses to call it a decision; so must you. |
| **`rows_same_transaction == 0` (S5)** | Same-transaction pairs are produced by `dual_write_legacy` itself. Divergence there means the writer is broken. No amount of schedule pressure makes that acceptable on FDA traceability data. |
| **The backfill dry run (5.1/5.2)** | It is the only review point before rows are written into a compliance-critical store, and there is no undo command. |
| **Zero-coverage guard (exit 3 / S6)** | A scan that compared 0 rows proves nothing. Accepting it converts "we verified" into a false statement in a regulated record. |
| **Classifying legacy orphans before acting on them (G3.0)** | The scan's `DO-NOT-PROCEED` may be reporting a known structural class rather than data loss — or it may be reporting real loss. Those demand opposite responses (sign off in daylight vs. roll back immediately as an incident). Guessing under time pressure gets it backwards. |
| **Step 6 / WS-1d** | Not reversible on this timescale. See Step 6. |

### Realistic budget

| Step | Wall clock |
|---|---|
| 0 — billing + runner proof | 30–90 min (mostly out of your hands) |
| 1 — CI green + deploy + verify | 60–120 min (backend-ci is long) |
| 2 — export flag + oracle + soak | 90 min |
| 3 — chain flag + oracle + soak | 90 min |
| 4 — parity scan | 30–120 min (unindexed; highly data-dependent) |
| 5 — backfill dry run + review + execute | 60–120 min, **or 0 if Step 4 is clean** |
| Contingency | ≥ 120 min |

That fits 12 hours only if Step 0 resolves quickly. **If Step 0 is not cleared
within the first 2 hours, abandon the window and reschedule.** Everything
downstream is gated on it, and a compressed Step 2–5 executed by someone who has
already burned 6 hours fighting billing is worse than no cutover at all.

---

## Accepted risks (we are accepting these, not eliminating them)

1. **A 60-minute soak sees fewer query shapes than a release.** The v1 export
   golden covers 7 filter combinations, but production filter mixes are
   long-tailed. *Accepted because* rollback is one env var and the legacy store
   remains current. *Not* accepted for WS-1d.
2. **Step 3's golden does not exercise production's chain shape.** Its corpus
   writes one chain row per event; the live ingest route writes two. Covered
   only by `tests/shared/test_chain_verify_dual_write_live.py` and the #2506
   combine rule. This is the thinnest evidence in the sequence — hence the
   `true → false` immediate-rollback trigger at 3.4.
3. **The parity scan adds production load.** No index on
   `traceability_events(sha256_hash)`; the twin lookup degrades toward a scan.
   Mitigated by `--batch-size`, `--statement-timeout-ms`, and `--since`
   narrowing. Adding the index would be better — but that is a migration, and a
   migration is not a 3am change.
4. **RLS may hide rows from the scan.** Mitigated by the owner-role scan and the
   S6 coverage floor, not eliminated. A tenant invisible to the scanning role is
   a tenant you have not verified.
5. **Cross-transaction `id` divergence changes a regulator-facing column.** If
   `--ignore-field id` is used, the v1 export's `id` value changes for those
   rows at cutover. This is a *conscious accepted change*, gated on G3.4, not a
   silent one.
6. **Backfill has no undo command.** Mitigated by hash-proof-or-refuse, the
   bounded first pass, the JSONL audit trail, and the `provenance_metadata.backfill`
   marker. Not eliminated.
7. **`chain_entry_missing` rows are reported, not fixed.** The script never
   writes to `fsma.hash_chain` (correctly — it is append-only and
   sequence-numbered; inserting would break `verify_chain`). Those rows need
   separate human handling.
8. **The project record was wrong once already.** Three separate places assert a
   soak that did not occur. Assume other status claims about this migration are
   similarly optimistic and verify rather than read.
9. **The parity gate as specified may be unreachable.** Legacy-native-hash rows
   cannot join canonical by `sha256_hash`, so `legacy_orphans == 0` is likely
   unattainable while `webhook_compat.ingest_events` is live — and the two
   sibling scripts document contradictory beliefs about it. Accepted for Steps
   2–3 (independently evidenced, instantly reversible); **blocking** for Steps 5
   and 6 until the classification is resolved in daylight. This is a known gap
   being carried, not one being closed tonight.

---

## Appendix A — Oracles: proving which store was actually read

There is **no log line** when a flag is read. These are the available proofs.
Oracle B is hermetic; A and C are strong signals with a stated caveat.

### Counter snapshot (used by A and C)

```sql
SELECT relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch
FROM pg_stat_user_tables
WHERE schemaname = 'fsma'
  AND relname IN ('cte_events', 'cte_kdes', 'traceability_events')
ORDER BY relname;
```

Take a snapshot, issue exactly one request, wait ~2 s for the stats collector,
snapshot again, diff.

**Caveat, stated honestly:** these counters are cluster-wide. On a busy
production database, concurrent traffic also moves them. Run the probe in the
quietest window you have, and prefer a *qualitative* read ("this table moved at
all / did not move at all") over exact deltas. Where Oracle B is available, it
overrides A.

### Oracle A — `FDA_EXPORT_V1_READ_CANONICAL`, via `fsma.cte_kdes`

Snapshot → issue **one** v1 recall export (`GET /api/v1/fda/...`) → snapshot.

| Flag state | `cte_kdes` | `traceability_events` |
|---|---|---|
| **OFF** (legacy reader) | **moves** | does not move |
| **ON** (canonical reader) | **does not move** | **moves** |

`fsma.cte_kdes` is the clean discriminator: only `fetch_recall_events` joins it
(correlated subquery on `k.cte_event_id = e.id`); `fetch_recall_events_canonical`
aggregates KDEs from the `traceability_events.kdes` JSONB instead, and **neither**
chain verifier touches `cte_kdes`. So this signal is not contaminated by Step 3.

*(One contaminant to know about: `compliance_score.py` also reads `cte_kdes`.
Don't run a compliance-score request during this probe.)*

### Oracle B — `FDA_EXPORT_V1_READ_CANONICAL`, canonical-only row visibility (hermetic, read-only, preferred)

Several ingest paths write canonical-only by design (`epcis`,
`webhook_router_v2`, `auditor_router`, and `webhook_compat`'s canonical-only
store — all `CanonicalEventStore(..., dual_write=False)`). A canonical-only row
therefore exists in `fsma.traceability_events` and **not** in `fsma.cte_events`.

1. From the Step 4 JSON, confirm `canonical_only.count > 0`.
2. As the owner role, read-only, find one such row for a tenant you can export:

```sql
SET LOCAL default_transaction_read_only = on;
SELECT t.tenant_id, t.event_id, t.traceability_lot_code
FROM fsma.traceability_events t
LEFT JOIN fsma.cte_events c
       ON c.sha256_hash = t.sha256_hash AND c.tenant_id = t.tenant_id
WHERE c.id IS NULL AND t.traceability_lot_code IS NOT NULL
LIMIT 1;
```

3. Run the v1 recall export for that tenant filtered to that TLC.

| Flag state | That event in the export |
|---|---|
| **OFF** | **absent** (legacy store has no such row) |
| **ON** | **present** |

This is definitive and requires writing nothing to production. **Do not create a
synthetic event to manufacture this condition** — injecting fabricated
traceability records into a regulated store to test a flag is not an acceptable
trade. If no canonical-only row exists, fall back to Oracle A.

*(Expect `chain_hash` to be empty for rows written by `epcis` /
`webhook_router_v2`, which use `skip_chain_write=True`. Presence is the signal,
not the chain hash.)*

### Oracle C — `CHAIN_VERIFY_READ_CANONICAL`, via the compliance-score path

Snapshot → issue **one** compliance-score request → snapshot.

| Flag state | `traceability_events` |
|---|---|
| **OFF** (`CTEPersistence.verify_chain`) | **does not move** |
| **ON** (`verify_chain_canonical`) | **moves** |

Why this is unambiguous: `compliance_score.py` reads only `fsma.cte_events`,
`fsma.cte_kdes` and `fsma.hash_chain` for every other dimension, and the legacy
`verify_chain` reads only `fsma.hash_chain` + `fsma.cte_events` — it never
touches `traceability_events`. So any movement on `traceability_events` during a
compliance-score request came from the flagged verifier.

**Use the compliance-score path, not an export.** If Step 2's flag is already on,
exports touch `traceability_events` via the export reader and the signal is
contaminated.

**Do not** use `cte_events` as the discriminator here: the canonical verifier
performs an existence-only probe of `cte_events` for orphan classification
(#2506), so that table moves under **both** flag states.

---

## Appendix B — Command index

```bash
# invariants (local; CI cannot do this for you)
python3 -m pytest tests/invariants/test_fda_export_v1_golden.py \
                  tests/invariants/test_chain_verify_golden.py \
                  tests/invariants/test_dual_write_parity.py -q

# alembic head (derive, never hardcode)
python3 scripts/check_alembic_revisions.py          # → "Head(s): 51701aedee57"
psql "$DATABASE_URL" -c "SELECT version_num FROM alembic_version;"

# CI / deploy
gh workflow run backend-ci.yml --repo "$REPO" --ref main
gh api "repos/$REPO/actions/runs/$RUN_ID/timing"     # billable_ms > 0
gh workflow run deploy.yml --repo "$REPO" --ref main

# parity gate (read-only)
python3 scripts/verify_canonical_parity_live.py --limit 1000 --json   # smoke
python3 scripts/verify_canonical_parity_live.py --json                # gate

# backfill
python3 scripts/backfill_canonical_from_legacy.py --json              # dry run (default)
python3 scripts/backfill_canonical_from_legacy.py --execute --limit 100 --batch-size 100 \
    --report-path /tmp/ws1c-exec.jsonl --state-file /tmp/ws1c-state.json --json
```

**Rollback, both flags (memorise this):**
Railway → service → Variables → delete `FDA_EXPORT_V1_READ_CANONICAL` and/or
`CHAIN_VERIFY_READ_CANONICAL` → service restarts → confirm with the matching
oracle that the legacy table is being read again. Legacy is still dual-written,
so there is nothing to reconcile.
