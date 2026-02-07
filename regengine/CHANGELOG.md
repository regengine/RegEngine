# Changelog

All notable changes to the RegEngine Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
