'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { MARKETING_FREE_TOOLS, MARKETING_PRIMARY_NAV } from '@/components/layout/marketing-nav';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { ThemeToggle } from '@/components/layout/theme-toggle';

export function MarketingHeader() {
    const pathname = usePathname();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [toolsOpen, setToolsOpen] = useState(false);
    const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const toolsWrapperRef = useRef<HTMLDivElement | null>(null);
    const toolsButtonRef = useRef<HTMLButtonElement | null>(null);
    const { user } = useAuth();
    const hideHeader =
        pathname === '/mobile/capture' ||
        pathname === '/fsma/field-capture' ||
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding');

    const handleToolsEnter = () => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current);
            closeTimeoutRef.current = null;
        }
        setToolsOpen(true);
    };

    const handleToolsLeave = () => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current);
        }

        closeTimeoutRef.current = setTimeout(() => {
            setToolsOpen(false);
        }, 500); // Increased delay for slow movement
    };

    const focusFirstToolsItem = () => {
        requestAnimationFrame(() => {
            const firstItem = toolsWrapperRef.current?.querySelector<HTMLElement>('[role="menuitem"]');
            firstItem?.focus();
        });
    };

    const handleToolsKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Escape') {
            setToolsOpen(false);
            toolsButtonRef.current?.focus();
            return;
        }

        if (!toolsOpen || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) {
            return;
        }

        const menuItems = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'));
        if (menuItems.length === 0) {
            return;
        }

        e.preventDefault();
        const activeIndex = menuItems.findIndex((item) => item === document.activeElement);

        if (activeIndex === -1) {
            const fallbackIndex = e.key === 'ArrowDown' ? 0 : menuItems.length - 1;
            menuItems[fallbackIndex]?.focus();
            return;
        }

        const nextIndex =
            e.key === 'ArrowDown'
                ? (activeIndex + 1) % menuItems.length
                : (activeIndex - 1 + menuItems.length) % menuItems.length;
        menuItems[nextIndex]?.focus();
    };

    useEffect(() => {
        if (hideHeader) {
            return;
        }

        const handleOutsideInteraction = (event: MouseEvent | TouchEvent) => {
            const target = event.target as Node;
            if (!toolsWrapperRef.current?.contains(target)) {
                setToolsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleOutsideInteraction);
        document.addEventListener('touchstart', handleOutsideInteraction);

        return () => {
            document.removeEventListener('mousedown', handleOutsideInteraction);
            document.removeEventListener('touchstart', handleOutsideInteraction);
            if (closeTimeoutRef.current) {
                clearTimeout(closeTimeoutRef.current);
            }
        };
    }, [hideHeader]);

    if (hideHeader) {
        return null;
    }

    return (
        <nav
            aria-label="Main navigation"
            style={{
                position: "sticky",
                top: 0,
                zIndex: 50,
                borderBottom: "1px solid var(--re-nav-border)",
                backdropFilter: "blur(16px)",
                background: "var(--re-nav-bg)",
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
                    <RegEngineWordmark size="md" />
                </Link>

                {/* Desktop Nav */}
                <div className="marketing-desktop-nav" style={{ display: "flex", alignItems: "center", gap: "28px" }}>
                    {[
                        ...MARKETING_PRIMARY_NAV,
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
                    <div
                        ref={toolsWrapperRef}
                        style={{ position: "relative" }}
                        onMouseEnter={handleToolsEnter}
                        onMouseLeave={handleToolsLeave}
                        onKeyDown={handleToolsKeyDown}
                    >
                        <button
                            ref={toolsButtonRef}
                            type="button"
                            aria-expanded={toolsOpen}
                            aria-haspopup="true"
                            aria-controls="tools-dropdown"
                            onClick={() => setToolsOpen((open) => !open)}
                            onKeyDown={(e) => {
                                if (e.key === 'Escape') {
                                    setToolsOpen(false);
                                    return;
                                }

                                if (e.key === 'ArrowDown') {
                                    e.preventDefault();
                                    if (!toolsOpen) {
                                        setToolsOpen(true);
                                    }
                                    focusFirstToolsItem();
                                }
                            }}
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
                                border: "none",
                            }}
                        >
                            Free Tools ▾
                        </button>
                        <div
                            data-tools-dropdown
                            style={{
                                position: "absolute",
                                top: "100%",
                                right: 0,
                                paddingTop: "60px", // Large bridge to cover gaps
                                marginTop: "-30px", // Move container up to overlap hit area
                                background: "none",
                                border: "none",
                                borderRadius: "10px",
                                opacity: toolsOpen ? 1 : 0,
                                pointerEvents: toolsOpen ? "auto" : "none",
                                transform: toolsOpen ? "translateY(0)" : "translateY(10px)",
                                transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)", // Smoother transition
                                zIndex: 100,
                            }}
                        >
                            <div
                                id="tools-dropdown"
                                role="menu"
                                aria-label="Free compliance tools"
                                aria-hidden={!toolsOpen}
                                style={{
                                    background: "var(--re-nav-dropdown-bg)",
                                    border: "1px solid var(--re-nav-dropdown-border)",
                                    borderRadius: "12px",
                                    padding: "8px 0",
                                    minWidth: "280px",
                                    backdropFilter: "blur(24px)",
                                    boxShadow: "var(--re-nav-dropdown-shadow)",
                                }}
                            >
                                <div className="px-4 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-re-text-muted uppercase">
                                    Featured Compliance Tools
                                </div>
                                {MARKETING_FREE_TOOLS.map((tool) => (
                                    <Link
                                        key={tool.href}
                                        href={tool.href}
                                        role="menuitem"
                                        tabIndex={toolsOpen ? 0 : -1}
                                        className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                                        onClick={() => setToolsOpen(false)}
                                        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--re-nav-hover)")}
                                        onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                                    >
                                        <span aria-hidden="true" className="text-sm">{tool.emoji}</span>
                                        <div>
                                            <div className="text-[13px] font-medium text-re-text-primary">{tool.label}</div>
                                            <div className="text-[11px] text-re-text-muted">{tool.desc}</div>
                                        </div>
                                    </Link>
                                ))}
                                <div style={{ height: "1px", background: "var(--re-nav-divider)", margin: "6px 12px" }} />
                                <Link
                                    href="/tools"
                                    role="menuitem"
                                    tabIndex={toolsOpen ? 0 : -1}
                                    className="flex items-center gap-2.5 py-2.5 px-4 no-underline transition-[background] duration-150"
                                    onClick={() => setToolsOpen(false)}
                                    onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.05)")}
                                    onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                                >
                                    <span aria-hidden="true" className="text-sm">🧰</span>
                                    <div>
                                        <div className="text-[13px] font-semibold text-re-brand">View All Tools →</div>
                                        <div className="text-[11px] text-re-text-muted">Explore the compliance toolkit</div>
                                    </div>
                                </Link>
                            </div>
                        </div>
                    </div>

                    <ThemeToggle />

                    {/* Auth-aware buttons */}
                    {user ? (
                        <Link
                            href="/dashboard"
                            style={{
                                fontSize: "13px",
                                fontWeight: 500,
                                color: "var(--re-text-muted)",
                                textDecoration: "none",
                                transition: "color 0.2s",
                            }}
                            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-primary)")}
                            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-muted)")}
                        >
                            Dashboard
                        </Link>
                    ) : (
                        <>
                            <Link
                                href="/login"
                                style={{
                                    fontSize: "13px",
                                    fontWeight: 500,
                                    color: "var(--re-text-muted)",
                                    textDecoration: "none",
                                    transition: "color 0.2s",
                                }}
                                onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-primary)")}
                                onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-muted)")}
                            >
                                Log In
                            </Link>
                            <Link
                                href="/onboarding"
                                style={{
                                    fontSize: "13px",
                                    fontWeight: 600,
                                    color: "var(--re-surface-base)",
                                    background: "linear-gradient(135deg, var(--re-brand), #3b82f6)",
                                    padding: "7px 18px",
                                    borderRadius: "6px",
                                    textDecoration: "none",
                                    transition: "all 0.2s",
                                }}
                            >
                                Get Started →
                            </Link>
                        </>
                    )}
                </div>

                {/* Mobile Hamburger */}
                <button
                    className="marketing-mobile-toggle"
                    onClick={() => setMobileOpen(!mobileOpen)}
                    aria-label="Toggle navigation menu"
                    style={{
                        display: "none",
                        background: "transparent",
                        border: "1px solid var(--re-mobile-toggle-border)",
                        borderRadius: "6px",
                        padding: "6px 10px",
                        cursor: "pointer",
                        color: "var(--re-text-primary)",
                        fontSize: "18px",
                        lineHeight: 1,
                        minWidth: "44px",
                        minHeight: "44px",
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
                        borderTop: "1px solid var(--re-nav-divider)",
                        background: "var(--re-mobile-menu-bg)",
                        padding: "16px 24px 24px",
                        maxHeight: "calc(100vh - 56px)",
                        overflowY: "auto",
                    }}
                >
                    <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                        {[
                            ...MARKETING_PRIMARY_NAV,
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
                                    borderBottom: "1px solid var(--re-mobile-border)",
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
                        {MARKETING_FREE_TOOLS.map((tool) => (
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
                                    borderBottom: "1px solid var(--re-mobile-border)",
                                }}
                            >
                                <span aria-hidden="true" style={{ fontSize: "16px" }}>{tool.emoji}</span>
                                <div>
                                    <div style={{ fontSize: "14px", fontWeight: 500, color: "var(--re-text-primary)" }}>{tool.label}</div>
                                    <div style={{ fontSize: "11px", color: "var(--re-text-muted)" }}>{tool.desc}</div>
                                </div>
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
                            <div style={{ color: "var(--re-brand)" }}>View All Tools →</div>
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
