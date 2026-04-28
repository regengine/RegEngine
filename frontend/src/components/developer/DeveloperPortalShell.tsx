'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import {
    LayoutDashboard, Key, BarChart3, BookOpen, LogOut,
    ShieldCheck, Terminal, Code2, Webhook, Package,
    AlertCircle, ChevronDown, ChevronRight, Zap,
    FileText, ExternalLink,
} from 'lucide-react';

const NAV_SECTIONS = [
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
            { label: 'Quickstart', href: '/docs', icon: Zap },
            { label: 'API Reference', href: '/docs/api', icon: BookOpen },
            { label: 'Authentication', href: '/docs/authentication', icon: ShieldCheck },
            { label: 'Error Codes', href: '/docs/errors', icon: AlertCircle },
            { label: 'Webhooks', href: '/docs/webhooks', icon: Webhook },
            { label: 'SDKs & Libraries', href: '/docs/sdks', icon: Package },
            { label: 'Changelog', href: '/docs/changelog', icon: FileText },
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

    function handleLogout() {
        logout();
        router.push('/login');
        router.refresh();
    }

    function toggleSection(label: string) {
        setCollapsed(prev => ({ ...prev, [label]: !prev[label] }));
    }

    function isActive(href: string) {
        if (href === '/developer/portal') return pathname === href;
        return pathname === href || pathname.startsWith(href + '/');
    }

    return (
        <div className="min-h-screen flex bg-[var(--re-surface-base)]">
            <aside className="w-60 flex-shrink-0 flex flex-col border-r border-white/[0.06] bg-black/[0.15]">
                <Link href="/developer/portal" className="p-4 flex items-center gap-2.5 no-underline border-b border-white/[0.06]">
                    <div className="w-7 h-7 rounded-md flex items-center justify-center bg-gradient-to-br from-[rgba(16,185,129,0.3)] to-[rgba(6,182,212,0.2)]">
                        <ShieldCheck className="w-4 h-4 text-[var(--re-brand)]" />
                    </div>
                    <div>
                        <span className="font-semibold text-sm block text-[var(--re-text-primary)]">RegEngine</span>
                        <span className="text-[10px] font-medium text-[var(--re-text-disabled)]">Developer Portal</span>
                    </div>
                </Link>

                <nav className="flex-1 overflow-y-auto py-3 px-2">
                    {NAV_SECTIONS.map((section) => {
                        const isCollapsed = collapsed[section.label];
                        return (
                            <div key={section.label} className="mb-1">
                                <button
                                    onClick={() => toggleSection(section.label)}
                                    className="w-full flex items-center justify-between px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider rounded"
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
                                                    className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-all no-underline"
                                                    style={{
                                                        color: active ? 'var(--re-text-primary)' : 'var(--re-text-muted)',
                                                        background: active ? 'rgba(16,185,129,0.1)' : 'transparent',
                                                        fontWeight: active ? 500 : 400,
                                                    }}
                                                >
                                                    <item.icon className="w-3.5 h-3.5 flex-shrink-0" style={{
                                                        color: active ? 'var(--re-brand)' : 'var(--re-text-disabled)',
                                                    }} />
                                                    {item.label}
                                                    {active && <div className="ml-auto w-1 h-1 rounded-full" style={{ background: 'var(--re-brand)' }} />}
                                                </Link>
                                            );
                                        })}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </nav>

                <div className="p-2 space-y-0.5 border-t border-white/[0.06]">
                    <a
                        href="https://status.regengine.co"
                        target="_blank"
                        rel="noopener"
                        className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] no-underline transition-colors"
                        style={{ color: 'var(--re-text-disabled)' }}
                    >
                        <div className="w-1.5 h-1.5 rounded-full bg-re-success" />
                        API Status
                        <ExternalLink className="w-3 h-3 ml-auto" />
                    </a>
                    <button
                        onClick={handleLogout}
                        className="flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] w-full transition-colors hover:bg-re-danger-muted0/10 no-underline"
                        style={{ color: 'var(--re-text-disabled)' }}
                    >
                        <LogOut className="w-3.5 h-3.5" />
                        Sign Out
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
