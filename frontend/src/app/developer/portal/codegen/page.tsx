'use client';

import { useState } from 'react';
import { CodeBlock } from '@/components/developer/CodeBlock';
import { API_BASE } from '@/lib/api-base';
import { Badge } from '@/components/ui/badge';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { fieldControlClasses } from '@/components/ui/field-control';
import { PageHeader } from '@/components/layout/page-header';
import { cn } from '@/lib/utils';

const OPERATIONS = [
  { id: 'ingest', label: 'Ingest Webhook Events', method: 'POST', path: '/api/v1/webhooks/ingest' },
  { id: 'fda-export', label: 'FDA Export (by TLC)', method: 'GET', path: '/api/v1/fda/export' },
  { id: 'fda-export-all', label: 'FDA Export (full tenant)', method: 'GET', path: '/api/v1/fda/export/all' },
  { id: 'compliance', label: 'Get FSMA Readiness Score (advisory)', method: 'GET', path: '/api/v1/compliance/score/{tenant_id}' },
  { id: 'chain-verify', label: 'Verify Chain Integrity', method: 'POST', path: '/api/v1/chain/verify-all' },
  { id: 'health', label: 'Health Check', method: 'GET', path: '/api/v1/monitoring/health/{tenant_id}' },
  { id: 'csv-template', label: 'CSV Template Download', method: 'GET', path: '/api/v1/templates/{cte_type}' },
  { id: 'portal-link', label: 'Create Supplier Portal Link', method: 'POST', path: '/api/v1/portal/links' },
  { id: 'merkle-root', label: 'Get Merkle Root', method: 'GET', path: '/api/v1/fda/export/merkle-root' },
];

function generateSnippets(op: typeof OPERATIONS[0], apiKey: string, tenantId: string) {
  const key = apiKey || 'YOUR_API_KEY';
  const tid = tenantId || 'YOUR_TENANT_ID';
  const base = API_BASE.replace(/\/api\/v1$/, '');

  const snippets: Record<string, Record<string, string>> = {
    ingest: {
      curl: `curl -X POST ${base}/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "Idempotency-Key: $(uuidgen)" \\
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
      python: `import uuid

import requests

response = requests.post(
    "${base}/api/v1/webhooks/ingest",
    headers={
        "X-RegEngine-API-Key": "${key}",
        "Idempotency-Key": str(uuid.uuid4()),
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
    'Idempotency-Key': crypto.randomUUID(),
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
    "supplier_name": "Example Farms",
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
        "supplier_name": "Example Farms",
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
    supplier_name: 'Example Farms',
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
      <PageHeader
        title="Code Generator"
        description="Generate ready-to-use code snippets with your API key pre-filled."
        className="mb-0"
      />

      {/* Config */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Field label="Operation" htmlFor="codegen-operation">
          <select
            value={selectedOp.id}
            onChange={(e) => setSelectedOp(OPERATIONS.find(o => o.id === e.target.value) || OPERATIONS[0])}
            className={cn(fieldControlClasses, 'appearance-none pr-8')}
          >
            {OPERATIONS.map(op => (
              <option key={op.id} value={op.id}>{op.method} -- {op.label}</option>
            ))}
          </select>
        </Field>
        <Field label="API Key" htmlFor="codegen-api-key">
          <Input
            type="text"
            mono
            placeholder="rge_live_..."
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </Field>
        <Field label="Tenant ID" htmlFor="codegen-tenant-id">
          <Input
            type="text"
            mono
            placeholder="your-tenant-uuid"
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
          />
        </Field>
      </div>

      {/* Endpoint badge */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-re-border bg-re-surface-card px-3 py-2">
        <Badge tone="neutral" size="sm" mono>{selectedOp.method}</Badge>
        <code className="min-w-0 break-all font-mono text-[0.8125rem] text-re-text-primary">{selectedOp.path}</code>
      </div>

      {/* Generated code */}
      <CodeBlock snippets={snippets} title={`${selectedOp.method} ${selectedOp.path}`} />
    </div>
  );
}
