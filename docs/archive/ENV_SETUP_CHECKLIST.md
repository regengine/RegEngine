# RegEngine Env Setup Checklist (Beginner-Friendly)

This is a practical setup guide for someone doing this for the first time.

It includes:
- a step-by-step setup flow,
- where each value comes from,
- direct links to the dashboards/docs you need,
- and a maximum key inventory from this repo.

---

## 1) Open These Links First

- Vercel environment variables: https://vercel.com/docs/projects/environment-variables
- Railway variables: https://docs.railway.com/guides/variables
- Railway Postgres: https://docs.railway.com/plugins/postgresql
- Railway Redis: https://docs.railway.com/plugins/redis
- Supabase API keys: https://supabase.com/docs/guides/api/api-keys
- Neo4j connection settings: https://neo4j.com/docs/operations-manual/current/configuration/connectors/
- OpenSSL random secret generation: https://www.openssl.org/docs/manmaster/man1/openssl-rand.html

Current production topology reference in this repo:
- `README.md` (Vercel + Railway)
- `docs/FSMA_RAILWAY_DEPLOYMENT.md`
- `docs/PRODUCTION_DEPLOYMENT.md`

---

## 2) Quick Primer (What You Are Setting)

- **Environment variable**: a `KEY=value` setting your app reads at runtime.
- **Public frontend vars**: start with `NEXT_PUBLIC_`; these are visible in the browser.
- **Server secrets**: never start with `NEXT_PUBLIC_`; set only on backend services.
- **Different environments**: set values separately for dev, preview/staging, and production.

---

## 3) Generate Strong Secrets

Run on your machine and save outputs in a password manager.

```bash
# 256-bit hex key (great for ADMIN_MASTER_KEY / SERVICE_AUTH_SECRET)
openssl rand -hex 32

# Strong random password
openssl rand -base64 24

# Optional: UUID salt
python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
```

---

## 4) P0 Checklist (Must Have for Login + Billing + Bulk Upload)

Use this first. Without these, auth and onboarding flows break.

### 4.1 Vercel (frontend)

Set in Vercel Project -> Settings -> Environment Variables:

- [ ] `NEXT_PUBLIC_ADMIN_URL` -> your public Railway admin API URL (for proxy target)
- [ ] `NEXT_PUBLIC_API_BASE_URL` -> optional gateway base URL if used
- [ ] `REGENGINE_DEPLOY_MODE=production`
- [ ] `NEXT_PUBLIC_OUTPUT_MODE` -> set only if you intentionally run static export mode

Notes:
- In this repo, web admin calls use `/api/admin` proxy and then forward to upstream.
- If upstream URL is missing or private-only, login and bulk upload can fail.

### 4.2 Railway `admin-service`

Set in Railway service Variables:

- [ ] `ADMIN_DATABASE_URL` (or `DATABASE_URL`, depending on service config)
- [ ] `REDIS_URL`
- [ ] `AUTH_SECRET_KEY`
- [ ] `ADMIN_MASTER_KEY`
- [ ] `SERVICE_AUTH_SECRET`
- [ ] `CORS_ORIGINS` (include your Vercel domain)
- [ ] `CORS_ALLOW_CREDENTIALS=true`

Where values come from:
- `ADMIN_DATABASE_URL` / `DATABASE_URL`: Railway Postgres -> Connect -> connection string
- `REDIS_URL`: Railway Redis -> Connect -> connection string
- secrets (`AUTH_SECRET_KEY`, `ADMIN_MASTER_KEY`, `SERVICE_AUTH_SECRET`): generated with `openssl rand`

### 4.3 Railway stateful services

- [ ] Postgres is running and reachable
- [ ] Redis is running and reachable
- [ ] Neo4j is running and reachable

### 4.4 Minimum auth sanity checks

- [ ] `POST /api/admin/auth/login` returns 200 for valid user
- [ ] `GET /api/admin/auth/me` returns 200 with bearer token
- [ ] `GET /api/admin/v1/supplier/bulk-upload/template?format=csv` returns file download

