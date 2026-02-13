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
                                minWidth: "240px",
                                opacity: 0,
                                pointerEvents: "none" as const,
                                transform: "translateY(4px)",
                                transition: "all 0.2s ease",
                                backdropFilter: "blur(20px)",
                                boxShadow: "0 12px 40px rgba(0,0,0,0.5)",
                            }}
                        >
                            <div className="px-4 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-re-text-muted uppercase">
                                Food Safety
                            </div>
                            <Link href="/ftl-checker" className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                            >
                                <span className="text-sm">🥬</span>
                                <div>
                                    <div className="text-[13px] font-medium text-re-text-primary">FTL Checker</div>
                                    <div className="text-[11px] text-re-text-muted">FSMA 204 Food Traceability</div>
                                </div>
                            </Link>
                            <div style={{ height: "1px", background: "rgba(255,255,255,0.06)", margin: "4px 12px" }} />
                            <div className="px-4 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-re-text-muted uppercase">
                                Finance AI Governance
                            </div>
                            <Link href="/tools/bias-checker" className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                            >
                                <span className="text-sm">⚖️</span>
                                <div>
                                    <div className="text-[13px] font-medium text-re-text-primary">Bias Checker</div>
                                    <div className="text-[11px] text-re-text-muted">Disparate Impact & 80% Rule</div>
                                </div>
                            </Link>
                            <Link href="/tools/obligation-scanner" className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                            >
                                <span className="text-sm">🔍</span>
                                <div>
                                    <div className="text-[13px] font-medium text-re-text-primary">Obligation Scanner</div>
                                    <div className="text-[11px] text-re-text-muted">Regulatory obligation mapping</div>
                                </div>
                            </Link>
                            <Link href="/tools/notice-validator" className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                            >
                                <span className="text-sm">📋</span>
                                <div>
                                    <div className="text-[13px] font-medium text-re-text-primary">Notice Validator</div>
                                    <div className="text-[11px] text-re-text-muted">Adverse action notice check</div>
                                </div>
                            </Link>
                        </div>
                    </div>
                </div>
            </div>
        </nav>
    );
}

