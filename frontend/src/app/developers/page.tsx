import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Code2, Terminal, ArrowRight, Zap, Clock, Shield, BookOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
    title: 'Developers | RegEngine FSMA API',
    description: 'RegEngine developer docs. Node.js, Python, and cURL SDKs for FSMA 204 compliance API.',
    openGraph: {
        title: 'Developers | RegEngine FSMA API',
        description: 'RegEngine developer docs. Node.js, Python, and cURL SDKs for FSMA 204 compliance API.',
        url: 'https://www.regengine.co/developers',
        type: 'website',
    },
};

const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    border: 'rgba(255,255,255,0.06)',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentBg: 'rgba(16,185,129,0.1)',
    mono: "'JetBrains Mono', monospace",
};

const QUICKSTART_NODE = `import { RegEngine } from '@regengine/fsma-sdk';

const rg = new RegEngine('rge_your_api_key_here');

const event = await rg.events.create({
  type: 'RECEIVING',
  tlc: 'LOT-2024-001',
  product: {
    description: 'Fresh Romaine Lettuce',
    gtin: '00614141000012'
  },
  quantity: { value: 500, unit: 'cases' },
  location: { gln: '0614141000012', name: 'Main Warehouse' },
  timestamp: new Date().toISOString(),
  kdes: {
    supplier_lot: 'SUPP-TF-2024-001',
    po_number: 'PO-12345',
    carrier: 'FastFreight Logistics'
  }
});

console.log('Event recorded:', event.id);`;

const QUICKSTART_PYTHON = `from regengine import RegEngine

rg = RegEngine(api_key='rge_your_api_key_here')

event = rg.events.create(
    event_type='RECEIVING',
    tlc='LOT-2024-001',
    product={
        'description': 'Fresh Romaine Lettuce',
        'gtin': '00614141000012'
    },
    quantity={'value': 500, 'unit': 'cases'},
    location={'gln': '0614141000012', 'name': 'Main Warehouse'},
    kdes={
        'supplier_lot': 'SUPP-TF-2024-001',
        'po_number': 'PO-12345',
        'carrier': 'FastFreight Logistics'
    }
)

print(f'Event recorded: {event.id}')`;

const QUICKSTART_CURL = `curl -X POST https://api.regengine.co/v1/fsma/events \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "RECEIVING",
    "tlc": "LOT-2024-001",
    "product": {
      "description": "Fresh Romaine Lettuce",
      "gtin": "00614141000012"
    },
    "quantity": {"value": 500, "unit": "cases"},
    "location": {"gln": "0614141000012"},
    "kdes": {
      "supplier_lot": "SUPP-TF-2024-001",
      "po_number": "PO-12345"
    }
  }'`;

const API_ENDPOINTS = [
    { method: 'POST', path: '/v1/fsma/events', description: 'Create a Critical Tracking Event' },
    { method: 'GET', path: '/v1/fsma/events', description: 'List events with filters' },
    { method: 'GET', path: '/v1/fsma/events/:id', description: 'Get event by ID' },
    { method: 'POST', path: '/v1/fsma/export', description: 'Generate FDA compliance package' },
    { method: 'POST', path: '/v1/fsma/recall-simulation', description: 'Run recall drill' },
    { method: 'GET', path: '/v1/fsma/compliance-score', description: 'Get compliance score' },
    { method: 'POST', path: '/v1/fsma/qr/decode', description: 'Decode GS1 barcode' },
    { method: 'POST', path: '/v1/fsma/query', description: 'Natural language traceability query' },
];

const DEV_FEATURES = [
    { Icon: Zap, title: '5-Minute Quickstart', description: 'Get your first CTE recorded in under 5 minutes with our SDK.' },
    { Icon: Clock, title: 'Real-Time Webhooks', description: 'Subscribe to compliance events. Get notified when scores change.' },
    { Icon: Shield, title: 'Per-Tenant API Keys', description: 'Scoped keys with RBAC. No cross-tenant leakage by design.' },
    { Icon: BookOpen, title: 'Full OpenAPI Spec', description: 'Every endpoint documented with schemas, examples, and error codes.' },
];