### 4.5 Billing + transactional email (P0 for paid onboarding)

Set in Railway service Variables:

- [ ] `RESEND_API_KEY` (admin-service)
- [ ] `RESEND_FROM_EMAIL` (admin-service, e.g. `onboarding@regengine.co`)
- [ ] `INVITE_BASE_URL` (admin-service, e.g. `https://regengine.co`)
- [ ] `STRIPE_SECRET_KEY` (ingestion-service)
- [ ] `STRIPE_WEBHOOK_SECRET` (ingestion-service)
- [ ] `STRIPE_PRICE_GROWTH_MONTHLY` (ingestion-service)
- [ ] `STRIPE_PRICE_GROWTH_ANNUAL` (ingestion-service)
- [ ] `STRIPE_PRICE_SCALE_MONTHLY` (ingestion-service)
- [ ] `STRIPE_PRICE_SCALE_ANNUAL` (ingestion-service)
- [ ] `ADMIN_SERVICE_URL` (ingestion-service URL used by Stripe webhook provisioning)

---

## 5) P1 Checklist (Strongly Recommended for Production)

- [ ] Observability: `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN`, `LOG_LEVEL`, `LOG_FORMAT`
- [ ] OTEL traces: `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACE_SAMPLING_RATE`
- [ ] Security headers: `SECURITY_HSTS_*`, `SECURITY_CSP_*`, `SECURITY_REFERRER_POLICY`, `SECURITY_FRAME_OPTIONS`
- [ ] Privacy/integrity: `PII_HASH_SALT`, `AUDIT_INTEGRITY_KEY`
- [ ] Rate limiting/isolation: `RATE_LIMIT_STORAGE_URI`, `TENANT_RATE_LIMIT_RPM`, `REQUIRE_TENANT_ID`

---

## 6) P2 Optional Feature Keys

Set only if you use these features:

