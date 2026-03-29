'use client';

import Link from 'next/link';
import { MARKETING_PRIMARY_NAV } from '@/components/layout/marketing-nav';
import { ThemeToggle } from '@/components/layout/theme-toggle';
import { NavDropdown } from './NavDropdown';
import type { DesktopNavProps } from './types';

export function DesktopNav({
    user,
    showLoggedIn,
    toolsOpen,
    setToolsOpen,
    toolsWrapperRef,
    toolsButtonRef,
    handleToolsEnter,
    handleToolsLeave,
    handleToolsKeyDown,
    focusFirstToolsItem,
}: DesktopNavProps) {
    const navLinkStyle: React.CSSProperties = {
        fontSize: "13px",
        color: "var(--re-text-muted)",
        textDecoration: "none",
        fontWeight: 500,
        transition: "color 0.2s",
        padding: "8px 0",
    };

    const handleLinkEnter = (e: React.MouseEvent) =>
        ((e.target as HTMLElement).style.color = "var(--re-text-primary)");
    const handleLinkLeave = (e: React.MouseEvent) =>
        ((e.target as HTMLElement).style.color = "var(--re-text-muted)");

    return (
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
                    style={navLinkStyle}
                    onMouseEnter={handleLinkEnter}
                    onMouseLeave={handleLinkLeave}
                >
                    {item.label}
                </Link>
            ))}

            <NavDropdown
                toolsOpen={toolsOpen}
                setToolsOpen={setToolsOpen}
                toolsWrapperRef={toolsWrapperRef}
                toolsButtonRef={toolsButtonRef}
                handleToolsEnter={handleToolsEnter}
                handleToolsLeave={handleToolsLeave}
                handleToolsKeyDown={handleToolsKeyDown}
                focusFirstToolsItem={focusFirstToolsItem}
            />

            {/* Developer & Docs links */}
            <Link
                href="/developer/portal"
                style={navLinkStyle}
                onMouseEnter={handleLinkEnter}
                onMouseLeave={handleLinkLeave}
            >
                Developers
            </Link>
            <Link
                href="/docs"
                style={navLinkStyle}
                onMouseEnter={handleLinkEnter}
                onMouseLeave={handleLinkLeave}
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
                        title={user?.email || "Account"}
                    >
                        {(user?.email?.[0] || "U")}
                    </div>
                </div>
            ) : (
                <>
                    <Link
                        href="/login"
                        style={navLinkStyle}
                        onMouseEnter={handleLinkEnter}
                        onMouseLeave={handleLinkLeave}
                    >
                        Log In
                    </Link>
                    <Link
                        href="/retailer-readiness"
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
                        Free Assessment &rarr;
                    </Link>
                </>
            )}
        </div>
    );
}
