'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
    Terminal, ArrowRight, Zap, Shield, BookOpen,
    Copy, Check, ChevronRight, ChevronDown, Layers, Lock, Activity,
    Package, Webhook, FileJson, BarChart3, Clock, Globe,
    Hash, Database, ArrowUpRight, Download, AlertTriangle,
    ExternalLink, Keyboard, Play,
} from 'lucide-react';

/* ═══════════════════════════════════════════════════
   DESIGN TOKENS
   ═══════════════════════════════════════════════════ */
const T = {
    bg: 'var(--re-surface-base)',
    surface: 'var(--re-surface-card, rgba(255,255,255,0.02))',
    surfaceHover: 'var(--re-surface-elevated, rgba(255,255,255,0.05))',
    border: 'var(--re-border-default, rgba(255,255,255,0.06))',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentBg: 'rgba(16,185,129,0.08)',
    accentBorder: 'rgba(16,185,129,0.2)',
    mono: "'JetBrains Mono', 'Fira Code', monospace",    blue: '#60a5fa', blueBg: 'rgba(96,165,250,0.12)',
    amber: '#fbbf24', amberBg: 'rgba(251,191,36,0.1)',
    red: '#ef4444', redBg: 'rgba(239,68,68,0.08)',
};

/* ═══════════════════════════════════════════════════
   GLOBAL CSS — hover states, animations, responsive
   ═══════════════════════════════════════════════════ */
const GLOBAL_CSS = `
@keyframes re-fade-in { from { opacity:0; transform:translateY(8px) } to { opacity:1; transform:translateY(0) } }
@keyframes re-pulse-dot { 0%,100% { opacity:1 } 50% { opacity:.4 } }
@keyframes re-count-in { from { opacity:0; transform:scale(0.8) } to { opacity:1; transform:scale(1) } }
.re-dev-card { transition: border-color .2s, background .2s, transform .15s; }
.re-dev-card:hover { border-color: rgba(255,255,255,0.12) !important; background: rgba(255,255,255,0.04) !important; transform: translateY(-2px); }
.re-endpoint-row { transition: border-color .15s, background .15s; }
.re-endpoint-row:hover { border-color: rgba(16,185,129,0.18) !important; background: rgba(255,255,255,0.03) !important; }
.re-btn-primary { transition: opacity .15s, transform .1s, box-shadow .15s; }
.re-btn-primary:hover { opacity:.92; transform:translateY(-1px); box-shadow: 0 4px 16px rgba(16,185,129,0.25); }
.re-btn-secondary { transition: border-color .15s, background .15s; }
.re-btn-secondary:hover { border-color: rgba(255,255,255,0.15) !important; background: rgba(255,255,255,0.03) !important; }
.re-link-accent { transition: opacity .15s; }
.re-link-accent:hover { opacity:.8; }
.re-code-tab { transition: all .15s; }
.re-code-tab:hover { color: rgba(255,255,255,0.7) !important; }
.re-nav-link { transition: color .15s, background .15s; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 500; text-decoration: none; white-space: nowrap; }
.re-nav-link:hover { background: rgba(255,255,255,0.04); }.re-nav-active { background: rgba(16,185,129,0.08) !important; color: var(--re-brand) !important; }
.re-grid-bg { background-image: radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px); background-size: 24px 24px; }
.re-sticky-nav { position: sticky; top: 0; z-index: 50; backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); background: rgba(10,10,10,0.85); border-bottom: 1px solid rgba(255,255,255,0.06); }
.re-kbd { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; padding: 0 5px; font-size: 10px; font-family: inherit; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; color: rgba(255,255,255,0.4); }
@media (max-width: 768px) {
  .re-endpoint-row { flex-wrap: wrap !important; gap: 6px !important; }
  .re-endpoint-row code { font-size: 11px !important; }
  .re-endpoint-desc { display: none !important; }
  .re-endpoint-latency { display: none !important; }
  .re-hero-stats { grid-template-columns: repeat(2, 1fr) !important; }
  .re-sticky-nav { display: none !important; }
  .re-nav-shortcuts { display: none !important; }
  .re-base-url { font-size: 11px !important; }
}
`;
/* ═══════════════════════════════════════════════════
   SYNTAX HIGHLIGHTING (zero-dep)
   ═══════════════════════════════════════════════════ */
