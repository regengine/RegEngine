# Neo4j Disaster Recovery (DR) Runbook

## Service Information
- **Service Name:** FSMA Graph Service (`neo4j-core`)
- **Criticality:** Tier 1 (Compliance Data System of Record)
- **RPO (Recovery Point Objective):** 15 minutes
- **RTO (Recovery Time Objective):** 1 hour

## Architecture
- **Cluster:** 3-node Causal Cluster (Core) + Read Replicas (optional)
- **Hosting:** AWS EKS / Kubernetes
- **Storage:** EBS gp3 (Encrypted)

## Backup Procedures

### 1. Continuous Backup
Neo4j Causal Clustering provides real-time replication. If one node fails, others handle traffic.

### 2. Point-in-Time Backup (Automated)
- **Frequency:** Hourly incremental, Daily full.
- **Method:** `neo4j-admin backup` to S3 bucket `s3://regengine-backups/neo4j/`.
- **Retention:** 30 days.

## Failover & Recovery Scenarios

### Scenario A: Single Node Failure
**Symptoms:** 
- Kubernetes Pod `neo4j-core-X` restarts or is stuck in `Pending`.
- Alert: `Neo4jClusterUnhealthy`.

**Action:**
1. No manual intervention usually required. StatefulSet will restart pod.
2. Verify re-joining:
   ```bash
   kubectl logs statefulset/neo4j-core | grep "Cluster"
   ```

### Scenario B: Region/Cluster Loss (Total Outage)
**Symptoms:** 
- All Neo4j endpoints unreachable. 503 Service Unavailable.

**Action (DR Activation):**
1. **Provision Infrastructure:**
   Deploy `infrastructure/neo4j/cluster.yaml` to DR region (e.g., us-east-2).
   
2. **Restore Data:**
   Use the `restore-backup` job:
   ```bash
   kubectl create job --from=cronjob/neo4j-restore neo4j-dr-restore \
     --env="BACKUP_SOURCE=s3://regengine-backups/neo4j/latest-full.tar.gz"
   ```

3. **Verify Integrity:**
   Run the "Day 0" verification suite:
   ```bash
   # Check basic counts
   kubectl exec neo4j-core-0 -- bin/cypher-shell "MATCH (n) RETURN count(n)"
   
   # Run Time Arrow validation
   python3 -m app.verify_integrity --strict
   ```

4. **Switch Traffic:**
   Update DNS `graph.regengine.internal` to point to DR LoadBalancer.

## Verification Drills
- **Schedule:** Quarterly.
- **Procedure:** Restore production backup to `staging` environment and run full regression suite.
- **Last Drill:** [Date] - Passed/Failed
