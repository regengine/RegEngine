'use client';

import { useState, useEffect } from "react";

const T = {
    bg: "var(--re-surface-base)",
    surface: "rgba(255,255,255,0.02)",
    border: "rgba(255,255,255,0.06)",
    accent: "var(--re-brand)",
    accentBg: "rgba(16,185,129,0.08)",
    textPrimary: "var(--re-text-primary)",
    textBody: "var(--re-text-secondary)",
    textMuted: "var(--re-text-muted)",
    textDim: "var(--re-text-disabled)",
    textGhost: "var(--re-text-disabled)",
    sans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    mono: "'JetBrains Mono', monospace",
};

const sections = [
    {
        title: "What We Collect",
        content: [
            {
                subtitle: "Account Information",
                text: "When you create an account, we collect your name, email address, company name, and billing information. We need this to provide you with our services and process payments.",
            },
            {
                subtitle: "Compliance Data",
                text: "When you use RegEngine to manage FSMA 204 compliance, we process and store the traceability data you submit — including Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs). This data belongs to you. We store it to provide the service.",
            },
            {
                subtitle: "Usage Data",
                text: "We collect basic analytics: pages visited, features used, API calls made. We use this to improve the product. We do not sell this data to anyone.",
            },
            {
                subtitle: "FTL Checker (Free Tool)",
                text: "The FTL Coverage Checker does not require an account and does not store your selections. If you submit your email for a gap analysis, we store that email solely to send you the analysis.",
            },
        ],
    },
    {
        title: "How We Use Your Data",
        content: [
            { text: "Providing and maintaining RegEngine services" },
            { text: "Processing your compliance data as directed by you" },
            { text: "Generating FDA-ready exports and reports you request" },
            { text: "Sending transactional emails (account, billing, compliance alerts)" },
            { text: "Improving our platform based on aggregate usage patterns" },
            { text: "Responding to your support requests" },
        ],
    },
    {
        title: "What We Don't Do",
        content: [
            { text: "We do not sell your personal data or compliance data to third parties." },
            { text: "We do not use your compliance data to train machine learning models." },
            { text: "We do not share your data with other RegEngine tenants. Row-Level Security enforces tenant isolation at the database level." },
            { text: "We do not serve targeted ads." },
            { text: "We do not share your data with data brokers." },
        ],
    },
    {
        title: "Data Storage & Security",
        content: [
            {
                subtitle: "Where",
                text: "Your data is stored in US-based cloud infrastructure with encryption at rest (AES-256) and in transit (TLS 1.3).",
            },
            {
                subtitle: "Isolation",
                text: "Each tenant's data is isolated via PostgreSQL Row-Level Security policies. This is enforced at the database layer, not the application layer. See our Security page for verification details.",
            },
            {
                subtitle: "Integrity",
                text: "Regulatory facts are cryptographically hashed with SHA-256. You can independently verify data integrity using our open verification tools.",
            },
            {
                subtitle: "Retention",
                text: "We retain your compliance data for the duration of your subscription plus 90 days. After cancellation, you can request a full data export. After the retention period, data is permanently deleted.",
            },
        ],
    },
    {
        title: "Your Rights",
        content: [
            {
                subtitle: "Access & Export",
                text: "You can export all of your compliance data at any time via the API or dashboard. We support FDA-compliant CSV formats.",
            },
            {
                subtitle: "Deletion",
                text: "You can request deletion of your account and all associated data by contacting privacy@regengine.co. We will complete deletion within 30 days.",
            },
            {
                subtitle: "Correction",
                text: "You can update your account information at any time through the dashboard.",
            },
            {
                subtitle: "California Residents (CCPA)",
                text: "California residents have additional rights under the CCPA, including the right to know what personal information we collect and the right to opt out of data sales. We do not sell personal information.",
            },
        ],
    },
    {
        title: "Cookies",
        content: [
            {
                text: "We use essential cookies for authentication and session management. We use basic analytics cookies to understand product usage. We do not use third-party advertising cookies. You can disable non-essential cookies in your browser settings.",
            },
        ],
    },
    {
        title: "Third-Party Services",
        content: [
            {
                text: "We use a limited number of third-party services to operate RegEngine: cloud hosting (data storage and compute), payment processing (Stripe — they have their own privacy policy), and email delivery (transactional emails only). Each service provider is bound by data processing agreements.",
            },
        ],
    },
    {
        title: "Changes to This Policy",
        content: [
            {
                text: "We'll notify you of material changes via email at least 30 days before they take effect. Non-material changes (clarifications, formatting) may be made without notice.",
            },
        ],
    },
    {
        title: "Contact",
        content: [
            {
                text: "Questions about this policy? privacy@regengine.co — you'll hear from the founder directly, not a legal department.",
            },
        ],
    },
];

export default function PrivacyPage() {
    const [animateIn, setAnimateIn] = useState(false);

    useEffect(() => {
        setAnimateIn(true);
    }, []);

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
            <section className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-12">
                <div
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? "translateY(0)" : "translateY(16px)",
                        transition: "all 0.7s cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                >
                    <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                        Legal
                    </span>
                    <h1 style={{ fontSize: "36px", fontWeight: 700, color: T.textPrimary, margin: "16px 0 12px", lineHeight: 1.15 }}>
                        Privacy Policy
                    </h1>
                    <p style={{ fontSize: "14px", color: T.textDim, fontFamily: T.mono }}>
                        Effective: February 5, 2026 · Last updated: February 5, 2026
                    </p>
                    <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: "20px 0 0" }}>
                        Plain language. No legalese walls. Here's what we collect, why, and what we do with it.
                    </p>
                </div>
            </section>

            {/* Sections */}
            <section className="relative z-[2] max-w-[720px] mx-auto px-6 pb-20">
                {sections.map((section, si) => (
                    <div
                        key={si}
                        style={{
                            padding: "32px 0",
                            borderTop: si > 0 ? `1px solid ${T.border}` : "none",
                        }}
                    >
                        <h2 style={{ fontSize: "20px", fontWeight: 700, color: T.textPrimary, margin: "0 0 20px" }}>
                            {section.title}
                        </h2>

                        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                            {section.content.map((item, i) => (
                                <div key={i}>
                                    {'subtitle' in item && item.subtitle && (
                                        <h3 style={{ fontSize: "14px", fontWeight: 600, color: T.accent, margin: "0 0 4px" }}>
                                            {item.subtitle}
                                        </h3>
                                    )}
                                    {item.text && (
                                        <p style={{ fontSize: "14px", color: T.textMuted, lineHeight: 1.7, margin: 0 }}>
                                            {item.text}
                                        </p>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </section>

            <style>{`* { box-sizing: border-box; margin: 0; }`}</style>
        </div>
    );
}
