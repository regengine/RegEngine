'use client';

import { useState, useEffect } from "react";

const T = {
    bg: "var(--re-surface-base)",
    surface: "rgba(255,255,255,0.02)",
    border: "rgba(255,255,255,0.06)",
    accent: "var(--re-brand)",
    accentBg: "rgba(16,185,129,0.08)",
    accentBorder: "rgba(16,185,129,0.2)",
    textPrimary: "var(--re-text-primary)",
    textMuted: "var(--re-text-muted)",
    textDim: "var(--re-text-disabled)",
    sans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    mono: "'JetBrains Mono', monospace",
};

export default function AboutPage() {
    const [animateIn, setAnimateIn] = useState(false);
    useEffect(() => { setAnimateIn(true); }, []);

    return (
        <div className="re-page">
            <link
                href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
                rel="stylesheet"
            />

            {/* Hero */}
            <section className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-[48px]">
                <div
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? "translateY(0)" : "translateY(16px)",
                        transition: "all 0.7s cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                >
                    <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                        About
                    </span>
                    <h1 style={{ fontSize: "36px", fontWeight: 700, color: T.textPrimary, margin: "16px 0 20px", lineHeight: 1.15, letterSpacing: "-0.02em" }}>
                        Compliance infrastructure, built from the ground up
                    </h1>
                    <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: 0 }}>
                        RegEngine turns FSMA 204 requirements into machine-readable, cryptographically verifiable records.
                        Scan a barcode, trace a lot, export an FDA-ready package — in minutes, not days.
                    </p>
                </div>
            </section>

            {/* Founder */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}`, background: T.surface }}>
                <div className="max-w-[720px] mx-auto py-[48px] px-6">
                    <div style={{ display: "flex", gap: "24px", alignItems: "start" }}>
                        <div
                            style={{
                                width: "72px", height: "72px", borderRadius: "12px", flexShrink: 0,
                                background: T.accentBg, border: `1px solid ${T.accentBorder}`,
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: "28px", fontWeight: 700, color: T.accent,
                            }}
                        >
                            CS
                        </div>
                        <div>
                            <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 4px" }}>
                                Christopher Sellers
                            </h2>
                            <p style={{ fontSize: "14px", color: T.accent, fontWeight: 600, margin: "0 0 16px" }}>
                                Founder & CEO
                            </p>
                            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                                <div style={{ display: "flex", gap: "10px", alignItems: "baseline" }}>
                                    <span style={{ fontSize: "12px", fontFamily: T.mono, color: T.textDim, fontWeight: 500, minWidth: "20px" }}>01</span>
                                    <p className="text-sm text-re-text-muted leading-relaxed m-0">
                                        U.S. Senate — served as aide to Senator Jeff Merkley, supporting 150+ constituent engagements statewide.
                                    </p>
                                </div>
                                <div style={{ display: "flex", gap: "10px", alignItems: "baseline" }}>
                                    <span style={{ fontSize: "12px", fontFamily: T.mono, color: T.textDim, fontWeight: 500, minWidth: "20px" }}>02</span>
                                    <p className="text-sm text-re-text-muted leading-relaxed m-0">
                                        AmeriCorps NCCC — Team Leader during Hurricane Katrina disaster response. President&apos;s Volunteer Service Award.
                                    </p>
                                </div>
                                <div style={{ display: "flex", gap: "10px", alignItems: "baseline" }}>
                                    <span style={{ fontSize: "12px", fontFamily: T.mono, color: T.textDim, fontWeight: 500, minWidth: "20px" }}>03</span>
                                    <p className="text-sm text-re-text-muted leading-relaxed m-0">
                                        Built every layer of RegEngine — architecture, backend, frontend, compliance logic, and cryptographic verification. Solo technical founder.
                                    </p>
                                </div>
                            </div>
                            <a
                                href="https://www.linkedin.com/in/christophersellers"
                                target="_blank"
                                rel="noopener noreferrer"
                                style={{ display: "inline-block", fontSize: "13px", color: T.accent, fontWeight: 500, marginTop: "16px", textDecoration: "none" }}
                            >
                                LinkedIn →
                            </a>
                        </div>
                    </div>
                </div>
            </section>

            {/* Beliefs */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}` }}>
                <div className="max-w-[720px] mx-auto py-[48px] px-6">
                    <h2 style={{ fontSize: "24px", fontWeight: 700, color: T.textPrimary, margin: "0 0 24px" }}>
                        What we believe
                    </h2>
                    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                        {[
                            { title: "Compliance data should be verifiable, not trusted.", body: "Every record is SHA-256 hashed. Run our open verification script — if the hashes don't match, don't trust us." },
                            { title: "Pricing should be public.", body: "We publish our prices. No 'contact sales' gates, no opaque enterprise contracts." },
                            { title: "Regulations are public. Tooling should be accessible.", body: "The CFR is free. We charge for the infrastructure that makes it operationally useful." },
                        ].map((belief, i) => (
                            <div key={i} style={{ padding: "16px 20px", background: T.surface, borderRadius: "8px", border: `1px solid ${T.border}` }}>
                                <h3 style={{ fontSize: "15px", fontWeight: 600, color: T.textPrimary, margin: "0 0 4px" }}>
                                    {belief.title}
                                </h3>
                                <p className="text-sm text-re-text-muted leading-relaxed m-0">
                                    {belief.body}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}`, maxWidth: "720px", margin: "0 auto", padding: "48px 24px", textAlign: "center" }}>
                <h2 style={{ fontSize: "22px", fontWeight: 700, color: T.textPrimary, margin: "0 0 8px" }}>
                    Talk to the founder directly
                </h2>
                <p style={{ fontSize: "15px", color: T.textMuted, margin: "0 0 24px" }}>
                    chris@regengine.co — no sales team, no gatekeepers.
                </p>
                <div style={{ display: "flex", gap: "12px", justifyContent: "center", flexWrap: "wrap" }}>
                    <a
                        href="/signup"
                        style={{
                            display: "inline-flex", alignItems: "center", gap: "8px",
                            padding: "14px 28px", background: T.accent, color: T.bg,
                            borderRadius: "8px", fontSize: "15px", fontWeight: 600, textDecoration: "none",
                        }}
                    >
                        Start Free Trial →
                    </a>
                    <a
                        href="/pricing"
                        style={{
                            display: "inline-flex", alignItems: "center", gap: "8px",
                            padding: "14px 28px", background: "transparent", color: T.textPrimary,
                            borderRadius: "8px", fontSize: "15px", fontWeight: 600, textDecoration: "none",
                            border: `1px solid ${T.border}`,
                        }}
                    >
                        View Pricing
                    </a>
                </div>
            </section>

            <style>{`* { box-sizing: border-box; margin: 0; }`}</style>
        </div>
    );
}
