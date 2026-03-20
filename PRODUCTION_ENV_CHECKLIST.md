# Production Environment Variables Checklist

**Generated:** 2026-03-20  
**Scope:** All RegEngine services (ingestion, admin, compliance, graph, nlp, scheduler, shared)

---

## Overview

This document lists all environment variables required, recommended, and optional for production deployment. Sourced from grep across services/ for `os.getenv()` and `os.environ` calls.

**Summary:**
- **Required:** 28 variables (service won't start without them)
- **Security:** 12 variables (must be set for production)
- **Optional:** 127 variables (have safe defaults or fallbacks)

---

## REQUIRED (Service Won't Start)

These must be set or services will fail at startup.

| Variable | Service | Purpose | Example |
|----------|---------|---------|---------|
| DATABASE_URL | All | Primary PostgreSQL connection | postgresql://user:pass@host:5432/regengine |
| REDIS_URL | Ingestion, Scheduler | Cache & rate limiting | redis://localhost:6379 |
| ENV or ENVIRONMENT | All | Deployment stage | production |
| KAFKA_BOOTSTRAP_SERVERS | Ingestion, Scheduler | Event streaming | broker1:9092,broker2:9092 |
| SUPABASE_URL | Auth, Admin | OAuth provider | https://project.supabase.co |
| SUPABASE_SERVICE_KEY | Auth, Admin | Service role key | eyJhbGc... |
| JWT_SECRET | Auth | Session signing | (32+ char random string) |
| JWT_PRIVATE_KEY | Auth | Token signing | (RSA private key PEM) |
| JWT_PUBLIC_KEY | Auth | Token verification | (RSA public key PEM) |
| OPENAI_API_KEY | NLP | LLM inference | sk-... |
| OBJECT_STORAGE_ENDPOINT_URL | Ingestion | S3/MinIO endpoint | https://s3.region.amazonaws.com |
| OBJECT_STORAGE_ACCESS_KEY_ID | Ingestion | S3 access key | AKIA... |
| OBJECT_STORAGE_SECRET_ACCESS_KEY | Ingestion | S3 secret | (aws secret) |
| OBJECT_STORAGE_REGION | Ingestion | AWS region | us-east-1 |
| RAW_INGEST_BUCKET | Ingestion | Document upload bucket | regengine-uploads |
| ADMIN_DATABASE_URL | Admin | Admin-specific DB | postgresql://admin:pass@host/admin |
| COMPLIANCE_DATABASE_URL | Compliance | Compliance service DB | postgresql://comp:pass@host/compliance |
| STRIPE_SECRET_KEY | Ingestion | Billing provider | sk_live_... |
| RESEND_API_KEY | Admin | Email provider | re_... |
| LOG_LEVEL | All | Logging verbosity | INFO |
| SERVICE_NAME | All | Service identifier | ingestion-service |

---

## SECURITY (Must Be Set in Production)

These control authentication, encryption, and sensitive operations.

| Variable | Service | Purpose | Production Notes |
|----------|---------|---------|------------------|
| AUTH_SECRET_KEY | Admin | Auth session encryption | Must be unique, 32+ chars |
| AUDIT_INTEGRITY_KEY | Ingestion | Audit log HMAC | Rotate quarterly |
| PII_HASH_SALT | All | PII anonymization | Never share or log |
| ADMIN_MASTER_KEY | Admin | Master authentication | Rotate monthly, store in vault |
| PARTNER_AUTH_SECRET | Ingestion | Partner API auth | Rotate on each deployment |
| SERVICE_AUTH_SECRET | Shared | Inter-service auth | Must match across services |
| REGENGINE_INTERNAL_SECRET | Admin | Internal API key | Used for health checks |
| JWT_ISSUER | Auth | Token issuer claim | Must match token validation |
| JWT_AUDIENCE | Auth | Token audience claim | Must match token validation |
| STRIPE_WEBHOOK_SECRET | Ingestion | Webhook validation | Retrieve from Stripe dashboard |
| MINIO_ACCESS_KEY | Ingestion (if using MinIO) | Object storage access | Separate from AWS keys |
| MINIO_SECRET_KEY | Ingestion (if using MinIO) | Object storage secret | Separate from AWS keys |

**Security Best Practices:**
- Store all keys in AWS Secrets Manager or HashiCorp Vault
- Rotate JWT keys quarterly
- Enable AWS KMS encryption for stored secrets
- Use separate API keys for production vs staging
- Never commit secrets to version control
- Audit access logs for secret retrieval

---

## OPTIONAL (Have Safe Defaults or Fallbacks)

These improve functionality but services will still start without them.

| Variable | Default | Purpose |
|----------|---------|---------|
| DB_POOL_SIZE | 20 | Connection pool size |
| DB_MAX_OVERFLOW | 10 | Additional connections if needed |
| DB_POOL_RECYCLE | 3600 | Recycle connections after (seconds) |
| DB_BULKHEAD_LIMIT | 5 | Max concurrent queries per tenant |
| ACCESS_TOKEN_EXPIRE_MINUTES | 60 | JWT token lifetime |
| REFRESH_TOKEN_EXPIRE_DAYS | 7 | Refresh token lifetime |
| SESSION_IDLE_TIMEOUT_MINUTES | 30 | Session timeout |
| SESSION_SECRET | (auto-generated) | Session cookie signing |
| PASSWORD_MIN_LENGTH | 8 | Minimum password length |
| PASSWORD_MAX_LENGTH | 128 | Maximum password length |
| PASSWORD_REQUIRE_UPPERCASE | true | Require A-Z |
| PASSWORD_REQUIRE_LOWERCASE | true | Require a-z |
| PASSWORD_REQUIRE_DIGIT | true | Require 0-9 |
| PASSWORD_REQUIRE_SPECIAL | true | Require !@#$%^&* |
| TENANT_RATE_LIMIT_RPM | 100 | Requests per minute per tenant |
| WEBHOOK_INGEST_RATE_LIMIT_RPM | 1000 | Webhook ingestion rate limit |
| INGESTION_RBAC_RATE_LIMIT_DEFAULT_RPM | 100 | Default rate limit |
| LLM_MODEL | gpt-4-turbo | Language model to use |
| LLM_TIMEOUT_S | 30 | LLM inference timeout |
| LLM_MAX_RETRIES | 3 | Retry failed LLM calls |
| LOG_MAX_SIZE | 10485760 | Log file size (10MB) |
| LOG_MAX_FILE | 10 | Max log file count |
| OTEL_TRACE_SAMPLING_RATE | 0.1 | OpenTelemetry sampling |
| PRESIGN_EXPIRES | 3600 | S3 presigned URL lifetime (seconds) |
| CONSUMER_STALE_THRESHOLD_SECONDS | 300 | Kafka consumer lag threshold |
| ALLOW_EPCIS_IN_MEMORY_FALLBACK | true | Use memory if DB unavailable |
| ALLOW_EXCHANGE_IN_MEMORY_FALLBACK | true | Use memory if DB unavailable |
| REQUIRE_TENANT_ID | true | Enforce tenant isolation |
| SQL_ECHO | false | Log all SQL queries (debug only) |
| DISABLED_ROUTERS | "" | Comma-separated routers to skip |
| GOOGLE_CLOUD_PROJECT | (none) | GCP project (if using GCP services) |
| GOOGLE_CLOUD_LOCATION | us-central1 | GCP region |
| OLLAMA_HOST | http://localhost:11434 | Local LLM fallback (offline mode) |
| OTEL_EXPORTER_OTLP_ENDPOINT | http://localhost:4317 | Observability backend |
| SECURITY_HSTS_ENABLED | true | HTTP Strict Transport Security |
| SECURITY_HSTS_MAX_AGE | 31536000 | HSTS cache duration (1 year) |
| SECURITY_HSTS_INCLUDE_SUBDOMAINS | true | Apply HSTS to subdomains |
| SECURITY_HSTS_PRELOAD | true | Enable HSTS preload |
| SECURITY_CSP_ENABLED | true | Content Security Policy |
| SECURITY_FRAME_OPTIONS | SAMEORIGIN | X-Frame-Options header |
| SECURITY_REFERRER_POLICY | strict-origin-when-cross-origin | Referrer-Policy |
| EDI_REQUIRE_PARTNER_ID | true | Require EDI partner validation |
| ALLOW_EXCHANGE_IN_MEMORY_FALLBACK | true | EPCIS in-memory fallback |

---

## Verification Commands

Run these before and after deployment to verify all required variables are set:

### Check Required Variables

```bash
#!/bin/bash
# Verify all required variables are set
REQUIRED=(
  "DATABASE_URL" "REDIS_URL" "ENV" "KAFKA_BOOTSTRAP_SERVERS"
  "SUPABASE_URL" "SUPABASE_SERVICE_KEY" "JWT_SECRET" 
  "JWT_PRIVATE_KEY" "JWT_PUBLIC_KEY" "OPENAI_API_KEY"
  "OBJECT_STORAGE_ENDPOINT_URL" "OBJECT_STORAGE_ACCESS_KEY_ID"
  "OBJECT_STORAGE_SECRET_ACCESS_KEY" "OBJECT_STORAGE_REGION"
  "RAW_INGEST_BUCKET" "STRIPE_SECRET_KEY" "RESEND_API_KEY"
  "LOG_LEVEL" "SERVICE_NAME"
)

MISSING=()
for var in "${REQUIRED[@]}"; do
  if [ -z "${!var}" ]; then
    MISSING+=("$var")
  fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
  echo "❌ Missing required variables:"
  printf '  - %s\n' "${MISSING[@]}"
  exit 1
else
  echo "✅ All required variables are set"
fi
```

### Check Security Variables

```bash
#!/bin/bash
# Verify security-critical variables are set
SECURITY=(
  "AUTH_SECRET_KEY" "AUDIT_INTEGRITY_KEY" "PII_HASH_SALT"
  "ADMIN_MASTER_KEY" "PARTNER_AUTH_SECRET" "SERVICE_AUTH_SECRET"
  "JWT_ISSUER" "JWT_AUDIENCE" "STRIPE_WEBHOOK_SECRET"
)

for var in "${SECURITY[@]}"; do
  if [ -z "${!var}" ]; then
    echo "⚠️ Security variable not set: $var"
  else
    echo "✅ $var: (***hidden***)"
  fi
done
```

### Database Connectivity Test

```bash
# Verify PostgreSQL connection
psql "$DATABASE_URL" -c "SELECT version();"

# Verify Redis connection
redis-cli -u "$REDIS_URL" PING

# Verify S3 connectivity
aws s3 ls s3://$RAW_INGEST_BUCKET/ --endpoint-url $OBJECT_STORAGE_ENDPOINT_URL
```

### Service Health Check

```bash
# After deployment, verify services are running
curl -H "Authorization: Bearer $JWT_SECRET" http://localhost:8000/health
curl -H "Authorization: Bearer $JWT_SECRET" http://localhost:8001/health
curl -H "Authorization: Bearer $JWT_SECRET" http://localhost:8002/health
```

---

## Grouping by Service

### Ingestion Service
**Required:** DATABASE_URL, REDIS_URL, ENV, KAFKA_BOOTSTRAP_SERVERS, OPENAI_API_KEY, OBJECT_STORAGE_* (all), RAW_INGEST_BUCKET, STRIPE_SECRET_KEY, JWT_SECRET, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY
**Security:** AUTH_SECRET_KEY, AUDIT_INTEGRITY_KEY, PII_HASH_SALT, PARTNER_AUTH_SECRET, STRIPE_WEBHOOK_SECRET

### Admin Service  
**Required:** DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY, JWT_SECRET, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY, ADMIN_DATABASE_URL, RESEND_API_KEY
**Security:** AUTH_SECRET_KEY, ADMIN_MASTER_KEY, JWT_ISSUER, JWT_AUDIENCE

### Compliance Service
**Required:** DATABASE_URL, COMPLIANCE_DATABASE_URL, KAFKA_BOOTSTRAP_SERVERS
**Security:** PII_HASH_SALT, AUDIT_INTEGRITY_KEY

### Shared Services (Auth, Rate Limiting, Observability)
**Required:** JWT_SECRET, LOG_LEVEL, SERVICE_NAME
**Security:** SERVICE_AUTH_SECRET, JWT_ISSUER, JWT_AUDIENCE

---

## Migration Path (Zero-Downtime Deployment)

1. **Pre-deployment:** Add new secrets to AWS Secrets Manager
2. **Update services:** Set `REGENGINE_SKIP_SECRET_CHECK=false` during rollout
3. **Health check:** Run verification commands above
4. **Canary:** Deploy to 10% of instances first
5. **Monitor:** Check error rates for 15 minutes
6. **Full rollout:** Deploy to remaining instances
7. **Cleanup:** Rotate old secrets after 30 days retention

---

## Troubleshooting

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| Service won't start | Missing required variable | Run required variables check above |
| 401 Unauthorized errors | JWT_SECRET or keys mismatch | Verify JWT_SECRET, JWT_PRIVATE_KEY, JWT_PUBLIC_KEY match across services |
| Database connection timeouts | DATABASE_URL invalid or DB down | Test with: `psql "$DATABASE_URL" -c "SELECT 1"` |
| Rate limiting errors | TENANT_RATE_LIMIT_RPM too low | Increase TENANT_RATE_LIMIT_RPM or WEBHOOK_INGEST_RATE_LIMIT_RPM |
| S3 upload failures | OBJECT_STORAGE_* variables wrong | Verify credentials with: `aws s3 ls --endpoint-url $OBJECT_STORAGE_ENDPOINT_URL` |
| Kafka errors | KAFKA_BOOTSTRAP_SERVERS wrong | Test with: `kafka-broker-api-versions.sh --bootstrap-server $KAFKA_BOOTSTRAP_SERVERS` |
