import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight, CheckCircle2, Code2, Database, Eye, FileCode, Globe,
  Hash, KeyRound, Lock, LockKeyhole, Server, Shield, ShieldCheck, Terminal,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
    title: 'Security | RegEngine',
    description: 'Independently verifiable security: Row-Level Security, SHA-256 hashing, immutable audit trails, and open-source verification.',
    openGraph: {
        title: 'Security | RegEngine',
        description: 'Independently verifiable security for FSMA 204 compliance.',
        url: 'https://www.regengine.co/security',
        type: 'website',
    },
};

const securityFeatures = [
    {
        Icon: Lock,
        title: "Row-Level Security (RLS)",
        description: "Every database query is scoped to the authenticated tenant. Cross-tenant data access is structurally impossible — enforced at the PostgreSQL policy level, not the application layer.",
        evidence: "Tested: Tenant A cannot query Tenant B data (0 rows returned). Public access correctly blocked.",
        regulation: "Multi-tenant isolation",
    },
    {
        Icon: Hash,
        title: "Cryptographic Fact Hashing",
        description: "Every extracted regulatory fact is hashed with SHA-256 using a deterministic composition: key|type|value|conditions|provenance. Any mutation produces a completely different hash.",
        evidence: "Verified: Re-running ingestion produces identical hashes. Independent verification script (verify_chain.py) confirms integrity.",
        regulation: "Tamper detection",
    },
    {
        Icon: ShieldCheck,
        title: "Immutable Audit Trail",
        description: "Database triggers block all updates and deletes on compliance tables (extracted facts, rule evaluations, audit events). Corrections must create new versioned records with lineage links.",
        evidence: "Enforced via prevent_mutation trigger (V20). Append-only audit_logs enforced via prevent_audit_modification (V30). Version chain verified from V1 through V16.",
        regulation: "21 CFR Part 11 alignment",
    },
    {
        Icon: Eye,
        title: "Independent Verification",
        description: "Our open-source verify_chain.py script lets anyone — auditors, customers, regulators — independently verify data integrity without database access. Zero trust required.",
        evidence: "Output: 430 record hashes verified, 0 failed across 7 Critical Tracking Events (Dairy, Imported Seafood, Produce recall chains).",
        regulation: "Third-party auditability",
    },
];

const securityControls = [
    { item: "Data encryption at rest (AES-256)", Icon: LockKeyhole },
    { item: "TLS 1.3 in transit — all API and web traffic", Icon: Globe },
    { item: "CSRF protection on all state-changing endpoints", Icon: Shield },
    { item: "Rate limiting on authentication and API endpoints", Icon: ShieldCheck },
    { item: "HTTP-only, Secure session cookies (no JS access)", Icon: LockKeyhole },
    { item: "JWT key rotation with configurable expiry windows", Icon: KeyRound },
    { item: "Branch protection (required reviews, no force-push)", Icon: Code2 },
    { item: "CI security scanning (SAST, secrets, deps, DAST)", Icon: Terminal },
    { item: "Vulnerability Disclosure Policy + security.txt", Icon: FileCode },
    { item: "Audit log export (tamper-evident)", Icon: Shield },
    { item: "Hardening gates: auth + tenant isolation in CI", Icon: KeyRound },
    { item: "Incident response plan (internal)", Icon: ShieldCheck },
];

const diligenceArtifacts = [
    { label: 'Trust Center', detail: 'Public product status, retention posture, and support model', href: '/trust', Icon: ShieldCheck },
    { label: 'Security details', detail: 'Implemented controls and verification-oriented security copy', href: '/security', Icon: Lock },
    { label: 'Additional artifacts', detail: 'Subprocessors, diligence materials, and extra security artifacts are available on request or under NDA', href: '/contact', Icon: FileCode },
];

const infrastructure = [
    { label: "Database", value: "Supabase (PostgreSQL)", detail: "SOC 2 Type II certified · Row-Level Security enforced", Icon: Database },
    { label: "Hosting & CI/CD", value: "Vercel", detail: "SOC 2 Type II certified · US data residency", Icon: Globe },
    { label: "Background services", value: "Railway", detail: "US-based infrastructure", Icon: Server },
    { label: "Encryption at rest", value: "AES-256", detail: "All stored data", Icon: LockKeyhole },
    { label: "Encryption in transit", value: "TLS 1.3", detail: "All API and web traffic", Icon: Globe },
    { label: "Authentication", value: "JWT + API keys", detail: "Per-tenant scoping with rotation", Icon: KeyRound },
    { label: "Hashing", value: "SHA-256", detail: "Deterministic, auditable", Icon: Hash },
];

