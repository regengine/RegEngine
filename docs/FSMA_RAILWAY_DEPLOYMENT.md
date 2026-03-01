# FSMA 204 Deployment Notes (Railway)

## Service Topology

Railway project layout for FSMA-focused deployment:

- `frontend` - Next.js web app
- `ingestion-service` - FSMA ingestion, EPCIS, recall simulation APIs
- `admin-service` - tenant/admin and persistence APIs
- `graph-service` - Neo4j traversal and lineage APIs
- `postgres` - PostgreSQL
- `neo4j` - Neo4j
- `redis` - queue and cache

## Environment Variables

### API services

- `DATABASE_URL`
- `NEO4J_URI`
- `NEO4J_USER`
- `NEO4J_PASSWORD`
- `REDIS_URL`
- `JWT_SECRET`
- `HASH_SALT`
- `OBJECT_STORAGE_ACCESS_KEY_ID`
- `OBJECT_STORAGE_SECRET_ACCESS_KEY`
- `OBJECT_STORAGE_REGION`
- `OBJECT_STORAGE_ENDPOINT_URL`

### Frontend

- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_STRIPE_KEY` (when billing is enabled)

## Rollout Steps

1. Apply PostgreSQL migrations:

```bash
psql "$DATABASE_URL" -f services/admin/migrations/V31__fsma_204_infrastructure.sql
```

2. Apply Neo4j constraints:

```bash
python services/graph/scripts/init_db_constraints.py
```

3. Start graph sync worker:

```bash
python services/graph/scripts/fsma_sync_worker.py
```

4. Deploy services in order:

- `postgres`, `neo4j`, `redis`
- backend services (`admin-service`, `graph-service`, `ingestion-service`)
- `frontend`

5. Validate critical endpoints:

- `GET /health`
- `POST /api/v1/epcis/validate`
- `POST /api/v1/simulations/run`

## Notes

- Use Railway managed variables for production secrets.
- Keep `REGENGINE_ENV=production` for production services.
- Run a mock recall simulation post-deploy to validate graph and export paths.
