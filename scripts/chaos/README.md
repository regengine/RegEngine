# RegEngine Chaos Engineering Tests

This directory contains chaos engineering tests to validate system resiliency and data durability under various failure scenarios.

## Overview

Chaos engineering helps us verify that the RegEngine platform can:
- Recover from infrastructure failures without data loss
- Resume processing automatically after recovery
- Maintain data integrity during and after failures
- Meet recovery time objectives (RTO < 60 seconds)

## Test Scenarios

### 1. Neo4j Database Failure (`kill_neo4j.sh`)

**What it tests**: Graph database failure during active writes

**Expected outcomes**:
- Kafka messages remain in queue (not acknowledged)
- Graph consumer resumes processing after Neo4j restart
- No provision data lost
- All writes eventually consistent

**How to run**:
```bash
./scripts/chaos/kill_neo4j.sh
```

### 2. Kafka Broker Failure (`kill_kafka.sh`)

**What it tests**: Message broker failure during production

**Expected outcomes**:
- Producers buffer messages locally
- No message loss after Kafka restart
- Consumers resume from last committed offset
- All buffered messages delivered

**How to run**:
```bash
./scripts/chaos/kill_kafka.sh
```

## Running Tests

### Run All Tests

```bash
# Full test suite
./scripts/chaos/run_all_chaos_tests.sh

# Quick smoke tests only
./scripts/chaos/run_all_chaos_tests.sh --quick

# Specific test
./scripts/chaos/run_all_chaos_tests.sh --test "Neo4j Failure"
```

### Prerequisites

1. Docker and Docker Compose installed
2. RegEngine stack running: `docker-compose up -d`
3. All services healthy before starting chaos tests

### Test Output

Each test provides:
- Step-by-step execution log
- Recovery time measurement
- Data integrity verification
- Pass/fail status with summary

Example output:
```
=========================================
🔥 Chaos Test: Neo4j Failure
=========================================
Step 1: Recording baseline state...
Step 2: 💀 Killing Neo4j container...
✓ Neo4j container killed
✓ Confirmed Neo4j is down
Step 3: ⏳ Waiting 10 seconds (simulating downtime)...
Step 4: 🔄 Restarting Neo4j container...
⏳ Waiting for Neo4j to become healthy...
✓ Neo4j is healthy again (18s recovery time)
Step 5: ✅ Verifying recovery...
✓ Total recovery time: 28s
=========================================
✅ Neo4j Failure - PASSED
=========================================
```

## CI/CD Integration

Chaos tests run automatically:
- **Scheduled**: Daily at 2 AM UTC (GitHub Actions)
- **Manual**: Via GitHub Actions workflow dispatch

### GitHub Actions Workflow

Located at `.github/workflows/chaos_tests.yml`

**Manual trigger**:
1. Go to Actions tab in GitHub
2. Select "Chaos Tests" workflow
3. Click "Run workflow"
4. Choose mode: `quick` or `full`
5. Optionally specify a specific test

**Artifacts**:
- Service logs collected on failure
- Retained for 7 days

## Adding New Tests

To add a new chaos test:

1. Create a new script: `scripts/chaos/kill_<service>.sh`
2. Follow the template:
   ```bash
   #!/bin/bash
   set -e

   TEST_NAME="Your Test Name"
   echo "🔥 Chaos Test: ${TEST_NAME}"

   # Pre-flight checks
   # Kill service
   # Wait
   # Restart service
   # Verify recovery
   # Check data integrity

   echo "✅ ${TEST_NAME} - PASSED"
   ```

3. Make it executable: `chmod +x scripts/chaos/kill_<service>.sh`
4. Add to `run_all_chaos_tests.sh`:
   ```bash
   run_test "Your Test Name" "kill_<service>.sh" false
   ```

5. Test locally before committing

## Best Practices

1. **Always verify data integrity** - Don't just check if the service restarted
2. **Measure recovery times** - Track and report how long it takes to recover
3. **Test real scenarios** - Simulate actual failure conditions
4. **Automate verification** - Don't rely on manual checks
5. **Document expected behavior** - Make it clear what should happen

## Troubleshooting

### Test fails with "Container not found"

Ensure the RegEngine stack is running:
```bash
docker-compose up -d
docker ps | grep regengine
```

### Recovery takes too long

Check service logs:
```bash
docker-compose logs <service-name>
```

### Data integrity check fails

This indicates a real problem! Investigate:
1. Check Kafka consumer offsets
2. Verify database state
3. Review service logs for errors

## Recovery Time Objectives (RTO)

Target recovery times:
- **Neo4j failure**: < 60 seconds
- **Kafka failure**: < 60 seconds
- **Service failures**: < 30 seconds

## Data Loss Tolerance

**Zero tolerance** for data loss:
- All messages must be delivered
- All provisions must be written
- No orphaned or duplicate records

## Support

For questions or issues with chaos tests:
1. Check service logs: `docker-compose logs <service>`
2. Review test output for specific errors
3. File an issue with test output and logs
