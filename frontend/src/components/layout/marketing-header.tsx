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
                className="sticky top-0 z-50 backdrop-blur-[16px]"
                style={{
                    borderBottom: "1px solid var(--re-nav-border)",
                    WebkitBackdropFilter: "blur(16px)",
                    background: "var(--re-nav-bg)",
                }}
            >
                <div className="max-w-[1120px] mx-auto px-[clamp(16px,4vw,24px)] h-14 flex items-center justify-between">

                    <Link href="/" className="flex items-center gap-2.5 no-underline mr-6 shrink-0">
                        <RegEngineWordmark size="md" />
                    </Link>

                    {/* ═══ Desktop Nav ═══ */}
                    <div className="marketing-desktop-nav flex items-center gap-7">
                        {(user ? [
                            { label: 'Dashboard', href: '/dashboard' },
                            { label: 'Compliance', href: '/dashboard/compliance' },
                            { label: 'Suppliers', href: '/dashboard/suppliers' },
                            { label: 'Products', href: '/dashboard/products' },
                        ] : MARKETING_PRIMARY_NAV).map((item) => (
                            <Link
                                key={item.label}
                                href={item.href}
                                className="text-[13px] text-[var(--re-text-muted)] no-underline font-medium transition-colors duration-200 py-2 hover:text-[var(--re-text-primary)]"
                            >
                                {item.label}
                            </Link>
                        ))}

                        {/* Free Tools Dropdown */}
                        <div
                            ref={toolsWrapperRef}
                            className="relative"
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
                                className="text-[13px] font-semibold text-[var(--re-surface-base)] bg-[var(--re-brand)] px-4 py-[7px] rounded-md no-underline transition-all duration-200 cursor-pointer inline-block border-none"
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
                                    <div className="h-px bg-[var(--re-nav-divider)] mx-3 my-1.5" />
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
                            className="text-[13px] font-medium text-[var(--re-text-muted)] no-underline transition-colors duration-200 py-2 hover:text-[var(--re-text-primary)]"
                        >
                            Developers
                        </Link>
                        <Link
                            href="/docs"
                            className="text-[13px] font-medium text-[var(--re-text-muted)] no-underline transition-colors duration-200 py-2 hover:text-[var(--re-text-primary)]"
                        >
                            Docs
                        </Link>

                        <ThemeToggle />

                        {/* Auth-aware buttons */}
                        {showLoggedIn ? (
                            <div className="flex items-center gap-3">
                                <Link
                                    href="/dashboard"
                                    className="text-[13px] font-semibold text-[var(--re-surface-base)] bg-[var(--re-brand)] px-[18px] py-[7px] rounded-md no-underline transition-all duration-200 shadow-[0_2px_8px_var(--re-brand-muted)] inline-flex items-center gap-1.5"
                                >
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                        <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="3" y="14" width="7" height="7" /><rect x="14" y="14" width="7" height="7" />
                                    </svg>
                                    Dashboard
                                </Link>
                                <div
                                    className="w-8 h-8 rounded-full bg-[var(--re-brand)] flex items-center justify-center text-xs font-bold text-[var(--re-surface-base)] cursor-pointer uppercase"
                                    title={user.email || "Account"}
                                >
                                    {(user.email?.[0] || "U")}
                                </div>
                            </div>
                        ) : (
                            <>
                                <Link
                                    href="/login"
                                    className="text-[13px] font-medium text-[var(--re-text-muted)] no-underline transition-colors duration-200 py-2 hover:text-[var(--re-text-primary)]"
                                >
                                    Log In
                                </Link>
                                <Link
                                    href="/retailer-readiness"
                                    className="text-[13px] font-semibold text-white bg-[var(--re-brand)] px-[18px] py-[7px] rounded-md no-underline transition-all duration-200 shadow-[0_2px_8px_var(--re-brand-muted)] hover:-translate-y-px hover:shadow-[0_4px_16px_var(--re-brand-muted)]"
                                >
                                    Free Assessment →
                                </Link>
                            </>
                        )}
                    </div>

                    {/* ═══ Mobile Hamburger ═══ */}
                    <button
                        className="marketing-mobile-toggle hidden items-center justify-center w-11 h-11 bg-transparent border border-[var(--re-mobile-toggle-border)] rounded-lg cursor-pointer text-[var(--re-text-primary)] p-0 transition-[border-color,background] duration-200"
                        onClick={() => setMobileOpen(!mobileOpen)}
                        aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
                        aria-expanded={mobileOpen}
                        style={{ WebkitTapHighlightColor: "transparent" }}
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
                className="fixed inset-0 z-[49] bg-black/50 backdrop-blur-[4px] transition-opacity duration-300"
                style={{
                    WebkitBackdropFilter: "blur(4px)",
                    opacity: mobileOpen ? 1 : 0,
                    pointerEvents: mobileOpen ? "auto" : "none",
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
                <div className="flex items-center justify-between px-5 py-4 min-h-14 border-b border-[var(--re-mobile-border)]">

                    <RegEngineWordmark size="sm" />
                    <button
                        onClick={() => setMobileOpen(false)}
                        aria-label="Close menu"
                        className="bg-transparent border-none text-[var(--re-text-muted)] w-11 h-11 flex items-center justify-center cursor-pointer rounded-lg p-0"
                        style={{ WebkitTapHighlightColor: "transparent" }}
                    >
                        <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                            <line x1="4" y1="4" x2="16" y2="16" />
                            <line x1="16" y1="4" x2="4" y2="16" />
                        </svg>
                    </button>
                </div>

                {/* Primary Nav Links */}
                <div className="px-3 py-2">
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
                            className="flex items-center text-[15px] no-underline px-3 py-3.5 rounded-[10px] transition-[background] duration-150 min-h-12"
                            style={{
                                color: pathname === item.href ? "var(--re-brand)" : "var(--re-text-primary)",
                                fontWeight: pathname === item.href ? 600 : 500,
                                WebkitTapHighlightColor: "transparent",
                            }}
                        >
                            {item.label}
                        </Link>
                    ))}
                </div>

                {/* Divider */}
                <div className="h-px bg-[var(--re-mobile-border)] mx-5 my-1" />

                {/* Free Tools Section */}
                <div className="px-3 py-2">
                    <div className="text-[10px] font-semibold tracking-[0.12em] uppercase text-[var(--re-text-muted)] px-3 pt-2 pb-1">

                        FSMA 204 Compliance Tools
                    </div>
                    {MARKETING_FREE_TOOLS.map((tool) => (
                        <Link
                            key={tool.href}
                            href={tool.href}
                            onClick={() => setMobileOpen(false)}
                            className="flex items-center gap-3 p-3 no-underline rounded-[10px] transition-[background] duration-150 min-h-12"
                            style={{ WebkitTapHighlightColor: "transparent" }}
                        >
                            <span aria-hidden="true" className="text-lg w-6 text-center">{tool.emoji}</span>
                            <div>
                                <div className="text-sm font-medium text-[var(--re-text-primary)]">{tool.label}</div>
                                <div className="text-xs text-[var(--re-text-muted)] leading-snug">{tool.desc}</div>
                            </div>
                        </Link>
                    ))}
                    <Link
                        href="/tools"
                        onClick={() => setMobileOpen(false)}
                        className="flex items-center gap-3 p-3 no-underline rounded-[10px] min-h-12"
                        style={{ WebkitTapHighlightColor: "transparent" }}
                    >
                        <span aria-hidden="true" className="text-lg w-6 text-center">🧰</span>
                        <div className="text-sm font-semibold text-[var(--re-brand)]">View All Tools →</div>
                    </Link>
                </div>

                {/* Divider */}
                <div className="h-px bg-[var(--re-mobile-border)] mx-5 my-1" />

                {/* Theme Toggle */}
                <div className="px-6 py-3 flex items-center justify-between">
                    <span className="text-[13px] text-[var(--re-text-muted)] font-medium">Theme</span>
                    <ThemeToggle />
                </div>

                {/* Spacer */}
                <div className="flex-1" />

                {/* CTA Buttons at bottom */}
                <div className="px-5 pt-4 border-t border-[var(--re-mobile-border)] flex flex-col gap-2.5" style={{ paddingBottom: "calc(16px + env(safe-area-inset-bottom, 0px))" }}>

                    {showLoggedIn ? (
                        <>
                            <div className="flex items-center gap-3 pb-3 border-b border-[var(--re-mobile-border)] mb-3">
                                <div className="w-9 h-9 rounded-full bg-[var(--re-brand)] flex items-center justify-center text-sm font-bold text-white uppercase shrink-0">

                                    {(user.email?.[0] || "U")}
                                </div>
                                <div className="min-w-0">
                                    <div className="text-sm font-semibold text-[var(--re-text-primary)] overflow-hidden text-ellipsis whitespace-nowrap">
                                        {user.email || "Account"}
                                    </div>
                                    <div className="text-[11px] text-[var(--re-text-muted)]">Logged in</div>
                                </div>
                            </div>
                            <Link
                                href="/dashboard"
                                onClick={() => setMobileOpen(false)}
                                className="flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white font-semibold text-[15px] px-6 py-3.5 rounded-[10px] no-underline min-h-12 transition-all duration-200"
                                style={{ WebkitTapHighlightColor: "transparent" }}
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
                                href="/retailer-readiness"
                                onClick={() => setMobileOpen(false)}
                                className="flex items-center justify-center bg-[var(--re-brand)] text-white font-semibold text-[15px] px-6 py-3.5 rounded-[10px] no-underline shadow-[0_2px_12px_var(--re-brand-muted)] min-h-12 transition-all duration-200"
                                style={{ WebkitTapHighlightColor: "transparent" }}
                            >
                                Start Your Workspace →
                            </Link>
                            <Link
                                href="/login"
                                onClick={() => setMobileOpen(false)}
                                className="flex items-center justify-center border border-[var(--re-mobile-border)] text-[var(--re-text-primary)] font-medium text-[15px] px-6 py-3.5 rounded-[10px] no-underline bg-transparent min-h-12 transition-all duration-200"
                                style={{ WebkitTapHighlightColor: "transparent" }}
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
