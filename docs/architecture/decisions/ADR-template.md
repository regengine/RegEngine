# Architecture Decision Record Template

## ADR-XXX: [Title]

**Status:** [Proposed | Accepted | Deprecated | Superseded]
**Date:** YYYY-MM-DD
**Decision Makers:** [Names]

## Context

What is the issue that we're seeing that is motivating this decision or change?

## Decision

What is the change that we're proposing and/or doing?

## Rationale

Why is this the best choice among alternatives?

### Alternatives Considered

1. **Option A** - Description
   - Pros: ...
   - Cons: ...

2. **Option B** - Description
   - Pros: ...
   - Cons: ...

## Consequences

### Positive
- ...

### Negative
- ...

### Neutral
- ...

## References

- [Link to relevant documentation]
- [Link to discussion thread]

---

# Example: ADR-001: Event-Driven Architecture with Kafka

**Status:** Accepted
**Date:** 2024-01-15
**Decision Makers:** Engineering Team

## Context

RegEngine needs to process regulatory documents through multiple stages (ingestion → NLP → graph storage) with varying processing times. Direct synchronous calls would create tight coupling and poor user experience.

## Decision

Use Kafka (Redpanda) for asynchronous message passing between services with the following topics:
- `ingest.normalized` - Ingestion → NLP
- `graph.update` - NLP → Graph (high confidence)
- `nlp.needs_review` - NLP → Admin (low confidence)
- `graph.audit` - All services → Audit

## Rationale

Kafka provides:
1. **Decoupling** - Services evolve independently
2. **Resilience** - Messages persist if consumers are down
3. **Scalability** - Partition-based horizontal scaling
4. **Replayability** - Re-process historical data

### Alternatives Considered

1. **RabbitMQ** - Simpler but less durable for regulatory data
2. **Direct HTTP** - Synchronous, creates coupling
3. **AWS SQS** - Vendor lock-in

## Consequences

### Positive
- Services can scale independently
- NLP processing doesn't block user requests
- Audit trail via event sourcing

### Negative
- Operational complexity (Kafka cluster management)
- Eventual consistency (not immediate)
- Debugging distributed flows is harder
