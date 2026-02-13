'use client';

import { useState, useEffect } from "react";

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
    textGhost: "var(--re-text-disabled)",
    sans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
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
        status: "verified",
        description: "Every database query is scoped to the authenticated tenant. Cross-tenant data access is structurally impossible — enforced at the PostgreSQL policy level, not the application layer.",
        evidence: "Tested: Tenant A cannot query Tenant B data (0 rows returned). Public access correctly blocked.",
        regulation: "Multi-tenant isolation",
    },
    {
        icon: <HashIcon />,
        title: "Cryptographic Fact Hashing",
        status: "verified",
        description: "Every extracted regulatory fact is hashed with SHA-256 using a deterministic composition: key|type|value|conditions|provenance. Any mutation produces a completely different hash.",
        evidence: "Verified: Re-running ingestion produces identical hashes. Independent verification script (verify_chain.py) confirms integrity.",
        regulation: "Tamper detection",
    },
    {
        icon: <ShieldIcon />,
        title: "Immutable Audit Trail",
        status: "verified",
        description: "Database triggers block all updates and deletes on compliance tables (extracted facts, rule evaluations, audit events). Corrections must create new versioned records with lineage links (supersedes_document_id, previous_fact_id).",
        evidence: "Enforced via prevent_mutation trigger (V20). Append-only audit_logs enforced via prevent_audit_modification (V30). Version chain verified from V1 through V16.",
        regulation: "21 CFR Part 11 alignment",
    },
    {
        icon: <EyeIcon />,
        title: "Independent Verification",
        status: "verified",
        description: "Our open-source verify_chain.py script lets anyone — auditors, customers, regulators — independently verify data integrity without database access. Zero trust required.",
        evidence: "Output: 430 record hashes verified, 0 failed across 7 Critical Tracking Events (Dairy, Imported Seafood, Produce recall chains).",
        regulation: "Third-party auditability",
    },
];

const roadmapItems = [
    // Shipped (Current)
    { item: "Data encryption at rest (AES-256)", status: "implemented", timeline: "Current" },
    { item: "TLS 1.3 in transit", status: "implemented", timeline: "Current" },
    { item: "Branch protection (required reviews, no force-push)", status: "implemented", timeline: "Current" },
    // Shipped
    { item: "CI security scanning (SAST, secrets, deps, DAST)", status: "implemented", timeline: "Current" },
    { item: "Vulnerability Disclosure Policy + security.txt", status: "implemented", timeline: "Current" },
    { item: "Audit log export (tamper-evident)", status: "implemented", timeline: "Current" },
    { item: "Hardening gates: auth + tenant isolation in CI", status: "implemented", timeline: "Current" },
    { item: "Incident response plan (internal)", status: "implemented", timeline: "Current" },
    // Next (Q2 2026)
    { item: "OWASP ZAP authenticated scans (full flows)", status: "planned", timeline: "Q2 2026" },
    { item: "Penetration testing (third-party)", status: "planned", timeline: "Q2 2026" },
    { item: "SSO / SAML integration", status: "planned", timeline: "Q3 2026" },
    { item: "API rate limiting + edge protection (WAF)", status: "planned", timeline: "Q2 2026" },
    { item: "Container image scanning (Trivy)", status: "planned", timeline: "Q2 2026" },
    // Audit Track
    { item: "SOC 2 Type II", status: "in-preparation", timeline: "2026" },
];

