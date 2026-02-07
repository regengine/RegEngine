# RegEngine Audit Events Integration

**Version**: 1.0
**Last Updated**: 2025-11-22
**Status**: Integrated

## Overview

RegEngine now emits **Kafka audit events** for all control and mapping operations in the Content Graph Overlay system. This provides a complete audit trail for compliance tracking and operational monitoring.

## Architecture

### Event Flow

```
API Request (POST /overlay/controls)
    ↓
OverlayWriter.create_tenant_control()
    ↓
1. Write to Neo4j (tenant database)
    ↓
2. Emit Kafka event → graph.audit topic
    ↓
Event consumed by audit/monitoring systems
```

### Components

**1. GraphEventPublisher** (`services/graph/app/graph_event_publisher.py`)
- Kafka producer for audit events
- Publishes to `graph.audit` topic
- Handles serialization and error logging

**2. OverlayWriter** (`services/graph/app/overlay_writer.py`)
- Integrated with GraphEventPublisher
- Emits events after successful Neo4j writes
- Includes tenant_id and full operation data

## Event Schema

### Control Event

```json
{
  "event_type": "control",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMMITTED",
  "control": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "control_id": "CTL-001",
    "title": "Access Control Policy",
    "description": "Manage user access with least privilege",
    "framework": "NIST CSF"
  }
}
```

### Mapping Event

```json
{
  "event_type": "mapping",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMMITTED",
  "mapping": {
    "id": "550e8400-e29b-41d4-a716-446655440002",
    "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
    "control_id": "550e8400-e29b-41d4-a716-446655440001",
    "provision_hash": "abc123def456...",
    "mapping_type": "IMPLEMENTS",
    "confidence": 0.95,
    "notes": "Policy addresses this requirement",
    "created_by": "550e8400-e29b-41d4-a716-446655440000",
    "created_at": "2025-11-22T10:30:00Z"
  }
}
```

## Configuration

### Kafka Broker

Set via environment variable:
```bash
export KAFKA_BROKER="kafka:9092"
```

Default: `kafka:9092`

### Topic

Audit events are published to: `graph.audit`

**Topic Configuration** (recommended):
- Partitions: 3
- Replication Factor: 3
- Retention: 30 days (or as required for compliance)
- Compression: lz4

## Operations Tracked

### Control Operations

| Operation | Event Type | Status |
|-----------|------------|--------|
| Create Control | `control` | `COMMITTED` |
| Update Control | `control` | `COMMITTED` |
| Delete Control | `control` | `DELETED` |

### Mapping Operations

| Operation | Event Type | Status |
|-----------|------------|--------|
| Create Mapping | `mapping` | `COMMITTED` |
| Update Mapping | `mapping` | `COMMITTED` |
| Delete Mapping | `mapping` | `DELETED` |

## Verification

### Running the Verification Script

```bash
./demo/verify_phase3_audit.sh
```

**What it does**:
1. Creates a test control via REST API
2. Creates a test mapping via REST API
3. Provides commands to verify Kafka events
4. Provides Neo4j queries to verify data

### Manual Verification

**1. Check Kafka Topic**:
```bash
docker exec -it regengine-kafka-1 kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic graph.audit \
  --from-beginning
```

**2. Query Neo4j**:
```cypher
// Check control exists
MATCH (c:TenantControl {control_id: "CTL-AUDIT-001"})
RETURN c

// Check mapping exists
MATCH (c:TenantControl)-[r:MAPS_TO]->(p:GlobalProvisionRef)
WHERE c.control_id = "CTL-AUDIT-001"
RETURN c, r, p
```

### Glass Box Provenance CLI

Use the provenance replay auditor to prove that a stored provision still matches the raw regulation text saved on disk.

```bash
python scripts/audit/verify_provenance.py \
  --tenant-id 550e8400-e29b-41d4-a716-446655440000 \
  --correlation-id 38f1ab0fb1f244e49e9dc6e0e3af8cdd \
  --file demo/documents/us-sec-capital-requirements.json
```

#### Flags

- `--framework` (optional) lets you override the extractor code (e.g., `US-SEC-SCI`) if the stored record is missing metadata.
- Exit code `0` = verified, `1` = mismatch/IO failure, `2` = model version mismatch (use historical container image).

The CLI prints the tenant, correlation hash, byte count, and the replay verdict so auditors can capture evidence during reviews.

## Use Cases

### 1. Compliance Audit Trail

Track all changes to control frameworks for regulatory compliance:

```python
# Consumer example
from kafka import KafkaConsumer

consumer = KafkaConsumer(
    'graph.audit',
    bootstrap_servers=['kafka:9092'],
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

for message in consumer:
    event = message.value
    if event['event_type'] == 'control':
        print(f"Control {event['control']['control_id']} created/updated")
        # Store in audit database, send notifications, etc.
```

### 2. Real-Time Monitoring

Monitor control and mapping operations in real-time:

```python
# Prometheus metrics
from prometheus_client import Counter

control_events = Counter(
    'regengine_control_events_total',
    'Total control events',
    ['tenant_id', 'framework']
)

for event in consumer:
    if event['event_type'] == 'control':
        control_events.labels(
            tenant_id=event['tenant_id'],
            framework=event['control']['framework']
        ).inc()
```

### 3. Change Notifications

Notify stakeholders when control frameworks change:

```python
# Slack notification example
import slack_sdk

for event in consumer:
    if event['event_type'] == 'mapping':
        send_slack_notification(
            f"New mapping created: {event['mapping']['control_id']} → "
            f"{event['mapping']['provision_hash'][:8]}"
        )
```

