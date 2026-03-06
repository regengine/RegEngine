'use client';

import { useState, useEffect, Suspense } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';

// ─── Data ────────────────────────────────────────────────────────────────────

const LAYERS = [
    {
        id: 'ingress',
        label: 'INGRESS & INTEGRATION',
        color: '#0ff',
        y: 0,
        nodes: [
            {
                id: 'erp',
                label: 'ERP Connectors',
                detail: 'SAP, Oracle, NetSuite adapters. Normalize POs, ASNs, invoices into canonical CTE schema. Webhook + polling modes.',
                status: 'missing',
                x: 0,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'edi',
                label: 'EDI / CSV Bulk',
                detail: 'ANSI X12 856/810 parsing, CSV template mapper, drag-drop bulk import. Validates against FTL item list on ingest.',
                status: 'missing',
                x: 1,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'api',
                label: 'REST / SDK API',
                detail: 'Existing SDK + REST endpoints. Add OpenAPI 3.1 spec, rate-limited API keys per tenant, versioned routes.',
                status: 'exists',
                x: 2,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/shared/',
            },
            {
                id: 'webhooks',
                label: 'Webhook Bus',
                detail: 'Inbound: receive events from partner systems. Outbound: notify subscribers on CTE creation, compliance alerts. At-least-once delivery with retry queue.',
                status: 'missing',
                x: 3,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'iot',
                label: 'IoT / Sensor Feed',
                detail: 'MQTT/HTTP bridge for temperature loggers, GPS trackers. Auto-generates receiving/transformation CTEs with KDE enrichment.',
                status: 'future',
                x: 4,
                lastUpdated: 'Mar 2026',
            },
        ],
    },
    {
        id: 'processing',
        label: 'PROCESSING CORE',
        color: '#7df',
        y: 1,
        nodes: [
            {
                id: 'ingestion',
                label: 'Ingestion Pipeline',
                detail: 'Validates, deduplicates, normalizes incoming events. Schema validation against FSMA 204 KDE requirements. Dead-letter queue for failures.',
                status: 'exists',
                x: 0,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/ingestion/',
            },
            {
                id: 'nlp',
                label: 'NLP Engine',
                detail: 'Extracts obligations from regulatory text. Maps to controls. Needs fine-tuning on FDA guidance docs + FTL updates.',
                status: 'exists',
                x: 1,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/nlp/',
            },
            {
                id: 'compliance',
                label: 'Compliance Engine',
                detail: 'CTE → KDE validation, one-up/one-back chain verification, 24hr export SLA enforcement, FTL coverage scoring.',
                status: 'partial',
                x: 2,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/compliance/',
            },
            {
                id: 'opportunity',
                label: 'Opportunity Scorer',
                detail: 'Analyzes compliance data to identify business opportunities, tax credits, and supply chain optimizations.',
                status: 'exists',
                x: 3,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/opportunity/',
            },
            {
                id: 'scheduler',
                label: 'Job Scheduler',
                detail: 'Background jobs: hash chain computation, evidence rollup, report generation, stale-data alerts. Cron + event-driven.',
                status: 'exists',
                x: 4,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/scheduler/',
            },
            {
                id: 'billing',
                label: 'Billing Platform',
                detail: 'Usage-based billing, tenant invoicing, Stripe integration. 331/331 tests passing. Needs metering hooks from ingestion.',
                status: 'exists',
                x: 5,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/billing/',
            },
        ],
    },
    {
        id: 'data',
        label: 'DATA & EVIDENCE LAYER',
        color: '#4fa',
        y: 2,
        nodes: [
            {
                id: 'postgres',
                label: 'Postgres (RLS)',
                detail: 'Multi-tenant with row-level security + double-lock isolation. Stores CTEs, KDEs, tenants, users, audit logs. Needs partitioning strategy for scale.',
                status: 'exists',
                x: 0,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'neo4j',
                label: 'Neo4j Graph',
                detail: 'Obligation → Control → Evidence knowledge graph. Powers gap analysis and audit readiness scoring. Needs query optimization.',
                status: 'exists',
                x: 1,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/graph/',
            },
            {
                id: 'redis',
                label: 'Redis',
                detail: 'Rate limiting, session cache, job queues, real-time event pub/sub. Add cache-aside for hot compliance queries.',
                status: 'exists',
                x: 2,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'hashchain',
                label: 'Hash Chain Store',
                detail: 'SHA-256 tamper-evident evidence chain. Needs periodic anchor to external timestamping authority for non-repudiation.',
                status: 'exists',
                x: 3,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'blob',
                label: 'Document Store',
                detail: 'S3-compatible blob storage for evidence artifacts: photos, PDFs, signed docs. Needs retention policies + lifecycle rules.',
                status: 'missing',
                x: 4,
                lastUpdated: 'Mar 2026',
            },
        ],
    },
    {
        id: 'output',
        label: 'OUTPUT & AUDIT RESPONSE',
        color: '#f8a',
        y: 3,
        nodes: [
            {
                id: 'fdaexport',
                label: 'FDA Export Engine',
                detail: 'Sortable/searchable records within 24hrs. Must output IFT spreadsheet format per FDA spec. Needs validation against FDA example datasets.',
                status: 'partial',
                x: 0,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'dashboard',
                label: 'Compliance Dashboard',
                detail: 'Real-time readiness score, gap analysis, CTE coverage map. WCAG 2.1 AA compliant. Needs drill-down into specific obligation chains.',
                status: 'exists',
                x: 1,
                lastUpdated: 'Mar 2026',
                repoPath: 'frontend/src/app/dashboard/',
            },
            {
                id: 'alerts',
                label: 'Alert System',
                detail: 'Proactive notifications: missing KDEs, broken chains, approaching SLA deadlines. Email + in-app + webhook channels.',
                status: 'partial',
                x: 2,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'reports',
                label: 'Audit Reports',
                detail: 'Pre-built report templates: FTL coverage, traceability chain, evidence integrity. PDF + Excel export. Scheduled generation.',
                status: 'partial',
                x: 3,
                lastUpdated: 'Mar 2026',
            },
            {
                id: 'sandbox',
                label: 'Demo Sandbox',
                detail: 'Self-serve trial environment with synthetic supply chain data. Time-to-value under 30 min. Guided onboarding wizard.',
                status: 'missing',
                x: 4,
                lastUpdated: 'Mar 2026',
            },
        ],
    },
    {
        id: 'platform',
        label: 'PLATFORM & OPS',
        color: '#fa0',
        y: 4,
        nodes: [
            {
                id: 'observability',
                label: 'Observability Stack',
                detail: 'Distributed tracing (OpenTelemetry), structured logging, metrics dashboards, SLO/SLA monitoring. Alert routing to PagerDuty/Opsgenie.',
                status: 'missing',
                x: 0,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/admin/',
            },
            {
                id: 'auth',
                label: 'Auth & Identity',
                detail: 'Current: same-origin proxy auth. Needs: SSO/SAML, SCIM provisioning, granular RBAC (admin/auditor/supplier/viewer roles).',
                status: 'partial',
                x: 1,
                lastUpdated: 'Mar 2026',
                repoPath: 'services/shared/middleware/security.py',
            },
            {
                id: 'cicd',
                label: 'CI/CD & Testing',
                detail: '7 workflow files. Needs: E2E compliance flow tests, contract tests between services, load testing for ingestion spikes, chaos engineering.',
                status: 'partial',
                x: 2,
                lastUpdated: 'Mar 2026',
                repoPath: '.github/workflows/',
            },
            {
                id: 'infra',
                label: 'Infra & Scaling',
                detail: 'Railway current. Plan migration path: data residency options, horizontal scaling, cost model at 50/500 tenants, SOC2 Type II audit.',
                status: 'partial',
                x: 3,
                lastUpdated: 'Mar 2026',
                repoPath: 'infra/',
            },
            {
                id: 'agents',
                label: 'Agent Swarm',
                detail: 'Fractal agent layer for automated security audits, feature pipelines, persona management. Extend to compliance monitoring agents.',
                status: 'exists',
                x: 4,
                lastUpdated: 'Mar 2026',
                repoPath: '_agent/',
            },
        ],
    },
];