export default function SecurityPage() {
    const [animateIn, setAnimateIn] = useState(false);

    useEffect(() => {
        setAnimateIn(true);
    }, []);

    const statusColors: Record<string, { bg: string; border: string; text: string; label: string }> = {
        verified: { bg: "rgba(16,185,129,0.1)", border: "rgba(16,185,129,0.2)", text: "var(--re-brand)", label: "✓ Verified" },
        implemented: { bg: "rgba(16,185,129,0.1)", border: "rgba(16,185,129,0.2)", text: "var(--re-brand)", label: "✓ Implemented" },
        implementing: { bg: "rgba(250,204,21,0.1)", border: "rgba(250,204,21,0.2)", text: "var(--re-warning)", label: "Implementing" },
        "in-progress": { bg: "rgba(96,165,250,0.1)", border: "rgba(96,165,250,0.2)", text: "var(--re-info)", label: "In Progress" },
        "in-preparation": { bg: "rgba(168,85,247,0.1)", border: "rgba(168,85,247,0.2)", text: "var(--re-accent-purple)", label: "In Preparation" },
        planned: { bg: T.elevated, border: T.border, text: T.textDim, label: "Planned" },
    };

    return (
        <div className="re-page">
            <link
                href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
                rel="stylesheet"
            />

            <div
                style={{
                    position: "fixed", inset: 0, opacity: 0.015, pointerEvents: "none", zIndex: 1,
                    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
                    backgroundSize: "128px 128px",
                }}
            />

            {/* Hero */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "80px 24px 60px" }}>
                <div
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? "translateY(0)" : "translateY(16px)",
                        transition: "all 0.7s cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                >
                    <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                        Security
                    </span>
                    <h1 style={{ fontSize: "36px", fontWeight: 700, color: T.textPrimary, margin: "16px 0 20px", lineHeight: 1.15 }}>
                        Don't trust us.<br />
                        <span className="text-re-brand">Verify us.</span>
                    </h1>
                    <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: 0 }}>
                        Security in compliance software shouldn't be a marketing claim — it should be independently auditable. Here's exactly what we've built, what we've verified, and what's still on the roadmap. No hand-waving.
                    </p>
                </div>
            </section>

            {/* Verified Security */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "0 24px 60px" }}>
                <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 24px" }}>
                    What's verified today
                </h2>

                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                    {securityFeatures.map((feature, i) => (
                        <div
                            key={i}
                            style={{
                                padding: "24px",
                                background: T.surface,
                                border: `1px solid ${T.accentBorder}`,
                                borderRadius: "12px",
                            }}
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
                                        color: statusColors.verified.text,
                                        background: statusColors.verified.bg,
                                    }}
                                >
                                    {statusColors.verified.label}
                                </span>
                            </div>
                            <p style={{ fontSize: "14px", color: T.textMuted, lineHeight: 1.6, margin: "0 0 12px" }}>
                                {feature.description}
                            </p>
                            <div
                                style={{
                                    padding: "10px 14px",
                                    background: "rgba(0,0,0,0.2)",
                                    borderRadius: "6px",
                                    fontSize: "12px",
                                    fontFamily: T.mono,
                                    color: T.textDim,
                                    lineHeight: 1.5,
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
                        {[
                            { label: "Database", value: "PostgreSQL (Supabase)", detail: "Row-Level Security enforced" },
                            { label: "Hosting", value: "Cloud infrastructure", detail: "US data residency" },
                            { label: "Encryption at rest", value: "AES-256", detail: "All stored data" },
                            { label: "Encryption in transit", value: "TLS 1.3", detail: "All API traffic" },
                            { label: "Authentication", value: "JWT + API keys", detail: "Per-tenant scoping" },
                            { label: "Hashing", value: "SHA-256", detail: "Deterministic, auditable" },
                        ].map((item, i) => (
                            <div
                                key={i}
                                style={{
                                    padding: "16px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: "8px",
                                }}
                            >
                                <div style={{ fontSize: "11px", color: T.textDim, fontFamily: T.mono, marginBottom: "4px", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                                    {item.label}
                                </div>
                                <div style={{ fontSize: "15px", fontWeight: 600, color: T.textPrimary, marginBottom: "2px" }}>
                                    {item.value}
                                </div>
                                <div style={{ fontSize: "12px", color: T.textMuted }}>
                                    {item.detail}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Roadmap */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "60px 24px 80px" }}>
                <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 8px" }}>
                    Security roadmap
                </h2>
                <p style={{ fontSize: "14px", color: T.textMuted, margin: "0 0 24px" }}>
                    We're honest about what's done and what's planned. No checkmarks we haven't earned.
                </p>

                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                    {roadmapItems.map((item, i) => {
                        const s = statusColors[item.status];
                        return (
                            <div
                                key={i}
                                style={{
                                    display: "flex", alignItems: "center", gap: "12px",
                                    padding: "12px 16px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: "8px",
                                }}
                            >
                                <span style={{ fontSize: "14px", fontWeight: 500, color: T.textBody, flex: 1 }}>
                                    {item.item}
                                </span>
                                <span style={{ fontSize: "12px", fontFamily: T.mono, color: T.textDim }}>
                                    {item.timeline}
                                </span>
                                <span
                                    style={{
                                        fontSize: "10px", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase",
                                        padding: "3px 10px", borderRadius: "10px",
                                        color: s.text, background: s.bg, border: `1px solid ${s.border}`,
                                        minWidth: "90px", textAlign: "center",
                                    }}
                                >
                                    {s.label}
                                </span>
                            </div>
                        );
                    })}
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

            <style>{`* { box-sizing: border-box; margin: 0; }`}</style>
        </div>
    );
}