## Error Handling

### Failed Event Publishing

Events are published **after** successful Neo4j writes. If event publishing fails:

1. **Neo4j write succeeds** (data is persisted)
2. **Event publishing fails** (logged as error)
3. **Operation continues** (doesn't block API response)

This ensures that:

- Data consistency is maintained
- API performance is not impacted by Kafka issues
- Audit events are "best effort"

### Error Logs

Failed event publishing is logged:

```text
ERROR Failed to publish control audit event: [Errno 111] Connection refused
```

Check logs with:

```bash
docker logs regengine-graph-1 | grep "Failed to publish"
```

## Performance Considerations

### Producer Configuration

The `GraphEventPublisher` uses fire-and-forget delivery:

```python
self.producer.send(TOPIC_GRAPH_AUDIT, value=payload)
# Does not wait for acknowledgment
```

**Benefits**:

- Low latency (<1ms)
- Non-blocking API operations
- High throughput

**Trade-offs**:

- Events may be lost if Kafka is down
- No delivery guarantees

### Production Recommendations

For production deployments:

**1. Add delivery confirmation**:

```python
future = self.producer.send(TOPIC_GRAPH_AUDIT, value=payload)
try:
    record_metadata = future.get(timeout=1)
    logger.info(f"Event sent to {record_metadata.topic}:{record_metadata.partition}")
except Exception as e:
    logger.error(f"Event delivery failed: {e}")
```

**2. Configure producer**:

```python
self.producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda x: json.dumps(x).encode('utf-8'),
    acks='all',  # Wait for all replicas
    retries=3,   # Retry on failure
    compression_type='lz4'  # Compress events
)
```

**3. Monitor lag**:

- Use Kafka exporter (already configured in Phase 4)
- Alert on consumer lag > 1000 messages
- Dashboard in Grafana

## Integration with Phase 4 (Audit Logging)

Phase 4 implemented structured audit logging to files/stdout. Phase 3 audit events complement this:

**Phase 4 Audit Logging** (`shared/audit.py`):

- Structured logs to stdout/file
- 20+ event types
- Full audit context (actor, resource, IP, user agent)

**Phase 3 Kafka Events** (`graph_event_publisher.py`):

- Event stream to Kafka
- Control/mapping specific
- Enables real-time monitoring and downstream processing

**Use Both**:

- Audit logs: Compliance and forensics
- Kafka events: Real-time monitoring and integrations

## Testing

### Unit Tests

Test event publishing in isolation:

```python
# tests/graph/test_graph_event_publisher.py
from unittest.mock import Mock, patch
from services.graph.app.graph_event_publisher import GraphEventPublisher

def test_publish_control_event():
    with patch('kafka.KafkaProducer') as mock_producer:
        publisher = GraphEventPublisher()
        publisher.publish_control_event(
            tenant_id="550e8400-e29b-41d4-a716-446655440000",
            control_data={"control_id": "CTL-001", "title": "Test"}
        )

        # Verify send was called
        mock_producer.return_value.send.assert_called_once()
```

### Integration Tests

Test end-to-end event flow:

```bash
# Start services
docker-compose up -d

# Create control
curl -X POST http://localhost:8000/overlay/controls \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -d '{"control_id": "TEST-001", "title": "Test Control", "framework": "NIST CSF"}'

# Verify event in Kafka
docker exec -it regengine-kafka-1 kafka-console-consumer \
  --bootstrap-server localhost:9092 \
  --topic graph.audit \
  --from-beginning \
  | grep "TEST-001"
```

## Troubleshooting

### Events Not Appearing in Kafka

**1. Check Kafka is running**:

```bash
docker ps | grep kafka
```

**2. Check topic exists**:

```bash
docker exec -it regengine-kafka-1 kafka-topics \
  --list --bootstrap-server localhost:9092
```

**3. Check logs**:

```bash
docker logs regengine-graph-1 | grep -i kafka
```

### Connection Refused Errors

If you see `[Errno 111] Connection refused`:

**1. Verify Kafka broker address**:

```bash
echo $KAFKA_BROKER
# Should be kafka:9092 for Docker Compose
```

**2. Check network connectivity**:

```bash
docker exec -it regengine-graph-1 ping kafka
```

**3. Verify Kafka listeners**:

```bash
docker exec -it regengine-kafka-1 kafka-broker-api-versions \
  --bootstrap-server localhost:9092
```

## Roadmap

### Future Enhancements

**1. Event Schema Versioning**:

- Add `schema_version` field
- Support backward compatibility

**2. Additional Event Types**:

- Product events
- Product-control link events
- Bulk operation events

**3. Event Replay**:

- Consumer offset management
- Replay events from specific timestamp
- Rebuild state from event log

**4. Event Enrichment**:

- Add actor information (API key, user ID)
- Include IP address and user agent
- Add request correlation IDs

**5. Dead Letter Queue**:

- Capture failed events
- Retry mechanism
- Alerting on DLQ size

## References

- **Phase 3**: Content Graph Overlay System
- **Phase 4**: Security Hardening (audit logging)
- **Kafka Documentation**: <https://kafka.apache.org/documentation/>
- **OverlayWriter Source**: `services/graph/app/overlay_writer.py`
- **GraphEventPublisher Source**: `services/graph/app/graph_event_publisher.py`

---

**Status**: ✅ Integrated and operational
**Last Updated**: 2025-11-22
