/* ═══════════════════════════════════════════════════
   Shared design tokens + data for /developers
   Importable by both server and client components
   ═══════════════════════════════════════════════════ */

export const T = {
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
    mono: "'JetBrains Mono', 'Fira Code', monospace",
    blue: '#60a5fa', blueBg: 'rgba(96,165,250,0.12)',
    amber: '#fbbf24', amberBg: 'rgba(251,191,36,0.1)',
    red: '#ef4444', redBg: 'rgba(239,68,68,0.08)',
};

export const NAV_SECTIONS = [
    { id: 'quickstart', label: 'Quickstart' },
    { id: 'examples', label: 'Examples' },
    { id: 'endpoints', label: 'Endpoints' },
    { id: 'auth', label: 'Auth' },
    { id: 'errors', label: 'Errors' },
    { id: 'webhooks', label: 'Webhooks' },
    { id: 'sdks', label: 'SDKs' },
    { id: 'resources', label: 'Resources' },
];

export const QUICKSTART = [
    { step: 1, title: 'Get your API key', desc: 'Generate a per-tenant key from the Developer Portal. Keys are scoped with RBAC.', link: '/developer/portal', linkText: 'Open Portal' },
    { step: 2, title: 'Record your first CTE', desc: 'POST a receiving event to /v1/webhooks/ingest. Every event gets a SHA-256 chain hash.', link: '/docs/quickstart', linkText: 'Quickstart Guide' },
    { step: 3, title: 'Check compliance', desc: 'GET your compliance score. Six dimensions scored 0-100 with an overall grade and next actions.', link: '/docs/api', linkText: 'API Reference' },
];

export const PLATFORM_STATS = [
    { label: 'Uptime', value: '99.9%', iconName: 'Activity' as const },
    { label: 'Avg Latency', value: '<150ms', iconName: 'Clock' as const },
    { label: 'Endpoints', value: '9', iconName: 'Globe' as const },
    { label: 'Chain Verified', value: 'SHA-256', iconName: 'Hash' as const },
];

export const ENDPOINT_GROUPS = [
    { category: 'Traceability', iconName: 'Layers' as const, endpoints: [
        { method: 'POST', path: '/v1/webhooks/ingest', desc: 'Ingest CTEs (batch)', latency: '~120ms' },
        { method: 'POST', path: '/v1/epcis/events', desc: 'Ingest EPCIS 2.0 events', latency: '~150ms' },
        { method: 'GET', path: '/v1/epcis/events/:id', desc: 'Get event by ID', latency: '~45ms' },
        { method: 'GET', path: '/v1/epcis/chain/verify', desc: 'Verify chain integrity', latency: '~90ms' },
    ]},
    { category: 'Compliance', iconName: 'Shield' as const, endpoints: [
        { method: 'GET', path: '/v1/compliance/score/:tenant_id', desc: 'Compliance risk score', latency: '~200ms' },
        { method: 'GET', path: '/v1/fda/export', desc: 'Export FDA package', latency: '~800ms' },
        { method: 'POST', path: '/v1/recall-simulations/run', desc: 'Run recall drill', latency: '~2s' },
    ]},
    { category: 'Utilities', iconName: 'Package' as const, endpoints: [
        { method: 'POST', path: '/v1/qr/decode', desc: 'Decode GS1/GTIN barcode', latency: '~30ms' },
        { method: 'GET', path: '/v1/audit-log/:tenant_id', desc: 'Audit log with chain hashes', latency: '~100ms' },
    ]},
];

export const SDK_ITEMS = [
    { lang: 'Python', status: 'planned' as const, note: 'Planned', icon: '🐍', docsHref: '/docs/sdks' },
    { lang: 'Node.js', status: 'planned' as const, note: 'Planned', icon: '⬢', docsHref: '/docs/sdks' },
    { lang: 'Go', status: 'planned' as const, note: 'Planned', icon: '🔵', docsHref: '/docs/sdks' },
];

export const ERROR_EXAMPLES = [
    { code: 400, title: 'Missing required field', body: `{ "error": "validation_error", "message": "events[0].tlc is required", "field": "events[0].tlc" }` },
    { code: 401, title: 'Invalid API key', body: `{ "error": "unauthorized", "message": "API key is invalid or expired" }` },
    { code: 422, title: 'Schema violation', body: `{ "error": "schema_error", "message": "event_type must be one of: receiving, shipping, transforming", "allowed": ["receiving", "shipping", "transforming"] }` },
    { code: 429, title: 'Rate limited', body: `{ "error": "rate_limited", "message": "Too many requests", "retry_after_seconds": 30 }` },
];

export const WEBHOOK_EVENTS = [
    { event: 'cte.created', desc: 'New CTE recorded and chain-hashed', payload: 'event_id, tlc, type, chain_hash' },
    { event: 'compliance.score_changed', desc: 'Tenant compliance score updated', payload: 'tenant_id, old_score, new_score, grade' },
    { event: 'recall.simulation_complete', desc: 'Recall drill finished', payload: 'simulation_id, lots_affected, sla_met' },
    { event: 'chain.integrity_alert', desc: 'Chain verification anomaly detected', payload: 'tenant_id, expected_hash, actual_hash' },
];
