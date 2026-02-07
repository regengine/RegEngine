'use client';

import Link from 'next/link';

export function MarketingHeader() {
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
                            background: "#10b981",
                            boxShadow: "0 0 10px rgba(16,185,129,0.4)",
                        }}
                    />
                    <span
                        style={{
                            fontSize: "14px",
                            fontWeight: 700,
                            letterSpacing: "0.06em",
                            color: "#f1f5f9",
                        }}
                    >
                        REGENGINE
                    </span>
                </Link>

                <div style={{ display: "flex", alignItems: "center", gap: "28px" }}>
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
                                color: "#64748b",
                                textDecoration: "none",
                                fontWeight: 500,
                                transition: "color 0.2s",
                            }}
                            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "#e2e8f0")}
                            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "#64748b")}
                        >
                            {item.label}
                        </Link>
                    ))}
                    <Link
                        href="/ftl-checker"
                        style={{
                            fontSize: "13px",
                            fontWeight: 600,
                            color: "#06090f",
                            background: "#10b981",
                            padding: "7px 16px",
                            borderRadius: "6px",
                            textDecoration: "none",
                            transition: "all 0.2s",
                        }}
                    >
                        Free Tool
                    </Link>
                </div>
            </div>
        </nav>
    );
}
