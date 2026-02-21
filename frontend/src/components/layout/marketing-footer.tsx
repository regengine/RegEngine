'use client';

import Link from 'next/link';
import Image from 'next/image';

const industries = [
    { name: "Food & Beverage", href: "/ftl-checker" },
    { name: "Energy", href: "/verticals/energy", comingSoon: true },
    { name: "Nuclear", href: "/verticals/nuclear", comingSoon: true },
    { name: "Finance", href: "/verticals/finance", comingSoon: true },
    { name: "Healthcare", href: "/verticals/healthcare", comingSoon: true },
    { name: "Manufacturing", href: "/verticals/manufacturing", comingSoon: true },
    { name: "Construction", href: "/verticals/construction", comingSoon: true },
    { name: "Aerospace", href: "/verticals/aerospace", comingSoon: true },
    { name: "Automotive", href: "/verticals/automotive", comingSoon: true },
    { name: "Gaming", href: "/verticals/gaming", comingSoon: true },
    { name: "Entertainment", href: "/verticals/entertainment", comingSoon: true },
    { name: "Technology", href: "/verticals/technology", comingSoon: true },
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
                    gridTemplateColumns: "2fr 1fr 1fr 1fr 1fr",
                    gap: "40px",
                }}
            >
                <div>
                    <Link href="/" style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", textDecoration: "none" }}>
                        <Image
                            src="/logo-dark.png"
                            alt="RegEngine"
                            width={120}
                            height={28}
                            style={{ objectFit: "contain" }}
                        />
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
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Product
                    </h4>
                    {[
                        { label: "Field Capture", href: "/mobile/capture", badge: "New" },
                        { label: "Compliance Snapshots", href: "/compliance/snapshots", badge: "New" },
                        { label: "Supply Chain Explorer", href: "/demo/supply-chains" },
                        { label: "Ingest Documents", href: "/ingest" },
                        { label: "FSMA Dashboard", href: "/fsma" },
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
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Free Tools
                    </h4>
                    {[
                        { label: "FSMA Dashboard", href: "/tools/fsma-unified" },
                        { label: "Anomaly Simulator", href: "/tools/fsma-unified?tab=anomaly" },
                        { label: "Knowledge Graph", href: "/tools/fsma-unified?tab=graph" },
                        { label: "FTL Checker", href: "/tools/ftl-checker" },
                        { label: "ROI Calculator", href: "/tools/roi-calculator" },
                        { label: "Exemption Qualifier", href: "/tools/exemption-qualifier" },
                        { label: "KDE Builder", href: "/tools/kde-checker" },
                    ].map((link) => (
                        <Link
                            key={link.label}
                            href={link.href}
                            style={{
                                display: "block",
                                fontSize: "13px",
                                color: "var(--re-text-tertiary)",
                                textDecoration: "none",
                                marginBottom: "10px",
                            }}
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>

                <div>
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Industries
                    </h4>
                    <div className="grid grid-cols-1 gap-y-2.5">
                        {industries.slice(0, 8).map((ind) => (
                            <Link
                                key={ind.name}
                                href={ind.href}
                                className="text-[13px] text-re-text-tertiary no-underline flex items-center gap-1.5"
                            >
                                {ind.name}
                                {ind.comingSoon && (
                                    <span style={{ fontSize: "9px", color: "var(--re-text-disabled)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                                        Soon
                                    </span>
                                )}
                            </Link>
                        ))}
                    </div>
                </div>

                <div>
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Company
                    </h4>
                    {["About", "Security", "Privacy", "Terms"].map((item) => (
                        <Link
                            key={item}
                            href={`/${item.toLowerCase()}`}
                            className="text-[13px] text-re-text-tertiary no-underline mb-2.5 block"
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
                <span className="text-xs text-re-text-disabled">
                    © 2026 RegEngine Inc. All rights reserved.
                </span>
                <span style={{ fontSize: "11px", color: "var(--re-surface-card)", fontFamily: "'JetBrains Mono', monospace" }}>
                    verify_chain.py — don't trust, verify
                </span>
            </div>
        </footer>
    );
}
