# RegEngine Python SDK

Official Python SDK for RegEngine FSMA 204 Compliance Platform.

> **Status:** Not yet published to PyPI. Install from source for now.

## Installation

```bash
# Install from the repository root
pip install -e ./regengine
```

## Quick Start

```python
from regengine import RegEngineClient

# Initialize client
client = RegEngineClient(
    api_key="rge_your_api_key",
    base_url="https://api.regengine.co"  # Optional
)

# Look up a traceability record
record = client.get_record("LOT-2026-001")

# Query records by date range
records = client.query_records("2026-01-01", "2026-01-31")
```

## API Reference

### RegEngineClient

#### `get_record(tlc)`
Retrieve a record by Traceability Lot Code.

#### `query_records(start_date, end_date, cte_type=None)`
Query traceability records by date range and optional CTE type.

### Experimental methods — NOT available on the hosted API

The methods below target the graph FSMA routers, which the production
deployment does not mount (they are excluded from the release-approved
router allowlist). **Against `https://api.regengine.co` they return 404.**
They work only against a self-hosted deployment that mounts the
experimental graph routers. The set is declared in
`RegEngineClient.EXPERIMENTAL_METHODS` and kept in sync with the production
route table by `tests/sdk/test_route_contract.py`.

#### `trace_forward(tlc, max_depth=10)`
Trace a lot forward to downstream customers and products.

#### `trace_backward(tlc, max_depth=10)`
Trace a lot backward to source materials and suppliers.

#### `get_timeline(tlc)`
Get chronological timeline of all events for a lot.

#### `export_fda(tlc, start_date, end_date)`
Generate FDA-compliant CSV export per 21 CFR 1.1455(b)(3).

#### `start_recall_drill(tlc, severity="class_ii")`
Initiate a mock recall drill.

#### `get_recall_drills(limit=20)`
Get history of mock recall drills.

#### `get_readiness_score()`
Get your FSMA 204 recall readiness score.

### Not supported by the client

- **Creating records**: the API has no public create-record endpoint —
  records are written through the ingestion pipeline (webhook/EPCIS/EDI).
- **Per-category FTL lookup**: use the category listing endpoint
  `/api/v1/products/categories/ftl` directly.

## CLI: Independent Verification

The SDK includes a CLI tool for independent hash verification:

```bash
# Install from source (not yet on PyPI)
pip install -e ./regengine

# Verify a lot online
regengine-verify --tlc LOT-2026-001 --api-key rge_live_xxx

# Verify exported records offline
regengine-verify --file exported_records.json --offline
```

The `regengine-verify` tool implements the "Verify, Don't Trust" principle — you can independently verify record integrity without relying on RegEngine servers.

---

**Version**: see `regengine.__version__` (source of truth: `__init__.py`)
**License**: Proprietary, source-visible — same terms as the repository [LICENSE](../LICENSE), except the `regengine-verify` CLI (`verify_records.py`), which is Apache 2.0 per that file's permissive-exceptions clause
**Documentation**: https://docs.regengine.co/sdks/python
