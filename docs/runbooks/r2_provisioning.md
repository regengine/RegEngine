# Cloudflare R2 provisioning runbook

> Historical provisioning instructions: current configuration, route availability,
> disclosure, and deployment status have not been reverified. Check the target
> environment and current release procedures before acting.

This historical procedure addressed `/v1/ingest/{url,file,direct,regulation}`
endpoints reported as returning 503 in #2348 when `OBJECT_STORAGE_*` variables
were unset. It recorded that the `/api/v1/webhooks/ingest` quickstart path
ingests events directly without document storage; verify current route and
deployment behavior separately.

## Prereqs

- Cloudflare account with R2 enabled (one-time, requires billing on file)
- Railway CLI authenticated to `RegEngine-Prod`
- DPA / Trust subprocessor disclosure: the earlier record stated disclosure landed ahead of provisioning (see [trust page](../../frontend/src/app/trust/page.tsx), [DPA page](../../frontend/src/app/dpa/page.tsx)). Reconfirm current disclosures and notice obligations before provisioning.

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

The historical procedure expected environment changes to trigger a Railway
redeploy. Verify the target environment and its current release behavior before
changing variables or interpreting deployment logs.

## Step 3 — Verify

```bash
# Confirm vars are set (values masked)
railway variables --json | python3 -c "import json,sys,re; v=json.load(sys.stdin); p=re.compile(r'OBJECT_STORAGE',re.I); print({k: '***SET***' if v[k] else '<empty>' for k in v if p.search(k)})"

# Hit the live endpoints (the smoke script defaults to localhost, so the
# production base must be set explicitly, with --allow-production)
REGENGINE_API_BASE=https://regengine.co/api/ingestion REGENGINE_API_KEY=rge_live_... ./scripts/smoke_test_ingest.sh --allow-production
```

The historical expectation was that the tested ingest endpoints would return
200 rather than 503. Verify the currently enabled route set, target environment,
response bodies, and behavior before interpreting a result as successful
provisioning. The script also exits 0 when all probes return 503, so its exit
code alone does not establish that R2 is provisioned. Without
`REGENGINE_API_BASE`, the script defaults to localhost. For a non-loopback
target it requires `--allow-production` or `REGENGINE_ALLOW_PRODUCTION=1`;
otherwise it exits without probing.

## Step 4 — Lifespan probe

On startup, [s3_utils.is_object_storage_configured](../../services/ingestion/app/s3_utils.py) is logged by
the FastAPI lifespan. Look for the `object_storage_not_configured` warning
to disappear from logs after redeploy.

## Rollback

The historical procedure removed credentials to restore a 503 gate. Do not
assume the current route set or deployed configuration behaves the same way;
verify the rollback plan and expected effects before changing credentials.
The old commands were:

```bash
railway variables remove OBJECT_STORAGE_ACCESS_KEY_ID
railway variables remove OBJECT_STORAGE_SECRET_ACCESS_KEY
```

The earlier record expected a 503 response after credential removal (#2348);
this is not a verified guarantee for the current deployment.

## Cost guard

R2 has no egress fees but charges per Class A/B operation and storage.
For pilot scale (≤ 100 documents/day, ≤ 10 GB total), expect <$1/month.
Set a Cloudflare billing alert at $50/month as a safety net.
