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
                    <Link
                        href="/ftl-checker"
                        style={{
                            fontSize: "13px",
                            fontWeight: 600,
                            color: "var(--re-surface-base)",
                            background: "var(--re-brand)",
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