const STATUS_CONFIG = {
    exists: {
        label: 'Built',
        bg: '#12342a',
        border: '#4fa',
        glow: '0 0 12px rgba(79,255,170,0.3)',
        description: 'Component is fully deployed to production and actively used.'
    },
    partial: {
        label: 'In Progress',
        bg: '#2a2a10',
        border: '#fa0',
        glow: '0 0 12px rgba(255,170,0,0.25)',
        description: 'Currently in active development, beta testing, or pending secondary features.'
    },
    missing: {
        label: 'Needed',
        bg: '#341222',
        border: '#f44',
        glow: '0 0 12px rgba(255,68,68,0.25)',
        description: 'Planned requirement for v1.0 but development has not yet started.'
    },
    future: {
        label: 'Future',
        bg: '#1a1a2e',
        border: '#88f',
        glow: '0 0 12px rgba(136,136,255,0.2)',
        description: 'Strategic roadmap item for post-v1.0 scalability or enhanced vertical support.'
    },
};

const FLOWS = [
    { from: 'erp', to: 'ingestion', label: 'Normalized CTEs' },
    { from: 'edi', to: 'ingestion', label: 'Bulk Import' },
    { from: 'api', to: 'ingestion', label: 'API Events' },
    { from: 'webhooks', to: 'ingestion', label: 'Partner Events' },
    { from: 'iot', to: 'ingestion', label: 'Sensor Data' },
    { from: 'ingestion', to: 'postgres', label: 'Validated Records' },
    { from: 'ingestion', to: 'neo4j', label: 'Graph Updates' },
    { from: 'ingestion', to: 'opportunity', label: 'Data Mining' },
    { from: 'compliance', to: 'hashchain', label: 'Evidence Sealing' },
    { from: 'compliance', to: 'fdaexport', label: 'Audit Packages' },
    { from: 'postgres', to: 'dashboard', label: 'Live Queries' },
    { from: 'opportunity', to: 'dashboard', label: 'Business Insights' },
    { from: 'neo4j', to: 'reports', label: 'Gap Analysis' },
];