export default function SecurityPage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Hero */}
            <section className="relative z-[2] max-w-[800px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-12 sm:pb-16 text-center">
                <Badge className="mb-5 bg-[var(--re-brand-muted)] text-[var(--re-brand)] border-[var(--re-brand)]/20">
                    Security
                </Badge>
                <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-bold text-re-text-primary leading-tight mb-5">
                    Don&apos;t trust us.<br />
                    <span className="text-re-brand">Verify us.</span>
                </h1>
                <p className="text-lg text-re-text-muted max-w-xl mx-auto leading-relaxed mb-8">
                    Security in compliance software shouldn&apos;t be a marketing claim &mdash; it should be independently auditable.
                    Here&apos;s exactly what we&apos;ve built and verified in production today.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                    <Link href="/alpha">
                        <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                            Become a Founding Design Partner
                            <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="/trust">
                        <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                            View Trust Center
                        </Button>
                    </Link>
                </div>
            </section>

            {/* Verified Security Pillars */}
            <section className="relative z-[2] max-w-[900px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3 text-center">What&apos;s verified today</h2>
                <p className="text-sm text-re-text-muted text-center mb-10 max-w-lg mx-auto">
                    Four pillars, each with concrete production evidence. No roadmap promises.
                </p>
                <div className="grid md:grid-cols-2 gap-5">
                    {securityFeatures.map((feature) => (
                        <article
                            key={feature.title}
                            className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 flex flex-col"
                            style={{
                                borderTop: '3px solid var(--re-brand)',
                                boxShadow: '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
                            }}
                        >
                            <div className="flex items-center gap-3 mb-4">
                                <div className="p-2 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20">
                                    <feature.Icon className="w-5 h-5 text-[var(--re-brand)]" />
                                </div>
                                <h3 className="font-display text-base font-semibold text-re-text-primary flex-1">{feature.title}</h3>
                                <span className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex-shrink-0">
                                    ✓ Verified
                                </span>
                            </div>
                            <p className="text-sm text-re-text-muted leading-relaxed mb-3">{feature.description}</p>
                            <div className="mt-auto rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] p-3">
                                <p className="text-xs font-mono text-re-text-disabled leading-relaxed">
                                    <span className="text-[var(--re-brand)] font-semibold">Evidence:</span> {feature.evidence}
                                </p>
                            </div>
                            <p className="text-[11px] text-re-text-disabled mt-2 font-mono">{feature.regulation}</p>
                        </article>
                    ))}
                </div>
            </section>

            {/* Verifier Script Callout */}
            <section className="relative z-[2] max-w-[900px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
                <div
                    className="rounded-2xl border-2 border-[var(--re-brand)]/20 p-5 sm:p-8"
                    style={{
                        background: 'var(--re-brand-muted)',
                        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
                    }}
                >
                    <div className="flex flex-col md:flex-row items-start gap-6">
                        <div className="w-14 h-14 rounded-xl bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20 flex items-center justify-center flex-shrink-0">
                            <Terminal className="w-7 h-7 text-[var(--re-brand)]" />
                        </div>
                        <div className="flex-1">
                            <h3 className="font-display text-lg font-bold text-re-text-primary mb-2">Open-source verification script</h3>
                            <p className="text-sm text-re-text-muted leading-relaxed mb-4">
                                <code className="text-[var(--re-brand)] font-mono text-xs bg-[var(--re-surface-elevated)] px-1.5 py-0.5 rounded border border-[var(--re-surface-border)]">verify_chain.py</code> lets anyone — auditors, customers, regulators — independently verify data integrity without database access. Download it, point it at an export package, and confirm every hash in the Merkle chain.
                            </p>
                            <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-4 mb-4 font-mono text-xs text-re-text-disabled overflow-x-auto"
                                style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
                            >
                                <p className="text-[var(--re-brand)]">$ python verify_chain.py --export dairy_recall_2024.json</p>
                                <p className="mt-1">Verifying 430 record hashes...</p>
                                <p className="text-emerald-500">✓ 430 verified, 0 failed</p>
                                <p className="text-emerald-500">✓ Merkle root matches signed manifest</p>
                                <p className="mt-1 text-re-text-disabled">7 CTEs verified: Dairy, Imported Seafood, Produce (3 recall chains)</p>
                            </div>
                            <div className="flex gap-3 flex-wrap">
                                <Link href="/verify">
                                    <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-5 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all text-sm">
                                        See Live Merkle Chain
                                        <ArrowRight className="ml-2 w-4 h-4" />
                                    </Button>
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Infrastructure */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[900px] mx-auto py-16 px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3 text-center">Infrastructure</h2>
                    <p className="text-sm text-re-text-muted text-center mb-10 max-w-lg mx-auto">
                        Enterprise-grade defaults from day one. Our infrastructure providers hold independent SOC 2 Type II certifications.
                    </p>
                    <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
                        {infrastructure.map((item) => (
                            <div
                                key={item.label}
                                className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5"
                                style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
                            >
                                <div className="flex items-center gap-3 mb-3">
                                    <div className="p-1.5 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20">
                                        <item.Icon className="w-4 h-4 text-[var(--re-brand)]" />
                                    </div>
                                    <span className="text-[11px] font-mono uppercase tracking-wider text-re-text-disabled">{item.label}</span>
                                </div>
                                <p className="text-sm font-semibold text-re-text-primary mb-0.5">{item.value}</p>
                                <p className="text-xs text-re-text-muted">{item.detail}</p>
                            </div>
                        ))}
                    </div>
                    <p className="text-[11px] text-re-text-disabled text-center mt-6 max-w-lg mx-auto leading-relaxed">
                        Supabase and Vercel independently hold SOC 2 Type II certifications.
                        RegEngine itself is working toward SOC 2 Type I (target Q3 2026) — see roadmap below.
                        Provider compliance reports are available on request.
                    </p>
                </div>
            </section>

            {/* Security Controls */}
            <section className="relative z-[2] max-w-[900px] mx-auto py-16 px-6">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3 text-center">Security controls in production</h2>
                <p className="text-sm text-re-text-muted text-center mb-10 max-w-lg mx-auto">
                    Controls below are implemented and running in the current platform.
                </p>
                <div className="grid sm:grid-cols-2 gap-3">
                    {securityControls.map((item) => (
                        <div
                            key={item.item}
                            className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 flex items-center gap-3"
                            style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
                        >
                            <div className="p-1.5 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex-shrink-0">
                                <item.Icon className="w-4 h-4 text-[var(--re-brand)]" />
                            </div>
                            <span className="text-sm font-medium text-re-text-secondary flex-1">{item.item}</span>
                            <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex-shrink-0">
                                ✓ Live
                            </span>
                        </div>
                    ))}
                </div>
            </section>

            {/* Compliance Roadmap */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[900px] mx-auto py-16 px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3 text-center">Compliance and certifications</h2>
                    <p className="text-sm text-re-text-muted text-center mb-10 max-w-lg mx-auto">
                        Where we are today and what&apos;s on the roadmap. We won&apos;t claim certifications we don&apos;t have.
                    </p>
                    <div className="grid sm:grid-cols-2 gap-4">
                        <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                            <div className="flex items-center gap-3 mb-3">
                                <span className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Today</span>
                            </div>
                            <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Implemented controls</h3>
                            <ul className="space-y-1.5 text-sm text-re-text-muted">
                                <li>• Row-Level Security (PostgreSQL RLS) — multi-tenant isolation</li>
                                <li>• SHA-256 cryptographic audit trail — tamper detection</li>
                                <li>• Immutable compliance tables — append-only by DB trigger</li>
                                <li>• AES-256 encryption at rest, TLS 1.3 in transit</li>
                                <li>• JWT + scoped API key authentication</li>
                                <li>• Branch protection with required code review</li>
                                <li>• Automated CI security scanning (SAST, secrets, deps)</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                            <div className="flex items-center gap-3 mb-3">
                                <span className="text-[10px] font-semibold uppercase tracking-wider px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-500 border border-amber-500/20">Roadmap</span>
                            </div>
                            <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Planned certifications</h3>
                            <ul className="space-y-1.5 text-sm text-re-text-muted">
                                <li>• SOC 2 Type I — target Q3 2026</li>
                                <li>• SOC 2 Type II — target Q1 2027</li>
                                <li>• Annual penetration testing — starting Q4 2026</li>
                                <li>• GDPR Data Processing Agreement template — Q2 2026</li>
                                <li>• Business Associate Agreement (BAA) availability</li>
                                <li>• Bug bounty program — evaluating launch</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                            <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Access controls</h3>
                            <ul className="space-y-1.5 text-sm text-re-text-muted">
                                <li>• Per-tenant API key scoping with permission levels</li>
                                <li>• Session management: 30-day JWT with explicit logout</li>
                                <li>• Audit logging of all API key usage and auth events</li>
                                <li>• Role-based access: admin, operator, viewer (per tenant)</li>
                                <li>• Automatic key rotation reminders</li>
                                <li>• last_used_at tracking on all API credentials</li>
                            </ul>
                        </div>
                        <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                            <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Data processing</h3>
                            <ul className="space-y-1.5 text-sm text-re-text-muted">
                                <li>• US data residency (all infrastructure US-based)</li>
                                <li>• No cross-tenant data sharing or commingling</li>
                                <li>• 90-day post-cancellation retention, then hard delete</li>
                                <li>• Full data export in EPCIS 2.0, FDA format, or CSV</li>
                                <li>• Subprocessor list available on request</li>
                                <li>• Data Processing Agreement (DPA) available for enterprise</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </section>

            {/* Incident Response */}
            <section className="relative z-[2] max-w-[900px] mx-auto py-16 px-6">
                <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3 text-center">Incident response</h2>
                <p className="text-sm text-re-text-muted text-center mb-10 max-w-lg mx-auto">
                    Transparency during incidents matters more than perfect uptime marketing.
                </p>
                <div className="grid sm:grid-cols-3 gap-4">
                    <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                        <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Detection</h3>
                        <p className="text-sm text-re-text-muted">Automated monitoring on all backend services, database health checks, and deployment verification. Alert escalation within 15 minutes of detection.</p>
                    </div>
                    <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                        <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Communication</h3>
                        <p className="text-sm text-re-text-muted">Affected customers notified within 1 hour of confirmed incidents. Status updates at minimum hourly intervals. Post-incident reports within 72 hours.</p>
                    </div>
                    <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5" style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                        <h3 className="font-display text-sm font-semibold text-re-text-primary mb-2">Recovery</h3>
                        <p className="text-sm text-re-text-muted">Immutable audit trail ensures compliance data survives service interruptions. Database backups with point-in-time recovery. No data loss guarantee on committed records.</p>
                    </div>
                </div>
            </section>

            {/* Diligence Artifacts */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[900px] mx-auto py-16 px-6">
                    <h2 className="font-display text-2xl font-bold text-re-text-primary mb-3 text-center">Diligence artifacts</h2>
                    <p className="text-sm text-re-text-muted text-center mb-10 max-w-xl mx-auto">
                        Security copy is only part of the diligence surface. Product status, retention, support posture, and additional materials are surfaced separately.
                    </p>
                    <div className="grid sm:grid-cols-3 gap-4">
                        {diligenceArtifacts.map((artifact) => (
                            <Link
                                key={artifact.label}
                                href={artifact.href}
                                className="group rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5 no-underline hover:border-[var(--re-brand)]/30 hover:-translate-y-0.5 transition-all"
                                style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
                            >
                                <div className="w-9 h-9 rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] flex items-center justify-center mb-3 group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-300">
                                    <artifact.Icon className="w-4 h-4 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
                                </div>
                                <h3 className="font-display text-sm font-semibold text-re-text-primary mb-1">{artifact.label}</h3>
                                <p className="text-xs text-re-text-muted leading-relaxed">{artifact.detail}</p>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>

            {/* Alpha CTA */}
            <section className="relative z-[2] max-w-[700px] mx-auto px-6 pb-8">
                <div
                    className="rounded-2xl border border-[var(--re-brand)]/20 p-8 text-center"
                    style={{
                        background: 'var(--re-brand-muted)',
                        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
                    }}
                >
                    <Badge className="mb-4 bg-[var(--re-brand)]/10 text-[var(--re-brand)] border-[var(--re-brand)]/20">
                        Founding Design Partner Program
                    </Badge>
                    <h3 className="font-display text-xl font-bold text-re-text-primary mb-2">See the full audit trail live</h3>
                    <p className="text-sm text-re-text-muted max-w-md mx-auto mb-5">
                        Founding Design Partners get full access to the Merkle chain, audit logs, and verification tools inside their dashboard.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/alpha">
                            <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                                Become a Founding Design Partner
                                <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <a href="mailto:security@regengine.co" className="no-underline">
                            <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                                Request Security Packet
                            </Button>
                        </a>
                    </div>
                </div>
            </section>

            {/* Vulnerability Disclosure */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[600px] mx-auto py-12 px-6 text-center">
                    <h2 className="font-display text-xl font-bold text-re-text-primary mb-2">Found a vulnerability?</h2>
                    <p className="text-sm text-re-text-muted mb-6">
                        Responsible disclosure: security@regengine.co
                    </p>
                    <a href="mailto:security@regengine.co" className="no-underline">
                        <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                            Report a Security Issue
                        </Button>
                    </a>
                </div>
            </section>
        </div>
    );
}
