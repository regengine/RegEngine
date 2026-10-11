# Cloudflare R2 provisioning runbook

Unblocks the `/v1/ingest/{url,file,direct,regulation}` endpoints (currently
returning 503 per #2348 because `OBJECT_STORAGE_*` env vars are unset).
The `/api/v1/webhooks/ingest` quickstart path does NOT depend on R2 — it
ingests events directly without document storage.

## Prereqs

- Cloudflare account with R2 enabled (one-time, requires billing on file)
- Railway CLI authenticated to `RegEngine-Prod`
- DPA / Trust subprocessor disclosure: **already current** ([trust/page.tsx:415](frontend/src/app/trust/page.tsx#L415), [dpa/page.tsx:115](frontend/src/app/dpa/page.tsx#L115)). No customer-notice clock to manage — disclosure landed ahead of provisioning per PR sequence in `project_session_2026_05_13.md`.

## Step 1 — Cloudflare console

1. Cloudflare dashboard → R2 → Create bucket.
   - Name: `regengine-ingest-raw` (matches `s3_utils.RAW_INGEST_BUCKET`)
   - Location: Automatic (R2 picks)
   - No public access (default)
2. R2 → Manage R2 API Tokens → Create API Token.
   - Permissions: **Object Read & Write**
   - Specify bucket: `regengine-ingest-raw`
   - TTL: no expiration (rotate manually)
3. Copy the four values shown ONCE:
   - Access Key ID
   - Secret Access Key
   - Endpoint (looks like `https://<account-id>.r2.cloudflarestorage.com`)
   - Account ID (used to construct the endpoint if not shown directly)

## Step 2 — Set Railway env vars

```bash
railway link --project RegEngine-Prod --environment production
railway service RegEngine

# Set all four — Railway prompts before applying
railway variables set OBJECT_STORAGE_ENDPOINT_URL="https://<account-id>.r2.cloudflarestorage.com"
railway variables set OBJECT_STORAGE_REGION="auto"
railway variables set OBJECT_STORAGE_ACCESS_KEY_ID="<from step 1>"
railway variables set OBJECT_STORAGE_SECRET_ACCESS_KEY="<from step 1>"
```

Railway auto-redeploys after env changes. Watch the deploy with
`railway logs --follow`.

## Step 3 — Verify

```bash
# Confirm vars are set (values masked)
railway variables --json | python3 -c "import json,sys,re; v=json.load(sys.stdin); p=re.compile(r'OBJECT_STORAGE',re.I); print({k: '***SET***' if v[k] else '<empty>' for k in v if p.search(k)})"

# Hit the live endpoints (the smoke script defaults to localhost, so the
# production base must be set explicitly, with --allow-production)
REGENGINE_API_BASE=https://regengine.co/api/ingestion REGENGINE_API_KEY=rge_live_... ./scripts/smoke_test_ingest.sh --allow-production
```

Expected: all `/v1/ingest/*` endpoints return 200 (not 503). The smoke
test script already encodes this — exit 0 means provisioning succeeded.
A localhost pass does not count for this step: without REGENGINE_API_BASE
and --allow-production the script probes the operator laptop, not Railway.

## Step 4 — Lifespan probe

On startup, [s3_utils.is_object_storage_configured](services/ingestion/app/s3_utils.py#L40) is logged by
the FastAPI lifespan. Look for the `object_storage_not_configured` warning
to disappear from logs after redeploy.

## Rollback

If R2 misbehaves and you need to revert to the 503 gate:

```bash
railway variables remove OBJECT_STORAGE_ACCESS_KEY_ID
railway variables remove OBJECT_STORAGE_SECRET_ACCESS_KEY
```

The endpoints return 503 (not 500) automatically — no code rollback
needed. See #2348.

## Cost guard

R2 has no egress fees but charges per Class A/B operation and storage.
For pilot scale (≤ 100 documents/day, ≤ 10 GB total), expect <$1/month.
Set a Cloudflare billing alert at $50/month as a safety net.
