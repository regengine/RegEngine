# RegEngine Operations Runbook

## Quick Reference

| Action | Command |
|--------|---------|
| Start all services | `./scripts/start-stack.sh` |
| Stop all services | `./scripts/stop-stack.sh` |
| Check health | `./scripts/verify-health.sh` |
| View logs | `docker-compose logs -f <service>` |

---

## Starting the Stack

```bash
# From project root
./scripts/start-stack.sh
```

This script:
1. Starts infrastructure (Postgres, Redis, Neo4j, Redpanda, LocalStack)
2. Waits for databases to be ready
3. Starts application services in dependency order
4. Runs health verification

---

## Health Verification

```bash
./scripts/verify-health.sh
```

**Expected Output (Healthy):**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RegEngine Health Check
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Infrastructure:
  ✅ Neo4j
  ✅ Redpanda

Application Services:
  ✅ Admin API
  ✅ Ingestion
  ✅ NLP
  ✅ Graph
  ✅ Opportunity
  ✅ Compliance

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Status: All systems operational
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## Service Ports

| Service | Port | Health Endpoint |
|---------|------|-----------------|
| Admin API | 8400 | `/health` |
| Ingestion | 8000 | `/health` |
| NLP | 8100 | `/health` |
| Graph | 8200 | `/health` |
| Opportunity | 8300 | `/health` |
| Compliance | 8500 | `/health` |
| Neo4j Browser | 7474 | N/A |
| Kafka UI | 8080 | N/A |
| Frontend | 3000 | N/A |

---

## Common Issues

### Admin API Unhealthy

**Symptoms**: Health check fails, API returns 500 errors

**Diagnosis**:
```bash
docker-compose logs --tail 50 admin-api | grep -E "(error|ERROR|failed)"
```

**Common Causes**:
1. **Database connection failed**: Check Postgres is running
   ```bash
   docker-compose exec postgres pg_isready -U regengine
   ```
2. **Missing migrations**: Run migrations manually
   ```bash
   docker-compose exec admin-api alembic upgrade head
   ```
3. **Missing secrets**: Verify `.env` has `ADMIN_MASTER_KEY` and `NEO4J_PASSWORD`

---

### Neo4j Connection Failures

**Symptoms**: Graph/Opportunity API can't query data

**Diagnosis**:
```bash
docker-compose logs --tail 30 neo4j
```

**Common Causes**:
1. **Auth mismatch**: `NEO4J_PASSWORD` in `.env` must match what Neo4j was initialized with
2. **Memory issues**: Neo4j needs at least 2GB RAM
   ```bash
   docker stats neo4j
   ```

**Fix for auth mismatch** (destructive, resets data):
```bash
docker-compose down -v  # Removes volumes
docker-compose up -d neo4j
```

---

### Kafka/Redpanda Issues

**Symptoms**: Events not flowing between services

**Diagnosis**:
```bash
# Check topics exist
docker-compose exec redpanda rpk topic list

# Check consumer lag
docker-compose exec redpanda rpk group describe nlp-consumer
```

**Common Causes**:
1. **Topics not created**: Services auto-create topics on first use
2. **Consumer crashed**: Check service logs

---

### Frontend Shows "X System(s) Unhealthy"

**Root Cause**: Frontend can't reach backend APIs

**Diagnosis**:
1. Check `api-config.ts` has correct ports
2. Verify services are running: `docker-compose ps`
3. Check CORS is enabled on services

**Quick Fix**:
```bash
./scripts/verify-health.sh  # Identify which services are down
docker-compose restart <service-name>
```

---

## Logs

### View Service Logs
```bash
# Single service
docker-compose logs -f admin-api

# Multiple services
docker-compose logs -f admin-api ingestion-service

# Last 100 lines
docker-compose logs --tail 100 admin-api
```

### Filter for Errors
```bash
docker-compose logs admin-api 2>&1 | grep -E "(ERROR|error|Exception)"
```

---

## Rebuilding Services

After code changes:
```bash
# Rebuild specific service
docker-compose build admin-api
docker-compose up -d admin-api

# Rebuild all
docker-compose build
docker-compose up -d
```

---

## Environment Variables

Required in `.env`:
```bash
# Security (REQUIRED - generate with `openssl rand -hex 32`)
ADMIN_MASTER_KEY=your-32-char-hex-key

# Database (REQUIRED - generate with `openssl rand -base64 32`)
NEO4J_PASSWORD=your-strong-password

# AWS (for LocalStack, use test values in dev)
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

---

## Chaos Testing

Run resilience tests (in a staging environment):
```bash
./scripts/chaos/run_all_chaos_tests.sh
```

---

## Support

- **Docs**: See `/docs` folder
- **API Docs**: http://localhost:8400/docs (Admin API)
- **Frontend**: http://localhost:3000