export default function DevelopersPage() {
    return (
        <div className="re-page" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
            {/* Hero */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '800px', margin: '0 auto', padding: '80px 24px 60px', textAlign: 'center' }}>
                <Badge style={{ background: T.accentBg, color: T.accent, border: '1px solid rgba(16,185,129,0.2)', marginBottom: '20px' }}>
                    Developer Docs
                </Badge>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, color: T.heading, lineHeight: 1.1, margin: '0 0 16px' }}>
                    Ship FSMA 204 compliance<br />
                    <span className="text-re-brand">with one API call</span>
                </h1>
                <p style={{ fontSize: '18px', color: T.textMuted, maxWidth: '560px', margin: '0 auto 32px', lineHeight: 1.6 }}>
                    Node.js, Python, and cURL SDKs. Record CTEs, run recall simulations, and export FDA packages programmatically.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                    <Link href="/alpha">
                        <Button style={{ background: T.accent, color: '#000', fontWeight: 600, padding: '12px 24px' }}>
                            Get API Access <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="/tools/ftl-checker">
                        <Button variant="outline" style={{ border: `1px solid ${T.border}`, color: T.text, padding: '12px 24px' }}>
                            Try Free Tools
                        </Button>
                    </Link>
                </div>
            </section>

            {/* Developer Features */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '900px', margin: '0 auto', padding: '0 24px 60px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                    {DEV_FEATURES.map((f) => (
                        <div key={f.title} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: '12px', padding: '20px' }}>
                            <f.Icon style={{ width: 20, height: 20, color: T.accent, marginBottom: '12px' }} />
                            <h3 style={{ fontSize: '15px', fontWeight: 600, color: T.heading, marginBottom: '6px' }}>{f.title}</h3>
                            <p style={{ fontSize: '13px', color: T.textMuted, lineHeight: 1.5 }}>{f.description}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* Quickstart Code Examples */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: '800px', margin: '0 auto', padding: '60px 24px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, marginBottom: '8px' }}>
                        Quickstart: Record your first CTE
                    </h2>
                    <p style={{ fontSize: '14px', color: T.textMuted, marginBottom: '32px' }}>
                        Send your first Critical Tracking Event in 5 minutes. Available in Node.js, Python, and cURL.
                    </p>

                    {/* Node.js */}
                    <div style={{ marginBottom: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Code2 style={{ width: 16, height: 16, color: T.accent }} />
                            <span style={{ fontSize: '13px', fontWeight: 600, color: T.heading }}>Node.js</span>
                        </div>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted }}>
                            <code>{QUICKSTART_NODE}</code>
                        </pre>
                    </div>

                    {/* Python */}
                    <div style={{ marginBottom: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Terminal style={{ width: 16, height: 16, color: T.accent }} />
                            <span style={{ fontSize: '13px', fontWeight: 600, color: T.heading }}>Python</span>
                        </div>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted }}>
                            <code>{QUICKSTART_PYTHON}</code>
                        </pre>
                    </div>

                    {/* cURL */}
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Terminal style={{ width: 16, height: 16, color: T.accent }} />
                            <span style={{ fontSize: '13px', fontWeight: 600, color: T.heading }}>cURL</span>
                        </div>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted }}>
                            <code>{QUICKSTART_CURL}</code>
                        </pre>
                    </div>
                </div>
            </section>

            {/* API Endpoints */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '800px', margin: '0 auto', padding: '60px 24px' }}>
                <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, marginBottom: '24px' }}>
                    API Endpoints
                </h2>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {API_ENDPOINTS.map((ep, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '8px' }}>
                            <span style={{
                                fontSize: '11px', fontWeight: 700, fontFamily: T.mono, padding: '2px 8px', borderRadius: '4px',
                                background: ep.method === 'POST' ? 'rgba(16,185,129,0.15)' : 'rgba(96,165,250,0.15)',
                                color: ep.method === 'POST' ? T.accent : '#60a5fa',
                            }}>
                                {ep.method}
                            </span>
                            <code style={{ fontSize: '13px', fontFamily: T.mono, color: T.heading, flex: 1 }}>{ep.path}</code>
                            <span style={{ fontSize: '12px', color: T.textMuted }}>{ep.description}</span>
                        </div>
                    ))}
                </div>
            </section>

            {/* CTA */}
            <section style={{ position: 'relative', zIndex: 2, background: T.accentBg, borderTop: `1px solid ${T.border}`, padding: '48px 24px', textAlign: 'center' }}>
                <h2 style={{ fontSize: '22px', fontWeight: 700, color: T.heading, marginBottom: '8px' }}>
                    Ready to integrate?
                </h2>
                <p style={{ fontSize: '14px', color: T.textMuted, marginBottom: '20px' }}>
                    Join the design partner program for API access and dedicated onboarding.
                </p>
                <Link href="/alpha">
                    <Button style={{ background: T.accent, color: '#000', fontWeight: 600, padding: '12px 24px' }}>
                        Apply for Access <ArrowRight className="ml-2 w-4 h-4" />
                    </Button>
                </Link>
            </section>
        </div>
    );
}