- AI providers: `OPENAI_API_KEY`, `GROQ_API_KEY`, `OLLAMA_HOST`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`
- Product analytics: `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_POSTHOG_HOST`, `NEXT_PUBLIC_VERCEL_ANALYTICS_ID`
- Supabase integration: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- Billing/webhooks: `NEXT_PUBLIC_BILLING_API_URL`
- Notifications/integrations: `SLACK_WEBHOOK_URL`, `TEAMS_WEBHOOK_URL`, `FDA_API_KEY`

---

## 7) Keys You Should Keep Unset in Production

- [ ] `AUTH_TEST_BYPASS_TOKEN`
- [ ] `FORGED_JWT_SECRET`
- [ ] `NEXT_PUBLIC_USE_MOCK`
- [ ] `REGENGINE_USE_MOCK_LLM` (unless intentionally mocking)
- [ ] `TEST_*` variables

---

## 8) Beginner Step-by-Step Setup Flow

1. **Create a secrets vault first**
   - Use 1Password, Bitwarden, or AWS Secrets Manager.
   - Never keep production secrets in plain text notes.

2. **Fill backend keys in Railway first**
   - Start with `admin-service` P0 keys.
   - Confirm service redeploys cleanly.

3. **Fill frontend keys in Vercel**
   - Add `NEXT_PUBLIC_ADMIN_URL` (and optionally `NEXT_PUBLIC_API_BASE_URL`).
   - Redeploy frontend.

4. **Verify auth chain**
   - Login page works.
   - `/api/admin/auth/me` works with bearer token.

5. **Verify bulk upload chain**
   - Download template.
   - Upload CSV/XLSX.
   - Parse/validate/commit flow completes.

6. **Only then add optional integrations**
   - AI, analytics, billing, CRM, etc.

---

## 9) Fill-In Worksheet (Copy/Paste)

Use this quick worksheet while setting values:

- [ ] `NEXT_PUBLIC_ADMIN_URL =`
- [ ] `NEXT_PUBLIC_API_BASE_URL =`
- [ ] `REGENGINE_DEPLOY_MODE =`
- [ ] `ADMIN_DATABASE_URL =`
- [ ] `DATABASE_URL =`
- [ ] `REDIS_URL =`
- [ ] `NEO4J_URI =`
- [ ] `NEO4J_USER =`
- [ ] `NEO4J_PASSWORD =`
- [ ] `AUTH_SECRET_KEY =`
- [ ] `ADMIN_MASTER_KEY =`
- [ ] `SERVICE_AUTH_SECRET =`
- [ ] `CORS_ORIGINS =`
- [ ] `CORS_ALLOW_CREDENTIALS =`
- [ ] `PII_HASH_SALT =`
- [ ] `SENTRY_DSN =`
- [ ] `NEXT_PUBLIC_SENTRY_DSN =`
- [ ] `RESEND_API_KEY =`
- [ ] `RESEND_FROM_EMAIL =`
- [ ] `INVITE_BASE_URL =`
- [ ] `STRIPE_SECRET_KEY =`
- [ ] `STRIPE_WEBHOOK_SECRET =`
- [ ] `STRIPE_PRICE_GROWTH_MONTHLY =`
- [ ] `STRIPE_PRICE_GROWTH_ANNUAL =`
- [ ] `STRIPE_PRICE_SCALE_MONTHLY =`
- [ ] `STRIPE_PRICE_SCALE_ANNUAL =`
- [ ] `ADMIN_SERVICE_URL =`

---

## 10) Maximum Key Inventory (Repo-Wide)

This is the broad inventory (runtime + template + test/dev references) grouped by category.

### Frontend/Public Keys (30)

`NEXT_PUBLIC_ADMIN_API_KEY`, `NEXT_PUBLIC_ADMIN_URL`, `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_API_KEY`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_BILLING_API_URL`, `NEXT_PUBLIC_COMPLIANCE_URL`, `NEXT_PUBLIC_ENABLE_QA_LOGIN_PRESETS`, `NEXT_PUBLIC_ENERGY_API_URL`, `NEXT_PUBLIC_GRAPH_API_URL`, `NEXT_PUBLIC_GRAPH_URL`, `NEXT_PUBLIC_INGESTION_URL`, `NEXT_PUBLIC_OPPORTUNITY_URL`, `NEXT_PUBLIC_OUTPUT_MODE`, `NEXT_PUBLIC_POSTHOG_HOST`, `NEXT_PUBLIC_POSTHOG_KEY`, `NEXT_PUBLIC_SENTRY_DSN`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_USE_MOCK`, `NEXT_PUBLIC_VERCEL_ANALYTICS_ID`, `NEXT_PUBLIC_VERCEL_ENV`, `NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA`, `NEXT_RUNTIME`, `NODE_ENV`, `REGENGINE_DEPLOY_MODE`, `VERCEL`, `VERCEL_ENV`, `VERCEL_GIT_COMMIT_SHA`, `VERCEL_URL`

### Auth/Security Keys (23)

`ADMIN_MASTER_KEY`, `AUDIT_INTEGRITY_KEY`, `AUTH_SECRET_KEY`, `JWT_AUDIENCE`, `JWT_ISSUER`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_SECRET`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `OAUTH_ISSUER`, `OAUTH_REDIRECT_URI`, `PASSWORD_MAX_LENGTH`, `PASSWORD_MIN_LENGTH`, `PASSWORD_REQUIRE_DIGIT`, `PASSWORD_REQUIRE_LOWERCASE`, `PASSWORD_REQUIRE_SPECIAL`, `PASSWORD_REQUIRE_UPPERCASE`, `PII_HASH_SALT`, `SERVICE_AUTH_SECRET`, `SESSION_IDLE_TIMEOUT_MINUTES`, `SESSION_SECRET`, `STRIPE_WEBHOOK_SECRET`

### Datastores (19)