function highlightSyntax(code: string, lang: 'curl' | 'python' | 'node'): React.ReactNode[] {
    const lines = code.split('\n');
    return lines.map((line, i) => {
        if (line.trimStart().startsWith('#') || line.trimStart().startsWith('//')) {
            return <span key={i}><span style={{ color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>{line}</span>{'\n'}</span>;
        }
        const patterns: [RegExp, string][] = lang === 'curl' ? [
            [/\b(curl)\b/g, '#c792ea'], [/-[HXd]\b/g, '#82aaff'],
            [/"[^"]*"/g, '#c3e88d'], [/https?:\/\/\S+/g, '#89ddff'],
        ] : lang === 'python' ? [
            [/\b(import|from|as|print|def|return|if|else|for|in)\b/g, '#c792ea'],
            [/\b(requests|resp|score|sim)\b/g, '#82aaff'],
            [/(f?"[^"]*"|'[^']*')/g, '#c3e88d'], [/\b\d+\b/g, '#f78c6c'],
        ] : [
            [/\b(const|let|var|await|async|import|from|export)\b/g, '#c792ea'],
            [/\b(fetch|console|JSON)\b/g, '#82aaff'],
            [/("[^"]*"|'[^']*'|`[^`]*`)/g, '#c3e88d'], [/\b\d+\b/g, '#f78c6c'],
        ];
        let segments: { text: string; color?: string }[] = [{ text: line }];
        for (const [regex, color] of patterns) {
            const next: { text: string; color?: string }[] = [];
            for (const seg of segments) {
                if (seg.color) { next.push(seg); continue; }
                let last = 0;
                const r = new RegExp(regex.source, regex.flags);
                let m: RegExpExecArray | null;                while ((m = r.exec(seg.text)) !== null) {
                    if (m.index > last) next.push({ text: seg.text.slice(last, m.index) });
                    next.push({ text: m[0], color });
                    last = m.index + m[0].length;
                }
                if (last < seg.text.length) next.push({ text: seg.text.slice(last) });
            }
            segments = next;
        }
        return (
            <span key={i}>
                {segments.map((s, j) => s.color
                    ? <span key={j} style={{ color: s.color }}>{s.text}</span>
                    : <span key={j}>{s.text}</span>
                )}{'\n'}
            </span>
        );
    });
}

/* Highlight JSON response */
function highlightJSON(json: string): React.ReactNode[] {
    return json.split('\n').map((line, i) => {
        const parts: React.ReactNode[] = [];
        let remaining = line;
        let key = 0;
        // Keys
        remaining = line.replace(/"([^"]+)":/g, (_, k) => `__KEY__${k}__ENDKEY__:`);
        // String values
        remaining = remaining.replace(/: "([^"]+)"/g, ': __STR__$1__ENDSTR__');        // Booleans & numbers
        remaining = remaining.replace(/\b(true|false|null)\b/g, '__BOOL__$1__ENDBOOL__');
        remaining = remaining.replace(/:\s*(\d+\.?\d*)/g, ': __NUM__$1__ENDNUM__');
        const tokens = remaining.split(/(__KEY__|__ENDKEY__|__STR__|__ENDSTR__|__BOOL__|__ENDBOOL__|__NUM__|__ENDNUM__)/);
        let mode = 'normal';
        for (const token of tokens) {
            if (token === '__KEY__') { mode = 'key'; continue; }
            if (token === '__ENDKEY__') { mode = 'normal'; continue; }
            if (token === '__STR__') { mode = 'str'; continue; }
            if (token === '__ENDSTR__') { mode = 'normal'; continue; }
            if (token === '__BOOL__') { mode = 'bool'; continue; }
            if (token === '__ENDBOOL__') { mode = 'normal'; continue; }
            if (token === '__NUM__') { mode = 'num'; continue; }
            if (token === '__ENDNUM__') { mode = 'normal'; continue; }
            if (!token) continue;
            const color = mode === 'key' ? '#82aaff' : mode === 'str' ? '#c3e88d' : mode === 'bool' ? '#c792ea' : mode === 'num' ? '#f78c6c' : undefined;
            parts.push(color ? <span key={key++} style={{ color }}>{mode === 'key' ? `"${token}"` : mode === 'str' ? `"${token}"` : token}</span> : <span key={key++}>{token}</span>);
        }
        return <span key={i}>{parts}{'\n'}</span>;
    });
}
/* ═══════════════════════════════════════════════════
   DATA — Code Examples with Response Previews
   ═══════════════════════════════════════════════════ */
const EXAMPLES: Record<string, { curl: string; python: string; node: string; response: string }> = {
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
    headers={"X-RegEngine-API-Key": "rge_live_abc123"},    json={"events": [{
        "event_type": "receiving",
        "tlc": "LOT-2024-001",
        "product_description": "Fresh Romaine Lettuce",
        "quantity": 500, "unit": "cases",
        "location_name": "Main Warehouse",
        "timestamp": "2025-03-10T14:30:00Z",
        "kdes": {"supplier_lot": "SUPP-TF-2024-001"}
    }]}
)
print(resp.json())`,
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
const data = await resp.json();`,        response: `{
  "status": "ok",
  "ingested": 1,
  "chain_hash": "sha256:a1b2c3d4e5f6...",
  "event_ids": ["evt_9f8e7d6c5b4a"],
  "timestamp": "2025-03-10T14:30:01Z"
}`,
    },
    'Compliance Score': {
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
        response: `{
  "tenant_id": "tenant_abc",
  "overall_score": 87,
  "grade": "B+",  "breakdown": {
    "chain_integrity": { "score": 95, "weight": 0.25 },
    "kde_completeness": { "score": 82, "weight": 0.20 },
    "cte_completeness": { "score": 88, "weight": 0.20 }
  },
  "next_actions": [
    { "priority": "high", "action": "Add supplier GLN" }
  ]
}`,
    },
    'Recall Drill': {
        curl: `curl -X POST https://api.regengine.co/v1/recall-simulations/run \\
  -H "X-RegEngine-API-Key: rge_live_abc123" \\
  -H "Content-Type: application/json" \\
  -d '{
    "tenant_id": "tenant_abc",
    "tlc": "LOT-2024-001",
    "reason": "Quarterly drill"
  }'`,
        python: `import requests

resp = requests.post(
    "https://api.regengine.co/v1/recall-simulations/run",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"},
    json={
        "tenant_id": "tenant_abc",
        "tlc": "LOT-2024-001",
        "reason": "Quarterly drill"
    }
)
sim = resp.json()
print(f"Traced {sim['lots_affected']} lots in {sim['response_time_hours']}h")`,        node: `const resp = await fetch(
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
const sim = await resp.json();`,
        response: `{
  "simulation_id": "sim_7a8b9c0d",
  "status": "complete",
  "lots_affected": 12,
  "suppliers_traced": 3,
  "facilities_involved": 5,
  "response_time_hours": 4.2,
  "sla_target_hours": 24,
  "sla_met": true,
  "fda_package_ready": true
}`,
    },
};
/* ═══════════════════════════════════════════════════
   DATA — Endpoints, Quickstart, SDKs, Stats
   ═══════════════════════════════════════════════════ */
