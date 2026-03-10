import type { Metadata } from 'next';

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

const T = {
    bg: "var(--re-surface-base)",
    surface: "rgba(255,255,255,0.02)",
    elevated: "rgba(255,255,255,0.04)",
    border: "rgba(255,255,255,0.06)",
    accent: "var(--re-brand)",
    accentBg: "rgba(16,185,129,0.08)",
    accentBorder: "rgba(16,185,129,0.2)",
    textPrimary: "var(--re-text-primary)",
    textBody: "var(--re-text-secondary)",
    textMuted: "var(--re-text-muted)",
    textDim: "var(--re-text-disabled)",
    mono: "'JetBrains Mono', monospace",
};

function ShieldIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2L4 6V12C4 16.4 7.4 20.5 12 22C16.6 20.5 20 16.4 20 12V6L12 2Z" />
            <path d="M8.5 12L11 14.5L16 9" strokeWidth="2" />
        </svg>
    );
}
function LockIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7C7 4.24 9.24 2 12 2C14.76 2 17 4.24 17 7V11" />
        </svg>
    );
}
function HashIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 9H20M4 15H20M10 3L8 21M16 3L14 21" />
        </svg>
    );
}
function EyeIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M1 12S5 4 12 4 23 12 23 12 19 20 12 20 1 12 1 12Z" />
            <circle cx="12" cy="12" r="3" />
        </svg>
    );
}

const securityFeatures = [
    {
        icon: <LockIcon />,
        title: "Row-Level Security (RLS)",
        description: "Every database query is scoped to the authenticated tenant. Cross-tenant data access is structurally impossible \u2014 enforced at the PostgreSQL policy level, not the application layer.",
        evidence: "Tested: Tenant A cannot query Tenant B data (0 rows returned). Public access correctly blocked.",
        regulation: "Multi-tenant isolation",
    },
    {
        icon: <HashIcon />,
        title: "Cryptographic Fact Hashing",
        description: "Every extracted regulatory fact is hashed with SHA-256 using a deterministic composition: key|type|value|conditions|provenance. Any mutation produces a completely different hash.",
        evidence: "Verified: Re-running ingestion produces identical hashes. Independent verification script (verify_chain.py) confirms integrity.",
        regulation: "Tamper detection",
    },
    {
        icon: <ShieldIcon />,
        title: "Immutable Audit Trail",
        description: "Database triggers block all updates and deletes on compliance tables (extracted facts, rule evaluations, audit events). Corrections must create new versioned records with lineage links.",
        evidence: "Enforced via prevent_mutation trigger (V20). Append-only audit_logs enforced via prevent_audit_modification (V30). Version chain verified from V1 through V16.",
        regulation: "21 CFR Part 11 alignment",
    },
    {
        icon: <EyeIcon />,
        title: "Independent Verification",
        description: "Our open-source verify_chain.py script lets anyone \u2014 auditors, customers, regulators \u2014 independently verify data integrity without database access. Zero trust required.",
        evidence: "Output: 430 record hashes verified, 0 failed across 7 Critical Tracking Events (Dairy, Imported Seafood, Produce recall chains).",
        regulation: "Third-party auditability",
    },
];

const securityControls = [
    { item: "Data encryption at rest (AES-256)", timeline: "Current" },
    { item: "TLS 1.3 in transit", timeline: "Current" },
    { item: "Branch protection (required reviews, no force-push)", timeline: "Current" },
    { item: "CI security scanning (SAST, secrets, deps, DAST)", timeline: "Current" },
    { item: "Vulnerability Disclosure Policy + security.txt", timeline: "Current" },
    { item: "Audit log export (tamper-evident)", timeline: "Current" },
    { item: "Hardening gates: auth + tenant isolation in CI", timeline: "Current" },
    { item: "Incident response plan (internal)", timeline: "Current" },
];

const infrastructure = [
    { label: "Database", value: "PostgreSQL (Supabase)", detail: "Row-Level Security enforced" },
    { label: "Hosting", value: "Cloud infrastructure", detail: "US data residency" },
    { label: "Encryption at rest", value: "AES-256", detail: "All stored data" },
    { label: "Encryption in transit", value: "TLS 1.3", detail: "All API traffic" },
    { label: "Authentication", value: "JWT + API keys", detail: "Per-tenant scoping" },
    { label: "Hashing", value: "SHA-256", detail: "Deterministic, auditable" },
];

