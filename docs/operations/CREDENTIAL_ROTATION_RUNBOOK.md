# Credential Rotation Runbook

## Background

Production credentials were committed to `.env.production` in the initial repository commit (`a130816`) and removed in `ff0b721`. While the file is no longer tracked, **the credentials remain in git history** and must be rotated.

## Exposed Credentials

| Secret | Environment Variable | Service |
|--------|---------------------|---------|
| Admin master key | `ADMIN_MASTER_KEY` | Railway (admin-api, ingestion-service) |
| JWT signing key | `AUTH_SECRET_KEY` | Railway + Vercel (all services + middleware) |
| Redis password | `REDIS_PASSWORD` | Railway (Redis instance) |
| Database password | `DATABASE_URL` (embedded) | Railway (Postgres), Supabase |

## Rotation Steps

### 1. Generate New Secrets

```bash
# Admin master key (64-char hex)
openssl rand -hex 32

# Auth/JWT signing key (base64, 32 bytes)
openssl rand -base64 32

# Redis password (alphanumeric, 32 chars)
openssl rand -base64 32 | tr -d '/+=' | head -c 32
```

### 2. Update Railway

1. Go to [Railway Dashboard](https://railway.app/dashboard)
2. For each service (admin-api, ingestion-service, graph-service, compliance-service):
   - Click service → Variables
   - Update `ADMIN_MASTER_KEY` with new value
   - Update `AUTH_SECRET_KEY` with new value
3. For the Redis instance:
   - Update `REDIS_PASSWORD`
   - Update `REDIS_URL` in all services that reference it
4. Redeploy all services

### 3. Update Vercel

1. Go to [Vercel Dashboard](https://vercel.com) → RegEngine → Settings → Environment Variables
2. Update `AUTH_SECRET_KEY` (used by Next.js middleware for JWT verification)
3. Update `ADMIN_MASTER_KEY` (used by API proxy routes)
4. Redeploy

### 4. Verify

- [ ] All services start without auth errors
- [ ] Login flow works end-to-end
- [ ] API proxy routes return 200 (not 401/403)
- [ ] Redis sessions are functional (new sessions only — old sessions will expire)

## Git History Scrub (Optional but Recommended)

After rotating all credentials, scrub the old values from git history:

```bash
# Install BFG Repo-Cleaner
brew install bfg

# Clone a fresh mirror
git clone --mirror https://github.com/regengine/RegEngine.git regengine-mirror
cd regengine-mirror

# Create a file with the secrets to remove (one per line)
cat > secrets.txt << 'EOF'
327972511adf1e4c80e9bcc4470999b3d355dfcd429f296860a6bd8ac94f64a0
uRqNfvHa7bgIcFkyxpOWZWFWzn5WMz6E8J4PqQBggrI=
oWetq/v3HGtSUNsc7rlhNYNFttL9+YCf
EOF

# Run BFG to replace secrets with ***REMOVED***
bfg --replace-text secrets.txt

# Clean up and force push
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force

# Delete the secrets file
rm secrets.txt
```

**Warning:** Force-pushing rewrites history. All contributors must re-clone after this operation.

## Prevention

- `.env.production` is now in `.gitignore`
- Pre-commit hooks with `detect-secrets` are configured (see `.pre-commit-config.yaml`)
- Never commit files matching `.env.*` patterns except `.env.example`
