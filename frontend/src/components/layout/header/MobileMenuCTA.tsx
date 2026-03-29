'use client';

import Link from 'next/link';
import type { User } from '@/types/api';

interface MobileMenuCTAProps {
    user: User | null;
    showLoggedIn: boolean;
    setMobileOpen: (open: boolean) => void;
}

export function MobileMenuCTA({ user, showLoggedIn, setMobileOpen }: MobileMenuCTAProps) {
    return (
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
                            {(user?.email?.[0] || "U")}
                        </div>
                        <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: "14px", fontWeight: 600, color: "var(--re-text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {user?.email || "Account"}
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
                        href="/retailer-readiness"
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
                        Start Your Workspace &rarr;
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
    );
}
