'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
    Code2, Terminal, ArrowRight, Zap, Clock, Shield, BookOpen,
    Copy, Check, ChevronRight, Layers, Globe, Lock, Activity,
    Package, Webhook, FileJson, BarChart3,
} from 'lucide-react';

/* ── Design Tokens (matching dashboard pages) ── */
const T = {
    bg: 'var(--re-surface-base)',
    surface: 'var(--re-surface-card, rgba(255,255,255,0.02))',
    surfaceElevated: 'var(--re-surface-elevated, rgba(255,255,255,0.04))',
    border: 'var(--re-border-default, rgba(255,255,255,0.06))',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentBg: 'rgba(16,185,129,0.08)',
    accentBorder: 'rgba(16,185,129,0.2)',
    mono: "'JetBrains Mono', 'Fira Code', monospace",
    blue: '#60a5fa',
    blueBg: 'rgba(96,165,250,0.12)',
};
/* ── Code Examples ── */
const EXAMPLES: Record<string, { curl: string; python: string; node: string }> = {
    'Record CTE': {
        curl: `curl -X POST https://api.regengine.co/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: rge_live_abc123" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [{
      "event_type": "receiving",
      "tlc": "LOT-2024-001",
      "product_description": "Fresh Romaine Lettuce",
      "quantity": 500,
      "unit": "cases",
      "location_name": "Main Warehouse",
      "timestamp": "2025-03-10T14:30:00Z",
      "kdes": {
        "supplier_lot": "SUPP-TF-2024-001",
        "po_number": "PO-12345"
      }
    }]
  }'`,
        python: `import requests

resp = requests.post(
    "https://api.regengine.co/v1/webhooks/ingest",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"},
    json={"events": [{
        "event_type": "receiving",
        "tlc": "LOT-2024-001",        "product_description": "Fresh Romaine Lettuce",
        "quantity": 500, "unit": "cases",
        "location_name": "Main Warehouse",
        "timestamp": "2025-03-10T14:30:00Z",
        "kdes": {"supplier_lot": "SUPP-TF-2024-001"}
    }]}
)
print(resp.json())  # {"ingested": 1, "chain_hash": "sha256:..."}`,
        node: `const resp = await fetch(
  "https://api.regengine.co/v1/webhooks/ingest",
  {
    method: "POST",
    headers: {
      "X-RegEngine-API-Key": "rge_live_abc123",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      events: [{
        event_type: "receiving",
        tlc: "LOT-2024-001",
        product_description: "Fresh Romaine Lettuce",
        quantity: 500, unit: "cases",
        location_name: "Main Warehouse",
        timestamp: "2025-03-10T14:30:00Z",
        kdes: { supplier_lot: "SUPP-TF-2024-001" },
      }],
    }),
  }
);
const data = await resp.json();
console.log(data); // { ingested: 1, chain_hash: "sha256:..." }`,
    },    'Compliance Score': {
        curl: `curl https://api.regengine.co/v1/compliance/score/tenant_abc \\
  -H "X-RegEngine-API-Key: rge_live_abc123"`,
        python: `import requests

resp = requests.get(
    "https://api.regengine.co/v1/compliance/score/tenant_abc",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"}
)
score = resp.json()
print(f"Grade: {score['grade']} ({score['overall_score']}%)")`,
        node: `const resp = await fetch(
  "https://api.regengine.co/v1/compliance/score/tenant_abc",
  { headers: { "X-RegEngine-API-Key": "rge_live_abc123" } }
);
const score = await resp.json();
console.log(\`Grade: \${score.grade} (\${score.overall_score}%)\`);`,
    },
    'Recall Simulation': {
        curl: `curl -X POST https://api.regengine.co/v1/recall-simulations/run \\
  -H "X-RegEngine-API-Key: rge_live_abc123" \\
  -H "Content-Type: application/json" \\
  -d '{
    "tenant_id": "tenant_abc",
    "tlc": "LOT-2024-001",
    "reason": "Quarterly drill"
  }'`,
        python: `import requests

resp = requests.post(    "https://api.regengine.co/v1/recall-simulations/run",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"},
    json={
        "tenant_id": "tenant_abc",
        "tlc": "LOT-2024-001",
        "reason": "Quarterly drill"
    }
)
sim = resp.json()
print(f"Traced {sim['lots_affected']} lots in {sim['response_time_hours']}h")`,
        node: `const resp = await fetch(
  "https://api.regengine.co/v1/recall-simulations/run",
  {
    method: "POST",
    headers: {
      "X-RegEngine-API-Key": "rge_live_abc123",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tenant_id: "tenant_abc",
      tlc: "LOT-2024-001",
      reason: "Quarterly drill",
    }),
  }
);
const sim = await resp.json();
console.log(\`Traced \${sim.lots_affected} lots in \${sim.response_time_hours}h\`);`,
    },
};
/* ── API Endpoint Categories ── */
const ENDPOINT_GROUPS = [
    {
        category: 'Traceability',
        Icon: Layers,
        endpoints: [
            { method: 'POST', path: '/v1/webhooks/ingest', desc: 'Ingest CTEs (batch)' },
            { method: 'POST', path: '/v1/epcis/events', desc: 'Ingest EPCIS 2.0 events' },
            { method: 'GET', path: '/v1/epcis/events/:id', desc: 'Get event by ID' },
            { method: 'GET', path: '/v1/epcis/chain/verify', desc: 'Verify chain integrity' },
        ],
    },
    {
        category: 'Compliance',
        Icon: Shield,
        endpoints: [
            { method: 'GET', path: '/v1/compliance/score/:tenant_id', desc: 'Compliance risk score' },
            { method: 'GET', path: '/v1/fda/export', desc: 'Export FDA package' },
            { method: 'POST', path: '/v1/recall-simulations/run', desc: 'Run recall drill' },
        ],
    },
    {
        category: 'Utilities',
        Icon: Package,
        endpoints: [
            { method: 'POST', path: '/v1/qr/decode', desc: 'Decode GS1/GTIN barcode' },
            { method: 'GET', path: '/v1/audit-log/:tenant_id', desc: 'Audit log with chain hashes' },
        ],
    },
];
/* ── Quick-Start Steps ── */
const QUICKSTART = [
    { step: 1, title: 'Get your API key', desc: 'Sign up and generate a per-tenant key from the Developer Portal.', link: '/developer/portal', linkText: 'Open Portal' },
    { step: 2, title: 'Record your first CTE', desc: 'POST a receiving event to /v1/webhooks/ingest. Each event gets a SHA-256 chain hash.', link: '/docs/quickstart', linkText: 'Quickstart Guide' },
    { step: 3, title: 'Check compliance', desc: 'GET your compliance score. Six dimensions scored 0-100 with an overall grade.', link: '/docs/api', linkText: 'API Reference' },
];

