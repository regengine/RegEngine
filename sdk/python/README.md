# RegEngine Energy SDK

Python client library for NERC CIP-013 compliance snapshots.

## Installation

```bash
pip install regengine-energy
```

## Quick Start

```python
from regengine_energy import EnergyCompliance

# Initialize client
client = EnergyCompliance(api_key="rge_your_api_key")

# Create a compliance snapshot
snapshot = client.snapshots.create(
    substation_id="ALPHA-001",
    facility_name="Alpha Substation",
    system_status="NOMINAL",
    assets=[
        {
            "id": "T1",
            "type": "TRANSFORMER",
            "firmware_version": "2.4.1",
            "last_verified": "2026-01-26T15:00:00Z"
        }
    ],
    esp_config={
        "firewall_version": "2.4.1",
        "ids_enabled": True,
        "patch_level": "current"
    }
)

print(f"✅ Snapshot created: {snapshot.snapshot_id}")
print(f"🔒 Content hash: {snapshot.content_hash}")

# Verify chain integrity
verification = client.verification.verify_latest("ALPHA-001")
print(f"⛓️  Chain intact: {verification.chain_intact}")
```

## Features

- ✅ Type-safe with Pydantic models
- ✅ Automatic retry logic with exponential backoff
- ✅ Comprehensive error handling
- ✅ Environment variable support for API keys
- ✅ Full async support (coming soon)

## Authentication

Set your API key via environment variable:

```bash
export REGENGINE_API_KEY=rge_your_api_key
```

Or pass directly to the client:

```python
client = EnergyCompliance(api_key="rge_your_api_key")
```

## API Reference

### EnergyCompliance

Main client class.

**Parameters:**
- `api_key` (str, optional): API key (or set `REGENGINE_API_KEY` env var)
- `base_url` (str, optional): API base URL (default: production)
- `timeout` (int, optional): Request timeout in seconds (default: 30)
- `max_retries` (int, optional): Maximum retry attempts (default: 3)

### Snapshots

#### `client.snapshots.create()`

Create a compliance snapshot.

**Parameters:**
- `substation_id` (str): Substation identifier
- `facility_name` (str): Facility name
- `system_status` (str): NOMINAL, DEGRADED, or NON_COMPLIANT
- `assets` (list): List of asset dictionaries
- `esp_config` (dict): ESP configuration
- `regulatory` (dict, optional): Regulatory information
- `trigger_reason` (str, optional): Human-readable reason

**Returns:** `SnapshotResponse`

#### `client.snapshots.get(snapshot_id)`

Retrieve a specific snapshot.

**Returns:** `SnapshotResponse`

#### `client.snapshots.list()`

List snapshots with pagination.

**Parameters:**
- `substation_id` (str, optional): Filter by substation
- `limit` (int): Results per page (default: 50)
- `offset` (int): Pagination offset (default: 0)

**Returns:** `SnapshotListResponse`

### Verification

#### `client.verification.verify_chain(substation_id)`

Verify chain integrity for all snapshots in a substation.

**Returns:** `VerificationResult`

#### `client.verification.verify_latest(substation_id)`

Verify the latest snapshot only.

**Returns:** `VerificationResult`

## Error Handling

```python
from regengine_energy import (
    EnergyCompliance,
    AuthenticationError,
    ValidationError,
    SnapshotCreationError,
)

client = EnergyCompliance()

try:
    snapshot = client.snapshots.create(...)
except AuthenticationError:
    print("Invalid API key")
except ValidationError as e:
    print(f"Validation failed: {e.message}")
    print(f"Details: {e.details}")
except SnapshotCreationError as e:
    print(f"Snapshot creation failed: {e}")
```

## License

MIT