`ADMIN_DATABASE_URL`, `COMPLIANCE_DATABASE_URL`, `DATABASE_URL`, `ENTERTAINMENT_DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_HOST`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`, `POSTGRES_URL`, `POSTGRES_USER`, `REDIS_URL`, `SQL_ECHO`, `SUPABASE_DB`, `SUPABASE_HOST`, `SUPABASE_PASSWORD`, `SUPABASE_PORT`, `SUPABASE_SERVICE_KEY`, `SUPABASE_URL`, `SUPABASE_USER`

### Graph/Kafka (21)

`GRAPH_API_URL`, `GRAPH_INTERNAL_API_KEY`, `GRAPH_SERVICE_URL`, `GRAPH_URL`, `KAFKA_BOOTSTRAP_SERVERS`, `KAFKA_BROKER`, `KAFKA_PASSWORD`, `KAFKA_SECURITY_PROTOCOL`, `KAFKA_TOPIC_GRAPH_UPDATE`, `KAFKA_TOPIC_NORMALIZED`, `KAFKA_USERNAME`, `NEO4J_CONSTRAINTS_FILE`, `NEO4J_DATABASE`, `NEO4J_PASSWORD`, `NEO4J_SYNC_BLOCK_TIMEOUT_SEC`, `NEO4J_SYNC_QUEUE`, `NEO4J_URI`, `NEO4J_URL`, `NEO4J_USER`, `SCHEMA_REGISTRY_URL`, `TRACEABILITY_DOMAIN`

### Object Storage (11)

`MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `OBJECT_STORAGE_ACCESS_KEY_ID`, `OBJECT_STORAGE_ENDPOINT_URL`, `OBJECT_STORAGE_EXPECTED_BUCKET_OWNER`, `OBJECT_STORAGE_REGION`, `OBJECT_STORAGE_SECRET_ACCESS_KEY`, `PRESIGN_EXPIRES`, `PROCESSED_DATA_BUCKET`, `RAW_INGEST_BUCKET`, `S3_BUCKET_PREFIX`

### AI/ML (11)

`GOOGLE_CLOUD_LOCATION`, `GOOGLE_CLOUD_PROJECT`, `GROQ_API_KEY`, `HF_HOME`, `LLM_MAX_RETRIES`, `LLM_MODEL`, `LLM_TIMEOUT_S`, `OLLAMA_HOST`, `OPENAI_API_KEY`, `OPENAI_USE_RESPONSES_API`, `REGENGINE_USE_MOCK_LLM`

### Observability (16)

