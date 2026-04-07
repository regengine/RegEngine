'use client';

import { useState } from 'react';
import { CodeBlock } from '@/components/developer/CodeBlock';

const OPERATIONS = [
  { id: 'ingest', label: 'Ingest Webhook Events', method: 'POST', path: '/api/v1/webhooks/ingest' },
  { id: 'fda-export', label: 'FDA Export (by TLC)', method: 'GET', path: '/api/v1/fda/export' },
  { id: 'fda-export-all', label: 'FDA Export (full tenant)', method: 'GET', path: '/api/v1/fda/export/all' },
  { id: 'compliance', label: 'Get Compliance Score', method: 'GET', path: '/api/v1/compliance/score/{tenant_id}' },
  { id: 'chain-verify', label: 'Verify Chain Integrity', method: 'POST', path: '/api/v1/chain/verify-all' },
  { id: 'sla-dashboard', label: 'SLA Dashboard', method: 'GET', path: '/api/v1/sla/dashboard/{tenant_id}' },
  { id: 'health', label: 'Health Check', method: 'GET', path: '/api/v1/monitoring/health/{tenant_id}' },
  { id: 'csv-template', label: 'CSV Template Download', method: 'GET', path: '/api/v1/templates/{cte_type}' },
  { id: 'portal-link', label: 'Create Supplier Portal Link', method: 'POST', path: '/api/v1/portal/links' },
  { id: 'merkle-root', label: 'Get Merkle Root', method: 'GET', path: '/api/v1/fda/export/merkle-root' },
];

