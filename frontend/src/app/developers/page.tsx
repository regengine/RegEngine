import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowRight, Webhook, Cog, Users, FileSpreadsheet,
    BarChart3, GitBranch, Terminal, BookOpen, LogIn,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
    title: 'Developers | RegEngine — FSMA 204 Compliance API',
    description:
        'Build on the RegEngine API: webhook ingestion with KDE validation, 25+ FSMA 204 rules, identity resolution, FDA export, compliance scoring, and request workflow management.',
    openGraph: {
        title: 'Developers | RegEngine — FSMA 204 Compliance API',
        description:
            'Build on the RegEngine API: webhook ingestion, rules engine, identity resolution, FDA export, compliance scoring, and request workflow.',
        url: 'https://www.regengine.co/developers',
        type: 'website',
    },
};

/* ── API Capabilities ── */
const capabilities = [
    {
        Icon: Webhook,
        title: 'Webhook Ingestion',
        description: 'POST events with KDE validation. Every inbound CTE is validated against FSMA 204 Key Data Elements before chain-hashing.',
    },
    {
        Icon: Cog,
        title: 'Rules Engine',
        description: '25+ FSMA 204 validation rules run automatically on every event. Catch missing fields, invalid TLCs, and schema violations in real time.',
    },
    {
        Icon: Users,
        title: 'Identity Resolution',
        description: 'Fuzzy matching across trading partners with confidence scoring. Deduplicate facilities, carriers, and contacts automatically.',
    },
    {
        Icon: FileSpreadsheet,
        title: 'FDA Export',
        description: '21 CFR 1.1455 sortable spreadsheet and EPCIS 2.0 event export. One API call to generate an FDA-ready compliance package.',
    },
    {
        Icon: BarChart3,
        title: 'Compliance Scoring',
        description: '6-dimension score with letter grade. Coverage, completeness, timeliness, accuracy, chain integrity, and identity resolution.',
    },
    {
        Icon: GitBranch,
        title: 'Request Workflow',
        description: '10-state machine for FDA response management. Track requests from intake through investigation, response, and closure.',
    },
];

/* ── SDKs (planned, not yet released) ── */

/* ── Quick-start curl snippet ── */
const curlSnippet = `curl -X POST https://api.regengine.co/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: rge_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "event_type": "receiving",
    "tlc": "urn:epc:id:sgln:0614141.00001.0",
    "event_time": "2026-03-26T14:30:00Z",
    "kde": {
      "product": "Atlantic Salmon Fillet",
      "lot": "LOT-2026-0326",
      "quantity": 500,
      "unit": "KG"
    }
  }'`;

