'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import {
    LayoutDashboard, Key, BarChart3, BookOpen, LogOut,
    ShieldCheck, Terminal, Code2, Webhook, Package,
    AlertCircle, ChevronDown, ChevronRight, Zap,
    FileText, ArrowLeft, ArrowUpRight,
} from 'lucide-react';

interface PortalNavItem {
    label: string;
    href: string;
    icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
    /** Leaves the portal shell for the shared public docs chrome. */
    external?: boolean;
}

const NAV_SECTIONS: { label: string; items: PortalNavItem[] }[] = [
    {
        label: 'Overview',
        items: [
            { label: 'Dashboard', href: '/developer/portal', icon: LayoutDashboard },
            { label: 'API Keys', href: '/developer/portal/keys', icon: Key },
            { label: 'Usage & Logs', href: '/developer/portal/usage', icon: BarChart3 },
        ],
    },
    {
        label: 'Documentation',
        items: [
            { label: 'Quickstart', href: '/docs', icon: Zap, external: true },
            { label: 'API Reference', href: '/docs/api', icon: BookOpen, external: true },
            { label: 'Authentication', href: '/docs/authentication', icon: ShieldCheck, external: true },
            { label: 'Error Codes', href: '/docs/errors', icon: AlertCircle, external: true },
            { label: 'Webhooks', href: '/docs/webhooks', icon: Webhook, external: true },
            { label: 'SDKs & Libraries', href: '/docs/sdks', icon: Package, external: true },
            { label: 'Changelog', href: '/docs/changelog', icon: FileText, external: true },
        ],
    },
    {
        label: 'Tools',
        items: [
            { label: 'API Playground', href: '/developer/portal/playground', icon: Terminal },
            { label: 'Code Generator', href: '/developer/portal/codegen', icon: Code2 },
        ],
    },
];

export function DeveloperPortalShell({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { logout } = useAuth();
    const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
    const [isLoggingOut, setIsLoggingOut] = useState(false);

    async function handleLogout() {
        if (isLoggingOut) return;
        setIsLoggingOut(true);
        try {
            await logout();
            router.replace('/login');
            router.refresh();
        } finally {
            setIsLoggingOut(false);
        }
    }

    function toggleSection(label: string) {
        setCollapsed(prev => ({ ...prev, [label]: !prev[label] }));
    }

    function isActive(href: string) {
        if (href === '/developer/portal') return pathname === href;
        return pathname === href || pathname.startsWith(href + '/');
    }

    return (
        <div className="re-devportal min-h-screen flex">
            <aside className="w-60 flex-shrink-0 flex flex-col border-r border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
                {/* Badge sits OUTSIDE the logo link so the link's accessible
                    name stays "RegEngine developer portal" — the badge is a
                    status indicator, not link text. */}
                <div className="p-4 flex items-center gap-2.5 border-b border-[var(--re-border-subtle)]">
                    <Link href="/developer/portal" className="flex-1 min-w-0 flex items-center gap-2.5 no-underline">
                        <div className="w-7 h-7 rounded-md flex items-center justify-center border border-[var(--re-surface-border)] bg-[var(--re-brand-muted)]">
                            <Terminal className="w-4 h-4 text-[var(--re-brand-light)]" />
                        </div>
                        <div className="min-w-0">
                            <span className="font-semibold text-sm block text-[var(--re-text-primary)]">RegEngine</span>
                            <span className="font-mono text-[10px] tracking-wide text-[var(--re-brand-light)]">developer portal</span>
                        </div>
                    </Link>
                    <span
                        className="font-mono text-[10px] font-semibold tracking-widest px-1.5 py-0.5 rounded border"
                        style={{ color: 'var(--re-warning)', borderColor: 'var(--re-warning-border)', background: 'var(--re-warning-bg)' }}
                    >
                        SANDBOX
                    </span>
                </div>

                <nav className="flex-1 overflow-y-auto py-3 px-2">
                    {NAV_SECTIONS.map((section) => {
                        const isCollapsed = collapsed[section.label];
                        return (
                            <div key={section.label} className="mb-1">
                                <button
                                    type="button"
                                    onClick={() => toggleSection(section.label)}
                                    aria-expanded={!isCollapsed}
                                    className="w-full flex items-center justify-between px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-widest rounded-md"
                                    style={{ color: 'var(--re-text-disabled)' }}
                                >
                                    {section.label}
                                    {isCollapsed
                                        ? <ChevronRight className="w-3 h-3" />
                                        : <ChevronDown className="w-3 h-3" />
                                    }
                                </button>
                                {!isCollapsed && (
                                    <div className="mt-0.5 space-y-0.5">
                                        {section.items.map((item) => {
                                            const active = isActive(item.href);
                                            return (
                                                <Link
                                                    key={item.href}
                                                    href={item.href}
                                                    aria-current={active ? 'page' : undefined}
                                                    className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-all no-underline"
                                                    style={{
                                                        color: active ? 'var(--re-brand-light)' : 'var(--re-text-muted)',
                                                        background: active ? 'var(--re-brand-muted)' : 'transparent',
                                                        boxShadow: active ? 'inset 2px 0 0 var(--re-brand)' : 'none',
                                                        fontWeight: active ? 600 : 400,
                                                    }}
                                                >
                                                    <item.icon className="w-3.5 h-3.5 flex-shrink-0" style={{
                                                        color: active ? 'var(--re-brand-light)' : 'var(--re-text-disabled)',
                                                    }} />
                                                    {item.label}
                                                    {item.external && (
                                                        <>
                                                            {/* Same-tab navigation out of the portal chrome — say so for AT users */}
                                                            <span className="sr-only">(opens documentation)</span>
                                                            <ArrowUpRight className="w-3 h-3 ml-auto flex-shrink-0" style={{ color: 'var(--re-text-disabled)' }} />
                                                        </>
                                                    )}
                                                </Link>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </nav>

                <div className="p-2 space-y-0.5 border-t border-[var(--re-border-subtle)]">
                    <div
                        className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px]"
                        style={{ color: 'var(--re-text-disabled)' }}
                    >
                        <div className="w-1.5 h-1.5 rounded-full bg-re-success" />
                        Service updates available through support
                    </div>
                    <Link
                        href="/dashboard"
                        className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] w-full transition-colors hover:bg-[var(--re-brand-muted)] no-underline"
                        style={{ color: 'var(--re-text-muted)' }}
                    >
                        <ArrowLeft className="w-3.5 h-3.5" />
                        Back to console
                    </Link>
                    <button
                        type="button"
                        onClick={handleLogout}
                        disabled={isLoggingOut}
                        className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] w-full transition-colors hover:bg-re-danger/10 disabled:opacity-60 no-underline"
                        style={{ color: 'var(--re-text-disabled)' }}
                    >
                        <LogOut className="w-3.5 h-3.5" />
                        {isLoggingOut ? 'Signing out…' : 'Sign Out'}
                    </button>
                </div>
            </aside>

            <main className="flex-1 overflow-auto">
                <div className="max-w-5xl mx-auto px-8 py-8">
                    {children}
                </div>
            </main>
        </div>
    );
}