function generateSnippets(op: typeof OPERATIONS[0], apiKey: string, tenantId: string) {
  const key = apiKey || 'YOUR_API_KEY';
  const tid = tenantId || 'YOUR_TENANT_ID';
  const base = process.env.NEXT_PUBLIC_API_BASE_URL || 'https://api.regengine.co';

  const snippets: Record<string, Record<string, string>> = {
    ingest: {
      curl: `curl -X POST ${base}/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [{
      "cte_type": "receiving",
      "traceability_lot_code": "LOT-2026-001",
      "product_description": "Romaine Lettuce",
      "quantity": 500,
      "unit_of_measure": "cases"
    }]
  }'`,
      python: `import requests

response = requests.post(
    "${base}/api/v1/webhooks/ingest",
    headers={
        "X-RegEngine-API-Key": "${key}",
        "Content-Type": "application/json",
    },
    json={
        "events": [{
            "cte_type": "receiving",
            "traceability_lot_code": "LOT-2026-001",
            "product_description": "Romaine Lettuce",
            "quantity": 500,
            "unit_of_measure": "cases",
        }]
    },
)
print(response.json())`,
      node: `const response = await fetch('${base}/api/v1/webhooks/ingest', {
  method: 'POST',
  headers: {
    'X-RegEngine-API-Key': '${key}',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    events: [{
      cte_type: 'receiving',
      traceability_lot_code: 'LOT-2026-001',
      product_description: 'Romaine Lettuce',
      quantity: 500,
      unit_of_measure: 'cases',
    }],
  }),
});
const data = await response.json();
console.log(data);`,
    },
    'fda-export': {
      curl: `curl -X GET "${base}/api/v1/fda/export?tlc=LOT-2026-001&tenant_id=${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
      python: `import requests

response = requests.get(
    "${base}/api/v1/fda/export",
    headers={"X-RegEngine-API-Key": "${key}"},
    params={"tlc": "LOT-2026-001", "tenant_id": "${tid}"},
)
print(response.json())`,
      node: `const params = new URLSearchParams({ tlc: 'LOT-2026-001', tenant_id: '${tid}' });
const response = await fetch(\`${base}/api/v1/fda/export?\${params}\`, {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const data = await response.json();
console.log(data);`,
    },
    'fda-export-all': {
      curl: `curl -X GET "${base}/api/v1/fda/export/all?tenant_id=${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
      python: `import requests

response = requests.get(
    "${base}/api/v1/fda/export/all",
    headers={"X-RegEngine-API-Key": "${key}"},
    params={"tenant_id": "${tid}"},
)
print(response.json())`,
      node: `const response = await fetch(\`${base}/api/v1/fda/export/all?tenant_id=${tid}\`, {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const data = await response.json();
console.log(data);`,
    },
    compliance: {
      curl: `curl -X GET "${base}/api/v1/compliance/score/${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
      python: `import requests

response = requests.get(
    f"${base}/api/v1/compliance/score/${tid}",
    headers={"X-RegEngine-API-Key": "${key}"},
)
score = response.json()
print(f"Score: {score.get('compliance_score')}/100")`,
      node: `const response = await fetch('${base}/api/v1/compliance/score/${tid}', {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const score = await response.json();
console.log(\`Score: \${score.compliance_score}/100\`);`,
    },
    'chain-verify': {
      curl: `curl -X POST ${base}/api/v1/chain/verify-all \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "Content-Type: application/json"`,
      python: `import requests

response = requests.post(
    "${base}/api/v1/chain/verify-all",
    headers={
        "X-RegEngine-API-Key": "${key}",
        "Content-Type": "application/json",
    },
)
result = response.json()
print(f"Chain valid: {result.get('valid')}")`,
      node: `const response = await fetch('${base}/api/v1/chain/verify-all', {
  method: 'POST',
  headers: {
    'X-RegEngine-API-Key': '${key}',
    'Content-Type': 'application/json',
  },
});
const result = await response.json();
console.log(\`Chain valid: \${result.valid}\`);`,
    },
    'sla-dashboard': {
      curl: `curl -X GET "${base}/api/v1/sla/dashboard/${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
      python: `import requests

response = requests.get(
    f"${base}/api/v1/sla/dashboard/${tid}",
    headers={"X-RegEngine-API-Key": "${key}"},
)
dashboard = response.json()
print(dashboard)`,
      node: `const response = await fetch('${base}/api/v1/sla/dashboard/${tid}', {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const dashboard = await response.json();
console.log(dashboard);`,
    },
    health: {
      curl: `curl -X GET "${base}/api/v1/monitoring/health/${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
      python: `import requests

response = requests.get(
    f"${base}/api/v1/monitoring/health/${tid}",
    headers={"X-RegEngine-API-Key": "${key}"},
)
health = response.json()
print(f"Status: {health.get('status')}")`,
      node: `const response = await fetch('${base}/api/v1/monitoring/health/${tid}', {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const health = await response.json();
console.log(\`Status: \${health.status}\`);`,
    },
    'csv-template': {
      curl: `curl -X GET "${base}/api/v1/templates/receiving" \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -o receiving_template.csv`,
      python: `import requests

response = requests.get(
    "${base}/api/v1/templates/receiving",
    headers={"X-RegEngine-API-Key": "${key}"},
)
with open("receiving_template.csv", "wb") as f:
    f.write(response.content)
print("Template saved to receiving_template.csv")`,
      node: `const response = await fetch('${base}/api/v1/templates/receiving', {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const blob = await response.blob();
// Save blob to file (Node.js)
const fs = await import('fs');
fs.writeFileSync('receiving_template.csv', Buffer.from(await blob.arrayBuffer()));
console.log('Template saved');`,
    },
    'portal-link': {
      curl: `curl -X POST ${base}/api/v1/portal/links \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "supplier_name": "Acme Farms",
    "cte_types": ["receiving", "shipping"],
    "expires_in_days": 30
  }'`,
      python: `import requests

response = requests.post(
    "${base}/api/v1/portal/links",
    headers={
        "X-RegEngine-API-Key": "${key}",
        "Content-Type": "application/json",
    },
    json={
        "supplier_name": "Acme Farms",
        "cte_types": ["receiving", "shipping"],
        "expires_in_days": 30,
    },
)
link = response.json()
print(f"Portal link: {link.get('url')}")`,
      node: `const response = await fetch('${base}/api/v1/portal/links', {
  method: 'POST',
  headers: {
    'X-RegEngine-API-Key': '${key}',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    supplier_name: 'Acme Farms',
    cte_types: ['receiving', 'shipping'],
    expires_in_days: 30,
  }),
});
const link = await response.json();
console.log(\`Portal link: \${link.url}\`);`,
    },
    'merkle-root': {
      curl: `curl -X GET "${base}/api/v1/fda/export/merkle-root?tenant_id=${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
      python: `import requests

response = requests.get(
    "${base}/api/v1/fda/export/merkle-root",
    headers={"X-RegEngine-API-Key": "${key}"},
    params={"tenant_id": "${tid}"},
)
result = response.json()
print(f"Merkle root: {result.get('merkle_root')}")`,
      node: `const response = await fetch(\`${base}/api/v1/fda/export/merkle-root?tenant_id=${tid}\`, {
  headers: { 'X-RegEngine-API-Key': '${key}' },
});
const result = await response.json();
console.log(\`Merkle root: \${result.merkle_root}\`);`,
    },
  };

  const s = snippets[op.id] || snippets.ingest;
  return [
    { language: 'curl', label: 'cURL', code: s.curl },
    { language: 'python', label: 'Python', code: s.python },
    { language: 'javascript', label: 'Node.js', code: s.node },
  ];
}

export default function CodeGenPage() {
  const [selectedOp, setSelectedOp] = useState(OPERATIONS[0]);
  const [apiKey, setApiKey] = useState('');
  const [tenantId, setTenantId] = useState('');

  const snippets = generateSnippets(selectedOp, apiKey, tenantId);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>Code Generator</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
          Generate ready-to-use code snippets with your API key pre-filled.
        </p>
      </div>

      {/* Config */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--re-text-muted)' }}>Operation</label>
          <select
            value={selectedOp.id}
            onChange={(e) => setSelectedOp(OPERATIONS.find(o => o.id === e.target.value) || OPERATIONS[0])}
            className="w-full px-3 py-2 rounded-md text-sm"
            style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
          >
            {OPERATIONS.map(op => (
              <option key={op.id} value={op.id}>{op.method} -- {op.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--re-text-muted)' }}>API Key</label>
          <input
            type="text"
            placeholder="rge_dev_..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            className="w-full px-3 py-2 rounded-md text-sm font-mono"
            style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
          />
        </div>
        <div>
          <label className="text-xs font-medium mb-1.5 block" style={{ color: 'var(--re-text-muted)' }}>Tenant ID</label>
          <input
            type="text"
            placeholder="your-tenant-uuid"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className="w-full px-3 py-2 rounded-md text-sm font-mono"
            style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
          />
        </div>
      </div>

      {/* Endpoint badge */}
      <div className="flex items-center gap-2 px-3 py-2 rounded-md" style={{ background: 'rgba(0,0,0,0.15)', border: '1px solid rgba(255,255,255,0.06)' }}>
        <span className="text-xs font-mono font-semibold px-1.5 py-0.5 rounded" style={{
          color: selectedOp.method === 'POST' ? '#10b981' : '#60a5fa',
          background: selectedOp.method === 'POST' ? 'rgba(16,185,129,0.1)' : 'rgba(96,165,250,0.1)',
        }}>{selectedOp.method}</span>
        <code className="text-sm font-mono" style={{ color: 'var(--re-text-primary)' }}>{selectedOp.path}</code>
      </div>

      {/* Generated code */}
      <CodeBlock snippets={snippets} title={`${selectedOp.method} ${selectedOp.path}`} />
    </div>
  );
}
