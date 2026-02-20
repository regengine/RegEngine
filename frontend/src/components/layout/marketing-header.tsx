'use client';

import { useState } from 'react';
import Link from 'next/link';

const TOOL_ITEMS = [
    { emoji: "🥬", label: "FTL Coverage Checker", desc: "Check if your products are on the FDA Food Traceability List", href: "/ftl-checker" },
    { emoji: "🛡️", label: "Exemption Qualifier", desc: "Check FSMA 204 exemption eligibility", href: "/tools/exemption-qualifier" },
    { emoji: "📋", label: "Recall Readiness Score", desc: "Grade your 24-hour retrieval capability", href: "/tools/recall-readiness" },
];

const MORE_TOOLS = [
    { label: "KDE Completeness Checker", href: "/tools/kde-checker" },
    { label: "TLC Validator", href: "/tools/tlc-validator" },
    { label: "CTE Coverage Mapper", href: "/tools/cte-mapper" },
    { label: "24-Hour Drill Simulator", href: "/tools/drill-simulator" },
    { label: "ROI Calculator", href: "/tools/roi-calculator" },
];

export function MarketingHeader() {
    const [mobileOpen, setMobileOpen] = useState(false);

    return (
        <nav
            style={{
                position: "sticky",
                top: 0,
                zIndex: 50,
                borderBottom: "1px solid rgba(255,255,255,0.04)",
                backdropFilter: "blur(16px)",
                background: "rgba(6,9,15,0.85)",
            }}
        >
            <div
                style={{
                    maxWidth: "1120px",
                    margin: "0 auto",
                    padding: "0 24px",
                    height: "56px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                }}
            >
                <Link href="/" style={{ display: "flex", alignItems: "center", gap: "10px", textDecoration: "none" }}>
                    <div
                        style={{
                            width: "8px",
                            height: "8px",
                            borderRadius: "50%",
                            background: "var(--re-brand)",
                            boxShadow: "0 0 10px rgba(16,185,129,0.4)",
                        }}
                    />
                    <span
                        style={{
                            fontSize: "14px",
                            fontWeight: 700,
                            letterSpacing: "0.06em",
                            color: "var(--re-text-primary)",
                        }}
                    >
                        REGENGINE
                    </span>
                </Link>

                {/* Desktop Nav */}
                <div className="marketing-desktop-nav" style={{ display: "flex", alignItems: "center", gap: "28px" }}>
                    {[
                        { label: "Product", href: "/#product" },
                        { label: "Industries", href: "/#industries" },
                        { label: "Developers", href: "/#developers" },
                        { label: "Pricing", href: "/pricing" },
                    ].map((item) => (
                        <Link
                            key={item.label}
                            href={item.href}
                            style={{
                                fontSize: "13px",
                                color: "var(--re-text-muted)",
                                textDecoration: "none",
                                fontWeight: 500,
                                transition: "color 0.2s",
                            }}
                            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-primary)")}
                            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-muted)")}
                        >
                            {item.label}
                        </Link>
                    ))}

                    {/* Free Tools Dropdown */}
                    <div style={{ position: "relative" }}
                        onMouseEnter={(e) => {
                            const dropdown = e.currentTarget.querySelector('[data-tools-dropdown]') as HTMLElement;
                            if (dropdown) dropdown.style.opacity = '1';
                            if (dropdown) dropdown.style.pointerEvents = 'auto';
                            if (dropdown) dropdown.style.transform = 'translateY(0)';
                        }}
                        onMouseLeave={(e) => {
                            const dropdown = e.currentTarget.querySelector('[data-tools-dropdown]') as HTMLElement;
                            if (dropdown) dropdown.style.opacity = '0';
                            if (dropdown) dropdown.style.pointerEvents = 'none';
                            if (dropdown) dropdown.style.transform = 'translateY(4px)';
                        }}
                    >
                        <span
                            style={{
                                fontSize: "13px",
                                fontWeight: 600,
                                color: "var(--re-surface-base)",
                                background: "var(--re-brand)",
                                padding: "7px 16px",
                                borderRadius: "6px",
                                textDecoration: "none",
                                transition: "all 0.2s",
                                cursor: "pointer",
                                display: "inline-block",
                            }}
                        >
                            Free Tools ▾
                        </span>
                        <div
                            data-tools-dropdown
                            style={{
                                position: "absolute",
                                top: "100%",
                                right: 0,
                                marginTop: "8px",
                                background: "rgba(15,20,30,0.97)",
                                border: "1px solid rgba(255,255,255,0.08)",
                                borderRadius: "10px",
                                padding: "8px 0",
                                minWidth: "280px",
                                opacity: 0,
                                pointerEvents: "none" as const,
                                transform: "translateY(4px)",
                                transition: "all 0.2s ease",
                                backdropFilter: "blur(20px)",
                                boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                            }}
                        >
                            <div className="px-4 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-re-text-muted uppercase">
                                FSMA 204 Compliance Tools
                            </div>
                            {TOOL_ITEMS.map((tool) => (
                                <Link key={tool.href} href={tool.href} className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                                    onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                    onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                                >
                                    <span className="text-sm">{tool.emoji}</span>
                                    <div>
                                        <div className="text-[13px] font-medium text-re-text-primary">{tool.label}</div>
                                        <div className="text-[11px] text-re-text-muted">{tool.desc}</div>
                                    </div>
                                </Link>
                            ))}
                            <div style={{ height: "1px", background: "rgba(255,255,255,0.06)", margin: "6px 12px" }} />
                            <Link href="/tools" className="flex items-center gap-2.5 py-2.5 px-4 no-underline transition-[background] duration-150"
                                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                            >
                                <span className="text-sm">🧰</span>
                                <div>
                                    <div className="text-[13px] font-semibold text-re-brand">View All Tools →</div>
                                    <div className="text-[11px] text-re-text-muted">7 free FSMA compliance tools</div>
                                </div>
                            </Link>
                        </div>
                    </div>
                </div>

                {/* Mobile Hamburger */}
                <button
                    className="marketing-mobile-toggle"
                    onClick={() => setMobileOpen(!mobileOpen)}
                    aria-label="Toggle navigation menu"
                    style={{
                        display: "none",
                        background: "transparent",
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: "6px",
                        padding: "6px 10px",
                        cursor: "pointer",
                        color: "var(--re-text-primary)",
                        fontSize: "18px",
                        lineHeight: 1,
                    }}
                >
                    {mobileOpen ? "✕" : "☰"}
                </button>
            </div>

            {/* Mobile Menu Panel */}
            {mobileOpen && (
                <div
                    className="marketing-mobile-menu"
                    style={{
                        display: "none",
                        borderTop: "1px solid rgba(255,255,255,0.06)",
                        background: "rgba(6,9,15,0.97)",
                        padding: "16px 24px 24px",
                        maxHeight: "calc(100vh - 56px)",
                        overflowY: "auto",
                    }}
                >
                    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                        {[
                            { label: "Product", href: "/#product" },
                            { label: "Industries", href: "/#industries" },
                            { label: "Developers", href: "/#developers" },
                            { label: "Pricing", href: "/pricing" },
                        ].map((item) => (
                            <Link
                                key={item.label}
                                href={item.href}
                                onClick={() => setMobileOpen(false)}
                                style={{
                                    fontSize: "15px",
                                    color: "var(--re-text-secondary, #a1a1aa)",
                                    textDecoration: "none",
                                    fontWeight: 500,
                                    padding: "10px 0",
                                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                                }}
                            >
                                {item.label}
                            </Link>
                        ))}
                    </div>

                    <div style={{ marginTop: "16px" }}>
                        <div style={{
                            fontSize: "10px",
                            fontWeight: 600,
                            letterSpacing: "0.12em",
                            textTransform: "uppercase" as const,
                            color: "var(--re-text-muted)",
                            marginBottom: "8px",
                        }}>
                            FSMA 204 Compliance Tools
                        </div>
                        {TOOL_ITEMS.map((tool) => (
                            <Link
                                key={tool.href}
                                href={tool.href}
                                onClick={() => setMobileOpen(false)}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "10px",
                                    padding: "10px 0",
                                    textDecoration: "none",
                                    borderBottom: "1px solid rgba(255,255,255,0.04)",
                                }}
                            >
                                <span style={{ fontSize: "16px" }}>{tool.emoji}</span>
                                <div>
                                    <div style={{ fontSize: "14px", fontWeight: 500, color: "var(--re-text-primary)" }}>{tool.label}</div>
                                    <div style={{ fontSize: "11px", color: "var(--re-text-muted)" }}>{tool.desc}</div>
                                </div>
                            </Link>
                        ))}
                        {MORE_TOOLS.map((tool) => (
                            <Link
                                key={tool.href}
                                href={tool.href}
                                onClick={() => setMobileOpen(false)}
                                style={{
                                    display: "block",
                                    padding: "8px 0 8px 26px",
                                    fontSize: "13px",
                                    color: "var(--re-text-muted)",
                                    textDecoration: "none",
                                }}
                            >
                                {tool.label}
                            </Link>
                        ))}
                        <Link
                            href="/tools"
                            onClick={() => setMobileOpen(false)}
                            style={{
                                display: "block",
                                marginTop: "8px",
                                fontSize: "14px",
                                fontWeight: 600,
                                color: "var(--re-brand)",
                                textDecoration: "none",
                                padding: "10px 0",
                            }}
                        >
                            View All Tools →
                        </Link>
                    </div>
                </div>
            )}

            {/* Responsive CSS */}
            <style jsx>{`
                @media (max-width: 768px) {
                    .marketing-desktop-nav {
                        display: none !important;
                    }
                    .marketing-mobile-toggle {
                        display: block !important;
                    }
                    .marketing-mobile-menu {
                        display: block !important;
                    }
                }
            `}</style>
        </nav>
    );
}