const ENDPOINT_GROUPS = [
    { category: 'Traceability', Icon: Layers, endpoints: [
        { method: 'POST', path: '/v1/webhooks/ingest', desc: 'Ingest CTEs (batch)', latency: '~120ms' },
        { method: 'POST', path: '/v1/epcis/events', desc: 'Ingest EPCIS 2.0 events', latency: '~150ms' },
        { method: 'GET', path: '/v1/epcis/events/:id', desc: 'Get event by ID', latency: '~45ms' },
        { method: 'GET', path: '/v1/epcis/chain/verify', desc: 'Verify chain integrity', latency: '~90ms' },
    ]},
    { category: 'Compliance', Icon: Shield, endpoints: [
        { method: 'GET', path: '/v1/compliance/score/:tenant_id', desc: 'Compliance risk score', latency: '~200ms' },
        { method: 'GET', path: '/v1/fda/export', desc: 'Export FDA package', latency: '~800ms' },
        { method: 'POST', path: '/v1/recall-simulations/run', desc: 'Run recall drill', latency: '~2s' },
    ]},
    { category: 'Utilities', Icon: Package, endpoints: [
        { method: 'POST', path: '/v1/qr/decode', desc: 'Decode GS1/GTIN barcode', latency: '~30ms' },
        { method: 'GET', path: '/v1/audit-log/:tenant_id', desc: 'Audit log with chain hashes', latency: '~100ms' },
    ]},
];

const QUICKSTART = [
    { step: 1, title: 'Get your API key', desc: 'Generate a per-tenant key from the Developer Portal. Keys are scoped with RBAC.', link: '/developer/portal', linkText: 'Open Portal' },
    { step: 2, title: 'Record your first CTE', desc: 'POST a receiving event to /v1/webhooks/ingest. Every event gets a SHA-256 chain hash.', link: '/docs/quickstart', linkText: 'Quickstart Guide' },
    { step: 3, title: 'Check compliance', desc: 'GET your compliance score. Six dimensions scored 0-100 with an overall grade and next actions.', link: '/docs/api', linkText: 'API Reference' },
];
const SDK_ITEMS = [
    { lang: 'Python', status: 'beta' as const, note: 'pip install regengine', icon: '🐍', docsHref: '/docs/sdks' },
    { lang: 'Node.js', status: 'beta' as const, note: 'npm install @regengine/sdk', icon: '⬢', docsHref: '/docs/sdks' },
    { lang: 'Ruby', status: 'planned' as const, note: 'Q3 2026', icon: '💎', docsHref: '/docs/sdks' },
    { lang: 'Go', status: 'planned' as const, note: 'Q4 2026', icon: '🔵', docsHref: '/docs/sdks' },
];

const PLATFORM_STATS = [
    { label: 'Uptime', value: '99.9%', Icon: Activity },
    { label: 'Avg Latency', value: '<150ms', Icon: Clock },
    { label: 'Endpoints', value: '9', Icon: Globe },
    { label: 'Chain Verified', value: 'SHA-256', Icon: Hash },
];

/* ── Error Examples ── */
const ERROR_EXAMPLES = [
    { code: 400, title: 'Missing required field', body: `{ "error": "validation_error", "message": "events[0].tlc is required", "field": "events[0].tlc" }` },
    { code: 401, title: 'Invalid API key', body: `{ "error": "unauthorized", "message": "API key is invalid or expired" }` },
    { code: 422, title: 'Schema violation', body: `{ "error": "schema_error", "message": "event_type must be one of: receiving, shipping, transforming", "allowed": ["receiving", "shipping", "transforming"] }` },
    { code: 429, title: 'Rate limited', body: `{ "error": "rate_limited", "message": "Too many requests", "retry_after_seconds": 30 }` },
];

/* ── Webhook Event Types ── */
const WEBHOOK_EVENTS = [
    { event: 'cte.created', desc: 'New CTE recorded and chain-hashed', payload: 'event_id, tlc, type, chain_hash' },
    { event: 'compliance.score_changed', desc: 'Tenant compliance score updated', payload: 'tenant_id, old_score, new_score, grade' },
    { event: 'recall.simulation_complete', desc: 'Recall drill finished', payload: 'simulation_id, lots_affected, sla_met' },
    { event: 'chain.integrity_alert', desc: 'Chain verification anomaly detected', payload: 'tenant_id, expected_hash, actual_hash' },
];
/* ── Section Nav Items ── */
const NAV_SECTIONS = [
    { id: 'quickstart', label: 'Quickstart' },
    { id: 'examples', label: 'Examples' },
    { id: 'endpoints', label: 'Endpoints' },
    { id: 'auth', label: 'Auth' },
    { id: 'errors', label: 'Errors' },
    { id: 'webhooks', label: 'Webhooks' },
    { id: 'sdks', label: 'SDKs' },
    { id: 'resources', label: 'Resources' },
];

