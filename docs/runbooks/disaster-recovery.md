# Disaster Recovery Runbook - RegEngine

## 1. Objectives & SLAs
*   **RPO (Recovery Point Objective)**: 15 minutes
    *   Maximum acceptable data loss: 15 minutes of transaction data.
*   **RTO (Recovery Time Objective)**: 1 hour
    *   Target time to restore full service functionality after a catastrophic failure.

## 2. Infrastructure Inventory
*   **Graph Database**: Neo4j Community Edition (Single Node)
*   **Relational Database**: PostgreSQL 15 (Single Node)
*   **Cache/Queue**: Redis 7 (AOF Persistence)
*   **Services**: Admin API, Graph API, Ingestion, Compliance, Opportunity

## 3. Backup Strategy

### 3.1 Neo4j (Community Edition)
*   **Challenge**: Hot backups are not supported in Community Edition.
*   **Strategy**: Scheduled offline dumps using `neo4j-admin`.
*   **Frequency**: Daily full backup at 02:00 UTC + Transaction logs archiving every 15 mins.
*   **Procedure**:
    ```bash
    # 1. Stop Neo4j Service (Brief downtime required for consistency)
    docker compose stop neo4j

    # 2. Perform Dump
    docker run --rm \
      -v regengine_neo4j_data:/data \
      -v $(pwd)/backups/neo4j:/backups \
      neo4j:5.24-community \
      neo4j-admin database dump neo4j --to-path=/backups

    # 3. Restart Service
    docker compose start neo4j
    
    # 4. Upload to S3 (Secure Offsite Storage)
    aws s3 cp backups/neo4j/neo4j.dump s3://regengine-backups/neo4j/$(date +%Y-%m-%d)/
    ```

### 3.2 PostgreSQL
*   **Strategy**: `pg_dump` (Logical Backup) + WAL Archiving (if PITR needed).
*   **Frequency**: Daily full dump at 03:00 UTC.
*   **Procedure**:
    ```bash
    # Non-blocking backup
    docker exec regengine-postgres-1 pg_dump -U regengine regengine_admin | gzip > backups/postgres/regengine_$(date +%Y-%m-%d).sql.gz
    
    # Upload
    aws s3 cp backups/postgres/*.gz s3://regengine-backups/postgres/
    ```

### 3.3 Redis
*   **Strategy**: AOF (Append Only File) persistence is enabled (`appendonly yes`).
*   **Backup**: Snapshot `dump.rdb` periodically.
*   **Procedure**:
    ```bash
    # Trigger save
    docker exec regengine-redis-1 redis-cli BGSAVE
    
    # Copy dump
    docker cp regengine-redis-1:/data/dump.rdb backups/redis/dump_$(date +%Y-%m-%d).rdb
    ```

## 4. Failover & Recovery Procedures

### 4.1 Scenario: Database Corruption or Loss

#### Neo4j Recovery
1.  **Assess**: Verify database is unresponsive or returning corruption errors.
2.  **Stop**: `docker compose stop neo4j`
3.  **Prepare Volume**: (Optional) Create fresh volume if corruption is disk-level.
4.  **Restore**:
    ```bash
    # Download latest backup
    aws s3 cp s3://regengine-backups/neo4j/2024-01-XX/neo4j.dump .

    # Load Dump
    docker run --rm \
      -v regengine_neo4j_data:/data \
      -v $(pwd):/backups \
      neo4j:5.24-community \
      neo4j-admin database load neo4j --from-path=/backups --overwrite-destination=true
    ```
5.  **Start**: `docker compose start neo4j`
6.  **Verify**: Run `MATCH (n) RETURN count(n)` and compare with metrics.

#### PostgreSQL Recovery
1.  **Stop**: `docker compose stop admin-api` (Prevent new writes)
2.  **Restore**:
    ```bash
    # Drop/Create DB
    docker exec -i regengine-postgres-1 psql -U regengine postgres -c "DROP DATABASE regengine_admin; CREATE DATABASE regengine_admin;"
    
    # Import Dump
    gunzip -c backups/postgres/latest.sql.gz | docker exec -i regengine-postgres-1 psql -U regengine regengine_admin
    ```
3.  **Restart Services**: `docker compose restart`

### 4.2 Scenario: Region/Data Center Failure
1.  **Switch Context**: Update `AWS_DEFAULT_REGION` in `.env`.
2.  **Provision**: Run Terraform/IaC scripts to provision infrastructure in secondary region.
3.  **Hydrate**: Restore data from S3 buckets (which should be cross-region replicated).
4.  **DNS Cutover**: Update Route53/DNS to point to new load balancer IP.

## 5. Recovery Drills
*   **Schedule**: Monthly (First Monday).
*   **Process**:
    1.  Spin up exact clone of production stack in isolated environment.
    2.  Restore databases from latest S3 backups.
    3.  Run automated `tests/e2e/verification.py` suite.
    4.  Measure TTR (Time To Restore).
    5.  Log results in `docs/compliance/dr_logs.md`.
