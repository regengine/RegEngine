'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
    MARKETING_FOOTER_COMPANY_LINKS,
    MARKETING_FOOTER_PRODUCT_LINKS,
    MARKETING_FREE_TOOLS,
} from '@/components/layout/marketing-nav';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';

export function MarketingFooter() {
    const pathname = usePathname();

    // Hide global footer on standalone mobile app and dashboard routes
    if (
        pathname === '/mobile/capture' ||
        pathname === '/fsma/field-capture' ||
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding')
    ) {
        return null;
    }

    return (
        <footer
            aria-label="Site footer"
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
                        <RegEngineWordmark size="sm" />
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
                    {MARKETING_FOOTER_PRODUCT_LINKS.map((link) => (
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
                        </Link>
                    ))}
                </div>

                <div>
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Free Tools
                    </h4>
                    {MARKETING_FREE_TOOLS.map((link) => (
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
                    <Link
                        href="/tools"
                        style={{
                            display: "block",
                            fontSize: "13px",
                            color: "var(--re-brand)",
                            textDecoration: "none",
                            marginTop: "4px",
                            fontWeight: 600,
                        }}
                    >
                        View all tools →
                    </Link>
                </div>

                <div>
                    <h4 className="text-xs font-semibold text-re-text-muted tracking-wider uppercase mb-4">
                        Company
                    </h4>
                    {MARKETING_FOOTER_COMPANY_LINKS.map((item) => (
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
