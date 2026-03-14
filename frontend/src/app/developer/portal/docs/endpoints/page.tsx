'use client';

import { Code2, Shield, AlertCircle, Zap } from 'lucide-react';
import { EndpointCard } from '@/components/developer/EndpointCard';

export default function EndpointsPage() {
  return (
    <div style={{ background: 'var(--re-surface-base)', color: 'var(--re-text-primary)' }}>
      {/* Header */}
      <div style={{ padding: 'clamp(1.5rem, 5vw, 40px) clamp(1rem, 4vw, 32px)', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <h1 style={{ fontSize: 'clamp(1.5rem, 4vw, 2rem)', fontWeight: 700, margin: '0 0 8px 0' }}>API Reference</h1>
        <p style={{ color: 'var(--re-text-muted)', margin: 0, fontSize: '16px' }}>
          FSMA 204 food traceability endpoints for supply chain visibility and compliance
        </p>
      </div>

      {/* Base URL Callout */}
      <div
        style={{
          margin: 'clamp(1rem, 4vw, 32px)',
          padding: 'clamp(0.75rem, 3vw, 16px)',
          background: 'rgba(16, 185, 129, 0.08)',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          borderRadius: '8px',
        }}
      >
        <p style={{ color: 'var(--re-brand)', fontWeight: 600, margin: '0 0 8px 0' }}>Base URL</p>
        <code style={{ color: 'var(--re-text-primary)', fontFamily: 'monospace', fontSize: '14px' }}>
          https://api.regengine.co
        </code>
      </div>

      {/* Ingestion API Section */}
      <div style={{ padding: '0 clamp(1rem, 4vw, 32px)' }}>
        <div style={{ marginTop: 'clamp(1.5rem, 5vw, 48px)', marginBottom: 'clamp(1rem, 4vw, 32px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <Zap size={24} style={{ color: 'var(--re-brand)' }} />
            <h2 style={{ fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 700, margin: 0 }}>Ingestion API</h2>
          </div>
          <p style={{ color: 'var(--re-text-muted)', margin: '0', fontSize: '14px' }}>
            Ingest Critical Tracking Events and EPCIS 2.0 data into RegEngine
          </p>
        </div>
        {/* Endpoint: POST /api/v1/webhooks/ingest */}
        <EndpointCard
          method="POST"
          endpoint="/api/v1/webhooks/ingest"
          title="Ingest Critical Tracking Events"
          description="Batch ingest Critical Tracking Events (CTE) for food items. Each event creates an immutable record in the supply chain."
          parameters={[
            { name: 'events', type: 'array', required: true, description: 'Array of CTE event objects' },
            { name: 'source', type: 'string', required: false, description: "Source system identifier (e.g., 'erp', 'wms')" },
          ]}
          responseExample={{
            accepted: 42,
            rejected: 2,
            events: [
              { id: 'evt_1a2b3c', timestamp: '2025-03-14T10:30:00Z', status: 'processed' },
            ],
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X POST https://api.regengine.co/api/v1/webhooks/ingest \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [
      {
        "product_gtin": "00012345678905",
        "lot_code": "LOT2025031401",
        "quantity": 100,
        "unit": "cases",
        "location_gln": "5412345000013",
        "timestamp": "2025-03-14T10:30:00Z",
        "event_type": "receiving"
      }
    ],
    "source": "erp"
  }'`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "events": [
        {
            "product_gtin": "00012345678905",
            "lot_code": "LOT2025031401",
            "quantity": 100,
            "unit": "cases",
            "location_gln": "5412345000013",
            "timestamp": "2025-03-14T10:30:00Z",
            "event_type": "receiving"
        }
    ],
    "source": "erp"
}

response = requests.post(
    "https://api.regengine.co/api/v1/webhooks/ingest",
    json=payload,
    headers=headers
)
print(response.json())`,
            },
            {
              language: 'javascript',
              label: 'Node.js',
              code: `const fetch = require('node-fetch');

const apiKey = process.env.REGENGINE_API_KEY;
const headers = {
  'Authorization': \`Bearer \${apiKey}\`,
  'Content-Type': 'application/json'
};

const payload = {
  events: [
    {
      product_gtin: '00012345678905',
      lot_code: 'LOT2025031401',
      quantity: 100,
      unit: 'cases',
      location_gln: '5412345000013',
      timestamp: '2025-03-14T10:30:00Z',
      event_type: 'receiving'
    }
  ],
  source: 'erp'
};

fetch('https://api.regengine.co/api/v1/webhooks/ingest', {
  method: 'POST',
  headers,
  body: JSON.stringify(payload)
})
  .then(res => res.json())
  .then(data => console.log(data));`,
            },
            {
              language: 'go',
              label: 'Go',
              code: `package main

import (
  "bytes"
  "encoding/json"
  "fmt"
  "net/http"
)

type Event struct {
  ProductGTIN string \`json:"product_gtin"\`
  LotCode    string \`json:"lot_code"\`
  Quantity   int    \`json:"quantity"\`
  Unit       string \`json:"unit"\`
  LocationGLN string \`json:"location_gln"\`
  Timestamp  string \`json:"timestamp"\`
  EventType  string \`json:"event_type"\`
}

type Payload struct {
  Events []Event \`json:"events"\`
  Source string  \`json:"source"\`
}

payload := Payload{
  Events: []Event{
    {
      ProductGTIN: "00012345678905",
      LotCode:     "LOT2025031401",
      Quantity:    100,
      Unit:        "cases",
      LocationGLN: "5412345000013",
      Timestamp:   "2025-03-14T10:30:00Z",
      EventType:   "receiving",
    },
  },
  Source: "erp",
}

jsonData, _ := json.Marshal(payload)
req, _ := http.NewRequest("POST", "https://api.regengine.co/api/v1/webhooks/ingest", bytes.NewBuffer(jsonData))
req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", os.Getenv("REGENGINE_API_KEY")))
req.Header.Set("Content-Type", "application/json")

client := &http.Client{}
resp, _ := client.Do(req)
fmt.Println(resp.Status)`,
            },
          ]}
        />

        {/* Endpoint: POST /api/v1/epcis/events */}
        <EndpointCard
          method="POST"
          endpoint="/api/v1/epcis/events"
          title="Ingest EPCIS 2.0 Events"
          description="Ingest EPCIS 2.0 standard event documents for advanced traceability workflows."
          parameters={[
            { name: 'epcisBody', type: 'object', required: true, description: 'EPCIS 2.0 document body' },
          ]}
          responseExample={{
            event_id: 'epcis_evt_5f6g7h',
            status: 'ingested',
            timestamp: '2025-03-14T11:15:00Z',
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X POST https://api.regengine.co/api/v1/epcis/events \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "EPCISDocument",
    "schemaVersion": "2.0",
    "creationDate": "2025-03-14T11:15:00Z",
    "eventList": [
      {
        "type": "ObjectEvent",
        "eventID": "urn:uuid:3a1fcc38-39c7-4471-9fb8-8ce09e5cfbfa",
        "eventTime": "2025-03-14T11:15:00Z",
        "action": "OBSERVE",
        "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
        "bizLocation": "urn:epc:id:sgln:0614141.00000.0",
        "readPoint": "urn:epc:id:sgln:0614141.00001.0"
      }
    ]
  }'`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests
import json

api_key = "YOUR_API_KEY"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

epcis_doc = {
    "type": "EPCISDocument",
    "schemaVersion": "2.0",
    "creationDate": "2025-03-14T11:15:00Z",
    "eventList": [
        {
            "type": "ObjectEvent",
            "eventID": "urn:uuid:3a1fcc38-39c7-4471-9fb8-8ce09e5cfbfa",
            "eventTime": "2025-03-14T11:15:00Z",
            "action": "OBSERVE",
            "epcList": ["urn:epc:id:sgtin:0614141.107346.2017"],
            "bizLocation": "urn:epc:id:sgln:0614141.00000.0",
            "readPoint": "urn:epc:id:sgln:0614141.00001.0"
        }
    ]
}

response = requests.post(
    "https://api.regengine.co/api/v1/epcis/events",
    json=epcis_doc,
    headers=headers
)
print(response.json())`,
            },
          ]}
        />

        {/* Endpoint: GET /api/v1/epcis/events/:id */}
        <EndpointCard
          method="GET"
          endpoint="/api/v1/epcis/events/:id"
          title="Get Event by ID"
          description="Retrieve a single event by its unique ID for inspection or audit purposes."
          parameters={[
            { name: 'id', type: 'string', required: true, description: 'Event UUID' },
          ]}
          responseExample={{
            id: 'evt_abc123xyz',
            product_gtin: '00012345678905',
            lot_code: 'LOT2025031401',
            location_gln: '5412345000013',
            timestamp: '2025-03-14T10:30:00Z',
            event_type: 'receiving',
            quantity: 100,
            status: 'processed',
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X GET https://api.regengine.co/api/v1/epcis/events/evt_abc123xyz \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json"`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
event_id = "evt_abc123xyz"
headers = {"Authorization": f"Bearer {api_key}"}

response = requests.get(
    f"https://api.regengine.co/api/v1/epcis/events/{event_id}",
    headers=headers
)
print(response.json())`,
            },
            {
              language: 'javascript',
              label: 'Node.js',
              code: `const fetch = require('node-fetch');

const apiKey = process.env.REGENGINE_API_KEY;
const eventId = 'evt_abc123xyz';
const headers = {
  'Authorization': \`Bearer \${apiKey}\`
};

fetch(\`https://api.regengine.co/api/v1/epcis/events/\${eventId}\`, {
  method: 'GET',
  headers
})
  .then(res => res.json())
  .then(data => console.log(data));`,
            },
          ]}
        />
      </div>

      {/* Compliance API Section */}
      <div style={{ padding: '0 clamp(1rem, 4vw, 32px)' }}>
        <div style={{ marginTop: 'clamp(1.5rem, 5vw, 48px)', marginBottom: 'clamp(1rem, 4vw, 32px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <Shield size={24} style={{ color: 'var(--re-brand)' }} />
            <h2 style={{ fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 700, margin: 0 }}>Compliance API</h2>
          </div>
          <p style={{ color: 'var(--re-text-muted)', margin: '0', fontSize: '14px' }}>
            FSMA 204 compliance scoring, FDA export, and event chain verification
          </p>
        </div>

        {/* Endpoint: GET /api/v1/compliance/score/:tenant_id */}
        <EndpointCard
          method="GET"
          endpoint="/api/v1/compliance/score/:tenant_id"
          title="Get Compliance Risk Score"
          description="Calculate real-time FSMA 204 compliance score for a tenant. Score 0-100, lower is better."
          parameters={[
            { name: 'tenant_id', type: 'string', required: true, description: 'Tenant UUID' },
          ]}
          responseExample={{
            score: 28,
            grade: 'A',
            breakdown: {
              traceability: 95,
              coverage: 87,
              timeliness: 72,
              data_quality: 65,
            },
            timestamp: '2025-03-14T12:00:00Z',
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X GET https://api.regengine.co/api/v1/compliance/score/tenant_xyz789 \\
  -H "Authorization: Bearer YOUR_API_KEY"`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
tenant_id = "tenant_xyz789"
headers = {"Authorization": f"Bearer {api_key}"}

response = requests.get(
    f"https://api.regengine.co/api/v1/compliance/score/{tenant_id}",
    headers=headers
)
data = response.json()
print(f"Score: {data['score']}, Grade: {data['grade']}")
print(f"Breakdown: {data['breakdown']}")`,
            },
            {
              language: 'javascript',
              label: 'Node.js',
              code: `const fetch = require('node-fetch');

const apiKey = process.env.REGENGINE_API_KEY;
const tenantId = 'tenant_xyz789';
const headers = { 'Authorization': \`Bearer \${apiKey}\` };

fetch(\`https://api.regengine.co/api/v1/compliance/score/\${tenantId}\`, { headers })
  .then(res => res.json())
  .then(data => {
    console.log(\`Score: \${data.score}, Grade: \${data.grade}\`);
    console.log('Breakdown:', data.breakdown);
  });`,
            },
          ]}
        />

        {/* Endpoint: GET /api/v1/fda/export */}
        <EndpointCard
          method="GET"
          endpoint="/api/v1/fda/export"
          title="Export FDA Compliance Package"
          description="Generate FDA-ready compliance export in JSON or CSV format for regulatory filing."
          parameters={[
            { name: 'format', type: 'string', required: false, description: "'json' or 'csv', default json" },
            { name: 'date_from', type: 'string', required: false, description: 'ISO 8601 start date' },
            { name: 'date_to', type: 'string', required: false, description: 'ISO 8601 end date' },
          ]}
          responseExample={{
            format: 'json',
            export_id: 'exp_2025031401',
            records: 1247,
            date_range: { from: '2025-01-01', to: '2025-03-14' },
            download_url: 'https://api.regengine.co/exports/exp_2025031401.json',
            expires_at: '2025-03-21T12:00:00Z',
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X GET "https://api.regengine.co/api/v1/fda/export?format=json&date_from=2025-01-01&date_to=2025-03-14" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -o fda_export.json`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
headers = {"Authorization": f"Bearer {api_key}"}
params = {
    "format": "json",
    "date_from": "2025-01-01",
    "date_to": "2025-03-14"
}

response = requests.get(
    "https://api.regengine.co/api/v1/fda/export",
    headers=headers,
    params=params
)
data = response.json()
print(f"Records: {data['records']}")
print(f"Download: {data['download_url']}")`,
            },
          ]}
        />

        {/* Endpoint: GET /api/v1/epcis/chain/verify */}
        <EndpointCard
          method="GET"
          endpoint="/api/v1/epcis/chain/verify"
          title="Verify Event Chain Integrity"
          description="Cryptographically verify the integrity of an event chain for a specific lot code."
          parameters={[
            { name: 'lot_code', type: 'string', required: true, description: 'Product lot code' },
          ]}
          responseExample={{
            lot_code: 'LOT2025031401',
            chain_valid: true,
            event_count: 7,
            chain_hash: 'sha256_abc123',
            timestamps: {
              first_event: '2025-03-01T08:00:00Z',
              last_event: '2025-03-14T14:22:00Z',
            },
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X GET "https://api.regengine.co/api/v1/epcis/chain/verify?lot_code=LOT2025031401" \\
  -H "Authorization: Bearer YOUR_API_KEY"`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
headers = {"Authorization": f"Bearer {api_key}"}
params = {"lot_code": "LOT2025031401"}

response = requests.get(
    "https://api.regengine.co/api/v1/epcis/chain/verify",
    headers=headers,
    params=params
)
result = response.json()
if result['chain_valid']:
    print(f"Chain verified: {result['event_count']} events")
else:
    print("Chain validation failed")`,
            },
            {
              language: 'javascript',
              label: 'Node.js',
              code: `const fetch = require('node-fetch');

const apiKey = process.env.REGENGINE_API_KEY;
const lotCode = 'LOT2025031401';
const headers = { 'Authorization': \`Bearer \${apiKey}\` };

fetch(\`https://api.regengine.co/api/v1/epcis/chain/verify?lot_code=\${lotCode}\`, { headers })
  .then(res => res.json())
  .then(data => {
    if (data.chain_valid) {
      console.log(\`Chain verified: \${data.event_count} events\`);
    } else {
      console.log('Chain validation failed');
    }
  });`,
            },
          ]}
        />
      </div>

      {/* Recall & Simulation Section */}
      <div style={{ padding: '0 clamp(1rem, 4vw, 32px)' }}>
        <div style={{ marginTop: 'clamp(1.5rem, 5vw, 48px)', marginBottom: 'clamp(1rem, 4vw, 32px)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
            <AlertCircle size={24} style={{ color: 'var(--re-brand)' }} />
            <h2 style={{ fontSize: 'clamp(1.25rem, 3vw, 1.5rem)', fontWeight: 700, margin: 0 }}>Recall & Simulation</h2>
          </div>
          <p style={{ color: 'var(--re-text-muted)', margin: '0', fontSize: '14px' }}>
            Run recall simulations and decode barcodes for rapid traceability drills
          </p>
        </div>

        {/* Endpoint: POST /api/v1/recall-simulations/run */}
        <EndpointCard
          method="POST"
          endpoint="/api/v1/recall-simulations/run"
          title="Run Recall Simulation Drill"
          description="Execute a recall simulation to test traceability readiness and measure scope impact."
          parameters={[
            { name: 'lot_code', type: 'string', required: true, description: 'Lot code to trace' },
            { name: 'depth', type: 'number', required: false, description: 'Trace depth, default 3' },
          ]}
          responseExample={{
            simulation_id: 'sim_drill_20250314',
            lot_code: 'LOT2025031401',
            depth: 3,
            total_affected_units: 5240,
            affected_locations: 12,
            upstream_suppliers: 4,
            downstream_customers: 18,
            recall_duration_hours: 2.5,
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X POST https://api.regengine.co/api/v1/recall-simulations/run \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "lot_code": "LOT2025031401",
    "depth": 3
  }'`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "lot_code": "LOT2025031401",
    "depth": 3
}

response = requests.post(
    "https://api.regengine.co/api/v1/recall-simulations/run",
    json=payload,
    headers=headers
)
result = response.json()
print(f"Simulation ID: {result['simulation_id']}")
print(f"Affected units: {result['total_affected_units']}")
print(f"Duration: {result['recall_duration_hours']} hours")`,
            },
            {
              language: 'javascript',
              label: 'Node.js',
              code: `const fetch = require('node-fetch');

const apiKey = process.env.REGENGINE_API_KEY;
const headers = {
  'Authorization': \`Bearer \${apiKey}\`,
  'Content-Type': 'application/json'
};

const payload = {
  lot_code: 'LOT2025031401',
  depth: 3
};

fetch('https://api.regengine.co/api/v1/recall-simulations/run', {
  method: 'POST',
  headers,
  body: JSON.stringify(payload)
})
  .then(res => res.json())
  .then(data => {
    console.log(\`Simulation: \${data.simulation_id}\`);
    console.log(\`Affected units: \${data.total_affected_units}\`);
  });`,
            },
          ]}
        />

        {/* Endpoint: POST /api/v1/qr/decode */}
        <EndpointCard
          method="POST"
          endpoint="/api/v1/qr/decode"
          title="Decode GS1/GTIN Barcode"
          description="Parse and decode GS1 or GTIN barcodes to extract product and lot information."
          parameters={[
            { name: 'barcode', type: 'string', required: true, description: 'GS1/GTIN barcode string' },
          ]}
          responseExample={{
            barcode_format: 'GTIN-14',
            product_gtin: '00012345678905',
            lot_code: 'LOT2025031401',
            serial_number: 'SN789456',
            valid: true,
            parsed: {
              ai_01: '00012345678905',
              ai_10: 'LOT2025031401',
              ai_21: 'SN789456',
            },
          }}
          snippets={[
            {
              language: 'bash',
              label: 'curl',
              code: `curl -X POST https://api.regengine.co/api/v1/qr/decode \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "barcode": "(01)00012345678905(10)LOT2025031401(21)SN789456"
  }'`,
            },
            {
              language: 'python',
              label: 'Python',
              code: `import requests

api_key = "YOUR_API_KEY"
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}

payload = {
    "barcode": "(01)00012345678905(10)LOT2025031401(21)SN789456"
}

response = requests.post(
    "https://api.regengine.co/api/v1/qr/decode",
    json=payload,
    headers=headers
)
result = response.json()
if result['valid']:
    print(f"GTIN: {result['product_gtin']}")
    print(f"Lot: {result['lot_code']}")
else:
    print("Invalid barcode format")`,
            },
            {
              language: 'javascript',
              label: 'Node.js',
              code: `const fetch = require('node-fetch');

const apiKey = process.env.REGENGINE_API_KEY;
const headers = {
  'Authorization': \`Bearer \${apiKey}\`,
  'Content-Type': 'application/json'
};

const payload = {
  barcode: '(01)00012345678905(10)LOT2025031401(21)SN789456'
};

fetch('https://api.regengine.co/api/v1/qr/decode', {
  method: 'POST',
  headers,
  body: JSON.stringify(payload)
})
  .then(res => res.json())
  .then(data => {
    if (data.valid) {
      console.log(\`GTIN: \${data.product_gtin}\`);
      console.log(\`Lot: \${data.lot_code}\`);
    } else {
      console.log('Invalid barcode');
    }
  });`,
            },
          ]}
        />
      </div>

      {/* Footer */}
      <div style={{ padding: 'clamp(1.5rem, 5vw, 48px) clamp(1rem, 4vw, 32px)', borderTop: '1px solid rgba(255,255,255,0.06)', marginTop: 'clamp(1.5rem, 5vw, 48px)' }}>
        <p style={{ color: 'var(--re-text-muted)', fontSize: '14px', margin: 0 }}>
          Need help? Email support@regengine.co or visit our{' '}
          <a href="#" style={{ color: 'var(--re-brand)', textDecoration: 'none' }}>documentation</a>.
        </p>
      </div>
    </div>
  );
}