'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Container } from '@/components/layout/container';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { clsx } from 'clsx';
import type { LucideIcon } from 'lucide-react';
import {
    LayoutDashboard, Key, BarChart3, BookOpen, LogOut,
    ShieldCheck, Terminal, Code2, Webhook, Package,
    AlertCircle, ChevronDown, ChevronRight, Zap,
    FileText, ArrowLeft, ArrowUpRight,
} from 'lucide-react';

interface PortalNavItem {
    label: string;
    href: string;
    icon: LucideIcon;
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

/**
 * The one nav-item recipe — shared with the dashboard sidebar (SPEC §3.3):
 * 36px row, inset tint when active, 2px brand rail on the left edge.
 */
function navItemClass(active: boolean) {
    return clsx(
        'relative flex h-9 items-center gap-2.5 rounded-md px-3 text-ui no-underline transition-colors duration-120 motion-reduce:transition-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-1 focus-visible:ring-offset-re-ring-offset',
        active
            ? 'bg-re-surface-inset font-medium text-re-text-primary before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-re-brand before:content-[""]'
            : 'text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary',
    );
}

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
        <div className="re-devportal flex min-h-screen bg-re-surface-base text-re-text-primary">
            <aside className="flex w-[244px] flex-shrink-0 flex-col border-r border-re-border-subtle bg-re-surface-elevated">
                {/* Badge sits OUTSIDE the logo link so the link's accessible
                    name stays "RegEngine developer portal" — the badge is a
                    status indicator, not link text. */}
                <div className="flex items-center gap-2 border-b border-re-border-subtle px-4 py-3">
                    <Link
                        href="/developer/portal"
                        className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-md no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
                    >
                        <RegEngineWordmark size="sm" />
                        <span className="font-mono text-label text-re-text-muted">developer portal</span>
                    </Link>
                    <Badge tone="warning" size="sm" mono className="shrink-0 uppercase">
                        SANDBOX
                    </Badge>
                </div>

                <nav aria-label="Developer portal navigation" className="flex-1 overflow-y-auto px-2 py-3">
                    {NAV_SECTIONS.map((section) => {
                        const isCollapsed = collapsed[section.label];
                        return (
                            <div key={section.label} className="mb-1">
                                <button
                                    type="button"
                                    onClick={() => toggleSection(section.label)}
                                    aria-expanded={!isCollapsed}
                                    className="flex w-full items-center justify-between gap-1.5 rounded-md px-3 py-2 text-label uppercase text-re-text-muted transition-colors duration-120 hover:text-re-text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                                >
                                    {section.label}
                                    {isCollapsed
                                        ? <ChevronRight className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        : <ChevronDown className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden="true" />
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
                                                    className={navItemClass(active)}
                                                >
                                                    <item.icon
                                                        className="h-4 w-4 flex-shrink-0"
                                                        strokeWidth={1.75}
                                                        aria-hidden="true"
                                                    />
                                                    {item.label}
                                                    {item.external && (
                                                        <>
                                                            {/* Same-tab navigation out of the portal chrome — say so for AT users */}
                                                            <span className="sr-only">(opens documentation)</span>
                                                            <ArrowUpRight
                                                                className="ml-auto h-3 w-3 flex-shrink-0 text-re-text-muted"
                                                                strokeWidth={1.75}
                                                                aria-hidden="true"
                                                            />
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

                <div className="space-y-0.5 border-t border-re-border-subtle p-2">
                    <p className="px-3 py-1.5 text-small text-re-text-muted">
                        Service updates available through support
                    </p>
                    <Link href="/dashboard" className={navItemClass(false)}>
                        <ArrowLeft className="h-4 w-4 flex-shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        Back to console
                    </Link>
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={handleLogout}
                        disabled={isLoggingOut}
                        className="h-9 w-full justify-start px-3 font-normal"
                        leadingIcon={<LogOut className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />}
                    >
                        {isLoggingOut ? 'Signing out…' : 'Sign Out'}
                    </Button>
                </div>
            </aside>

            <div className="flex-1 overflow-auto">
                <Container width="docs" className="py-8">
                    {children}
                </Container>
            </div>
        </div>
    );
}
