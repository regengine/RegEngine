# Object Storage Subprocessor Decision (Trust Center / DPA)

**Issue:** regengine/RegEngine#2311
**Date:** 2026-05-12
**Status:** Awaiting founder approval
**Owner:** Christopher Sellers

## Current state

`services/ingestion/app/s3_utils.py` is **not a dev-only stub.** It is imported
live by `services/ingestion/app/routes_ingest.py` (`put_bytes`, `put_json` at
lines 475 / 477 / 482 / 544) and by `services/nlp/app/consumer.py` (`get_bytes`,
line 77). These calls back the production endpoints `POST /v1/ingest/url`,
`POST /v1/ingest/file`, and the Kafka claim-check path — endpoints that the
frontend (`frontend/src/lib/api-client.ts`) and `services/ingestion/main.py`
both register. Bucket targets are `RAW_DATA_BUCKET` and `PROCESSED_BUCKET`
(default names `reg-engine-raw-data-dev` / `reg-engine-processed-data-dev` per
`services/ingestion/app/config.py`).

The client builder requires `OBJECT_STORAGE_ACCESS_KEY_ID` +
`OBJECT_STORAGE_SECRET_ACCESS_KEY`; absent those, every call raises
`NotImplementedError`. There is no try/except wrapping the `put_*` calls in
`routes_ingest.py`, so the route either succeeds against a configured S3-API
backend or 500s. Therefore one of the following is true in production today:

1. The keys **are** set on Railway → an object-storage provider is already an
   active subprocessor and must appear in the DPA / Trust Center, or
2. The keys are **not** set → URL/file ingest is silently broken in production.

Data shapes that route through this path: raw fetched regulation documents
(URL ingest), raw uploaded supplier/CSV files (file ingest), and normalized
JSON manifests. Adjacent data types **not** currently in object storage:
label images (handled by OpenAI vision inline, not persisted to S3), FDA
export archives (built in-memory, streamed to client), recall packets
(Postgres + email attachment), Sensitech CSVs (parsed inline, persisted as
canonical rows in Postgres).

This memo selects a path forward and unblocks the §4 Sub-Processors table in
`frontend/src/app/dpa/page.tsx` and the Infrastructure-and-subprocessors
section in `frontend/src/app/trust/page.tsx`.

## Options

### A. Adopt Vercel Blob as the production object store

Provision Vercel Blob via the Marketplace, point
`OBJECT_STORAGE_ENDPOINT_URL` / keys at the S3-compatible endpoint, add Vercel
Blob (Cloudflare R2 underneath, per Vercel docs) to the DPA table with
location "United States / Cloudflare R2." One-vendor billing relationship,
familiar Vercel surface, fastest provisioning.

- **Pros:** zero new vendor contract; consolidates onto Vercel which is
  already a subprocessor; provisioning is a single Marketplace click.
- **Cons:** Vercel Blob fronts Cloudflare R2 — the DPA needs to disclose
  **both** entities, and pricing is materially higher than R2 direct for
  egress-heavy or large-object workloads. Limits on object size and request
  rate are tighter than R2/S3.

### B. Adopt Cloudflare R2 directly

Open a Cloudflare account, provision an R2 bucket per environment, configure
the S3-compatible API endpoint and credentials. Add Cloudflare as a new
subprocessor.

- **Pros:** zero egress fees (material for FDA-export and label-image traffic
  later); native S3-compatible API — drop-in for existing `boto3` code; mature
  IAM and bucket-level policies; cheaper at scale than Vercel Blob or S3.
- **Cons:** new vendor onboarding (account, billing, DPA signature on
  Cloudflare's side); one more subprocessor row to disclose and notify
  customers about under the existing DPA's change-notice clause.

### C. Defer + document `s3_utils` as dev-only stub

Stop relying on object storage in production. Replace the live `put_bytes` /
`put_json` calls in `routes_ingest.py` with Postgres `bytea` persistence
(consistent with how recall packets and Sensitech CSVs are already stored),
and treat `s3_utils.py` as a local-dev/test helper backed by MinIO. No new
subprocessor row required.

- **Pros:** no new subprocessor disclosure; simpler ops surface; consistent
  with the target architecture direction in
  `memory/project_target_architecture.md` (replace Kafka/Neo4j/Redis with
  PostgreSQL — extending that thesis to object storage).
- **Cons:** requires code changes in `routes_ingest.py` and the NLP consumer;
  Postgres `bytea` is fine up to ~10 MB documents but degrades for large
  uploads (FDA archive bundles, multi-page label PDFs); pushes a real
  decision into the future the first time a customer uploads anything large.

## Recommendation

**Option B — Cloudflare R2, direct.** The S3-compatible API is a drop-in for
the existing `boto3` code, egress is free (the FDA-export and label-image
workloads will be egress-heavy), and adding one cleanly-scoped subprocessor
row to the DPA is cheaper than either re-architecting persistence (C) or
disclosing a two-layer Vercel-Blob-over-R2 relationship (A).

### Follow-on actions (post-approval)

1. Provision R2 buckets `regengine-ingest-raw-prod` and
   `regengine-ingest-processed-prod`; set the four `OBJECT_STORAGE_*` vars on
   the Railway `ingestion` and `nlp` services.
2. Add a `Cloudflare (R2)` row to `SUBPROCESSORS` in
   `frontend/src/app/dpa/page.tsx` (purpose: "Object storage for raw and
   normalized ingestion documents (S3-compatible API)"; location: "United
   States / global edge"; link: `https://www.cloudflare.com/privacypolicy/`).
2a. Mirror the row in the Infrastructure-and-subprocessors table on
    `frontend/src/app/trust/page.tsx`.
3. Send the customary subprocessor change notice per the DPA's notification
   clause.
4. Close #2311 once the rows ship to production.