export default function DevelopersPage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* ═══ HERO ═══ */}
            <section className="relative z-[2] max-w-[800px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-12 sm:pb-16 text-center">
                <Badge className="mb-5 bg-[var(--re-brand-muted)] text-[var(--re-brand)] border-[var(--re-brand)]/20">
                    <Terminal className="w-3.5 h-3.5 mr-1.5" />
                    Developer Platform
                </Badge>
                <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold text-re-text-primary leading-tight mb-5">
                    Build on{' '}
                    <span className="text-re-brand">RegEngine</span>
                </h1>
                <p className="text-lg text-re-text-muted max-w-xl mx-auto leading-relaxed mb-8">
                    The FSMA 204 compliance API. Record critical tracking events,
                    validate against 25+ rules, resolve identities, and export
                    FDA-ready packages &mdash; all through a single REST interface.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                    <Link href="/alpha">
                        <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                            Get API Access
                            <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="/docs">
                        <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                            <BookOpen className="mr-2 w-4 h-4" />
                            Full Documentation
                        </Button>
                    </Link>
                </div>
            </section>

            {/* ═══ QUICK START CURL ═══ */}
            <section className="relative z-[2] max-w-[900px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
                <h2 className="text-2xl font-bold text-re-text-primary mb-3 text-center">Quick start</h2>
                <p className="text-sm text-re-text-muted text-center mb-8 max-w-lg mx-auto">
                    Record your first critical tracking event in one request.
                </p>
                <div
                    className="rounded-2xl border border-[var(--re-surface-border)] overflow-hidden"
                    style={{ boxShadow: '0 4px 24px rgba(0,0,0,0.10)' }}
                >
                    <div className="flex items-center gap-2 px-4 py-2.5 bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)]">
                        <Terminal className="w-3.5 h-3.5 text-[var(--re-brand)]" />
                        <span className="text-xs font-mono font-semibold text-re-text-muted">bash</span>
                    </div>
                    <pre className="bg-[var(--re-surface-card)] p-5 overflow-x-auto text-[13px] leading-relaxed font-mono text-re-text-secondary">
                        <code>{curlSnippet}</code>
                    </pre>
                </div>
            </section>

            {/* ═══ API CAPABILITIES GRID ═══ */}
            <section className="relative z-[2] max-w-[900px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
                <h2 className="text-2xl font-bold text-re-text-primary mb-3 text-center">API capabilities</h2>
                <p className="text-sm text-re-text-muted text-center mb-10 max-w-lg mx-auto">
                    Six core services, one unified API. Everything you need for end-to-end FSMA 204 compliance.
                </p>
                <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
                    {capabilities.map((cap) => (
                        <article
                            key={cap.title}
                            className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 flex flex-col"
                            style={{
                                borderTop: '3px solid var(--re-brand)',
                                boxShadow: '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
                            }}
                        >
                            <div className="flex items-center gap-3 mb-4">
                                <div className="p-2 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20">
                                    <cap.Icon className="w-5 h-5 text-[var(--re-brand)]" />
                                </div>
                                <h3 className="text-base font-semibold text-re-text-primary">{cap.title}</h3>
                            </div>
                            <p className="text-sm text-re-text-muted leading-relaxed">{cap.description}</p>
                        </article>
                    ))}
                </div>
            </section>

            {/* ═══ SDKs Coming Soon ═══ */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[900px] mx-auto py-16 px-6 text-center">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3">SDKs Coming Soon</h2>
                    <p className="text-sm text-re-text-muted mb-6 max-w-md mx-auto">
                        Official client libraries for Python, Node.js, and Go are planned.
                        In the meantime, use our REST API directly &mdash; all endpoints accept and return JSON.
                    </p>
                    <Link href="/docs/sdks">
                        <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                            Get Notified When SDKs Launch
                        </Button>
                    </Link>
                </div>
            </section>

            {/* ═══ RATE LIMITS ═══ */}
            <section className="relative z-[2] max-w-[900px] mx-auto py-16 px-6">
                <h2 className="text-2xl font-bold text-re-text-primary mb-3 text-center">Rate limits</h2>
                <p className="text-sm text-re-text-muted text-center mb-6 max-w-lg mx-auto">
                    All API requests are rate limited per API key.
                    If you hit a limit, the API returns a <code className="text-re-text-secondary">429</code> with a <code className="text-re-text-secondary">Retry-After</code> header.
                </p>
                <p className="text-sm text-re-text-muted text-center max-w-lg mx-auto">
                    Need higher throughput?{' '}
                    <Link href="/alpha" className="text-[var(--re-brand)] underline">Contact us</Link> to discuss your requirements.
                </p>
            </section>

            {/* ═══ CTA ═══ */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[700px] mx-auto py-16 px-6 text-center">
                    <Badge className="mb-4 bg-[var(--re-brand)]/10 text-[var(--re-brand)] border-[var(--re-brand)]/20">
                        Ready to integrate?
                    </Badge>
                    <h2 className="text-xl font-bold text-re-text-primary mb-2">Start building on RegEngine</h2>
                    <p className="text-sm text-re-text-muted max-w-md mx-auto mb-6">
                        Get your API key and record your first critical tracking event in under 5 minutes.
                        Full REST API with EPCIS 2.0 support.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/alpha">
                            <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                                Get API Access
                                <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/login?next=/developer/portal">
                            <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                                <LogIn className="mr-2 w-4 h-4" />
                                Developer Portal
                            </Button>
                        </Link>
                    </div>
                    <p className="text-xs text-re-text-disabled mt-6">
                        Already have an account?{' '}
                        <Link href="/login?next=/developer/portal" className="text-[var(--re-brand)] underline">
                            Sign in to the portal
                        </Link>
                        {' '}&middot;{' '}
                        <Link href="/docs" className="text-[var(--re-brand)] underline">
                            Read the docs
                        </Link>
                    </p>
                </div>
            </section>
        </div>
    );
}
