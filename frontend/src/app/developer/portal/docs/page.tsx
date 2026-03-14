'use client';

import Link from 'next/link';
import { CodeBlock } from '@/components/developer/CodeBlock';
import { ArrowRight, Zap, Key, Terminal, BookOpen, Webhook, Package } from 'lucide-react';

const INSTALL_SNIPPETS = [
    { language: 'bash-pip', label: 'Python', code: 'pip install regengine' },
    { language: 'bash-npm', label: 'Node.js', code: 'npm install @regengine/sdk' },
    { language: 'bash-go', label: 'Go', code: 'go get github.com/regengine/regengine-go' },
    { language: 'bash-curl', label: 'cURL', code: '# No installation needed — use curl directly' },
];

const FIRST_REQUEST = [
    {
        language: 'curl', label: 'cURL',
        code: `curl -X POST https://api.regengine.co/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [{
      "cte_type": "receiving",
      "traceability_lot_code": "LOT-2026-001",
      "product_description": "Romaine Lettuce",
      "quantity": 500,
      "unit_of_measure": "cases",
      "timestamp": "2026-03-14T08:30:00Z"
    }]
  }'`,
    },
    {
        language: 'python', label: 'Python',
        code: `import regengine

client = regengine.Client(api_key="YOUR_API_KEY")

response = client.events.ingest([{
    "cte_type": "receiving",
    "traceability_lot_code": "LOT-2026-001",
    "product_description": "Romaine Lettuce",
    "quantity": 500,
    "unit_of_measure": "cases",
    "timestamp": "2026-03-14T08:30:00Z",
}])

print(f"Accepted: {response.accepted}, Rejected: {response.rejected}")`,
    },
    {
        language: 'javascript', label: 'Node.js',
        code: `import RegEngine from '@regengine/sdk';

const client = new RegEngine({ apiKey: 'YOUR_API_KEY' });

const response = await client.events.ingest([{
  cte_type: 'receiving',
  traceability_lot_code: 'LOT-2026-001',
  product_description: 'Romaine Lettuce',
  quantity: 500,
  unit_of_measure: 'cases',
  timestamp: '2026-03-14T08:30:00Z',
}]);

console.log(\`Accepted: \${response.accepted}\`);`,
    },
    {
        language: 'go', label: 'Go',
        code: `package main

import "github.com/regengine/regengine-go"

func main() {
    client := regengine.NewClient("YOUR_API_KEY")

    resp, _ := client.Events.Ingest([]regengine.Event{{
        CTEType:              "receiving",
        TraceabilityLotCode:  "LOT-2026-001",
        ProductDescription:   "Romaine Lettuce",
        Quantity:             500,
        UnitOfMeasure:        "cases",
        Timestamp:            "2026-03-14T08:30:00Z",
    }})

    fmt.Printf("Accepted: %d\\n", resp.Accepted)
}`,
    },
];

const RESPONSE_EXAMPLE = `{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [{
    "traceability_lot_code": "LOT-2026-001",
    "cte_type": "receiving",
    "status": "accepted",
    "event_id": "evt_a1b2c3d4",
    "sha256_hash": "a3f2b891c4d5e6f7...",
    "chain_hash": "7f6e5d4c3b2a1908..."
  }]
}`;

const NEXT_STEPS = [
    { label: 'API Reference', desc: 'Explore all endpoints', href: '/developer/portal/docs/endpoints', icon: BookOpen },
    { label: 'Authentication', desc: 'API key management', href: '/developer/portal/docs/auth', icon: Key },
    { label: 'Webhooks', desc: 'Real-time event delivery', href: '/developer/portal/docs/webhooks', icon: Webhook },
    { label: 'SDKs', desc: 'Python, Node.js, Go', href: '/developer/portal/docs/sdks', icon: Package },
    { label: 'Playground', desc: 'Try endpoints live', href: '/developer/portal/playground', icon: Terminal },
];

export default function QuickstartPage() {
    return (
        <div className="space-y-10">
            {/* Hero */}
            <div>
                <div className="flex items-center gap-2 mb-3">
                    <div className="px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider"
                        style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--re-brand)' }}>
                        Quickstart
                    </div>
                    <span className="text-[11px]" style={{ color: 'var(--re-text-disabled)' }}>~ 60 seconds</span>
                </div>
                <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--re-text-primary)' }}>
                    Get started with RegEngine
                </h1>
                <p className="text-sm leading-relaxed max-w-2xl" style={{ color: 'var(--re-text-muted)' }}>
                    Submit your first FSMA 204 traceability event in three steps: install the SDK, grab an API key, and send a request.
                </p>
            </div>

            {/* Step 1: Install */}
            <section>
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                        style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--re-brand)' }}>1</div>
                    <h2 className="text-lg font-semibold" style={{ color: 'var(--re-text-primary)' }}>Install the SDK</h2>
                </div>
                <CodeBlock snippets={INSTALL_SNIPPETS} title="Install" />
            </section>

            {/* Step 2: API Key */}
            <section>
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                        style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--re-brand)' }}>2</div>
                    <h2 className="text-lg font-semibold" style={{ color: 'var(--re-text-primary)' }}>Get your API key</h2>
                </div>
                <div className="rounded-lg p-4 flex items-center justify-between" style={{
                    background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.15)',
                }}>
                    <div className="flex items-center gap-3">
                        <Key className="w-4 h-4" style={{ color: 'var(--re-brand)' }} />
                        <span className="text-sm" style={{ color: 'var(--re-text-muted)' }}>
                            Generate a key from your dashboard. Keys start with <code className="font-mono text-xs px-1 py-0.5 rounded" style={{ background: 'rgba(0,0,0,0.2)', color: 'var(--re-brand)' }}>rge_dev_</code>
                        </span>
                    </div>
                    <Link href="/developer/portal/keys" className="flex items-center gap-1.5 text-sm font-medium no-underline" style={{ color: 'var(--re-brand)' }}>
                        Manage Keys <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                </div>
            </section>

            {/* Step 3: First request */}
            <section>
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                        style={{ background: 'rgba(16,185,129,0.15)', color: 'var(--re-brand)' }}>3</div>
                    <h2 className="text-lg font-semibold" style={{ color: 'var(--re-text-primary)' }}>Send your first event</h2>
                </div>
                <div className="space-y-3">
                    <CodeBlock snippets={FIRST_REQUEST} title="POST /v1/webhooks/ingest" />
                    <CodeBlock snippets={[{ language: 'json', label: 'JSON', code: RESPONSE_EXAMPLE }]} title="Response · 201 Created" />
                </div>
            </section>

            {/* What's next */}
            <section>
                <h2 className="text-sm font-semibold uppercase tracking-wider mb-4" style={{ color: 'var(--re-text-disabled)' }}>
                    What&apos;s next
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {NEXT_STEPS.map((item) => (
                        <Link key={item.href} href={item.href} className="group rounded-lg p-4 no-underline transition-all" style={{
                            background: 'rgba(255,255,255,0.02)',
                            border: '1px solid rgba(255,255,255,0.06)',
                        }}>
                            <item.icon className="w-4 h-4 mb-2" style={{ color: 'var(--re-brand)' }} />
                            <p className="text-sm font-medium mb-0.5" style={{ color: 'var(--re-text-primary)' }}>{item.label}</p>
                            <p className="text-xs" style={{ color: 'var(--re-text-disabled)' }}>{item.desc}</p>
                        </Link>
                    ))}
                </div>
            </section>
        </div>
    );
}
