# Changelog

All notable changes to the **RegEngine Python SDK** (`regengine` package) are
documented in this file. Platform/backend changes live in the repository's
release notes, not here — earlier revisions of this file mixed in platform
history (SQL-injection fixes, NLP worker changes) under versions `1.0.0` and
`1.1.0` that were never SDK releases; that history was removed when the
version strings were reconciled (WS-11).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The single source of truth for the version is `regengine/__init__.py`
(`__version__`); `setup.py` and the `regengine-verify --version` output both
derive from it.

## [0.1.0.dev0] — Unreleased

Pre-PyPI development line. Not yet published.

### Added
- `RegEngineClient` — httpx-based client with retry/backoff on transient
  failures (429/500/502/503, `Retry-After`-aware) and typed exceptions
  (`AuthenticationError`, `NotFoundError`, `RateLimitError`,
  `ValidationError`, `RegEngineError`).
- Read/trace surface: `get_record`, `trace_forward`, `trace_backward`,
  `get_timeline`, `export_fda`, `start_recall_drill`, `get_readiness_score`.
- `regengine-verify` CLI (`regengine/verify_records.py`) — Apache-2.0-licensed
  (originally announced as MIT; relicensed pre-release to match the repository
  LICENSE's permissive-exceptions clause — copies received under MIT remain
  MIT-licensed),
  dependency-light offline verifier for canonical record hashes, pinned
  byte-for-byte to the server's hash by a golden-digest test (#2507).

### Changed
- `verify_chain.py` renamed to `verify_records.py` (WS-11) to end the
  filename collision with the Merkle *bundle* verifier published at
  `https://regengine.co/sdk/verify_chain.py` (a different program).
  `regengine.verify_chain` remains as a deprecation shim until the first
  PyPI release.
- Packaging fixed (WS-11): `pip install` previously installed the `swarm/`
  and `tests/` subdirectories as top-level packages and omitted the client
  itself. The built artifact now contains exactly the `regengine` package;
  the legacy swarm agent framework is repo-internal and no longer ships.

### Removed
- `create_record` and `check_ftl` (WS-11): both raised
  `NotImplementedError` — the consolidated API has no public create-record
  endpoint (records are written by the ingestion pipeline: webhook/EPCIS/
  EDI) and no per-category FTL lookup (use the category listing at
  `/api/v1/products/categories/ftl`). Advertising them in the README while
  they always raised was a documentation lie (#2531).

### Fixed
- Response deserialisation (#2933): `Record`, `Facility` and `TimelineEvent`
  each defined a hand-written `__init__` that filtered kwargs through
  `hasattr`. `@dataclass` leaves an existing `__init__` alone, and a field
  declared without a default is not a class attribute, so every required
  field was silently dropped — `client.get_record(tlc).tlc` and
  `repr(record)` both raised `AttributeError`. The generated (strict)
  constructors are back, and each model gained a `from_api(payload)`
  classmethod that maps the server's key names (`event_id`,
  `traceability_lot_code`, `unit_of_measure`, ...) onto the SDK field names
  and ignores keys the SDK does not model.
