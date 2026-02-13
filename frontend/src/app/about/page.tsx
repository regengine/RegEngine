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

const timeline = [
    {
        year: "2003–2006",
        title: "AmeriCorps NCCC",
        description: "Team Leader during Hurricane Katrina response. Learned that compliance failures during crises aren't about bad people — they're about bad infrastructure.",
        tag: "Disaster Response",
    },
    {
        year: "2006–2009",
        title: "U.S. Senate — Personal Aide to Senator Jeff Merkley",
        description: "Managed 150+ town halls with 100% federal compliance. Saw firsthand how regulatory complexity creates coordination failures at scale.",
        tag: "Federal Government",
    },
    {
        year: "2009–2013",
        title: "Epilepsy Foundation of Los Angeles",
        description: "Program Manager overseeing $2.8M portfolio. Achieved 50% enrollment increases while navigating healthcare compliance requirements.",
        tag: "Nonprofit",
    },
    {
        year: "2013–2023",
        title: "Tech Startups — SeatGeek, RadarFirst, Shift Technologies",
        description: "Operations and technical roles across ticketing, privacy compliance, and automotive marketplaces. Built the technical foundation for what became RegEngine.",
        tag: "Technology",
    },
    {
        year: "2024–Present",
        title: "RegEngine",
        description: "Built an audit-grade regulatory compliance platform from architecture to deployment. Solo technical founder. Every line of code, every CFR citation, every SHA-256 hash.",
        tag: "Current",
    },
];

export default function AboutPage() {
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
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "80px 24px 60px" }}>
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
                        Built by someone who's actually done compliance work
                    </h1>
                    <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: "0 0 16px" }}>
                        RegEngine isn't a venture-backed team that read about FSMA 204 in a TechCrunch article. It's built by a founder with 20+ years of federal compliance, nonprofit program management, and technical operations experience.
                    </p>
                    <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: 0 }}>
                        The thesis is simple: regulatory compliance is a coordination problem, not an information problem. The rules are public. The challenge is making them machine-readable, cryptographically verifiable, and operationally useful — without requiring a six-figure consulting engagement.
                    </p>
                </div>
            </section>

            {/* Founder */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}`, background: "rgba(255,255,255,0.01)" }}>
                <div className="max-w-[720px] mx-auto py-[60px] px-6">
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
                                Christopher Lee Sellers
                            </h2>
                            <p style={{ fontSize: "14px", color: T.accent, fontWeight: 600, margin: "0 0 12px" }}>
                                CEO & Technical Founder
                            </p>
                            <p className="text-sm text-re-text-muted leading-relaxed m-0">
                                20+ years spanning federal government (U.S. Senate), nonprofit program management (Epilepsy Foundation), disaster response (AmeriCorps NCCC / Hurricane Katrina), and tech startups (SeatGeek, RadarFirst, Shift Technologies). President's Volunteer Service Award for lifetime achievement. B.S. Political Science, Portland State University.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Timeline */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "60px 24px 80px" }}>
                <h2 style={{ fontSize: "24px", fontWeight: 700, color: T.textPrimary, margin: "0 0 36px" }}>
                    The path to RegEngine
                </h2>

                <div style={{ display: "flex", flexDirection: "column", gap: "0", position: "relative" }}>
                    {/* Vertical line */}
                    <div
                        style={{
                            position: "absolute", left: "15px", top: "8px", bottom: "8px", width: "1px",
                            background: `linear-gradient(to bottom, ${T.border}, ${T.accentBorder}, ${T.accent})`,
                        }}
                    />

                    {timeline.map((item, i) => {
                        const isCurrent = i === timeline.length - 1;
                        return (
                            <div key={i} style={{ display: "flex", gap: "24px", padding: "20px 0", position: "relative" }}>
                                <div
                                    style={{
                                        width: "10px", height: "10px", borderRadius: "50%", flexShrink: 0, marginTop: "6px",
                                        background: isCurrent ? T.accent : T.textGhost,
                                        boxShadow: isCurrent ? `0 0 12px ${T.accentBorder}` : "none",
                                        border: isCurrent ? "none" : `2px solid ${T.textDim}`,
                                        position: "relative", left: "10px", zIndex: 2,
                                    }}
                                />
                                <div className="flex-1">
                                    <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px", flexWrap: "wrap" }}>
                                        <span style={{ fontSize: "12px", fontFamily: T.mono, color: T.textDim, fontWeight: 500 }}>
                                            {item.year}
                                        </span>
                                        <span
                                            style={{
                                                fontSize: "10px", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase",
                                                padding: "2px 8px", borderRadius: "4px",
                                                color: isCurrent ? T.accent : T.textDim,
                                                background: isCurrent ? T.accentBg : T.elevated,
                                                border: `1px solid ${isCurrent ? T.accentBorder : T.border}`,
                                            }}
                                        >
                                            {item.tag}
                                        </span>
                                    </div>
                                    <h3 style={{ fontSize: "15px", fontWeight: 600, color: T.textPrimary, margin: "0 0 6px" }}>
                                        {item.title}
                                    </h3>
                                    <p className="text-sm text-re-text-muted leading-relaxed m-0">
                                        {item.description}
                                    </p>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* What we believe */}
            <section style={{ position: "relative", zIndex: 2, borderTop: `1px solid ${T.border}`, background: T.accentBg }}>
                <div className="max-w-[720px] mx-auto py-[60px] px-6">
                    <h2 style={{ fontSize: "24px", fontWeight: 700, color: T.textPrimary, margin: "0 0 28px" }}>
                        What we believe
                    </h2>
                    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                        {[
                            { title: "Compliance data should be verifiable, not trusted.", body: "Every fact in RegEngine is cryptographically hashed with SHA-256. Run our open verification script yourself. If the hashes don't match, don't trust us." },
                            { title: "Pricing should be public.", body: "The compliance industry runs on 'contact sales' and opaque enterprise contracts. We publish our prices. If you can't afford us, we'll point you to free resources that can help." },
                            { title: "Regulations are public. Access shouldn't be expensive.", body: "The Code of Federal Regulations is freely available. The challenge is operationalizing it. We charge for the infrastructure, not the information." },
                            { title: "Solo founder ≠ unserious.", body: "We're honest about being early-stage with a single founder. That means you get direct access to the person who built every layer of the system — not a support ticket queue." },
                        ].map((belief, i) => (
                            <div key={i}>
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
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "60px 24px", textAlign: "center" }}>
                <h2 style={{ fontSize: "24px", fontWeight: 700, color: T.textPrimary, margin: "0 0 12px" }}>
                    Questions? Talk to the founder directly.
                </h2>
                <p style={{ fontSize: "15px", color: T.textMuted, margin: "0 0 24px" }}>
                    chris@regengine.co — no sales team, no gatekeepers.
                </p>
                <a
                    href="/ftl-checker"
                    style={{
                        display: "inline-flex", alignItems: "center", gap: "8px",
                        padding: "14px 28px", background: T.accent, color: T.bg,
                        borderRadius: "8px", fontSize: "15px", fontWeight: 600, textDecoration: "none",
                    }}
                >
                    Try the FTL Checker →
                </a>
            </section>

            <style>{`* { box-sizing: border-box; margin: 0; }`}</style>
        </div>
    );
}