export default function SecurityPage() {
    return (
        <div className="re-page">
            {/* Hero */}
            <section className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-[60px]">
                <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                    Security
                </span>
                <h1 style={{ fontSize: "36px", fontWeight: 700, color: T.textPrimary, margin: "16px 0 20px", lineHeight: 1.15 }}>
                    Don&apos;t trust us.<br />
                    <span className="text-re-brand">Verify us.</span>
                </h1>
                <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: 0 }}>
                    Security in compliance software shouldn&apos;t be a marketing claim &mdash; it should be independently auditable.
                    Here&apos;s exactly what we&apos;ve built and verified in production today.
                </p>
            </section>

            {/* Verified Security */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "0 24px 60px" }}>
                <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 24px" }}>
                    What&apos;s verified today
                </h2>
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {securityFeatures.map((feature, i) => (
                        <div
                            key={i}
                            style={{ padding: "24px", background: T.surface, border: `1px solid ${T.accentBorder}`, borderRadius: "12px" }}
                        >
                            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "12px" }}>
                                <span className="text-re-brand">{feature.icon}</span>
                                <h3 style={{ fontSize: "16px", fontWeight: 600, color: T.textPrimary, margin: 0, flex: 1 }}>
                                    {feature.title}
                                </h3>
                                <span
                                    style={{
                                        fontSize: "10px", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase",
                                        padding: "3px 10px", borderRadius: "10px",
                                        color: T.accent, background: T.accentBg,
                                    }}
                                >
                                    ✓ Verified
                                </span>
                            </div>
                            <p style={{ fontSize: "14px", color: T.textMuted, lineHeight: 1.6, margin: "0 0 12px" }}>
                                {feature.description}
                            </p>
                            <div
                                style={{
                                    padding: "10px 14px", background: "rgba(0,0,0,0.2)", borderRadius: "6px",
                                    fontSize: "12px", fontFamily: T.mono, color: T.textDim, lineHeight: 1.5,
                                }}
                            >
                                <span className="text-re-brand">Evidence:</span> {feature.evidence}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* Infrastructure */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}`, background: "rgba(255,255,255,0.01)" }}>
                <div className="max-w-[720px] mx-auto py-[60px] px-6">
                    <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 24px" }}>
                        Infrastructure
                    </h2>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                        {infrastructure.map((item, i) => (
                            <div key={i} style={{ padding: "16px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: "8px" }}>
                                <div style={{ fontSize: "11px", color: T.textDim, fontFamily: T.mono, marginBottom: "4px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                                    {item.label}
                                </div>
                                <div style={{ fontSize: "15px", fontWeight: 600, color: T.textPrimary, marginBottom: "2px" }}>
                                    {item.value}
                                </div>
                                <div style={{ fontSize: "12px", color: T.textMuted }}>{item.detail}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Security Controls */}
            <section className="relative z-[2] max-w-[720px] mx-auto py-[60px] px-6 pb-20">
                <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 8px" }}>
                    Security controls in production
                </h2>
                <p style={{ fontSize: "14px", color: T.textMuted, margin: "0 0 24px" }}>
                    Controls below are implemented and running in the current platform.
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {securityControls.map((item, i) => (
                        <div
                            key={i}
                            style={{
                                display: "flex", alignItems: "center", gap: "12px",
                                padding: "12px 16px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: "8px",
                            }}
                        >
                            <span style={{ fontSize: "14px", fontWeight: 500, color: T.textBody, flex: 1 }}>{item.item}</span>
                            <span style={{ fontSize: "12px", fontFamily: T.mono, color: T.textDim }}>{item.timeline}</span>
                            <span
                                style={{
                                    fontSize: "10px", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase",
                                    padding: "3px 10px", borderRadius: "10px", minWidth: "90px", textAlign: "center",
                                    color: T.accent, background: T.accentBg, border: `1px solid ${T.accentBorder}`,
                                }}
                            >
                                ✓ Implemented
                            </span>
                        </div>
                    ))}
                </div>
            </section>

            {/* CTA */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}`, background: T.accentBg }}>
                <div style={{ maxWidth: "720px", margin: "0 auto", padding: "48px 24px", textAlign: "center" }}>
                    <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 8px" }}>
                        Found a vulnerability?
                    </h2>
                    <p style={{ fontSize: "14px", color: T.textMuted, margin: "0 0 20px" }}>
                        Responsible disclosure: security@regengine.co
                    </p>
                    <a
                        href="mailto:security@regengine.co"
                        style={{
                            display: "inline-flex", padding: "12px 24px", background: T.accent, color: T.bg,
                            borderRadius: "8px", fontSize: "14px", fontWeight: 600, textDecoration: "none",
                        }}
                    >
                        Report a Security Issue
                    </a>
                </div>
            </section>
        </div>
    );
}