`APP_ENV`, `ENV`, `ENVIRONMENT`, `HOSTNAME`, `K8S_CONTAINER_NAME`, `K8S_NAMESPACE`, `K8S_POD_NAME`, `LOG_ALL_SAMPLED_OUT`, `LOG_FORMAT`, `LOG_LEVEL`, `LOG_MAX_FILE`, `LOG_MAX_SIZE`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_TRACE_SAMPLING_RATE`, `SENTRY_DSN`, `SERVICE_VERSION`

### Runtime Controls (14)

`CORS_ALLOW_CREDENTIALS`, `CORS_ORIGINS`, `DB_BULKHEAD_LIMIT`, `RATE_LIMIT_STORAGE_URI`, `REQUIRE_TENANT_ID`, `SECURITY_CSP_ENABLED`, `SECURITY_CSP_POLICY`, `SECURITY_FRAME_OPTIONS`, `SECURITY_HSTS_ENABLED`, `SECURITY_HSTS_INCLUDE_SUBDOMAINS`, `SECURITY_HSTS_MAX_AGE`, `SECURITY_HSTS_PRELOAD`, `SECURITY_REFERRER_POLICY`, `TENANT_RATE_LIMIT_RPM`

### Feature Flags (7)

`ENABLE_CRM_INTEGRATION`, `ENABLE_DB_API_KEYS`, `ENABLE_EMAIL_CAMPAIGNS`, `ENABLE_INFRASTRUCTURE_DEPLOYMENT`, `ENABLE_LINKEDIN_AUTOMATION`, `ENABLE_REVIEW_CONSUMER`, `ENABLE_SLACK_NOTIFICATIONS`

### Service URLs and Integration URLs (24)

`ADMIN_API_URL`, `ADMIN_SERVICE_URL`, `ADMIN_URL`, `API_BASE_URL`, `API_DOCS_URL`, `COMPLIANCE_SERVICE_URL`, `COMPLIANCE_URL`, `HALLUCINATION_WEBHOOK_URL`, `HUBSPOT_API_BASE_URL`, `INGESTION_API_URL`, `INGESTION_BASE`, `INGESTION_SERVICE_URL`, `INGESTION_URL`, `INGEST_SERVICE_URL`, `MARKETING_SITE_URL`, `NLP_URL`, `REGENGINE_BASE_URL`, `REGENGINE_DEMO_URL`, `REGENGINE_PRODUCTION_URL`, `REGENGINE_SANDBOX_URL`, `SALESFORCE_INSTANCE_URL`, `SLACK_WEBHOOK_URL`, `STATUS_PAGE_URL`, `TEAMS_WEBHOOK_URL`

### Test/Dev Keys (13)

`AUTH_TEST_BYPASS_TOKEN`, `DOCKER_RUNNING`, `FORGED_JWT_SECRET`, `GITHUB_ACTIONS`, `TEST_ADMIN_URL`, `TEST_DB_URL`, `TEST_GRAPH_URL`, `TEST_TENANT_A_EMAIL`, `TEST_TENANT_A_PASSWORD`, `TEST_TENANT_B_EMAIL`, `TEST_TENANT_B_PASSWORD`, `TEST_USER_EMAIL`, `TEST_USER_PASSWORD`

### Misc/Operational Keys (54)

`ACCESS_TOKEN_EXPIRE_MINUTES`, `ADMIN_FALLBACK_SQLITE`, `API_DOCS_DEPLOY_COMMAND`, `API_KEY`, `APP_HOME`, `CALCOM_LINK`, `CALENDLY_API_KEY`, `CALENDLY_LINK`, `CHAOS_CANARY_UUID`, `CHAOS_SEED_MANIFEST`, `CONSUMER_STALE_THRESHOLD_SECONDS`, `CRM_API_TOKEN`, `CRM_PROVIDER`, `DATADOG_API_KEY`, `DATADOG_APP_KEY`, `DESIGN_PARTNER_DURATION_WEEKS`, `DESIGN_PARTNER_MAX_DOCS`, `DESIGN_PARTNER_MAX_PARTNERS`, `DESIGN_PARTNER_RATE_LIMIT_RPM`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, `EMAIL_PROVIDER`, `EMAIL_PROVIDER_API_KEY`, `FDA_API_KEY`, `GA4_MEASUREMENT_ID`, `GA_TRACKING_ID`, `GITHUB_REPO`, `GITHUB_TOKEN`, `HEALTH_FILE`, `INGESTION_API_KEY`, `INTERNAL_API_KEY`, `LINKEDIN_AUTOMATION_PROVIDER`, `LINKEDIN_AUTOMATION_TOKEN`, `MAILCHIMP_LIST_ID`, `MARKETING_SITE_DEPLOY_COMMAND`, `PHASE2B_API_SECRET`, `PROJECT_ROOT`, `REFRESH_TOKEN_EXPIRE_DAYS`, `REGENGINE_ADMIN_MASTER_KEY`, `REGENGINE_API_KEY`, `REGENGINE_CI_AUTO_FIX`, `REGENGINE_DB_PASSWORD`, `REGENGINE_ENV`, `REGENGINE_OUTPUT_DIR`, `REGENGINE_SERVICES_DIR`, `REGENGINE_SKIP_SECRET_CHECK`, `REGENGINE_TENANT_ID`, `REGENGINE_VERTICALS_DIR`, `REGULATORY_DISCOVERY_INTERVAL`, `REGULATORY_POLITE_DELAY`, `SCHEMA_DIR`, `SECRETS_ENCRYPTION_KEY`, `SES_REGION`, `VERSION`, `X_REGENGINE_API_KEY`

---

## 11) Final Validation Checklist

- [ ] I can log in from production UI.
- [ ] Bulk upload template download works.
- [ ] Bulk upload parse/validate works with CSV/XLSX.
- [ ] No test bypass keys are set in production.
- [ ] Secrets are in a secret manager (not plain text docs).
- [ ] All critical keys have owners and rotation reminders.
