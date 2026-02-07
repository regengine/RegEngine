# RegEngine API Usage Examples

This guide provides code examples for common RegEngine API operations in multiple programming languages.

## Table of Contents

- [Authentication](#authentication)
- [Controls Management](#controls-management)
- [Products Management](#products-management)
- [Control Mappings](#control-mappings)
- [Compliance Analysis](#compliance-analysis)
- [Complete Workflow Example](#complete-workflow-example)
- [Domain Endpoints](#domain-endpoints)

## Authentication

All API requests require your API key in the `X-RegEngine-API-Key` header.

### cURL

```bash
export API_KEY="your_api_key_here"
export BASE_URL="https://api.regengine.example.com"

curl -X GET "$BASE_URL/overlay/controls" \
  -H "X-RegEngine-API-Key: $API_KEY"
```

### Python

```python
import requests

API_KEY = "your_api_key_here"
BASE_URL = "https://api.regengine.example.com"

headers = {
    "X-RegEngine-API-Key": API_KEY,
    "Content-Type": "application/json"
}

response = requests.get(f"{BASE_URL}/overlay/controls", headers=headers)
print(response.json())
```

### JavaScript/TypeScript

```typescript
const API_KEY = "your_api_key_here";
const BASE_URL = "https://api.regengine.example.com";

const headers = {
  "X-RegEngine-API-Key": API_KEY,
  "Content-Type": "application/json"
};

// Using fetch
fetch(`${BASE_URL}/overlay/controls`, { headers })
  .then(res => res.json())
  .then(data => console.log(data));

// Using axios
import axios from 'axios';

const client = axios.create({
  baseURL: BASE_URL,
  headers: headers
});

const controls = await client.get('/overlay/controls');
console.log(controls.data);
```

## Controls Management

### List All Controls

<details>
<summary><b>cURL</b></summary>

```bash
curl -X GET "$BASE_URL/overlay/controls" \
  -H "X-RegEngine-API-Key: $API_KEY"
```
</details>

<details>
<summary><b>Python</b></summary>

```python
def list_controls(framework=None):
    """List all controls, optionally filtered by framework."""
    url = f"{BASE_URL}/overlay/controls"
    params = {"framework": framework} if framework else {}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# List all controls
all_controls = list_controls()
print(f"Total controls: {all_controls['count']}")

# Filter by framework
nist_controls = list_controls(framework="NIST CSF")
print(f"NIST CSF controls: {nist_controls['count']}")
```
</details>

<details>
<summary><b>TypeScript</b></summary>

```typescript
interface Control {
  id: string;
  control_id: string;
  title: string;
  description: string;
  framework: string;
}

interface ControlsResponse {
  controls: Control[];
  count: number;
}

async function listControls(framework?: string): Promise<ControlsResponse> {
  const params = framework ? `?framework=${encodeURIComponent(framework)}` : '';
  const response = await client.get<ControlsResponse>(`/overlay/controls${params}`);
  return response.data;
}

// Usage
const allControls = await listControls();
console.log(`Total controls: ${allControls.count}`);

const nistControls = await listControls("NIST CSF");
console.log(`NIST CSF controls: ${nistControls.count}`);
```
</details>

### Create a Control

<details>
<summary><b>cURL</b></summary>

```bash
curl -X POST "$BASE_URL/overlay/controls" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "AC-001",
    "title": "Access Control Policy",
    "description": "Comprehensive access control policy for all systems",
    "framework": "NIST CSF"
  }'
```
</details>

<details>
<summary><b>Python</b></summary>

```python
def create_control(control_id, title, description, framework):
    """Create a new tenant control."""
    url = f"{BASE_URL}/overlay/controls"
    payload = {
        "control_id": control_id,
        "title": title,
        "description": description,
        "framework": framework
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# Create a control
control = create_control(
    control_id="AC-001",
    title="Access Control Policy",
    description="Comprehensive access control policy for all systems",
    framework="NIST CSF"
)
print(f"Created control: {control['id']}")
```
</details>

<details>
<summary><b>TypeScript</b></summary>

```typescript
interface CreateControlRequest {
  control_id: string;
  title: string;
  description: string;
  framework: string;
}

interface CreateControlResponse {
  id: string;
  tenant_id: string;
  control_id: string;
  title: string;
  description: string;
  framework: string;
  created_at: string;
}

async function createControl(request: CreateControlRequest): Promise<CreateControlResponse> {
  const response = await client.post<CreateControlResponse>('/overlay/controls', request);
  return response.data;
}

// Usage
const control = await createControl({
  control_id: "AC-001",
  title: "Access Control Policy",
  description: "Comprehensive access control policy for all systems",
  framework: "NIST CSF"
});
console.log(`Created control: ${control.id}`);
```
</details>

### Get Control Details

<details>
<summary><b>cURL</b></summary>

```bash
CONTROL_ID="550e8400-e29b-41d4-a716-446655440000"

curl -X GET "$BASE_URL/overlay/controls/$CONTROL_ID" \
  -H "X-RegEngine-API-Key: $API_KEY"
```
</details>

<details>
<summary><b>Python</b></summary>

```python
def get_control_details(control_id):
    """Get detailed information about a control."""
    url = f"{BASE_URL}/overlay/controls/{control_id}"

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

# Get control details
details = get_control_details("550e8400-e29b-41d4-a716-446655440000")
print(f"Control: {details['control']['title']}")
print(f"Mappings: {details['summary']['total_mappings']}")
print(f"Products: {details['summary']['total_products']}")
```
</details>

## Products Management

### Create a Product

<details>
<summary><b>cURL</b></summary>

```bash
curl -X POST "$BASE_URL/overlay/products" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_name": "Crypto Trading Platform",
    "description": "Institutional cryptocurrency trading and custody",
    "product_type": "TRADING",
    "jurisdictions": ["US", "EU", "UK"]
  }'
```
</details>

<details>
<summary><b>Python</b></summary>

```python
def create_product(product_name, description, product_type, jurisdictions):
    """Create a new customer product."""
    url = f"{BASE_URL}/overlay/products"
    payload = {
        "product_name": product_name,
        "description": description,
        "product_type": product_type,
        "jurisdictions": jurisdictions
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# Create a product
product = create_product(
    product_name="Crypto Trading Platform",
    description="Institutional cryptocurrency trading and custody",
    product_type="TRADING",
    jurisdictions=["US", "EU", "UK"]
)
print(f"Created product: {product['id']}")
```
</details>

<details>
<summary><b>TypeScript</b></summary>

```typescript
type ProductType = 'TRADING' | 'LENDING' | 'CUSTODY' | 'PAYMENTS' | 'DERIVATIVES' | 'OTHER';

interface CreateProductRequest {
  product_name: string;
  description: string;
  product_type: ProductType;
  jurisdictions: string[];
}

interface CreateProductResponse {
  id: string;
  tenant_id: string;
  product_name: string;
  description: string;
  product_type: ProductType;
  jurisdictions: string[];
  created_at: string;
}

async function createProduct(request: CreateProductRequest): Promise<CreateProductResponse> {
  const response = await client.post<CreateProductResponse>('/overlay/products', request);
  return response.data;
}

// Usage
const product = await createProduct({
  product_name: "Crypto Trading Platform",
  description: "Institutional cryptocurrency trading and custody",
  product_type: "TRADING",
  jurisdictions: ["US", "EU", "UK"]
});
console.log(`Created product: ${product.id}`);
```
</details>

## Control Mappings

### Map Control to Provision

<details>
<summary><b>cURL</b></summary>

```bash
curl -X POST "$BASE_URL/overlay/mappings" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "control_id": "550e8400-e29b-41d4-a716-446655440000",
    "provision_hash": "abc123def456",
    "mapping_type": "IMPLEMENTS",
    "confidence": 0.95,
    "notes": "Our access control policy fully implements this requirement"
  }'
```
</details>

<details>
<summary><b>Python</b></summary>

```python
def map_control_to_provision(control_id, provision_hash, mapping_type, confidence, notes=None):
    """Map a control to a regulatory provision."""
    url = f"{BASE_URL}/overlay/mappings"
    payload = {
        "control_id": control_id,
        "provision_hash": provision_hash,
        "mapping_type": mapping_type,
        "confidence": confidence,
        "notes": notes
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# Create a mapping
mapping = map_control_to_provision(
    control_id="550e8400-e29b-41d4-a716-446655440000",
    provision_hash="abc123def456",
    mapping_type="IMPLEMENTS",
    confidence=0.95,
    notes="Our access control policy fully implements this requirement"
)
print(f"Created mapping: {mapping['id']}")
```
</details>

### Link Control to Product

<details>
<summary><b>cURL</b></summary>

```bash
curl -X POST "$BASE_URL/overlay/products/link-control" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "product-uuid-here",
    "control_id": "control-uuid-here"
  }'
```
</details>

<details>
<summary><b>Python</b></summary>

```python
def link_control_to_product(product_id, control_id):
    """Link a control to a product."""
    url = f"{BASE_URL}/overlay/products/link-control"
    payload = {
        "product_id": product_id,
        "control_id": control_id
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

# Link control to product
link = link_control_to_product(
    product_id="product-uuid-here",
    control_id="control-uuid-here"
)
print(f"Linked at: {link['created_at']}")
```
</details>

## Compliance Analysis

### Get Product Requirements

<details>
<summary><b>Python</b></summary>

```python
def get_product_requirements(product_id):
    """Get all regulatory requirements for a product."""
    url = f"{BASE_URL}/overlay/products/{product_id}/requirements"

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

# Get requirements
requirements = get_product_requirements("product-uuid-here")
print(f"Controls: {requirements['summary']['total_controls']}")
print(f"Mappings: {requirements['summary']['total_mappings']}")
print(f"Provisions: {requirements['summary']['total_provisions']}")
```
</details>

## Domain Endpoints

The ingestion service exposes domain-scoped, stateless endpoints with disclaimers and rate limiting. Include `X-Request-ID` to enable end-to-end correlation and expect `X-RateLimit-*` headers in responses.

### KYC – Basic Identity Validation

<details>
<summary><b>cURL</b></summary>

```bash
export BASE_URL="http://localhost:8000"
export API_KEY="$DEMO_KEY"

curl -sS -X POST "$BASE_URL/v1/kyc/validate" \
  -H "X-RegEngine-API-Key: $API_KEY" \
  -H "X-Request-ID: req-$(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Jane Q. Doe",
    "national_id": "123-45-6789",
    "date_of_birth": "1988-03-14",
    "country_code": "US"
  }' | jq .
```

Response includes headers:

```text
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 59
X-RateLimit-Reset: 1700000000
```

</details>

### AML – Watchlist Check (placeholder)

<details>
<summary><b>Python</b></summary>

```python
import requests, uuid

BASE_URL = "http://localhost:8000"
API_KEY = "your_demo_key"
headers = {
    "X-RegEngine-API-Key": API_KEY,
    "X-Request-ID": f"req-{uuid.uuid4()}",
    "Content-Type": "application/json",
}

payload = {
    "entity_name": "Acme Trading LLC",
    "jurisdiction_codes": ["US", "EU"],
}

r = requests.post(f"{BASE_URL}/v1/aml/watchlist", json=payload, headers=headers)
print(r.status_code, r.headers.get("X-RateLimit-Remaining"))
print(r.json())
```

</details>

### Privacy – Rule Lookup with Citations

<details>
<summary><b>TypeScript</b></summary>

```typescript
import axios from 'axios';

const client = axios.create({
  baseURL: 'http://localhost:8000',
  headers: { 'X-RegEngine-API-Key': process.env.DEMO_KEY || '', 'Content-Type': 'application/json' }
});

type PrivacyQuery = { concept: string; jurisdiction_code?: string };

async function lookupPrivacyRule(q: PrivacyQuery) {
  const res = await client.post('/v1/privacy/lookup', q);
  console.log('limit', res.headers['x-ratelimit-limit']);
  console.log('remaining', res.headers['x-ratelimit-remaining']);
  return res.data; // includes citations and rule_version
}

const data = await lookupPrivacyRule({ concept: 'data_retention', jurisdiction_code: 'EU' });
console.log(data);
```

</details>

### Filings – Schema Validation

<details>
<summary><b>cURL</b></summary>

```bash
curl -sS -X POST "http://localhost:8000/v1/filings/validate" \
  -H "X-RegEngine-API-Key: $DEMO_KEY" \
  -H "X-Request-ID: req-$(uuidgen)" \
  -H "Content-Type: application/json" \
  -d '{
    "filing_type": "ADV",
    "jurisdiction_code": "US",
    "fields": {"advisor_crd": "123456"}
  }' | jq .
```

Notes:
- Endpoints are stateless format checks; they do not provide legal advice.
- Rate limiting defaults to in-memory; set `RATE_LIMIT_BACKEND=redis` and `REDIS_URL` for production.
- Send `X-Request-ID` to correlate across HTTP → Kafka → Graph.

</details>

### Graph – Provisions By Request ID

Query provisions linked to a specific `request_id` (set via `X-Request-ID` during ingestion/NLP). Useful for audit and tracing.

```bash
curl -s "http://localhost:8300/v1/provisions/by-request?id=req-123456" | jq .
```

Returns a list of provisions with provenance fields including `request_id`, `source_uri`, and `rule_version`.

### Identify Compliance Gaps

<details>
<summary><b>Python</b></summary>

```python
def get_compliance_gaps(product_id, jurisdiction):
    """Identify unmapped regulatory provisions."""
    url = f"{BASE_URL}/overlay/products/{product_id}/compliance-gaps"
    params = {"jurisdiction": jurisdiction}

    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()

# Get gaps for US jurisdiction
gaps = get_compliance_gaps("product-uuid-here", "US")
print(f"Total provisions: {gaps['total_provisions']}")
print(f"Mapped: {gaps['mapped_provisions']}")
print(f"Coverage: {gaps['coverage_percentage']}%")
print(f"\nUnmapped provisions: {len(gaps['unmapped_provisions'])}")
for provision in gaps['unmapped_provisions'][:5]:  # Show first 5
    print(f"  - {provision.get('title', 'N/A')}")
```
</details>

## Complete Workflow Example

### Python Script: Full Compliance Setup

```python
#!/usr/bin/env python3
"""
Complete RegEngine compliance setup workflow.
This script demonstrates the full process of setting up compliance tracking.
"""

import requests
from typing import List, Dict, Any

API_KEY = "your_api_key_here"
BASE_URL = "https://api.regengine.example.com"

headers = {
    "X-RegEngine-API-Key": API_KEY,
    "Content-Type": "application/json"
}

class RegEngineClient:
    """RegEngine API client."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.headers = {
            "X-RegEngine-API-Key": api_key,
            "Content-Type": "application/json"
        }

    def create_control(self, control_id: str, title: str, description: str, framework: str) -> Dict[str, Any]:
        """Create a tenant control."""
        url = f"{self.base_url}/overlay/controls"
        payload = {
            "control_id": control_id,
            "title": title,
            "description": description,
            "framework": framework
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def create_product(self, product_name: str, description: str, product_type: str, jurisdictions: List[str]) -> Dict[str, Any]:
        """Create a customer product."""
        url = f"{self.base_url}/overlay/products"
        payload = {
            "product_name": product_name,
            "description": description,
            "product_type": product_type,
            "jurisdictions": jurisdictions
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def map_control(self, control_id: str, provision_hash: str, mapping_type: str, confidence: float, notes: str = None) -> Dict[str, Any]:
        """Map a control to a provision."""
        url = f"{self.base_url}/overlay/mappings"
        payload = {
            "control_id": control_id,
            "provision_hash": provision_hash,
            "mapping_type": mapping_type,
            "confidence": confidence,
            "notes": notes
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def link_control_to_product(self, product_id: str, control_id: str) -> Dict[str, Any]:
        """Link a control to a product."""
        url = f"{self.base_url}/overlay/products/link-control"
        payload = {
            "product_id": product_id,
            "control_id": control_id
        }
        response = requests.post(url, headers=self.headers, json=payload)
        response.raise_for_status()
        return response.json()

    def get_compliance_gaps(self, product_id: str, jurisdiction: str) -> Dict[str, Any]:
        """Get compliance gaps for a product."""
        url = f"{self.base_url}/overlay/products/{product_id}/compliance-gaps"
        params = {"jurisdiction": jurisdiction}
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        return response.json()

def main():
    """Main workflow."""
    client = RegEngineClient(BASE_URL, API_KEY)

    print("🚀 Starting compliance setup workflow...\n")

    # Step 1: Create controls
    print("Step 1: Creating controls...")
    control1 = client.create_control(
        control_id="AC-001",
        title="Access Control Policy",
        description="Comprehensive access control policy for all systems",
        framework="NIST CSF"
    )
    print(f"✅ Created control: {control1['control_id']}")

    control2 = client.create_control(
        control_id="RM-001",
        title="Risk Assessment Process",
        description="Quarterly risk assessments for all trading operations",
        framework="NIST CSF"
    )
    print(f"✅ Created control: {control2['control_id']}\n")

    # Step 2: Create product
    print("Step 2: Creating product...")
    product = client.create_product(
        product_name="Crypto Trading Platform",
        description="Institutional cryptocurrency trading and custody",
        product_type="TRADING",
        jurisdictions=["US", "EU"]
    )
    print(f"✅ Created product: {product['product_name']}\n")

    # Step 3: Link controls to product
    print("Step 3: Linking controls to product...")
    client.link_control_to_product(product['id'], control1['id'])
    client.link_control_to_product(product['id'], control2['id'])
    print(f"✅ Linked {2} controls to product\n")

    # Step 4: Map controls to provisions (example with dummy hash)
    print("Step 4: Mapping controls to provisions...")
    # In real usage, you'd get provision_hash from RegEngine's provision search
    # client.map_control(
    #     control_id=control1['id'],
    #     provision_hash="abc123def456",
    #     mapping_type="IMPLEMENTS",
    #     confidence=0.95,
    #     notes="Fully implements access control requirements"
    # )
    print("⚠️  Skipping provision mapping (requires actual provision hashes)\n")

    # Step 5: Check compliance gaps
    print("Step 5: Analyzing compliance gaps...")
    gaps = client.get_compliance_gaps(product['id'], "US")
    print(f"📊 Compliance Coverage:")
    print(f"   Total provisions: {gaps['total_provisions']}")
    print(f"   Mapped: {gaps['mapped_provisions']}")
    print(f"   Coverage: {gaps['coverage_percentage']:.1f}%\n")

    print("✅ Compliance setup workflow complete!")

if __name__ == "__main__":
    main()
```

### TypeScript: React Hook for Controls

```typescript
import { useState, useEffect } from 'react';
import axios from 'axios';

const API_KEY = process.env.NEXT_PUBLIC_REGENGINE_API_KEY;
const BASE_URL = process.env.NEXT_PUBLIC_REGENGINE_API_URL;

const client = axios.create({
  baseURL: BASE_URL,
  headers: {
    'X-RegEngine-API-Key': API_KEY,
    'Content-Type': 'application/json'
  }
});

export function useControls(framework?: string) {
  const [controls, setControls] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchControls() {
      try {
        const params = framework ? { framework } : {};
        const response = await client.get('/overlay/controls', { params });
        setControls(response.data.controls);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchControls();
  }, [framework]);

  const createControl = async (control) => {
    const response = await client.post('/overlay/controls', control);
    setControls([...controls, response.data]);
    return response.data;
  };

  return { controls, loading, error, createControl };
}

// Usage in a component
function ControlsList() {
  const { controls, loading, error, createControl } = useControls('NIST CSF');

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;

  return (
    <div>
      <h2>Controls ({controls.length})</h2>
      <ul>
        {controls.map(control => (
          <li key={control.id}>{control.title}</li>
        ))}
      </ul>
    </div>
  );
}
```

## Error Handling

### Python

```python
from requests.exceptions import HTTPError

try:
    control = create_control(...)
except HTTPError as e:
    if e.response.status_code == 401:
        print("Authentication failed. Check your API key.")
    elif e.response.status_code == 429:
        print("Rate limit exceeded. Please wait before retrying.")
        retry_after = e.response.headers.get('Retry-After')
        print(f"Retry after: {retry_after} seconds")
    elif e.response.status_code == 400:
        print(f"Bad request: {e.response.json()}")
    else:
        print(f"Error: {e}")
```

### TypeScript

```typescript
try {
  const control = await createControl({...});
} catch (error) {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 401) {
      console.error('Authentication failed. Check your API key.');
    } else if (error.response?.status === 429) {
      const retryAfter = error.response.headers['retry-after'];
      console.error(`Rate limit exceeded. Retry after ${retryAfter}s`);
    } else if (error.response?.status === 400) {
      console.error('Bad request:', error.response.data);
    }
  }
}
```

## Rate Limiting

All API responses include rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1700000000
```

### Python: Respecting Rate Limits

```python
import time

def make_request_with_retry(func, *args, **kwargs):
    """Make request with automatic retry on rate limit."""
    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:
        try:
            return func(*args, **kwargs)
        except HTTPError as e:
            if e.response.status_code == 429:
                retry_after = int(e.response.headers.get('Retry-After', 60))
                print(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                retry_count += 1
            else:
                raise

    raise Exception("Max retries exceeded")

# Usage
control = make_request_with_retry(create_control, "AC-001", "Title", "Description", "NIST CSF")
```

## Next Steps

- Review the [Onboarding Guide](./ONBOARDING_GUIDE.md) for conceptual overview
- Visit the [API Documentation](https://api.regengine.example.com/docs) for interactive testing
- Check out example integrations in the `examples/` directory
