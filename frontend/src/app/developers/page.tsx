import Link from 'next/link';
import {
    Terminal, ArrowRight, Shield, BookOpen, ChevronRight,
    Layers, Lock, Activity, Package, Webhook, FileJson,
    Clock, Globe, Hash, AlertTriangle, ExternalLink,
    Download, Database, ArrowUpRight,
} from 'lucide-react';
import { T, QUICKSTART, PLATFORM_STATS, ENDPOINT_GROUPS, SDK_ITEMS, ERROR_EXAMPLES, WEBHOOK_EVENTS } from './_data';
import { StickyNav } from './_components/sticky-nav';
import { CodeExamples } from './_components/code-examples';
import { CopyButton } from './_components/copy-button';
import { DevProviders } from './_components/dev-providers';
import './developers.css';

/* Icon lookup for data-driven rendering */
const ICONS: Record<string, React.ComponentType<{ style?: React.CSSProperties }>> = {
    Activity, Clock, Globe, Hash, Layers, Shield, Package,
};

export default function DevelopersPage() {
    return (
        <DevProviders>
        <div className="re-page re-grid-bg" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>

            {/* ═══ HERO (server-rendered for SEO) ═══ */}
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
                        <span style={{ fontSize: 36, fontWeight: 700, color: T.accent, fontFamily: T.mono }}>5</span>
                        <span style={{ fontSize: 14, color: T.textMuted }}>min to first CTE</span>
                    </div>
                    <div style={{ width: 1, height: 28, background: T.border }} />
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: 36, fontWeight: 700, color: T.accent, fontFamily: T.mono }}>1</span>
                        <span style={{ fontSize: 14, color: T.textMuted }}>API call to record</span>
                    </div>
                    <div style={{ width: 1, height: 28, background: T.border }} />
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
                        <span style={{ fontSize: 36, fontWeight: 700, color: T.accent, fontFamily: T.mono }}>24h</span>
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
                    {PLATFORM_STATS.map((s) => {
                        const Icon = ICONS[s.iconName];
                        return (
                            <div key={s.label} style={{ background: T.surface, padding: '16px 12px', textAlign: 'center' }}>
                                {Icon && <Icon style={{ width: 14, height: 14, color: T.accent, margin: '0 auto 6px', display: 'block' }} />}
                                <div style={{ fontSize: 18, fontWeight: 700, color: T.heading, fontFamily: T.mono }}>{s.value}</div>
                                <div style={{ fontSize: 11, color: T.textMuted, marginTop: 2 }}>{s.label}</div>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* ═══ STICKY NAV (client island) ═══ */}
            <StickyNav />

            {/* ═══ QUICKSTART (server-rendered) ═══ */}
            <section id="quickstart" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '48px 24px 48px', scrollMarginTop: 60 }}>
                <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Get Started</h2>
                <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, marginBottom: 28 }}>Three steps to your first compliance event</p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                    {QUICKSTART.map((s, idx) => (
                        <div key={s.step} className="re-dev-card" style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: '24px 20px' }}>
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

            {/* ═══ CODE EXAMPLES (client island) ═══ */}
            <CodeExamples />

            {/* ═══ API ENDPOINTS (server-rendered for SEO) ═══ */}
            <section id="endpoints" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '64px 24px', scrollMarginTop: 60 }}>
                <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Reference</h2>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8, marginBottom: 8 }}>
                    <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, margin: 0 }}>API Endpoints</p>
                    <a href="/docs/api" style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: T.accent, textDecoration: 'none', fontWeight: 600 }}>
                        Full docs <ExternalLink style={{ width: 11, height: 11 }} />
                    </a>
                </div>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 32 }}>
                    All endpoints require <code style={{ fontFamily: T.mono, fontSize: 12, color: T.accent, background: T.accentBg, padding: '2px 8px', borderRadius: 4 }}>X-RegEngine-API-Key</code>. Latency shown is p50 production.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
                    {ENDPOINT_GROUPS.map((g) => {
                        const Icon = ICONS[g.iconName];
                        return (
                            <div key={g.category}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                                    {Icon && <Icon style={{ width: 15, height: 15, color: T.accent }} />}
                                    <h3 style={{ fontSize: 13, fontWeight: 700, color: T.heading, margin: 0, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{g.category}</h3>
                                    <span style={{ fontSize: 11, color: T.textMuted }}>{g.endpoints.length} endpoints</span>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                                    {g.endpoints.map((ep, i) => (
                                        <div key={i} className="re-endpoint-row" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8 }}>
                                            <span style={{ fontSize: 11, fontWeight: 700, fontFamily: T.mono, padding: '3px 8px', borderRadius: 4, minWidth: 46, textAlign: 'center' as const, background: ep.method === 'POST' ? T.accentBg : T.blueBg, color: ep.method === 'POST' ? T.accent : T.blue }}>{ep.method}</span>
                                            <code style={{ fontSize: 13, fontFamily: T.mono, color: T.heading, flex: 1 }}>{ep.path}</code>
                                            <span className="re-endpoint-desc" style={{ fontSize: 12, color: T.textMuted }}>{ep.desc}</span>
                                            <span className="re-endpoint-latency" style={{ fontSize: 11, fontFamily: T.mono, color: 'rgba(255,255,255,0.2)', minWidth: 56, textAlign: 'right' as const }}>{ep.latency}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* ═══ AUTHENTICATION (server-rendered) ═══ */}
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
                                    { code: '200', label: 'OK', desc: 'Sync response', color: '#10b981' },
                                    { code: '202', label: 'Accepted', desc: 'Async job queued', color: '#10b981' },
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

            {/* ═══ ERROR HANDLING (server-rendered) ═══ */}
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
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: `1px solid ${T.border}` }}>
                                <code style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: err.code >= 500 ? T.red : err.code >= 400 ? T.amber : T.accent }}>{err.code}</code>
                                <span style={{ fontSize: 13, fontWeight: 600, color: T.heading }}>{err.title}</span>
                            </div>
                            <pre style={{ background: 'rgba(0,0,0,0.3)', padding: '12px 16px', overflow: 'auto', fontSize: 12, lineHeight: 1.6, fontFamily: T.mono, color: T.textMuted, margin: 0 }}>
                                <code>{err.body}</code>
                            </pre>
                        </div>
                    ))}
                </div>
            </section>

            {/* ═══ WEBHOOKS (server-rendered) ═══ */}
            <section id="webhooks" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                        <Webhook style={{ width: 20, height: 20, color: T.accent }} />
                        <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Webhook Events</h2>
                    </div>
                    <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 24, maxWidth: 540 }}>
                        Subscribe to real-time events. All payloads include an HMAC-SHA256 signature for verification.
                    </p>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {WEBHOOK_EVENTS.map((w) => (
                            <div key={w.event} className="re-endpoint-row" style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8 }}>
                                <code style={{ fontSize: 12, fontFamily: T.mono, color: T.accent, fontWeight: 600, minWidth: 200 }}>{w.event}</code>
                                <span className="re-endpoint-desc" style={{ fontSize: 12, color: T.textMuted, flex: 1 }}>{w.desc}</span>
                                <span className="re-endpoint-latency" style={{ fontSize: 11, fontFamily: T.mono, color: 'rgba(255,255,255,0.2)' }}>{w.payload}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ═══ SDKs (server-rendered) ═══ */}
            <section id="sdks" style={{ position: 'relative', zIndex: 2, maxWidth: 880, margin: '0 auto', padding: '64px 24px', scrollMarginTop: 60 }}>
                <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Libraries</h2>
                <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, marginBottom: 28 }}>Official SDKs</p>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
                    {SDK_ITEMS.map((sdk) => (
                        <div key={sdk.lang} className="re-dev-card" style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px', display: 'flex', flexDirection: 'column', gap: 8 }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <span style={{ fontSize: 22 }}>{sdk.icon}</span>
                                <span style={{
                                    fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
                                    padding: '3px 10px', borderRadius: 20,
                                    background: sdk.status === 'beta' ? T.accentBg : 'rgba(255,255,255,0.04)',
                                    color: sdk.status === 'beta' ? T.accent : T.textMuted,
                                    border: `1px solid ${sdk.status === 'beta' ? T.accentBorder : T.border}`,
                                }}>{sdk.status}</span>
                            </div>
                            <h3 style={{ fontSize: 15, fontWeight: 600, color: T.heading, margin: 0 }}>{sdk.lang}</h3>
                            <code style={{ fontSize: 11, fontFamily: T.mono, color: T.textMuted }}>{sdk.note}</code>
                        </div>
                    ))}
                </div>
            </section>

            {/* ═══ RESOURCES (server-rendered) ═══ */}
            <section id="resources" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
                <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                    <h2 style={{ fontSize: 13, fontWeight: 700, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>Developer Resources</h2>
                    <p style={{ fontSize: 22, fontWeight: 600, color: T.heading, marginBottom: 28 }}>Everything you need</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
                        {[
                            { title: 'API Reference', desc: 'Full endpoint docs with Swagger UI', href: '/docs/api', Icon: BookOpen },
                            { title: 'FSMA 204 Guide', desc: 'Regulatory background and CTE requirements', href: '/fsma-204-guide', Icon: FileJson },
                            { title: 'Trust Center', desc: 'Security, compliance, and SLA details', href: '/trust', Icon: Shield },
                            { title: 'Changelog', desc: 'API versions, breaking changes, deprecations', href: '/changelog', Icon: Database },
                        ].map((r) => (
                            <Link key={r.title} href={r.href} className="re-dev-card" style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: '20px', textDecoration: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
                                <r.Icon style={{ width: 18, height: 18, color: T.accent }} />
                                <h3 style={{ fontSize: 15, fontWeight: 600, color: T.heading, margin: 0 }}>{r.title}</h3>
                                <p style={{ fontSize: 13, color: T.textMuted, margin: 0, lineHeight: 1.5 }}>{r.desc}</p>
                                <span style={{ fontSize: 12, fontWeight: 600, color: T.accent, display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 'auto' }}>
                                    View <ArrowUpRight style={{ width: 12, height: 12 }} />
                                </span>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>

            {/* ═══ CTA ═══ */}
            <section style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: T.accentBg, padding: '64px 24px', textAlign: 'center' }}>
                <h2 style={{ fontSize: 28, fontWeight: 700, color: T.heading, marginBottom: 12 }}>Ready to integrate?</h2>
                <p style={{ fontSize: 15, color: T.textMuted, marginBottom: 28, maxWidth: 480, margin: '0 auto 28px' }}>
                    Get your API key and record your first CTE in under 5 minutes. Full REST API with EPCIS 2.0 support.
                </p>
                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <Link href="/developer/portal">
                        <button className="re-btn-primary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: T.accent, color: '#000', fontWeight: 600, padding: '13px 30px', borderRadius: 8, border: 'none', cursor: 'pointer', fontSize: 14 }}>
                            Get API Key <ArrowRight style={{ width: 16, height: 16 }} />
                        </button>
                    </Link>
                    <Link href="/contact">
                        <button className="re-btn-secondary" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: 'transparent', color: T.text, fontWeight: 600, padding: '13px 30px', borderRadius: 8, border: `1px solid ${T.border}`, cursor: 'pointer', fontSize: 14 }}>
                            Scope an Integration
                        </button>
                    </Link>
                </div>
            </section>

        </div>
        </DevProviders>
    );
}
