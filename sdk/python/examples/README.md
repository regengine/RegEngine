# Energy SDK Examples

This directory contains example scripts demonstrating how to use the RegEngine Energy SDK.

## Running Examples

1. **Set your API key:**
   ```bash
   export REGENGINE_API_KEY=rge_your_api_key_here
   ```

2. **Run the demo script:**
   ```bash
   python3 examples/demo.py
   ```

## Examples

### `demo.py`
Complete demonstration of SDK capabilities:
- Creating compliance snapshots
- Retrieving snapshot details
- Listing snapshots with pagination
- Verifying chain integrity

## Local Development

To run examples against a local Energy service:

```bash
export ENERGY_API_URL=http://localhost:8002
export REGENGINE_API_KEY=rge_test_key
python3 examples/demo.py
```
