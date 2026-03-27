'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { MARKETING_FREE_TOOLS, MARKETING_PRIMARY_NAV } from '@/components/layout/marketing-nav';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { ThemeToggle } from '@/components/layout/theme-toggle';
// GlobalSearch removed — not ready for production

export function MarketingHeader() {
    const pathname = usePathname();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [toolsOpen, setToolsOpen] = useState(false);
    const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const toolsWrapperRef = useRef<HTMLDivElement | null>(null);
    const toolsButtonRef = useRef<HTMLButtonElement | null>(null);
    const { user, isAuthenticated, isHydrated } = useAuth();
    // Only show logged-in state when auth is fully verified
    const showLoggedIn = isHydrated && isAuthenticated && !!user;
    const hideHeader =
        pathname === '/mobile/capture' ||
        pathname === '/fsma/field-capture' ||
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding');

    // Close mobile menu on route change
    useEffect(() => {
        setMobileOpen(false);
    }, [pathname]);

    // Prevent body scroll when mobile menu is open
    useEffect(() => {
        if (mobileOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => { document.body.style.overflow = ''; };
    }, [mobileOpen]);

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
        }, 500);
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
        <>
            <nav
                aria-label="Main navigation"
                style={{
                    position: "sticky",
                    top: 0,
                    zIndex: 50,
                    borderBottom: "1px solid var(--re-nav-border)",
                    backdropFilter: "blur(16px)",
                    WebkitBackdropFilter: "blur(16px)",
                    background: "var(--re-nav-bg)",
                }}
            >
                <div
                    style={{
                        maxWidth: "1120px",
                        margin: "0 auto",
                        padding: "0 clamp(16px, 4vw, 24px)",
                        height: "56px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}
                >
                    <Link href="/" style={{ display: "flex", alignItems: "center", gap: "10px", textDecoration: "none", marginRight: "24px", flexShrink: 0 }}>
                        <RegEngineWordmark size="md" />
                    </Link>

                    {/* ═══ Desktop Nav ═══ */}
                    <div className="marketing-desktop-nav" style={{ display: "flex", alignItems: "center", gap: "28px" }}>
                        {(user ? [
                            { label: 'Dashboard', href: '/dashboard' },
                            { label: 'Compliance', href: '/dashboard/compliance' },
                            { label: 'Suppliers', href: '/dashboard/suppliers' },
                            { label: 'Products', href: '/dashboard/products' },
                        ] : MARKETING_PRIMARY_NAV).map((item) => (
                            <Link
                                key={item.label}
                                href={item.href}
                                style={{
                                    fontSize: "13px",
                                    color: "var(--re-text-muted)",
                                    textDecoration: "none",
                                    fontWeight: 500,
                                    transition: "color 0.2s",
                                    padding: "8px 0",
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
                                    paddingTop: "60px",
                                    marginTop: "-30px",
                                    background: "none",
                                    border: "none",
                                    borderRadius: "10px",
                                    opacity: toolsOpen ? 1 : 0,
                                    pointerEvents: toolsOpen ? "auto" : "none",
                                    transform: toolsOpen ? "translateY(0)" : "translateY(10px)",
                                    transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
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
                                        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--re-nav-hover)")}
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

                        {/* Developer & Docs links — outside dropdown wrapper so they're always clickable */}
                        <Link
                            href="/developer/portal"
                            style={{
                                fontSize: "13px",
                                fontWeight: 500,
                                color: "var(--re-text-muted)",
                                textDecoration: "none",
                                transition: "color 0.2s",
                                padding: "8px 0",
                            }}
                            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-primary)")}
                            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-muted)")}
                        >
                            Developers
                        </Link>
                        <Link
                            href="/docs"
                            style={{
                                fontSize: "13px",
                                fontWeight: 500,
                                color: "var(--re-text-muted)",
                                textDecoration: "none",
                                transition: "color 0.2s",
                                padding: "8px 0",
                            }}
                            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-primary)")}
                            onMouseLeave={(e) => ((e.target as HTMLElement).style.color = "var(--re-text-muted)")}
                        >
                            Docs
                        </Link>

                        <ThemeToggle />

                        {/* Auth-aware buttons */}
                        {showLoggedIn ? (
                            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                                <Link
                                    href="/dashboard"
                                    style={{
                                        fontSize: "13px",
                                        fontWeight: 600,
                                        color: "var(--re-surface-base)",
                                        background: "var(--re-brand)",
                                        padding: "7px 18px",
                                        borderRadius: "6px",
                                        textDecoration: "none",
                                        transition: "all 0.2s",
                                        boxShadow: "0 2px 8px var(--re-brand-muted)",
                                        display: "inline-flex",
                                        alignItems: "center",
                                        gap: "6px",
                                    }}
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
                                    </svg>
                                    Dashboard
                                </Link>
                                <div
                                    style={{
                                        width: "32px",
                                        height: "32px",
                                        borderRadius: "50%",
                                        background: "var(--re-brand)",
                                        display: "flex",
                                        alignItems: "center",
                                        justifyContent: "center",
                                        fontSize: "12px",
                                        fontWeight: 700,
                                        color: "var(--re-surface-base)",
                                        cursor: "pointer",
                                        textTransform: "uppercase",
                                    }}
                                    title={user.email || "Account"}
                                >
                                    {(user.email?.[0] || "U")}
                                </div>
                            </div>
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
                                        padding: "8px 0",
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
                                        color: "#fff",
                                        background: "var(--re-brand)",
                                        padding: "7px 18px",
                                        borderRadius: "6px",
                                        textDecoration: "none",
                                        transition: "all 0.2s",
                                        boxShadow: "0 2px 8px var(--re-brand-muted)",
                                    }}
                                    onMouseEnter={(e) => { (e.target as HTMLElement).style.transform = "translateY(-1px)"; (e.target as HTMLElement).style.boxShadow = "0 4px 16px var(--re-brand-muted)"; }}
                                    onMouseLeave={(e) => { (e.target as HTMLElement).style.transform = "translateY(0)"; (e.target as HTMLElement).style.boxShadow = "0 2px 8px var(--re-brand-muted)"; }}
                                >
                                    Start Your Workspace →
                                </Link>
                            </>
                        )}
                    </div>

                    {/* ═══ Mobile Hamburger ═══ */}
                    <button
                        className="marketing-mobile-toggle"
                        onClick={() => setMobileOpen(!mobileOpen)}
                        aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
                        aria-expanded={mobileOpen}
                        style={{
                            background: "transparent",
                            border: "1px solid var(--re-mobile-toggle-border)",
                            borderRadius: "8px",
                            cursor: "pointer",
                            color: "var(--re-text-primary)",
                            width: "44px",
                            height: "44px",
                            display: "none",
                            alignItems: "center",
                            justifyContent: "center",
                            padding: 0,
                            WebkitTapHighlightColor: "transparent",
                            transition: "border-color 0.2s, background 0.2s",
                        }}
                    >
                        {/* Animated hamburger → X */}
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                            <line
                                x1="3" y1={mobileOpen ? "10" : "5"} x2="17" y2={mobileOpen ? "10" : "5"}
                                style={{
                                    transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                                    transform: mobileOpen ? "rotate(45deg)" : "rotate(0)",
                                    transformOrigin: "center",
                                }}
                            />
                            <line
                                x1="3" y1="10" x2="17" y2="10"
                                style={{
                                    transition: "opacity 0.2s",
                                    opacity: mobileOpen ? 0 : 1,
                                }}
                            />
                            <line
                                x1="3" y1={mobileOpen ? "10" : "15"} x2="17" y2={mobileOpen ? "10" : "15"}
                                style={{
                                    transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                                    transform: mobileOpen ? "rotate(-45deg)" : "rotate(0)",
                                    transformOrigin: "center",
                                }}
                            />
                        </svg>
                    </button>
                </div>
            </nav>

            {/* ═══ Mobile Drawer Overlay ═══ */}
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

            {/* ═══ Mobile Drawer Panel ═══ */}
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
                        <span aria-hidden="true" style={{ fontSize: "18px", width: "24px", textAlign: "center" }}>🧰</span>
                        <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--re-brand)" }}>View All Tools →</div>
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
                <div style={{
                    padding: "16px 20px",
                    borderTop: "1px solid var(--re-mobile-border)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "10px",
                    paddingBottom: "calc(16px + env(safe-area-inset-bottom, 0px))",
                }}>
                    {showLoggedIn ? (
                        <>
                            <div style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "12px",
                                padding: "0 0 12px",
                                borderBottom: "1px solid var(--re-mobile-border)",
                                marginBottom: "12px",
                            }}>
                                <div style={{
                                    width: "36px",
                                    height: "36px",
                                    borderRadius: "50%",
                                    background: "var(--re-brand)",
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    fontSize: "14px",
                                    fontWeight: 700,
                                    color: "#fff",
                                    textTransform: "uppercase",
                                    flexShrink: 0,
                                }}>
                                    {(user.email?.[0] || "U")}
                                </div>
                                <div style={{ minWidth: 0 }}>
                                    <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--re-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                        {user.email || "Account"}
                                    </div>
                                    <div style={{ fontSize: "11px", color: "var(--re-text-muted)" }}>Logged in</div>
                                </div>
                            </div>
                            <Link
                                href="/dashboard"
                                onClick={() => setMobileOpen(false)}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    gap: "8px",
                                    background: "var(--re-brand)",
                                    color: "#fff",
                                    fontWeight: 600,
                                    fontSize: "15px",
                                    padding: "14px 24px",
                                    borderRadius: "10px",
                                    textDecoration: "none",
                                    minHeight: "48px",
                                    WebkitTapHighlightColor: "transparent",
                                    transition: "all 0.2s",
                                }}
                            >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                    <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
                                </svg>
                                Go to Dashboard
                            </Link>
                        </>
                    ) : (
                        <>
                            <Link
                                href="/onboarding"
                                onClick={() => setMobileOpen(false)}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    background: "var(--re-brand)",
                                    color: "#fff",
                                    fontWeight: 600,
                                    fontSize: "15px",
                                    padding: "14px 24px",
                                    borderRadius: "10px",
                                    textDecoration: "none",
                                    boxShadow: "0 2px 12px var(--re-brand-muted)",
                                    minHeight: "48px",
                                    WebkitTapHighlightColor: "transparent",
                                    transition: "all 0.2s",
                                }}
                            >
                                Start Your Workspace →
                            </Link>
                            <Link
                                href="/login"
                                onClick={() => setMobileOpen(false)}
                                style={{
                                    display: "flex",
                                    alignItems: "center",
                                    justifyContent: "center",
                                    border: "1px solid var(--re-mobile-border)",
                                    color: "var(--re-text-primary)",
                                    fontWeight: 500,
                                    fontSize: "15px",
                                    padding: "14px 24px",
                                    borderRadius: "10px",
                                    textDecoration: "none",
                                    background: "transparent",
                                    minHeight: "48px",
                                    WebkitTapHighlightColor: "transparent",
                                    transition: "all 0.2s",
                                }}
                            >
                                Log In
                            </Link>
                        </>
                    )}
                </div>
            </div>

            {/* ═══ Responsive CSS ═══ */}
            <style jsx>{`
                @media (max-width: 768px) {
                    .marketing-desktop-nav {
                        display: none !important;
                    }
                    .marketing-mobile-toggle {
                        display: flex !important;
                    }
                }
            `}</style>
        </>
    );
}
