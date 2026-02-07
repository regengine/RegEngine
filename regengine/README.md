# RegEngine Python SDK

Official Python SDK for RegEngine FSMA 204 Compliance Platform.

## Installation

```bash
pip install regengine
```

## Quick Start

```python
from regengine import RegEngineClient

# Initialize client
client = RegEngineClient(
    api_key="rge_your_api_key",
    base_url="https://api.regengine.co"  # Optional
)

# Create a traceability record
record = client.create_record(
    cte_type="RECEIVING",
    tlc="LOT-2026-001",
    location="GLN-1234567890123",
    quantity=100,
    product_description="Romaine Lettuce"
)

# Trace forward through supply chain
trace = client.trace_forward("LOT-2026-001", max_depth=10)
print(f"Found {trace.hop_count} downstream facilities")

# Trace backward to source
source = client.trace_backward("LOT-2026-001")
print(f"Traced to {len(source.source_lots)} source lots")

# Check FTL coverage
ftl = client.check_ftl("leafy-greens")
print(f"FSMA 204 applies: {ftl.covered}")
print(f"Required CTEs: {ftl.ctes}")

# Export FDA-compliant spreadsheet
csv_data = client.export_fda("LOT-2026-001", "2026-01-01", "2026-01-31")
with open("fda_export.csv", "wb") as f:
    f.write(csv_data)
```

## API Reference

### RegEngineClient

#### `create_record(cte_type, tlc, location, quantity, **kwargs)`
Create a traceability record for a Critical Tracking Event.

#### `get_record(tlc)`
Retrieve a record by Traceability Lot Code.

#### `trace_forward(tlc, max_depth=10)`
Trace a lot forward to downstream customers and products.

#### `trace_backward(tlc, max_depth=10)`
Trace a lot backward to source materials and suppliers.

#### `get_timeline(tlc)`
Get chronological timeline of all events for a lot.

#### `check_ftl(product_category)`
Check if a product category is on FDA's Food Traceability List.

#### `export_fda(tlc, start_date, end_date)`
Generate FDA-compliant CSV export per 21 CFR 1.1455(b)(3).

#### `start_recall_drill(tlc, severity="class_ii")`
Initiate a mock recall drill.

#### `get_readiness_score()`
Get your FSMA 204 recall readiness score.

## CLI: Independent Verification

The SDK includes a CLI tool for independent hash verification:

```bash
# Install with CLI
pip install regengine

# Verify a lot online
regengine-verify --tlc LOT-2026-001 --api-key rge_live_xxx

# Verify exported records offline
regengine-verify --file exported_records.json --offline
```

The `regengine-verify` tool implements the "Verify, Don't Trust" principle — you can independently verify record integrity without relying on RegEngine servers.

---

**Version**: 1.0.0  
**License**: MIT  
**Documentation**: https://docs.regengine.co/sdks/python
