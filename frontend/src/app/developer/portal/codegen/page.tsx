'use client';

import { useState } from 'react';
import { CodeBlock } from '@/components/developer/CodeBlock';
import { Code2, Copy, Check } from 'lucide-react';

const OPERATIONS = [
    { id: 'ingest', label: 'Ingest CTE Events', method: 'POST', path: '/api/v1/webhooks/ingest' },
    { id: 'compliance', label: 'Get Compliance Score', method: 'GET', path: '/api/v1/compliance/score/:tenant_id' },
    { id: 'verify', label: 'Verify Chain Integrity', method: 'GET', path: '/api/v1/epcis/chain/verify' },
    { id: 'recall', label: 'Run Recall Simulation', method: 'POST', path: '/api/v1/recall-simulations/run' },
    { id: 'export', label: 'Export FDA Package', method: 'GET', path: '/api/v1/fda/export' },
];

function generateSnippets(op: typeof OPERATIONS[0], apiKey: string, tenantId: string) {
    const key = apiKey || 'YOUR_API_KEY';
    const tid = tenantId || 'YOUR_TENANT_ID';
    const base = 'https://api.regengine.co';

    const snippets: Record<string, Record<string, string>> = {
        ingest: {
            curl: `curl -X POST ${base}/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "X-Tenant-ID: ${tid}" \\
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
            python: `import regengine

client = regengine.Client(api_key="${key}")
response = client.events.ingest([{
    "cte_type": "receiving",
    "traceability_lot_code": "LOT-2026-001",
    "product_description": "Romaine Lettuce",
    "quantity": 500,
    "unit_of_measure": "cases",
}])
print(response)`,
            node: `import RegEngine from '@regengine/sdk';

const client = new RegEngine({ apiKey: '${key}' });
const response = await client.events.ingest([{
  cte_type: 'receiving',
  traceability_lot_code: 'LOT-2026-001',
  product_description: 'Romaine Lettuce',
  quantity: 500,
  unit_of_measure: 'cases',
}]);
console.log(response);`,
        },
        compliance: {
            curl: `curl -X GET "${base}/v1/compliance/score/${tid}" \\
  -H "X-RegEngine-API-Key: ${key}"`,
            python: `import regengine

client = regengine.Client(api_key="${key}")
score = client.compliance.get_score("${tid}")
print(f"Score: {score.overall}/100 — Grade: {score.grade}")`,
            node: `import RegEngine from '@regengine/sdk';

const client = new RegEngine({ apiKey: '${key}' });
const score = await client.compliance.getScore('${tid}');
console.log(\`Score: \${score.overall}/100\`);`,
        },
        verify: {
            curl: `curl -X GET "${base}/v1/epcis/chain/verify?lot_code=LOT-2026-001" \\
  -H "X-RegEngine-API-Key: ${key}"`,
            python: `import regengine

client = regengine.Client(api_key="${key}")
result = client.chain.verify(lot_code="LOT-2026-001")
print(f"Valid: {result.valid}, Events: {result.event_count}")`,
            node: `import RegEngine from '@regengine/sdk';

const client = new RegEngine({ apiKey: '${key}' });
const result = await client.chain.verify({ lotCode: 'LOT-2026-001' });
console.log(\`Valid: \${result.valid}\`);`,
        },
        recall: {
            curl: `curl -X POST ${base}/v1/recall-simulations/run \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "Content-Type: application/json" \\
  -d '{ "lot_code": "LOT-2026-001", "depth": 3 }'`,
            python: `import regengine

client = regengine.Client(api_key="${key}")
sim = client.recall.simulate(lot_code="LOT-2026-001", depth=3)
print(f"Traced {sim.nodes_found} nodes in {sim.duration_ms}ms")`,
            node: `import RegEngine from '@regengine/sdk';

const client = new RegEngine({ apiKey: '${key}' });
const sim = await client.recall.simulate({ lotCode: 'LOT-2026-001', depth: 3 });
console.log(\`Traced \${sim.nodesFound} nodes\`);`,
        },
        export: {
            curl: `curl -X GET "${base}/v1/fda/export?format=json" \\
  -H "X-RegEngine-API-Key: ${key}" \\
  -H "X-Tenant-ID: ${tid}"`,
            python: `import regengine

client = regengine.Client(api_key="${key}")
export = client.fda.export(tenant_id="${tid}", format="json")
print(f"Records: {len(export.records)}")`,
            node: `import RegEngine from '@regengine/sdk';

const client = new RegEngine({ apiKey: '${key}' });
const exp = await client.fda.export({ tenantId: '${tid}', format: 'json' });
console.log(\`Records: \${exp.records.length}\`);`,
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
                            <option key={op.id} value={op.id}>{op.method} — {op.label}</option>
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
