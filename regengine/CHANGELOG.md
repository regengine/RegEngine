# Changelog

All notable changes to the RegEngine Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-02-11

### Security
- **SEC-P0-1**: Fixed SQL injection in compliance worker tenant context setting — now uses parameterized query binding
- **SEC-P1-1**: Fixed Cypher injection in Neo4j `create_tenant_database` — regex sanitization + backtick-escaped DB names
- **DEBT-023**: Fixed serialization mismatch where NLP REGULATORY_DATE entities were silently dropped by Pydantic

### Fixed
- **BUG-P1-1**: Removed duplicate `except Exception` handler (dead code) in compliance worker
- Removed unreachable duplicate `return` statement in `validate_tlc` endpoint
- Consolidated `shared/schemas.py` to single source of truth (eliminated identical 490-line copies)

### Changed
- **OPS-P0-1**: Drift detection engine now queries live PostgreSQL (`pcos_extracted_facts`) for trace completeness, ingestion latency, and error rate instead of returning hardcoded values
- **REL-P1-2**: Compliance worker uses per-batch DB sessions with `pool_pre_ping=True` instead of a single long-lived session
- **REL-P1-1**: Added DLQ-style error tracking with structured logging (topic, partition, offset) and throttling
- **MAINT-P2-2**: Replaced `sys.path.append` hacks with deterministic `Path.resolve()` import resolution
- **OPS-P2-2**: Schema loading now uses `SCHEMA_DIR` environment variable with fallback paths

### Added
- **OPS-P2-1**: Compliance worker health file + `HEALTHCHECK` in `worker.Dockerfile` for container liveness probes
- Mock recall engine wired to live Neo4j graph trace queries

### Deprecated
- **MAINT-P2-1**: Migrated all `datetime.utcnow()` calls to `datetime.now(timezone.utc)` (4 files)

## [1.0.0] - 2026-02-05

### Added
- **RegEngineClient**: Full-featured API client for FSMA 204 compliance
  - Record management: `create_record()`, `get_record()`, `list_records()`
  - Supply chain tracing: `trace_forward()`, `trace_backward()`
  - Graph visualization: `get_trace_graph()`
  - FTL compliance checking: `check_ftl()`
  - Recall management: `start_recall_drill()`, `get_recall_readiness()`
  - FDA export: `export_fda()`

- **CTEType Enum**: All 7 FSMA 204 Critical Tracking Events
  - `GROWING`, `RECEIVING`, `TRANSFORMATION`, `SHIPPING`
  - `FIRST_LAND_RECEIVING`, `COOLING`, `INITIAL_PACKING`

- **Data Models**: Type-safe dataclasses
  - `Record`, `TraceResult`, `FTLResult`, `RecallDrill`, `ReadinessScore`

- **Exception Hierarchy**: Semantic error handling
  - `RegEngineError`, `AuthenticationError`, `RateLimitError`
  - `NotFoundError`, `ValidationError`

- **CLI Tool**: `regengine-verify` for independent hash verification
  - Offline file verification: `--file records.json --offline`
  - Online API verification: `--tlc LOT-001 --api-key rge_live_xxx`
  - Canonical JSON hashing with SHA-256

### Security
- API keys stored in memory only, never logged
- All requests use HTTPS
- Rate limit handling with exponential backoff

## [Unreleased]
- Async client (`RegEngineAsyncClient`)
- Webhook event parsing
- Batch verification optimization
