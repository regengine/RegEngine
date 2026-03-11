import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Code2, Terminal, ArrowRight, Zap, Clock, Shield, BookOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
    title: 'Developers | RegEngine FSMA 204 API',
    description: 'RegEngine REST API for FSMA 204 compliance. Record CTEs, run recall simulations, and export FDA packages programmatically.',
    openGraph: {
        title: 'Developers | RegEngine FSMA 204 API',
        description: 'RegEngine REST API for FSMA 204 compliance. Record CTEs, run recall simulations, and export FDA packages programmatically.',
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
/* ── Real code examples using actual REST endpoints ── */

const EXAMPLE_INGEST_CTE = `# Record a Critical Tracking Event (Receiving)
curl -X POST https://www.regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [{
      "event_type": "receiving",
      "tlc": "LOT-2024-001",
      "product_description": "Fresh Romaine Lettuce",
      "gtin": "00614141000012",
      "quantity": 500,
      "unit": "cases",
      "location_gln": "0614141000012",
      "location_name": "Main Warehouse",
      "timestamp": "2025-03-10T14:30:00Z",
      "kdes": {
        "supplier_lot": "SUPP-TF-2024-001",
        "po_number": "PO-12345",
        "carrier": "FastFreight Logistics"
      }
    }]
  }'`;

const EXAMPLE_EPCIS = `# Ingest EPCIS 2.0 event
curl -X POST https://www.regengine.co/api/v1/epcis/events \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "eventList": [{
      "type": "ObjectEvent",
      "action": "OBSERVE",
      "bizStep": "urn:epcglobal:cbv:bizstep:receiving",
      "epcList": ["urn:epc:id:sgtin:0614141.000012.LOT2024001"],
      "eventTime": "2025-03-10T14:30:00Z",
      "bizLocation": {"id": "urn:epc:id:sgln:0614141.00001.0"},
      "ilmd": {
        "lotNumber": "LOT-2024-001",
        "itemDescription": "Fresh Romaine Lettuce"
      }
    }]
  }'`;

const EXAMPLE_COMPLIANCE = `# Get compliance score
curl https://www.regengine.co/api/v1/compliance/score/your_tenant_id \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here"

# Run a recall simulation
curl -X POST https://www.regengine.co/api/v1/recall-simulations/run \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "tenant_id": "your_tenant_id",
    "tlc": "LOT-2024-001",
    "reason": "Quarterly drill"
  }'

# Export FDA compliance package
curl https://www.regengine.co/api/v1/fda/export?tenant_id=your_tenant_id \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here" \\
  --output fda_package.json`;
/* ── Actual API endpoints that exist in the backend ── */

const API_ENDPOINTS = [
    { method: 'POST', path: '/api/v1/webhooks/ingest', description: 'Ingest Critical Tracking Events (batch)' },
    { method: 'POST', path: '/api/v1/epcis/events', description: 'Ingest EPCIS 2.0 events' },
    { method: 'GET', path: '/api/v1/epcis/events/:id', description: 'Get event by ID' },
    { method: 'GET', path: '/api/v1/epcis/chain/verify', description: 'Verify event chain integrity' },
    { method: 'GET', path: '/api/v1/fda/export', description: 'Export FDA compliance package' },
    { method: 'POST', path: '/api/v1/recall-simulations/run', description: 'Run recall simulation drill' },
    { method: 'GET', path: '/api/v1/compliance/score/:tenant_id', description: 'Get compliance risk score' },
    { method: 'POST', path: '/api/v1/qr/decode', description: 'Decode GS1 / GTIN barcode' },
    { method: 'POST', path: '/api/v1/integrations/csv-upload/:tenant_id', description: 'Upload CSV traceability data' },
    { method: 'GET', path: '/api/v1/integrations/status/:tenant_id', description: 'List connected integrations' },
];

const DEV_FEATURES = [
    { Icon: Zap, title: 'Quick Integration', description: 'Record your first CTE with a single API call. Full REST API with cURL examples.' },
    { Icon: Clock, title: 'Real-Time Webhooks', description: 'Ingest traceability events via webhooks with SHA-256 chain verification.' },
    { Icon: Shield, title: 'Per-Tenant API Keys', description: 'Scoped keys with RBAC. Multi-tenant isolation by design.' },
    { Icon: BookOpen, title: 'Interactive API Docs', description: 'Swagger UI with live endpoint testing. Python and Node.js SDKs coming soon.' },
];
export default function DevelopersPage() {
    return (
        <div className="re-page" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
            {/* Hero */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '800px', margin: '0 auto', padding: '80px 24px 60px', textAlign: 'center' }}>
                <Badge style={{ background: T.accentBg, color: T.accent, border: '1px solid rgba(16,185,129,0.2)', marginBottom: '20px' }}>
                    REST API
                </Badge>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, color: T.heading, lineHeight: 1.1, margin: '0 0 16px' }}>
                    Ship FSMA 204 compliance<br />
                    <span className="text-re-brand">with one API call</span>
                </h1>
                <p style={{ fontSize: '18px', color: T.textMuted, maxWidth: '560px', margin: '0 auto 32px', lineHeight: 1.6 }}>
                    REST API with full EPCIS 2.0 support. Record CTEs, run recall simulations, and export FDA packages programmatically.
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

            {/* Code Examples */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: '800px', margin: '0 auto', padding: '60px 24px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, marginBottom: '8px' }}>
                        Record your first CTE
                    </h2>
                    <p style={{ fontSize: '14px', color: T.textMuted, marginBottom: '32px' }}>
                        Send Critical Tracking Events via our webhook endpoint or EPCIS 2.0 standard format.
                    </p>

                    {/* Webhook Ingest */}
                    <div style={{ marginBottom: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Terminal style={{ width: 16, height: 16, color: T.accent }} />
                            <span style={{ fontSize: '13px', fontWeight: 600, color: T.heading }}>Webhook Ingest</span>
                        </div>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted }}>
                            <code>{EXAMPLE_INGEST_CTE}</code>
                        </pre>
                    </div>
                    {/* EPCIS 2.0 */}
                    <div style={{ marginBottom: '24px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Code2 style={{ width: 16, height: 16, color: T.accent }} />
                            <span style={{ fontSize: '13px', fontWeight: 600, color: T.heading }}>EPCIS 2.0</span>
                        </div>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted }}>
                            <code>{EXAMPLE_EPCIS}</code>
                        </pre>
                    </div>

                    {/* Compliance & Recall */}
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                            <Shield style={{ width: 16, height: 16, color: T.accent }} />
                            <span style={{ fontSize: '13px', fontWeight: 600, color: T.heading }}>Compliance & Recall</span>
                        </div>
                        <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted }}>
                            <code>{EXAMPLE_COMPLIANCE}</code>
                        </pre>
                    </div>
                </div>
            </section>
            {/* API Endpoints */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '800px', margin: '0 auto', padding: '60px 24px' }}>
                <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, marginBottom: '8px' }}>
                    API Endpoints
                </h2>
                <p style={{ fontSize: '14px', color: T.textMuted, marginBottom: '24px' }}>
                    Core endpoints for FSMA 204 traceability. All endpoints require <code style={{ fontFamily: T.mono, fontSize: '12px', color: T.accent }}>X-RegEngine-API-Key</code> header.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {API_ENDPOINTS.map((ep, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: '8px' }}>
                            <span style={{
                                fontSize: '11px', fontWeight: 700, fontFamily: T.mono, padding: '2px 8px', borderRadius: '4px',
                                background: ep.method === 'POST' ? 'rgba(16,185,129,0.15)' : 'rgba(96,165,250,0.15)',
                                color: ep.method === 'POST' ? T.accent : '#60a5fa',
                                minWidth: '44px', textAlign: 'center',
                            }}>
                                {ep.method}
                            </span>
                            <code style={{ fontSize: '13px', fontFamily: T.mono, color: T.heading, flex: 1 }}>{ep.path}</code>
                            <span style={{ fontSize: '12px', color: T.textMuted }}>{ep.description}</span>
                        </div>
                    ))}
                </div>
            </section>

            {/* Authentication */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: '800px', margin: '0 auto', padding: '60px 24px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 700, color: T.heading, marginBottom: '8px' }}>
                        Authentication
                    </h2>
                    <p style={{ fontSize: '14px', color: T.textMuted, marginBottom: '24px' }}>
                        All API requests require a per-tenant API key passed via header.
                    </p>
                    <pre style={{ background: 'rgba(0,0,0,0.3)', border: `1px solid ${T.border}`, borderRadius: '8px', padding: '16px', overflow: 'auto', fontSize: '12px', lineHeight: 1.8, fontFamily: T.mono, color: T.textMuted }}>
                        <code>{`# Required headers
X-RegEngine-API-Key: rge_your_api_key_here
Content-Type: application/json

# Response codes
200  OK (sync response)
202  Accepted (async job queued)
400  Bad Request (validation error)
401  Unauthorized (missing or invalid key)
422  Unprocessable Entity (schema violation)`}</code>
                    </pre>
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