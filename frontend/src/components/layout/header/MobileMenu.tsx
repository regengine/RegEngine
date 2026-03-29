'use client';

import Link from 'next/link';
import { MARKETING_PRIMARY_NAV, MARKETING_FREE_TOOLS } from '@/components/layout/marketing-nav';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { ThemeToggle } from '@/components/layout/theme-toggle';
import { MobileMenuCTA } from './MobileMenuCTA';
import type { MobileMenuProps } from './types';

export function MobileMenu({ user, showLoggedIn, pathname, mobileOpen, setMobileOpen }: MobileMenuProps) {
    return (
        <>
            {/* Mobile Drawer Overlay */}
            <div
                style={{
                    position: "fixed",
                    inset: 0,
                    zIndex: 49,
                    background: "rgba(0,0,0,0.5)",
                    backdropFilter: "blur(4px)",
                    WebkitBackdropFilter: "blur(4px)",
                    opacity: mobileOpen ? 1 : 0,
                    pointerEvents: mobileOpen ? "auto" : "none",
                    transition: "opacity 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                }}
                onClick={() => setMobileOpen(false)}
                aria-hidden="true"
            />

            {/* Mobile Drawer Panel */}
            <div
                className="marketing-mobile-drawer"
                role="dialog"
                aria-modal={mobileOpen}
                aria-label="Navigation menu"
                style={{
                    position: "fixed",
                    top: 0,
                    right: 0,
                    bottom: 0,
                    width: "min(320px, 85vw)",
                    zIndex: 51,
                    background: "var(--re-mobile-menu-bg)",
                    borderLeft: "1px solid var(--re-mobile-border)",
                    transform: mobileOpen ? "translateX(0)" : "translateX(100%)",
                    transition: "transform 0.35s cubic-bezier(0.16, 1, 0.3, 1)",
                    overflowY: "auto",
                    WebkitOverflowScrolling: "touch",
                    display: "flex",
                    flexDirection: "column",
                    paddingTop: "env(safe-area-inset-top, 0px)",
                    paddingBottom: "env(safe-area-inset-bottom, 0px)",
                }}
            >
                {/* Drawer Header */}
                <div style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "16px 20px",
                    borderBottom: "1px solid var(--re-mobile-border)",
                    minHeight: "56px",
                }}>
                    <RegEngineWordmark size="sm" />
                    <button
                        onClick={() => setMobileOpen(false)}
                        aria-label="Close menu"
                        style={{
                            background: "transparent",
                            border: "none",
                            color: "var(--re-text-muted)",
                            width: "44px",
                            height: "44px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            cursor: "pointer",
                            borderRadius: "8px",
                            WebkitTapHighlightColor: "transparent",
                            padding: 0,
                        }}
                    >
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                            <line x1="4" y1="4" x2="16" y2="16" />
                            <line x1="16" y1="4" x2="4" y2="16" />
                        </svg>
                    </button>
                </div>

                {/* Primary Nav Links */}
                <div style={{ padding: "8px 12px" }}>
                    {(user ? [
                        { label: 'Dashboard', href: '/dashboard' },
                        { label: 'Heartbeat', href: '/dashboard/heartbeat' },
                        { label: 'Compliance', href: '/dashboard/compliance' },
                        { label: 'Alerts', href: '/dashboard/alerts' },
                        { label: 'Suppliers', href: '/dashboard/suppliers' },
                        { label: 'Products', href: '/dashboard/products' },
                        { label: 'Settings', href: '/dashboard/settings' },
                    ] : MARKETING_PRIMARY_NAV).map((item) => (
                        <Link
                            key={item.label}
                            href={item.href}
                            onClick={() => setMobileOpen(false)}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                fontSize: "15px",
                                color: pathname === item.href ? "var(--re-brand)" : "var(--re-text-primary)",
                                textDecoration: "none",
                                fontWeight: pathname === item.href ? 600 : 500,
                                padding: "14px 12px",
                                borderRadius: "10px",
                                transition: "background 0.15s",
                                minHeight: "48px",
                                WebkitTapHighlightColor: "transparent",
                            }}
                        >
                            {item.label}
                        </Link>
                    ))}
                </div>

                {/* Divider */}
                <div style={{ height: "1px", background: "var(--re-mobile-border)", margin: "4px 20px" }} />

                {/* Free Tools Section */}
                <div style={{ padding: "8px 12px" }}>
                    <div style={{
                        fontSize: "10px",
                        fontWeight: 600,
                        letterSpacing: "0.12em",
                        textTransform: "uppercase" as const,
                        color: "var(--re-text-muted)",
                        padding: "8px 12px 4px",
                    }}>
                        FSMA 204 Compliance Tools
                    </div>
                    {MARKETING_FREE_TOOLS.map((tool) => (
                        <Link
                            key={tool.href}
                            href={tool.href}
                            onClick={() => setMobileOpen(false)}
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "12px",
                                padding: "12px",
                                textDecoration: "none",
                                borderRadius: "10px",
                                transition: "background 0.15s",
                                minHeight: "48px",
                                WebkitTapHighlightColor: "transparent",
                            }}
                        >
                            <span aria-hidden="true" style={{ fontSize: "18px", width: "24px", textAlign: "center" }}>{tool.emoji}</span>
                            <div>
                                <div style={{ fontSize: "14px", fontWeight: 500, color: "var(--re-text-primary)" }}>{tool.label}</div>
                                <div style={{ fontSize: "12px", color: "var(--re-text-muted)", lineHeight: 1.3 }}>{tool.desc}</div>
                            </div>
                        </Link>
                    ))}
                    <Link
                        href="/tools"
                        onClick={() => setMobileOpen(false)}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "12px",
                            padding: "12px",
                            textDecoration: "none",
                            borderRadius: "10px",
                            minHeight: "48px",
                            WebkitTapHighlightColor: "transparent",
                        }}
                    >
                        <span aria-hidden="true" style={{ fontSize: "18px", width: "24px", textAlign: "center" }}>&#129520;</span>
                        <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--re-brand)" }}>View All Tools &rarr;</div>
                    </Link>
                </div>

                {/* Divider */}
                <div style={{ height: "1px", background: "var(--re-mobile-border)", margin: "4px 20px" }} />

                {/* Theme Toggle */}
                <div style={{ padding: "12px 24px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: "13px", color: "var(--re-text-muted)", fontWeight: 500 }}>Theme</span>
                    <ThemeToggle />
                </div>

                {/* Spacer */}
                <div style={{ flex: 1 }} />

                {/* CTA Buttons at bottom */}
                <MobileMenuCTA user={user} showLoggedIn={showLoggedIn} setMobileOpen={setMobileOpen} />
            </div>
        </>
    );
}
