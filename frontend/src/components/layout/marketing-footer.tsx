'use client';

import Link from 'next/link';

const industries = [
    { name: "Food & Beverage", status: "live" as const },
    { name: "Energy", status: "coming" as const },
    { name: "Nuclear", status: "coming" as const },
    { name: "Finance", status: "coming" as const },
    { name: "Healthcare", status: "coming" as const },
    { name: "Manufacturing", status: "coming" as const },
];

export function MarketingFooter() {
    return (
        <footer
            style={{
                position: "relative",
                zIndex: 2,
                borderTop: "1px solid rgba(255,255,255,0.04)",
                background: "rgba(0,0,0,0.2)",
                fontFamily: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
            }}
        >
            <div
                style={{
                    maxWidth: "1120px",
                    margin: "0 auto",
                    padding: "48px 24px 32px",
                    display: "grid",
                    gridTemplateColumns: "2fr 1fr 1fr 1fr",
                    gap: "40px",
                }}
            >
                <div>
                    <Link href="/" style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", textDecoration: "none" }}>
                        <div
                            style={{
                                width: "6px",
                                height: "6px",
                                borderRadius: "50%",
                                background: "var(--re-brand)",
                            }}
                        />
                        <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--re-text-primary)", letterSpacing: "0.06em" }}>
                            REGENGINE
                        </span>
                    </Link>
                    <p style={{ fontSize: "13px", color: "var(--re-text-disabled)", lineHeight: 1.6, margin: "0 0 16px", maxWidth: "280px" }}>
                        API-first regulatory compliance. Built by a founder who's done federal
                        compliance for 20 years — not a marketing team.
                    </p>
                    <div style={{ fontSize: "12px", fontFamily: "'JetBrains Mono', monospace", color: "var(--re-text-disabled)" }}>
                        FSMA 204 Deadline: July 20, 2028
                    </div>
                </div>

                <div>
                    <h4 style={{ fontSize: "12px", fontWeight: 600, color: "var(--re-text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "16px" }}>
                        Product
                    </h4>
                    {[
                        { label: "FTL Checker", href: "/ftl-checker", badge: "Free" },
                        { label: "Retailer Readiness", href: "/retailer-readiness" },
                        { label: "API Docs", href: "/docs" },
                        { label: "Pricing", href: "/pricing" },
                    ].map((link) => (
                        <Link
                            key={link.label}
                            href={link.href}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "6px",
                                fontSize: "13px",
                                color: "var(--re-text-tertiary)",
                                textDecoration: "none",
                                marginBottom: "10px",
                            }}
                        >
                            {link.label}
                            {link.badge && (
                                <span style={{ fontSize: "9px", color: "var(--re-brand)", fontWeight: 600, textTransform: "uppercase" }}>
                                    {link.badge}
                                </span>
                            )}
                        </Link>
                    ))}
                </div>

                <div>
                    <h4 style={{ fontSize: "12px", fontWeight: 600, color: "var(--re-text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "16px" }}>
                        Industries
                    </h4>
                    <Link href="/ftl-checker" style={{ fontSize: "13px", color: "var(--re-brand)", textDecoration: "none", marginBottom: "10px", display: "block" }}>
                        Food & Beverage ✓
                    </Link>
                    {industries.filter(i => i.status === "coming").slice(0, 5).map((ind) => (
                        <span
                            key={ind.name}
                            style={{ fontSize: "13px", color: "var(--re-text-disabled)", marginBottom: "10px", display: "block" }}
                        >
                            {ind.name}
                        </span>
                    ))}
                    <Link href="/#industries" style={{ fontSize: "12px", color: "var(--re-text-disabled)", textDecoration: "none", marginTop: "4px", display: "block" }}>
                        +5 more →
                    </Link>
                </div>

                <div>
                    <h4 style={{ fontSize: "12px", fontWeight: 600, color: "var(--re-text-muted)", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "16px" }}>
                        Company
                    </h4>
                    {["About", "Security", "Privacy", "Terms"].map((item) => (
                        <Link
                            key={item}
                            href={`/${item.toLowerCase()}`}
                            style={{ fontSize: "13px", color: "var(--re-text-tertiary)", textDecoration: "none", marginBottom: "10px", display: "block" }}
                        >
                            {item}
                        </Link>
                    ))}
                </div>
            </div>

            <div
                style={{
                    maxWidth: "1120px",
                    margin: "0 auto",
                    padding: "20px 24px",
                    borderTop: "1px solid rgba(255,255,255,0.03)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                }}
            >
                <span style={{ fontSize: "12px", color: "var(--re-text-disabled)" }}>
                    © 2026 RegEngine Inc. All rights reserved.
                </span>
                <span style={{ fontSize: "11px", color: "var(--re-surface-card)", fontFamily: "'JetBrains Mono', monospace" }}>
                    verify_chain.py — don't trust, verify
                </span>
            </div>
        </footer>
    );
}