/* ═══════════════════════════════════════════════════
   COMPONENTS
   ═══════════════════════════════════════════════════ */
function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    const copy = useCallback(() => {
        navigator.clipboard.writeText(text).then(() => { setCopied(true); setTimeout(() => setCopied(false), 2000); });
    }, [text]);
    return (
        <button onClick={copy} aria-label={copied ? 'Copied' : 'Copy to clipboard'}
            style={{ position: 'absolute', top: 12, right: 12, background: 'rgba(255,255,255,0.06)', border: `1px solid ${T.border}`, borderRadius: 6, padding: '4px 10px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, color: copied ? T.accent : T.textMuted, transition: 'all 0.2s', zIndex: 5 }}>
            {copied ? <Check style={{ width: 12, height: 12 }} /> : <Copy style={{ width: 12, height: 12 }} />}
            {copied ? 'Copied!' : 'Copy'}
        </button>
    );
}
function CodeBlock({ examples, response }: { examples: { curl: string; python: string; node: string }; response: string }) {
    const [lang, setLang] = useState<'curl' | 'python' | 'node'>('curl');
    const [showResponse, setShowResponse] = useState(false);
    const labels: Record<string, string> = { curl: 'cURL', python: 'Python', node: 'Node.js' };
    return (
        <div style={{ animation: 're-fade-in .3s ease-out' }}>
            <div style={{ position: 'relative', borderRadius: '10px 10px 0 0', overflow: 'hidden', border: `1px solid ${T.border}`, borderBottom: 'none' }}>
                <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}`, background: 'rgba(0,0,0,0.25)' }}>
                    {(Object.keys(labels) as Array<'curl' | 'python' | 'node'>).map((k) => (
                        <button key={k} onClick={() => setLang(k)} className="re-code-tab" style={{
                            padding: '9px 18px', fontSize: 12, fontWeight: 600, fontFamily: T.mono,
                            background: lang === k ? 'rgba(255,255,255,0.04)' : 'transparent',
                            color: lang === k ? T.accent : T.textMuted,
                            border: 'none', borderBottom: lang === k ? `2px solid ${T.accent}` : '2px solid transparent',
                            cursor: 'pointer',
                        }}>{labels[k]}</button>
                    ))}
                    <div style={{ flex: 1 }} />
                    <span style={{ padding: '9px 14px', fontSize: 11, color: 'rgba(255,255,255,0.18)', fontFamily: T.mono }}>request</span>
                </div>
                <div style={{ position: 'relative' }}>
                    <CopyButton text={examples[lang]} />
                    <pre style={{ background: 'rgba(0,0,0,0.4)', padding: '18px 18px 18px 22px', overflow: 'auto', fontSize: 12, lineHeight: 1.75, fontFamily: T.mono, color: T.textMuted, margin: 0, maxHeight: 340 }}>
                        <code>{highlightSyntax(examples[lang], lang)}</code>
                    </pre>
                </div>
            </div>            {/* Response toggle */}
            <div style={{ borderRadius: '0 0 10px 10px', overflow: 'hidden', border: `1px solid ${T.border}` }}>
                <button onClick={() => setShowResponse(!showResponse)} style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 18px', background: 'rgba(16,185,129,0.04)', border: 'none',
                    cursor: 'pointer', fontSize: 12, fontFamily: T.mono, color: T.accent, fontWeight: 600,
                }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981' }} />
                        200 OK — Response
                    </span>
                    <ChevronDown style={{ width: 14, height: 14, transition: 'transform .2s', transform: showResponse ? 'rotate(180deg)' : 'rotate(0)' }} />
                </button>
                {showResponse && (
                    <div style={{ position: 'relative' }}>
                        <CopyButton text={response} />
                        <pre style={{ background: 'rgba(0,0,0,0.35)', padding: '16px 18px 16px 22px', overflow: 'auto', fontSize: 12, lineHeight: 1.65, fontFamily: T.mono, margin: 0, maxHeight: 260, color: T.textMuted }}>
                            <code>{highlightJSON(response)}</code>
                        </pre>
                    </div>
                )}
            </div>
        </div>
    );
}
/* ═══════════════════════════════════════════════════
   MAIN PAGE
   ═══════════════════════════════════════════════════ */
export default function DevelopersPage() {
    const [activeExample, setActiveExample] = useState<string>('Record CTE');
    const [activeSection, setActiveSection] = useState('quickstart');
    const [env, setEnv] = useState<'production' | 'sandbox'>('production');
    const baseUrl = env === 'production' ? 'https://api.regengine.co' : 'https://sandbox.regengine.co';

    /* Inject CSS */
    useEffect(() => {
        const s = document.createElement('style');
        s.textContent = GLOBAL_CSS;
        document.head.appendChild(s);
        return () => { s.remove(); };
    }, []);

    /* Intersection observer for sticky nav highlight */
    useEffect(() => {
        const obs = new IntersectionObserver((entries) => {
            for (const e of entries) {
                if (e.isIntersecting) setActiveSection(e.target.id);
            }
        }, { rootMargin: '-20% 0px -70% 0px' });
        NAV_SECTIONS.forEach(({ id }) => {
            const el = document.getElementById(id);
            if (el) obs.observe(el);
        });
        return () => obs.disconnect();
    }, []);
    /* Keyboard shortcuts: 1/2/3 to switch examples */
    useEffect(() => {
        const keys = Object.keys(EXAMPLES);
        const handler = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            const idx = parseInt(e.key) - 1;
            if (idx >= 0 && idx < keys.length) setActiveExample(keys[idx]);
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    return (
        <div className="re-page re-grid-bg" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>

            {/* ═══ HERO ═══ */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '72px 24px 28px', textAlign: 'center' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accentBg, border: `1px solid ${T.accentBorder}`, borderRadius: 20, padding: '6px 16px', fontSize: 13, fontWeight: 600, color: T.accent, marginBottom: 24 }}>
                    <Terminal style={{ width: 14, height: 14 }} />
                    REST API &middot; EPCIS 2.0 &middot; Webhooks
                </div>
                <h1 style={{ fontSize: 'clamp(34px, 5vw, 56px)', fontWeight: 700, color: T.heading, lineHeight: 1.05, margin: '0 0 18px', letterSpacing: '-0.025em' }}>
                    Build FSMA 204 compliance<br />
                    <span style={{ color: T.accent }}>into your stack</span>
                </h1>
                <p style={{ fontSize: 18, color: T.textMuted, maxWidth: 580, margin: '0 auto 28px', lineHeight: 1.65 }}>
                    One API to record CTEs, verify chain integrity, run recall simulations, and export FDA-ready packages. Ship compliance in hours, not months.
                </p>
                {/* Time to integrate */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20, marginBottom: 32, flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: 36, fontWeight: 700, color: T.accent, fontFamily: T.mono, animation: 're-count-in .6s ease-out' }}>5</span>
                        <span style={{ fontSize: 14, color: T.textMuted }}>min to first CTE</span>
                    </div>
                    <div style={{ width: 1, height: 28, background: T.border }} />
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: 36, fontWeight: 700, color: T.accent, fontFamily: T.mono, animation: 're-count-in .6s ease-out .1s both' }}>1</span>
                        <span style={{ fontSize: 14, color: T.textMuted }}>API call to record</span>
                    </div>
                    <div style={{ width: 1, height: 28, background: T.border }} />
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: 36, fontWeight: 700, color: T.accent, fontFamily: T.mono, animation: 're-count-in .6s ease-out .2s both' }}>24h</span>
                        <span style={{ fontSize: 14, color: T.textMuted }}>recall SLA</span>
                    </div>
                </div>

                {/* CTA */}
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap', marginBottom: 40 }}>
                    <Link href="/docs/api">
                        <button className="re-btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accent, color: '#000', fontWeight: 600, padding: '13px 30px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 14 }}>
                            API Reference <ArrowRight style={{ width: 16, height: 16 }} />
                        </button>
                    </Link>
                    <a href="#quickstart">
                        <button className="re-btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'transparent', color: T.text, fontWeight: 600, padding: '13px 30px', borderRadius: 8, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 14 }}>
                            Quickstart Guide
                        </button>
                    </a>
                </div>
                {/* Stats bar */}
                <div className="re-hero-stats" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1, background: T.border, borderRadius: 12, overflow: 'hidden', border: `1px solid ${T.border}` }}>
                    {PLATFORM_STATS.map((s) => (
                        <div key={s.label} style={{ background: T.surface, padding: '16px 12px', textAlign: 'center' }}>
                            <s.Icon style={{ width: 14, height: 14, color: T.accent, margin: '0 auto 6px', display: 'block' }} />
                            <div style={{ fontSize: 18, fontWeight: 700, color: T.heading, fontFamily: T.mono }}>{s.value}</div>
                            <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{s.label}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ═══ STICKY NAV ═══ */}
            <nav className="re-sticky-nav" style={{ marginBottom: 0 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '0 24px', display: 'flex', alignItems: 'center', gap: 4, overflowX: 'auto' }}>
                    {NAV_SECTIONS.map((s) => (
                        <a key={s.id} href={`#${s.id}`} className={`re-nav-link ${activeSection === s.id ? 're-nav-active' : ''}`}
                            style={{ color: activeSection === s.id ? T.accent : T.textMuted }}>
                            {s.label}
                        </a>
                    ))}
                    <div style={{ flex: 1 }} />
                    {/* Env toggle */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 0, background: 'rgba(255,255,255,0.03)', borderRadius: 6, border: `1px solid ${T.border}`, overflow: 'hidden' }}>
                        {(['production', 'sandbox'] as const).map((e) => (
                            <button key={e} onClick={() => setEnv(e)} style={{
                                padding: '5px 12px', fontSize: 11, fontWeight: 600, fontFamily: T.mono, border: 'none', cursor: 'pointer',
                                background: env === e ? (e === 'production' ? T.accentBg : T.amberBg) : 'transparent',
                                color: env === e ? (e === 'production' ? T.accent : T.amber) : T.textMuted,
                                transition: 'all .15s', textTransform: 'capitalize',
                            }}>{e}</button>
                        ))}
                    </div>
                </div>
            </nav>
            {/* Base URL indicator */}
            <div style={{ maxWidth: 880, margin: '0 auto', padding: '16px 24px 0' }}>
                <div className="re-base-url" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: env === 'production' ? T.accentBg : T.amberBg, border: `1px solid ${env === 'production' ? T.accentBorder : 'rgba(251,191,36,0.2)'}`, borderRadius: 6, padding: '6px 14px', fontSize: 12, fontFamily: T.mono }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: env === 'production' ? '#10b981' : T.amber, animation: 're-pulse-dot 2s ease-in-out infinite' }} />
                    <span style={{ color: T.textMuted }}>Base URL:</span>
                    <span style={{ color: env === 'production' ? T.accent : T.amber, fontWeight: 600 }}>{baseUrl}</span>
                </div>
            </div>

            {/* ═══ QUICKSTART ═══ */}
            <section id="quickstart" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '48px 24px 48px', scrollMarginTop: 60 }}>
                <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Get Started</h2>
                <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, marginBottom: 28 }}>Three steps to your first compliance event</p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                    {QUICKSTART.map((s, idx) => (
                        <div key={s.step} className="re-dev-card" style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: '24px 20px', animation: `re-fade-in .4s ease-out ${idx * 0.08}s both` }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
                                <span style={{ width: 30, height: 30, borderRadius: '50%', background: T.accentBg, border: `1px solid ${T.accentBorder}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700, color: T.accent }}>{s.step}</span>
                                <h3 style={{ fontSize: 15, fontWeight: 600, color: T.heading, margin: 0 }}>{s.title}</h3>
                            </div>
                            <p style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.6, margin: '0 0 16px' }}>{s.desc}</p>
                            <Link href={s.link} className="re-link-accent" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, fontWeight: 600, color: T.accent, textDecoration: 'none' }}>
                                {s.linkText} <ChevronRight style={{ width: 12, height: 12 }} />
                            </Link>
                        </div>
                    ))}
                </div>
            </section>
            {/* ═══ CODE EXAMPLES ═══ */}
            <section id="examples" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 8 }}>
                        <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Try it now</h2>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <span className="re-nav-shortcuts" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'rgba(255,255,255,0.2)' }}>
                                <Keyboard style={{ width: 12, height: 12 }} /> Press <kbd className="re-kbd">1</kbd><kbd className="re-kbd">2</kbd><kbd className="re-kbd">3</kbd> to switch
                            </span>
                            <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', animation: 're-pulse-dot 2s ease-in-out infinite' }} />
                                <span style={{ fontSize: 12, color: T.textMuted }}>Live API</span>
                            </span>
                        </div>
                    </div>
                    <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 28, maxWidth: 540 }}>
                        Copy-paste examples against the live API. Toggle response preview to see exactly what comes back.
                    </p>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
                        {Object.keys(EXAMPLES).map((name, idx) => (
                            <button key={name} onClick={() => setActiveExample(name)} style={{
                                padding: '8px 18px', fontSize: 13, fontWeight: 500, borderRadius: 8,
                                background: activeExample === name ? T.accentBg : 'transparent',
                                color: activeExample === name ? T.accent : T.textMuted,
                                border: `1px solid ${activeExample === name ? T.accentBorder : T.border}`,
                                cursor: 'pointer', transition: 'all 0.15s',
                            }}>
                                {name} <span className="re-nav-shortcuts" style={{ marginLeft: 4, opacity: 0.4, fontSize: 11 }}>{idx + 1}</span>
                            </button>
                        ))}
                    </div>
                    <CodeBlock examples={EXAMPLES[activeExample]} response={EXAMPLES[activeExample].response} />
                </div>
            </section>
            {/* ═══ API ENDPOINTS ═══ */}
            <section id="endpoints" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '64px 24px', scrollMarginTop: 60 }}>
                <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Reference</h2>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                    <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, margin: 0 }}>API Endpoints</p>
                    <div style={{ display: 'flex', gap: 8 }}>
                        <a href="/docs/api" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: T.accent, textDecoration: 'none', fontWeight: 600 }}>
                            Full docs <ExternalLink style={{ width: 11, height: 11 }} />
                        </a>
                    </div>
                </div>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 32 }}>
                    All endpoints require <code style={{ fontFamily: T.mono, fontSize: 12, color: T.accent, background: T.accentBg, padding: '2px 8px', borderRadius: 4 }}>X-RegEngine-API-Key</code>. Latency shown is p50 production.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
                    {ENDPOINT_GROUPS.map((g) => (
                        <div key={g.category}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                                <g.Icon style={{ width: 15, height: 15, color: T.accent }} />
                                <h3 style={{ fontSize: 13, fontWeight: 700, color: T.heading, margin: 0, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{g.category}</h3>
                                <span style={{ fontSize: 11, color: T.textMuted }}>{g.endpoints.length} endpoints</span>
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                {g.endpoints.map((ep, i) => (
                                    <div key={i} className="re-endpoint-row" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8 }}>
                                        <span style={{ fontSize: 11, fontWeight: 700, fontFamily: T.mono, padding: '3px 8px', borderRadius: 4, minWidth: 46, textAlign: 'center' as const, background: ep.method === 'POST' ? T.accentBg : T.blueBg, color: ep.method === 'POST' ? T.accent : T.blue }}>{ep.method}</span>
                                        <code style={{ fontSize: 13, fontFamily: T.mono, color: T.heading, flex: 1 }}>{ep.path}</code>
                                        <span className="re-endpoint-desc" style={{ fontSize: 12, color: T.textMuted }}>{ep.desc}</span>
                                        <span className="re-endpoint-latency" style={{ fontSize: 11, fontFamily: T.mono, color: 'rgba(255,255,255,0.2)', minWidth: 56, textAlign: 'right' as const }}>{ep.latency}</span>                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ═══ AUTHENTICATION ═══ */}
            <section id="auth" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                        <Lock style={{ width: 20, height: 20, color: T.accent }} />
                        <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Authentication</h2>
                    </div>
                    <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 24, maxWidth: 540 }}>
                        Per-tenant API keys with RBAC scoping. Generate keys in the <Link href="/developer/portal" style={{ color: T.accent, textDecoration: 'underline' }}>Developer Portal</Link>.
                    </p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
                        <div style={{ position: 'relative', borderRadius: 10, overflow: 'hidden', border: `1px solid ${T.border}` }}>
                            <div style={{ padding: '10px 16px', background: 'rgba(0,0,0,0.25)', borderBottom: `1px solid ${T.border}`, fontSize: 12, fontFamily: T.mono, color: T.textMuted, fontWeight: 600 }}>Required Headers</div>
                            <CopyButton text={`X-RegEngine-API-Key: rge_live_abc123\nContent-Type: application/json`} />
                            <pre style={{ background: 'rgba(0,0,0,0.35)', padding: '16px 18px', overflow: 'auto', fontSize: 12, lineHeight: 2.2, fontFamily: T.mono, color: T.textMuted, margin: 0 }}>
                                <code><span style={{ color: '#82aaff' }}>X-RegEngine-API-Key</span>: rge_live_...<br/><span style={{ color: '#82aaff' }}>Content-Type</span>: application/json</code>
                            </pre>
                        </div>
                        <div style={{ borderRadius: 10, overflow: 'hidden', border: `1px solid ${T.border}` }}>
                            <div style={{ padding: '10px 16px', background: 'rgba(0,0,0,0.25)', borderBottom: `1px solid ${T.border}`, fontSize: 12, fontFamily: T.mono, color: T.textMuted, fontWeight: 600 }}>Response Codes</div>
                            <div style={{ background: 'rgba(0,0,0,0.35)', padding: '10px 0' }}>
                                {[
                                    { code: '200', label: 'OK', desc: 'Sync response', color: '#10b981' },                                    { code: '202', label: 'Accepted', desc: 'Async job queued', color: '#10b981' },
                                    { code: '400', label: 'Bad Request', desc: 'Validation error', color: T.amber },
                                    { code: '401', label: 'Unauthorized', desc: 'Invalid key', color: T.red },
                                    { code: '422', label: 'Unprocessable', desc: 'Schema violation', color: T.red },
                                    { code: '429', label: 'Rate Limited', desc: 'Backoff required', color: T.amber },
                                ].map((r) => (
                                    <div key={r.code} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '5px 18px' }}>
                                        <code style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: r.color, minWidth: 28 }}>{r.code}</code>
                                        <span style={{ fontSize: 12, color: T.heading, minWidth: 90 }}>{r.label}</span>
                                        <span style={{ fontSize: 11, color: T.textMuted }}>{r.desc}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ═══ ERROR HANDLING ═══ */}
            <section id="errors" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '64px 24px', scrollMarginTop: 60 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                    <AlertTriangle style={{ width: 20, height: 20, color: T.amber }} />
                    <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Error Handling</h2>
                </div>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 24, maxWidth: 540 }}>
                    All errors return structured JSON with an error code, message, and relevant context. Parse the <code style={{ fontFamily: T.mono, fontSize: 12, color: T.accent }}>error</code> field for programmatic handling.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    {ERROR_EXAMPLES.map((err) => (
                        <div key={err.code} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, overflow: 'hidden' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: `1px solid ${T.border}` }}>                                <code style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: err.code >= 500 ? T.red : err.code >= 400 ? T.amber : T.accent }}>{err.code}</code>
                                <span style={{ fontSize: 13, fontWeight: 600, color: T.heading }}>{err.title}</span>
                            </div>
                            <pre style={{ background: 'rgba(0,0,0,0.25)', padding: '12px 16px', fontSize: 12, lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted, margin: 0, overflow: 'auto' }}>
                                <code>{err.body}</code>
                            </pre>
                        </div>
                    ))}
                </div>
            </section>

            {/* ═══ WEBHOOKS ═══ */}
            <section id="webhooks" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                        <Webhook style={{ width: 20, height: 20, color: T.accent }} />
                        <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Webhook Events</h2>
                    </div>
                    <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 24, maxWidth: 540 }}>
                        Subscribe to real-time events via webhook. All payloads include a <code style={{ fontFamily: T.mono, fontSize: 12, color: T.accent }}>chain_hash</code> for verification.
                        <Link href="/docs/webhooks" style={{ color: T.accent, marginLeft: 6, textDecoration: 'underline', fontSize: 13 }}>Setup guide</Link>
                    </p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {WEBHOOK_EVENTS.map((w) => (
                            <div key={w.event} className="re-endpoint-row" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8 }}>
                                <code style={{ fontSize: 13, fontFamily: T.mono, color: T.accent, fontWeight: 600, minWidth: 200 }}>{w.event}</code>
                                <span style={{ fontSize: 12, color: T.heading, flex: 1 }}>{w.desc}</span>
                                <span className="re-endpoint-desc" style={{ fontSize: 11, fontFamily: T.mono, color: T.textMuted }}>{w.payload}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>
            {/* ═══ SDKs ═══ */}
            <section id="sdks" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '64px 24px', scrollMarginTop: 60 }}>
                <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Client Libraries</h2>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                    <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, margin: 0 }}>SDKs &amp; Libraries</p>
                    <div style={{ display: 'flex', gap: 10 }}>
                        <a href="/docs/api" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: T.textMuted, textDecoration: 'none', fontWeight: 500, padding: '5px 12px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 6 }}>
                            <Download style={{ width: 12, height: 12 }} /> OpenAPI Spec
                        </a>
                        <a href="/docs/api" style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, color: T.textMuted, textDecoration: 'none', fontWeight: 500, padding: '5px 12px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 6 }}>
                            <Play style={{ width: 12, height: 12 }} /> Postman Collection
                        </a>
                    </div>
                </div>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 28 }}>
                    Official client libraries with typed helpers, automatic retries, and chain verification. The REST API works with any HTTP client.
                </p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(185px, 1fr))', gap: 12 }}>
                    {SDK_ITEMS.map((sdk, idx) => (
                        <Link key={sdk.lang} href={sdk.docsHref} style={{ textDecoration: 'none' }}>
                            <div className="re-dev-card" style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: '20px 16px', display: 'flex', flexDirection: 'column', gap: 8, animation: `re-fade-in .4s ease-out ${idx * 0.06}s both` }}>
                                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                    <span style={{ fontSize: 20 }}>{sdk.icon}</span>
                                    <span style={{ fontSize: 10, fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.06em', padding: '3px 8px', borderRadius: 4, background: sdk.status === 'beta' ? T.accentBg : T.amberBg, color: sdk.status === 'beta' ? T.accent : T.amber }}>{sdk.status}</span>
                                </div>
                                <h4 style={{ fontSize: 15, fontWeight: 600, color: T.heading, margin: 0 }}>{sdk.lang}</h4>
                                <code style={{ fontSize: 11, fontFamily: T.mono, color: T.textMuted }}>{sdk.note}</code>
                            </div>
                        </Link>
                    ))}
                </div>
            </section>
            {/* ═══ DEVELOPER RESOURCES ═══ */}
            <section id="resources" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                    <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Documentation</h2>
                    <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, marginBottom: 28 }}>Developer Resources</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 14 }}>
                        {[
                            { Icon: BookOpen, title: 'API Reference', desc: 'Complete endpoint docs with request/response schemas and error codes.', href: '/docs/api' },
                            { Icon: Zap, title: 'Quickstart', desc: 'From zero to first CTE in under 5 minutes with copy-paste examples.', href: '/docs/quickstart' },
                            { Icon: Webhook, title: 'Webhooks', desc: 'Real-time event ingestion with SHA-256 chain verification.', href: '/docs/webhooks' },
                            { Icon: FileJson, title: 'EPCIS 2.0', desc: 'Full GS1 EPCIS 2.0 standard event format support.', href: '/docs/api' },
                            { Icon: BarChart3, title: 'Rate Limits', desc: 'Throughput tiers, burst handling, and backoff strategy.', href: '/docs/rate-limits' },
                            { Icon: Activity, title: 'Changelog', desc: 'API updates, new endpoints, versioning, and deprecations.', href: '/docs/changelog' },
                        ].map((r) => (
                            <Link key={r.title} href={r.href} style={{ textDecoration: 'none' }}>
                                <div className="re-dev-card" style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 10, padding: '22px 18px', cursor: 'pointer', height: '100%' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                                        <r.Icon style={{ width: 18, height: 18, color: T.accent }} />
                                        <ArrowUpRight style={{ width: 13, height: 13, color: 'rgba(255,255,255,0.12)' }} />
                                    </div>
                                    <h4 style={{ fontSize: 14, fontWeight: 600, color: T.heading, margin: '0 0 6px' }}>{r.title}</h4>
                                    <p style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.55, margin: 0 }}>{r.desc}</p>
                                </div>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>
            {/* ═══ CTA ═══ */}
            <section style={{ position: 'relative', zIndex: 2, background: 'linear-gradient(135deg, rgba(16,185,129,0.06) 0%, rgba(16,185,129,0.02) 100%)', borderTop: `1px solid ${T.accentBorder}`, padding: '64px 24px', textAlign: 'center' }}>
                <Database style={{ width: 28, height: 28, color: T.accent, margin: '0 auto 16px', display: 'block', opacity: 0.7 }} />
                <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, marginBottom: 10 }}>Ready to integrate?</h2>
                <p style={{ fontSize: 15, color: T.textMuted, marginBottom: 28, maxWidth: 480, margin: '0 auto 28px', lineHeight: 1.6 }}>
                    Start with the public API or request guided onboarding for your engineering team.
                </p>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <Link href="/docs/quickstart">
                        <button className="re-btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accent, color: '#000', fontWeight: 600, padding: '14px 32px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 15 }}>
                            Start Building <ArrowRight style={{ width: 16, height: 16 }} />
                        </button>
                    </Link>
                    <Link href="/contact">
                        <button className="re-btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'transparent', color: T.text, fontWeight: 600, padding: '14px 32px', borderRadius: 8, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 15 }}>
                            Talk to Engineering
                        </button>
                    </Link>
                </div>
                <p style={{ fontSize: 11, color: T.textMuted, marginTop: 20, opacity: 0.5 }}>
                    API v1 &middot; Last updated March 2026
                </p>
            </section>

        </div>
    );
}