/* ── SDK Roadmap ── */
const SDK_ITEMS = [
    { lang: 'Python', status: 'beta', note: 'pip install regengine', icon: '🐍' },
    { lang: 'Node.js', status: 'beta', note: 'npm install @regengine/sdk', icon: '⬢' },
    { lang: 'Ruby', status: 'planned', note: 'Q3 2026', icon: '💎' },
    { lang: 'Go', status: 'planned', note: 'Q4 2026', icon: '🔵' },
];

/* ── CopyButton Component ── */
function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <button
            onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            style={{ position: 'absolute', top: 12, right: 12, background: 'rgba(255,255,255,0.06)', border: `1px solid ${T.border}`, borderRadius: 6, padding: '4px 8px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: copied ? T.accent : T.textMuted, transition: 'all 0.2s' }}
        >
            {copied ? <Check style={{ width: 12, height: 12 }} /> : <Copy style={{ width: 12, height: 12 }} />}
            {copied ? 'Copied' : 'Copy'}
        </button>
    );
}
/* ── CodeBlock with Language Tabs ── */
function CodeBlock({ examples }: { examples: { curl: string; python: string; node: string } }) {
    const [lang, setLang] = useState<'curl' | 'python' | 'node'>('curl');
    const labels = { curl: 'cURL', python: 'Python', node: 'Node.js' };
    return (
        <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', border: `1px solid ${T.border}` }}>
            <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}`, background: 'rgba(0,0,0,0.2)' }}>
                {(Object.keys(labels) as Array<'curl' | 'python' | 'node'>).map((k) => (
                    <button
                        key={k}
                        onClick={() => setLang(k)}
                        style={{
                            padding: '8px 16px', fontSize: 12, fontWeight: 600, fontFamily: T.mono,
                            background: lang === k ? 'rgba(255,255,255,0.04)' : 'transparent',
                            color: lang === k ? T.accent : T.textMuted,
                            border: 'none', borderBottom: lang === k ? `2px solid ${T.accent}` : '2px solid transparent',
                            cursor: 'pointer', transition: 'all 0.15s',
                        }}
                    >
                        {labels[k]}
                    </button>
                ))}
            </div>
            <div style={{ position: 'relative' }}>
                <CopyButton text={examples[lang]} />
                <pre style={{ background: 'rgba(0,0,0,0.35)', padding: '16px 16px 16px 20px', overflow: 'auto', fontSize: 12, lineHeight: 1.7, fontFamily: T.mono, color: T.textMuted, margin: 0, maxHeight: 360 }}>
                    <code>{examples[lang]}</code>
                </pre>
            </div>
        </div>
    );
}
/* ── Main Page ── */
export default function DevelopersPage() {
    const [activeExample, setActiveExample] = useState<string>('Record CTE');

    return (
        <div className="re-page" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>

            {/* ─── Hero ─── */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: 820, margin: '0 auto', padding: '80px 24px 48px', textAlign: 'center' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accentBg, border: `1px solid ${T.accentBorder}`, borderRadius: 20, padding: '6px 16px', fontSize: 13, fontWeight: 600, color: T.accent, marginBottom: 24 }}>
                    <Terminal style={{ width: 14, height: 14 }} />
                    REST API &middot; EPCIS 2.0 &middot; Webhooks
                </div>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 52px)', fontWeight: 700, color: T.heading, lineHeight: 1.08, margin: '0 0 16px', letterSpacing: '-0.02em' }}>
                    Build FSMA 204 compliance<br />
                    <span style={{ color: T.accent }}>into your stack</span>
                </h1>
                <p style={{ fontSize: 18, color: T.textMuted, maxWidth: 560, margin: '0 auto 32px', lineHeight: 1.65 }}>
                    One API to record CTEs, verify chain integrity, run recall simulations, and export FDA packages. Ship compliance in hours, not months.
                </p>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <Link href="/docs/api">
                        <button style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accent, color: '#000', fontWeight: 600, padding: '12px 28px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 14, transition: 'opacity 0.15s' }}>
                            API Reference <ArrowRight style={{ width: 16, height: 16 }} />
                        </button>
                    </Link>                    <Link href="/docs/quickstart">
                        <button style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'transparent', color: T.text, fontWeight: 600, padding: '12px 28px', borderRadius: 8, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 14, transition: 'all 0.15s' }}>
                            Quickstart Guide
                        </button>
                    </Link>
                </div>
            </section>

            {/* ─── Quick-Start Steps ─── */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: 820, margin: '0 auto', padding: '0 24px 64px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                    {QUICKSTART.map((s) => (
                        <div key={s.step} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: '24px 20px', position: 'relative' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                                <span style={{ width: 28, height: 28, borderRadius: '50%', background: T.accentBg, border: `1px solid ${T.accentBorder}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: T.accent }}>{s.step}</span>
                                <h3 style={{ fontSize: 15, fontWeight: 600, color: T.heading, margin: 0 }}>{s.title}</h3>
                            </div>
                            <p style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.55, margin: '0 0 14px' }}>{s.desc}</p>
                            <Link href={s.link} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600, color: T.accent, textDecoration: 'none' }}>
                                {s.linkText} <ChevronRight style={{ width: 12, height: 12 }} />
                            </Link>
                        </div>
                    ))}
                </div>
            </section>
            {/* ─── Interactive Code Examples ─── */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: 820, margin: '0 auto', padding: '64px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 8 }}>
                        <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>
                            Try it now
                        </h2>
                        <span style={{ fontSize: 13, color: T.textMuted }}>Real endpoints &middot; Copy &amp; paste ready</span>
                    </div>
                    <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 28, maxWidth: 520 }}>
                        Send your first CTE, check compliance, or trigger a recall drill. Every example works against the live API.
                    </p>

                    {/* Example Selector Tabs */}
                    <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
                        {Object.keys(EXAMPLES).map((name) => (
                            <button
                                key={name}
                                onClick={() => setActiveExample(name)}
                                style={{
                                    padding: '7px 16px', fontSize: 13, fontWeight: 500, borderRadius: 8,
                                    background: activeExample === name ? T.accentBg : 'transparent',
                                    color: activeExample === name ? T.accent : T.textMuted,
                                    border: `1px solid ${activeExample === name ? T.accentBorder : T.border}`,
                                    cursor: 'pointer', transition: 'all 0.15s',
                                }}
                            >
                                {name}
                            </button>
                        ))}
                    </div>

                    <CodeBlock examples={EXAMPLES[activeExample]} />
                </div>
            </section>
            {/* ─── API Endpoints (Grouped) ─── */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: 820, margin: '0 auto', padding: '64px 24px' }}>
                <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, marginBottom: 8 }}>API Endpoints</h2>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 32 }}>
                    All endpoints require the <code style={{ fontFamily: T.mono, fontSize: 12, color: T.accent, background: T.accentBg, padding: '2px 6px', borderRadius: 4 }}>X-RegEngine-API-Key</code> header.
                </p>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
                    {ENDPOINT_GROUPS.map((g) => (
                        <div key={g.category}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                                <g.Icon style={{ width: 16, height: 16, color: T.accent }} />
                                <h3 style={{ fontSize: 14, fontWeight: 600, color: T.heading, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{g.category}</h3>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {g.endpoints.map((ep, i) => (
                                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, transition: 'border-color 0.15s' }}>
                                        <span style={{
                                            fontSize: 11, fontWeight: 700, fontFamily: T.mono, padding: '2px 8px', borderRadius: 4, minWidth: 44, textAlign: 'center' as const,
                                            background: ep.method === 'POST' ? T.accentBg : T.blueBg,
                                            color: ep.method === 'POST' ? T.accent : T.blue,
                                        }}>
                                            {ep.method}
                                        </span>
                                        <code style={{ fontSize: 13, fontFamily: T.mono, color: T.heading, flex: 1 }}>{ep.path}</code>
                                        <span style={{ fontSize: 12, color: T.textMuted, textAlign: 'right' as const }}>{ep.desc}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </section>
            {/* ─── Authentication ─── */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: 820, margin: '0 auto', padding: '64px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                        <Lock style={{ width: 20, height: 20, color: T.accent }} />
                        <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Authentication</h2>
                    </div>
                    <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 24, maxWidth: 520 }}>
                        Per-tenant API keys with RBAC scoping. Keys are generated in the Developer Portal and passed via header on every request.
                    </p>
                    <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', border: `1px solid ${T.border}` }}>
                        <CopyButton text={`X-RegEngine-API-Key: rge_live_abc123\nContent-Type: application/json`} />
                        <pre style={{ background: 'rgba(0,0,0,0.35)', padding: '20px', overflow: 'auto', fontSize: 12, lineHeight: 2, fontFamily: T.mono, color: T.textMuted, margin: 0 }}>
                            <code>{`# Required headers
X-RegEngine-API-Key: rge_live_abc123
Content-Type: application/json

# Response codes
200  OK              Sync response with data
202  Accepted        Async job queued (recall sims)
400  Bad Request     Validation error — check payload
401  Unauthorized    Missing or invalid API key
422  Unprocessable   Schema violation — see error.details`}</code>
                        </pre>
                    </div>
                </div>
            </section>
            {/* ─── SDK Roadmap ─── */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: 820, margin: '0 auto', padding: '64px 24px' }}>
                <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, marginBottom: 8 }}>SDKs &amp; Libraries</h2>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 28 }}>
                    Official client libraries to get you started faster. The REST API works with any HTTP client.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12 }}>
                    {SDK_ITEMS.map((sdk) => (
                        <div key={sdk.lang} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: '18px 16px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <span style={{ fontSize: 18 }}>{sdk.icon}</span>
                                <span style={{
                                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.06em', padding: '2px 8px', borderRadius: 4,
                                    background: sdk.status === 'beta' ? T.accentBg : 'rgba(251,191,36,0.1)',
                                    color: sdk.status === 'beta' ? T.accent : '#fbbf24',
                                }}>
                                    {sdk.status}
                                </span>
                            </div>
                            <h4 style={{ fontSize: 14, fontWeight: 600, color: T.heading, margin: 0 }}>{sdk.lang}</h4>
                            <code style={{ fontSize: 11, fontFamily: T.mono, color: T.textMuted }}>{sdk.note}</code>
                        </div>
                    ))}
                </div>
            </section>
            {/* ─── Developer Resources Grid ─── */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ maxWidth: 820, margin: '0 auto', padding: '64px 24px' }}>
                    <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, marginBottom: 28 }}>Developer Resources</h2>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 14 }}>
                        {[
                            { Icon: BookOpen, title: 'API Reference', desc: 'Complete endpoint docs with request/response schemas.', href: '/docs/api' },
                            { Icon: Zap, title: 'Quickstart', desc: 'From zero to first CTE in under 5 minutes.', href: '/docs/quickstart' },
                            { Icon: Webhook, title: 'Webhooks', desc: 'Real-time event ingestion with chain verification.', href: '/docs/webhooks' },
                            { Icon: FileJson, title: 'EPCIS 2.0', desc: 'GS1 standard event format support.', href: '/docs/api' },
                            { Icon: BarChart3, title: 'Rate Limits', desc: 'Throughput tiers and burst handling.', href: '/docs/rate-limits' },
                            { Icon: Activity, title: 'Changelog', desc: 'API updates, new endpoints, and deprecations.', href: '/docs/changelog' },
                        ].map((r) => (
                            <Link key={r.title} href={r.href} style={{ textDecoration: 'none' }}>
                                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: '20px 18px', transition: 'border-color 0.15s, background 0.15s', cursor: 'pointer' }}>
                                    <r.Icon style={{ width: 18, height: 18, color: T.accent, marginBottom: 10 }} />
                                    <h4 style={{ fontSize: 14, fontWeight: 600, color: T.heading, margin: '0 0 4px' }}>{r.title}</h4>
                                    <p style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.5, margin: 0 }}>{r.desc}</p>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>
            {/* ─── CTA ─── */}
            <section style={{ position: 'relative', zIndex: 2, background: T.accentBg, borderTop: `1px solid ${T.accentBorder}`, padding: '56px 24px', textAlign: 'center' }}>
                <h2 style={{ fontSize: 24, fontWeight: 700, color: T.heading, marginBottom: 8 }}>
                    Ready to integrate?
                </h2>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 24, maxWidth: 480, margin: '0 auto 24px' }}>
                    Start with the public API docs or request a guided onboarding for your team.
                </p>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <Link href="/docs/quickstart">
                        <button style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accent, color: '#000', fontWeight: 600, padding: '12px 28px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 14 }}>
                            Start Building <ArrowRight style={{ width: 16, height: 16 }} />
                        </button>
                    </Link>
                    <Link href="/contact">
                        <button style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'transparent', color: T.text, fontWeight: 600, padding: '12px 28px', borderRadius: 8, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 14 }}>
                            Talk to Engineering
                        </button>
                    </Link>
                </div>
            </section>

        </div>
    );
}