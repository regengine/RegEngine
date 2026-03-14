'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { DashboardBreadcrumb } from '@/components/dashboard/breadcrumb';
import {
    BarChart3,
    Archive,
    Bell,
    FileText,
    Users,
    Package,
    ScrollText,
    ShieldCheck,
    Link2,
    Settings,
    UserCog,
    Activity,
    ChevronRight,
} from 'lucide-react';

const NAV_ITEMS = [
    { label: 'Compliance', href: '/dashboard/compliance', icon: BarChart3 },
    { label: 'Alerts', href: '/dashboard/alerts', icon: Bell },
    { label: 'Recall Report', href: '/dashboard/recall-report', icon: ShieldCheck },
    { label: 'Recall Drills', href: '/dashboard/recall-drills', icon: ShieldCheck },
    { label: 'Export Jobs', href: '/dashboard/export-jobs', icon: Archive },
    { label: 'Integrations', href: '/dashboard/integrations', icon: Link2 },
    { label: 'Suppliers', href: '/dashboard/suppliers', icon: Users },
    { label: 'Products', href: '/dashboard/products', icon: Package },
    { label: 'Audit Log', href: '/dashboard/audit-log', icon: ScrollText },
    { label: 'Notifications', href: '/dashboard/notifications', icon: Settings },
    { label: 'Team', href: '/dashboard/team', icon: UserCog },
    { label: 'Settings', href: '/dashboard/settings', icon: Settings },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();

    return (
        <div className="flex min-h-screen">
            {/* Sidebar */}
            <aside aria-label="Dashboard sidebar" className="hidden md:flex flex-col w-60 border-r border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                <div className="p-4 border-b border-[var(--re-border-default)]">
                    <Link href="/dashboard" className="flex items-center gap-2">
                        <Activity className="h-5 w-5 text-[var(--re-brand)]" />
                        <span className="font-bold text-sm">Command Center</span>
                    </Link>
                    <Link
                        href="/"
                        className="text-[11px] text-[var(--re-text-disabled)] hover:text-[var(--re-text-muted)] transition-colors"
                    >
                        regengine.co
                    </Link>
                </div>
                <nav aria-label="Dashboard navigation" className="flex-1 p-3 space-y-0.5 overflow-y-auto">
                    {NAV_ITEMS.map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all ${isActive
                                        ? 'bg-[color-mix(in_srgb,var(--re-brand)_12%,transparent)] text-[var(--re-brand)] font-medium'
                                        : 'text-muted-foreground hover:bg-[var(--re-surface-elevated)] hover:text-foreground'
                                    }`}
                            >
                                <Icon className="h-4 w-4 flex-shrink-0" />
                                <span className="flex-1">{item.label}</span>
                                {isActive && <ChevronRight className="h-3 w-3" />}
                            </Link>
                        );
                    })}
                </nav>
                <div className="p-3 border-t border-[var(--re-border-default)]">
                    <div className="px-3 py-2 rounded-lg bg-[color-mix(in_srgb,var(--re-brand)_5%,transparent)] border border-[color-mix(in_srgb,var(--re-brand)_15%,transparent)]">
                        <div className="text-[10px] text-muted-foreground">Plan</div>
                        <div className="text-xs font-medium">Growth</div>
                        <div className="text-[10px] text-muted-foreground mt-0.5">5 facilities · 50K events/mo</div>
                    </div>
                    <Link
                        href="/onboarding"
                        className="block mt-2 text-[11px] text-center text-[var(--re-text-disabled)] hover:text-[var(--re-text-muted)]"
                    >
                        Re-run onboarding
                    </Link>
                </div>
            </aside>

            {/* Mobile top nav */}
            <div className="md:hidden fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur border-b border-[var(--re-border-default)]">
                <nav aria-label="Dashboard quick navigation" className="flex items-center gap-2 px-4 py-2 overflow-x-auto no-scrollbar">
                    {NAV_ITEMS.slice(0, 6).map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap border transition-all ${isActive
                                        ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                        : 'border-[var(--re-border-default)]'
                                    }`}
                            >
                                <Icon className="h-3 w-3" />
                                {item.label}
                            </Link>
                        );
                    })}
                </nav>
            </div>

            {/* Main content */}
            <main className="flex-1 md:pt-0 pt-14 overflow-y-auto">
                <DashboardBreadcrumb />
                {children}
            </main>
        </div>
    );
}
