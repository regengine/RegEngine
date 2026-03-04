'use client';

import Link from 'next/link';
import Image from 'next/image';
import { usePathname } from 'next/navigation';

const industries = [
    { name: "Food & Beverage", href: "/retailer-readiness" },
];

export function MarketingFooter() {
    const pathname = usePathname();

    // Hide global footer on standalone mobile app and dashboard routes
    if (pathname === '/fsma/field-capture' || pathname.startsWith('/dashboard')) {
        return null;
    }

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
                        <span className="text-[9px] font-bold uppercase tracking-widest text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-1.5 py-0.5 rounded-full">Beta</span>
                    </Link>
                    <p style={{ fontSize: "13px", color: "var(--re-text-disabled)", lineHeight: 1.6, margin: "0 0 16px", maxWidth: "280px" }}>
                        API-first regulatory compliance.
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
                        { label: "FSMA Dashboard", href: "/fsma" },
                        { label: "FTL Checker", href: "/tools/ftl-checker", badge: "Free" },
                        { label: "Retailer Readiness", href: "/retailer-readiness" },
                        { label: "Developers", href: "/developers" },
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
                        { label: "FTL Checker", href: "/tools/ftl-checker" },
                        { label: "FSMA Exemption Check", href: "/tools/ftl-checker" },
                        { label: "Bulk Upload Templates", href: "/onboarding/bulk-upload" },
                        { label: "Anomaly Simulator", href: "/tools/fsma-unified" },
                        { label: "Knowledge Graph", href: "/tools/knowledge-graph" },
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
                        Industry Focus
                    </h4>
                    <div className="grid grid-cols-1 gap-y-2.5">
                        {industries.map((ind) => (
                            <Link
                                key={ind.name}
                                href={ind.href}
                                className="text-[13px] text-re-text-tertiary no-underline flex items-center gap-1.5"
                            >
                                {ind.name}
                            </Link>
                        ))}
                    </div>
                </div>

                <div>
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Company
                    </h4>
                    {[
                        { label: "About", href: "/about" },
                        { label: "Security", href: "/security" },
                        { label: "Privacy", href: "/privacy" },
                        { label: "Terms", href: "/terms" },
                        { label: "Design Partner Program", href: "/alpha" },
                    ].map((item) => (
                        <Link
                            key={item.label}
                            href={item.href}
                            className="text-[13px] text-re-text-tertiary no-underline mb-2.5 block"
                        >
                            {item.label}
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
                <span style={{ fontSize: "11px", color: "var(--re-text-disabled)", fontFamily: "'JetBrains Mono', monospace" }}>
                    verify_chain.py — don&apos;t trust, verify
                </span>
            </div>
        </footer>
    );
}