// ─── Dev-time flow integrity guard ───────────────────────────────────────────
if (typeof process !== 'undefined' && process.env.NODE_ENV === 'development') {
    const allIds = new Set(LAYERS.flatMap((l) => l.nodes.map((n) => n.id)));
    FLOWS.forEach((f) => {
        if (!allIds.has(f.from)) console.warn(`[Architecture] Unknown flow source: "${f.from}"`);
        if (!allIds.has(f.to)) console.warn(`[Architecture] Unknown flow target: "${f.to}"`);
    });
}

// ─── Component ───────────────────────────────────────────────────────────────

function RegEngineArchitectureContent() {
    const searchParams = useSearchParams();
    const router = useRouter();

    const [selected, setSelected] = useState(() => searchParams.get('node') ?? null);
    const [hoveredLayer, setHoveredLayer] = useState(null);
    const [showFlows, setShowFlows] = useState(true);
    const [filter, setFilter] = useState('all');
    const [searchQuery, setSearchQuery] = useState('');
    const [hoveredFlow, setHoveredFlow] = useState(null);
    const [showLegend, setShowLegend] = useState(false);

    // Sync selection → URL
    const handleSelect = (id) => {
        const next = selected === id ? null : id;
        setSelected(next);
        const params = new URLSearchParams(searchParams.toString());
        if (next) params.set('node', next);
        else params.delete('node');
        router.replace(`/architecture?${params.toString()}`, { scroll: false });
    };

    useEffect(() => {
        setSelected(searchParams.get('node') ?? null);
    }, [searchParams]);

    const selectedNode = selected ? LAYERS.flatMap((l) => l.nodes).find((n) => n.id === selected) : null;

    const matchesSearch = (node) => !searchQuery || node.label.toLowerCase().includes(searchQuery.toLowerCase()) || node.id.includes(searchQuery.toLowerCase());
    const matchesStatus = (node) => filter === 'all' || node.status === filter;
    const filteredVisible = (node) => matchesStatus(node) && matchesSearch(node);

    const counts = LAYERS.flatMap((l) => l.nodes).reduce((acc, n) => {
        acc[n.status] = (acc[n.status] || 0) + 1;
        return acc;
    }, {});

    return (
        <>
            <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0);   }
        }
        @keyframes pulseDot {
          0%, 100% { opacity: 0.7; }
          50%       { opacity: 1;   }
        }
        .arch-close-btn:focus-visible {
          outline: 2px solid #888;
          outline-offset: 2px;
        }
        @media (max-width: 640px) {
          .arch-filter-bar {
            flex-wrap: nowrap !important;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            padding-bottom: 4px;
          }
          .arch-filter-bar button {
            flex-shrink: 0;
          }
        }
        @media print {
          .arch-controls, .arch-filter-bar, .arch-search { display: none !important; }
          body { background: #fff !important; color: #000 !important; }
          * { box-shadow: none !important; animation: none !important; }
          [style*="background: #0a0a0f"] { background: #fff !important; }
          [style*="color: #e0e0e0"]       { color: #111 !important;  }
        }
        .legend-card {
            position: absolute;
            top: 40px;
            left: 0;
            width: 260px;
            background: #111118;
            border: 1px solid #222;
            padding: 16px;
            border-radius: 8px;
            z-index: 100;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            animation: fadeIn 0.15s ease-out;
        }
      `}</style>

            <div
                style={{
                    background: '#0a0a0f',
                    minHeight: '100vh',
                    fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
                    color: '#e0e0e0',
                    padding: '32px 24px',
                    position: 'relative',
                    overflow: 'hidden',
                }}
            >
                <div
                    style={{
                        position: 'fixed',
                        inset: 0,
                        backgroundImage:
                            'linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)',
                        backgroundSize: '40px 40px',
                        pointerEvents: 'none',
                        zIndex: 0,
                    }}
                />

                <div style={{ maxWidth: 1200, margin: '0 auto', position: 'relative', zIndex: 1 }}>
                    <div style={{ marginBottom: 8 }}>
                        <span style={{ fontSize: 10, letterSpacing: 4, color: '#666', textTransform: 'uppercase' }}>
                            Target State Architecture
                        </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 20 }}>
                        <div>
                            <h1
                                style={{
                                    fontSize: 36,
                                    fontWeight: 800,
                                    margin: '0 0 4px 0',
                                    background: 'linear-gradient(135deg, #0ff, #4fa, #f8a)',
                                    WebkitBackgroundClip: 'text',
                                    WebkitTextFillColor: 'transparent',
                                    letterSpacing: -1,
                                }}
                            >
                                RegEngine
                            </h1>
                            <p style={{ color: '#777', fontSize: 13, margin: '0 0 28px 0' }}>
                                FSMA 204 Compliance Infrastructure — Full System Map
                            </p>
                        </div>

                        <div className="arch-search" style={{ position: 'relative' }}>
                            <input
                                type="text"
                                placeholder="Find component..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                style={{
                                    background: '#12121a',
                                    border: '1px solid #222',
                                    borderRadius: 6,
                                    padding: '8px 12px 8px 32px',
                                    color: '#fff',
                                    fontSize: 12,
                                    fontFamily: 'inherit',
                                    width: 200,
                                    transition: 'border-color 0.2s',
                                }}
                            />
                            <span style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', opacity: 0.4, fontSize: 11 }}>🔍</span>
                            {searchQuery && (
                                <button
                                    onClick={() => setSearchQuery('')}
                                    style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#666', cursor: 'pointer', fontSize: 10 }}
                                >✕</button>
                            )}
                        </div>
                    </div>

                    <div
                        className="arch-filter-bar"
                        style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}
                    >
                        <div style={{ position: 'relative' }}>
                            <button
                                onClick={() => setShowLegend(!showLegend)}
                                style={{
                                    background: '#1a1a24',
                                    border: '1px solid #333',
                                    borderRadius: 6,
                                    width: 28,
                                    height: 28,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: 'pointer',
                                    color: showLegend ? '#4fa' : '#666',
                                    transition: 'all 0.2s',
                                }}
                            >
                                {showLegend ? '×' : 'ℹ'}
                            </button>
                            {showLegend && (
                                <div className="legend-card">
                                    <h4 style={{ margin: '0 0 12px 0', fontSize: 11, color: '#fff' }}>STATUS DEFINITIONS</h4>
                                    {Object.values(STATUS_CONFIG).map((cfg) => (
                                        <div key={cfg.label} style={{ marginBottom: 12 }}>
                                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                                <span style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.border }} />
                                                <span style={{ fontSize: 10, fontWeight: 700, color: cfg.border }}>{cfg.label.toUpperCase()}</span>
                                            </div>
                                            <div style={{ fontSize: 10, color: '#666', lineHeight: 1.4 }}>{cfg.description}</div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {Object.entries(STATUS_CONFIG).map(([key, cfg]) => (
                            <button
                                key={key}
                                onClick={() => setFilter(filter === key ? 'all' : key)}
                                style={{
                                    display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px', borderRadius: 6,
                                    border: `1px solid ${filter === key || filter === 'all' ? cfg.border : '#333'}`,
                                    background: filter === key ? cfg.bg : 'transparent',
                                    color: filter === key || filter === 'all' ? cfg.border : '#555',
                                    cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', transition: 'all 0.2s',
                                    opacity: filter === 'all' || filter === key ? 1 : 0.4,
                                }}
                            >
                                <span style={{ width: 8, height: 8, borderRadius: '50%', background: cfg.border, display: 'inline-block' }} />
                                {cfg.label} ({counts[key] || 0})
                            </button>
                        ))}

                        <div className="arch-controls" style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
                            <button
                                onClick={() => setShowFlows(!showFlows)}
                                style={{
                                    padding: '6px 14px', borderRadius: 6,
                                    border: `1px solid ${showFlows ? '#555' : '#333'}`,
                                    background: showFlows ? '#1a1a2e' : 'transparent',
                                    color: showFlows ? '#aaa' : '#555',
                                    cursor: 'pointer', fontSize: 11, fontFamily: 'inherit', transition: 'all 0.2s',
                                }}
                            >{showFlows ? '⬡' : '⬢'} Data Flows</button>
                            <button
                                onClick={() => window.print()}
                                style={{
                                    padding: '6px 14px', borderRadius: 6, border: '1px solid #333',
                                    background: 'transparent', color: '#555', cursor: 'pointer',
                                    fontSize: 11, fontFamily: 'inherit', transition: 'all 0.2s',
                                }}
                            >🖨 Export</button>
                        </div>
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {LAYERS.map((layer) => {
                            const builtCount = layer.nodes.filter(n => n.status === 'exists').length;
                            const totalCount = layer.nodes.length;
                            const progressPct = Math.round((builtCount / totalCount) * 100);

                            return (
                                <div
                                    key={layer.id}
                                    onMouseEnter={() => setHoveredLayer(layer.id)}
                                    onMouseLeave={() => setHoveredLayer(null)}
                                    style={{
                                        background: hoveredLayer === layer.id ? `linear-gradient(135deg, ${layer.color}08, ${layer.color}04)` : '#0d0d14',
                                        border: `1px solid ${hoveredLayer === layer.id ? layer.color + '40' : '#1a1a24'}`,
                                        borderRadius: 12, padding: '16px 20px', transition: 'all 0.3s',
                                    }}
                                >
                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                            <div style={{ width: 3, height: 16, background: layer.color, borderRadius: 2 }} />
                                            <span style={{ fontSize: 10, letterSpacing: 3, color: layer.color, fontWeight: 700, opacity: 0.8 }}>{layer.label}</span>
                                        </div>
                                        <div style={{ fontSize: 9, color: '#444', letterSpacing: 1, fontWeight: 600 }}>
                                            {progressPct}% BUILT | {builtCount}/{totalCount}
                                        </div>
                                    </div>

                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8 }}>
                                        {layer.nodes.map((node) => {
                                            const cfg = STATUS_CONFIG[node.status];
                                            const isSelected = selected === node.id;
                                            const visible = filteredVisible(node);
                                            const isFlowHighlight = hoveredFlow && (hoveredFlow.from === node.id || hoveredFlow.to === node.id);

                                            return (
                                                <button
                                                    key={node.id}
                                                    onClick={() => handleSelect(node.id)}
                                                    style={{
                                                        padding: '14px 16px', borderRadius: 8,
                                                        border: `1px solid ${isSelected || isFlowHighlight ? cfg.border : cfg.border + '55'}`,
                                                        background: isSelected || isFlowHighlight ? cfg.bg : cfg.bg + '88',
                                                        cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', transition: 'all 0.25s',
                                                        opacity: visible ? 1 : 0.15, boxShadow: isSelected || isFlowHighlight ? cfg.glow : 'none',
                                                        transform: isSelected || isFlowHighlight ? 'scale(1.02)' : 'scale(1)',
                                                        position: 'relative', overflow: 'hidden',
                                                    }}
                                                >
                                                    <div
                                                        style={{
                                                            position: 'absolute', top: 8, right: 10, width: 6, height: 6, borderRadius: '50%',
                                                            background: cfg.border, opacity: 0.7,
                                                            animation: node.status === 'partial' ? 'pulseDot 2s ease-in-out infinite' : 'none',
                                                        }}
                                                    />
                                                    <div style={{ fontSize: 13, fontWeight: 600, color: '#e8e8e8', marginBottom: 4 }}>{node.label}</div>
                                                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                                        <div style={{ fontSize: 9, color: cfg.border, letterSpacing: 1.5, textTransform: 'uppercase', fontWeight: 600 }}>{cfg.label}</div>
                                                        {node.repoPath && (
                                                            <div style={{ fontSize: 8, color: '#333' }}>[SRC]</div>
                                                        )}
                                                    </div>
                                                </button>
                                            );
                                        })}
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    {showFlows && (
                        <div style={{ marginTop: 20, padding: '16px 20px', background: '#0d0d14', border: '1px solid #1a1a24', borderRadius: 12 }}>
                            <div style={{ fontSize: 10, letterSpacing: 3, color: '#555', fontWeight: 700, marginBottom: 12 }}>KEY DATA FLOWS</div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 6 }}>
                                {FLOWS.map((flow, i) => (
                                    <div
                                        key={i}
                                        onMouseEnter={() => setHoveredFlow(flow)}
                                        onMouseLeave={() => setHoveredFlow(null)}
                                        style={{
                                            display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: '#777',
                                            padding: '6px 10px', borderRadius: 4, transition: 'all 0.2s',
                                            background: hoveredFlow === flow ? '#ffffff05' : 'transparent',
                                        }}
                                    >
                                        <span style={{ color: hoveredFlow === flow ? '#0ff' : '#0ff8', fontWeight: 600, minWidth: 90, textAlign: 'right', fontSize: 10 }}>{flow.from}</span>
                                        <span style={{ color: '#333' }}>→</span>
                                        <span style={{ color: hoveredFlow === flow ? '#4fa' : '#4fa8', fontWeight: 600, minWidth: 90, fontSize: 10 }}>{flow.to}</span>
                                        <span style={{ color: '#444', fontSize: 10 }}>{flow.label}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {selectedNode && (
                        <div style={{ marginTop: 20, padding: '24px', background: STATUS_CONFIG[selectedNode.status].bg, border: `1px solid ${STATUS_CONFIG[selectedNode.status].border}55`, borderRadius: 12, boxShadow: STATUS_CONFIG[selectedNode.status].glow }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                                <div>
                                    <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: '#fff' }}>{selectedNode.label}</h2>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4 }}>
                                        <span style={{ fontSize: 10, letterSpacing: 2, color: STATUS_CONFIG[selectedNode.status].border, fontWeight: 600 }}>{STATUS_CONFIG[selectedNode.status].label}</span>
                                        <span style={{ fontSize: 9, color: '#444' }}>· updated {selectedNode.lastUpdated}</span>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: 8 }}>
                                    {selectedNode.repoPath && (
                                        <div
                                            title={selectedNode.repoPath}
                                            style={{
                                                fontSize: 10, color: '#4fa', border: '1px solid #4fa55',
                                                padding: '4px 10px', borderRadius: 6, background: '#12342a',
                                                fontFamily: 'inherit', display: 'flex', alignItems: 'center', gap: 6
                                            }}
                                        >
                                            <span style={{ opacity: 0.5 }}>📂</span>
                                            {selectedNode.repoPath}
                                        </div>
                                    )}
                                    <button
                                        className="arch-close-btn"
                                        onClick={() => handleSelect(selectedNode.id)}
                                        style={{ background: 'none', border: '1px solid #333', color: '#666', cursor: 'pointer', borderRadius: 6, padding: '4px 10px', fontSize: 12 }}
                                    >✕</button>
                                </div>
                            </div>
                            <p style={{ margin: '0 0 16px 0', fontSize: 13, lineHeight: 1.7, color: '#bbb' }}>{selectedNode.detail}</p>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
                                <div>
                                    <div style={{ fontSize: 10, color: '#555', letterSpacing: 1.5, marginBottom: 8, fontWeight: 600 }}>CONNECTED FLOWS</div>
                                    {FLOWS.filter((f) => f.from === selectedNode.id || f.to === selectedNode.id).map((f, i) => (
                                        <div key={i} onMouseEnter={() => setHoveredFlow(f)} onMouseLeave={() => setHoveredFlow(null)} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '4px 10px', margin: '0 0 6px 0', background: '#ffffff08', borderRadius: 4, fontSize: 10, color: '#888' }}>
                                            <span style={{ color: '#0ff', minWidth: 60, textAlign: 'right' }}>{f.from}</span>
                                            <span style={{ color: '#333' }}>→</span>
                                            <span style={{ color: '#4fa', minWidth: 60 }}>{f.to}</span>
                                            <span style={{ color: '#444', fontSize: 8, marginLeft: 'auto' }}>{f.label}</span>
                                        </div>
                                    ))}
                                    {FLOWS.filter((f) => f.from === selectedNode.id || f.to === selectedNode.id).length === 0 && (
                                        <span style={{ fontSize: 11, color: '#444' }}>No mapped data flows</span>
                                    )}
                                </div>
                                <div style={{ borderLeft: '1px solid #ffffff08', paddingLeft: 24 }}>
                                    <div style={{ fontSize: 10, color: '#555', letterSpacing: 1.5, marginBottom: 8, fontWeight: 600 }}>ENGINEERING METADATA</div>
                                    <div style={{ fontSize: 10, color: '#666', display: 'flex', flexDirection: 'column', gap: 8 }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span>Component ID:</span>
                                            <span style={{ color: '#888' }}>{selectedNode.id}</span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span>Integration:</span>
                                            <span style={{ color: '#888' }}>{selected === 'postgres' ? 'SQL/RLS' : selected === 'neo4j' ? 'Cypher' : 'REST/gRPC'}</span>
                                        </div>
                                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                            <span>Observability:</span>
                                            <span style={{ color: '#22c55e' }}>Healthy</span>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}

                    <div style={{ marginTop: 20, display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 8 }}>
                        {[
                            { label: 'Total Components', value: LAYERS.flatMap((l) => l.nodes).length, color: '#fff' },
                            { label: 'Built', value: counts.exists || 0, color: STATUS_CONFIG.exists.border },
                            { label: 'In Progress', value: counts.partial || 0, color: STATUS_CONFIG.partial.border },
                            { label: 'Needed', value: counts.missing || 0, color: STATUS_CONFIG.missing.border },
                            { label: 'Future', value: counts.future || 0, color: STATUS_CONFIG.future.border },
                        ].map((stat) => (
                            <div key={stat.label} style={{ padding: '16px', background: '#0d0d14', border: '1px solid #1a1a24', borderRadius: 8, textAlign: 'center' }}>
                                <div style={{ fontSize: 28, fontWeight: 800, color: stat.color }}>{stat.value}</div>
                                <div style={{ fontSize: 9, color: '#555', marginTop: 4 }}>{stat.label.toUpperCase()}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </>
    );
}

export default function RegEngineArchitecture() {
    return (
        <Suspense>
            <RegEngineArchitectureContent />
        </Suspense>
    );
}
