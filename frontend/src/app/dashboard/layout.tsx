'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { DashboardBreadcrumb } from '@/components/dashboard/breadcrumb';
import { useAuth } from '@/lib/auth-context';
import {
    BarChart3,
    Archive,
    Bell,
    FileText,
    Users,
    Package,
    Scan,
    Truck,
    FileSpreadsheet,
    ScrollText,
    ShieldCheck,
    Link2,
    Settings,
    UserCog,
    Activity,
    ChevronRight,
    LogOut,
    Zap,
} from 'lucide-react';

interface NavItem {
    label: string;
    href: string;
    icon: React.ComponentType<{ className?: string }>;
}

interface NavSection {
    title?: string;
    items: NavItem[];
}

const NAV_SECTIONS: NavSection[] = [
    {
        title: 'Overview',
        items: [
            { label: 'Heartbeat', href: '/dashboard/heartbeat', icon: Activity },
            { label: 'Compliance', href: '/dashboard/compliance', icon: BarChart3 },
            { label: 'Alerts', href: '/dashboard/alerts', icon: Bell },
        ],
    },
    {
        title: 'Compliance',
        items: [
            { label: 'Recall Report', href: '/dashboard/recall-report', icon: ShieldCheck },
            { label: 'Recall Drills', href: '/dashboard/recall-drills', icon: Zap },
            { label: 'Export Jobs', href: '/dashboard/export-jobs', icon: Archive },
        ],
    },
    {
        title: 'Data',
        items: [
            { label: 'Data Import', href: '/tools/data-import', icon: FileSpreadsheet },
            { label: 'Field Capture', href: '/dashboard/scan', icon: Scan },
            { label: 'Receiving Dock', href: '/dashboard/receiving', icon: Truck },
            { label: 'Integrations', href: '/dashboard/integrations', icon: Link2 },
            { label: 'Suppliers', href: '/dashboard/suppliers', icon: Users },
            { label: 'Products', href: '/dashboard/products', icon: Package },
            { label: 'Audit Log', href: '/dashboard/audit-log', icon: ScrollText },
        ],
    },
    {
        title: 'Settings',
        items: [
            { label: 'Notifications', href: '/dashboard/notifications', icon: Bell },
            { label: 'Team', href: '/dashboard/team', icon: UserCog },
            { label: 'Settings', href: '/dashboard/settings', icon: Settings },
        ],
    },
];

const ALL_NAV_ITEMS = NAV_SECTIONS.flatMap(s => s.items);

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { clearCredentials, demoMode } = useAuth();

    return (
        <div className="flex flex-col min-h-screen">
            {/* MEDIUM #11: Demo mode visual indicator */}
            {demoMode && (
                <div className="bg-amber-500/90 text-black text-xs font-medium text-center py-1.5 px-4 flex items-center justify-center gap-2 z-50">
                    <span>⚠️ Demo Mode — Data shown is sample data.</span>
                    <Link href="/dashboard/settings" className="underline hover:no-underline">
                        Disable in Settings
                    </Link>
                </div>
            )}
            <div className="flex flex-1">
            {/* Sidebar */}
            <aside aria-label="Dashboard sidebar" className="hidden md:flex flex-col w-[232px] border-r border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] flex-shrink-0">
                {/* Brand */}
                <div className="p-4 border-b border-[var(--re-border-default)]">
                    <Link href="/dashboard" className="flex items-center gap-2.5 group">
                        <div className="w-7 h-7 rounded-lg bg-[var(--re-brand)] flex items-center justify-center">
                            <Activity className="h-4 w-4 text-white" />
                        </div>
                        <div>
                            <span className="font-bold text-sm block leading-tight">RegEngine</span>
                            <span className="text-[10px] text-[var(--re-text-disabled)] leading-tight">Command Center</span>
                        </div>
                    </Link>
                </div>

                {/* Nav sections */}
                {/* MEDIUM #12: Keyboard navigation — arrow keys traverse nav items */}
                <nav
                    aria-label="Dashboard navigation"
                    className="flex-1 py-3 overflow-y-auto"
                    role="navigation"
                    onKeyDown={(e) => {
                        if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) return;
                        e.preventDefault();
                        const links = Array.from(e.currentTarget.querySelectorAll<HTMLAnchorElement>('a[href]'));
                        const current = links.findIndex(l => l === document.activeElement);
                        let next = current;
                        if (e.key === 'ArrowDown') next = Math.min(current + 1, links.length - 1);
                        else if (e.key === 'ArrowUp') next = Math.max(current - 1, 0);
                        else if (e.key === 'Home') next = 0;
                        else if (e.key === 'End') next = links.length - 1;
                        links[next]?.focus();
                    }}
                >
                    {NAV_SECTIONS.map((section, si) => (
                        <div key={si} className={si > 0 ? 'mt-4' : ''}>
                            {section.title && (
                                <div className="px-5 mb-1.5">
                                    <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--re-text-disabled)]">
                                        {section.title}
                                    </span>
                                </div>
                            )}
                            <div className="px-2.5 space-y-0.5" role="list">
                                {section.items.map((item) => {
                                    const Icon = item.icon;
                                    const isActive = pathname === item.href;
                                    return (
                                        <Link
                                            key={item.href}
                                            href={item.href}
                                            role="listitem"
                                            aria-current={isActive ? 'page' : undefined}
                                            className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] transition-all min-h-[36px] ${isActive
                                                    ? 'bg-[var(--re-brand)]/10 text-[var(--re-brand)] font-medium shadow-[inset_2px_0_0_var(--re-brand)]'
                                                    : 'text-[var(--re-text-muted)] hover:bg-white/[0.03] hover:text-foreground'
                                                }`}
                                        >
                                            <Icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-[var(--re-brand)]' : ''}`} />
                                            <span className="flex-1">{item.label}</span>
                                            {isActive && <ChevronRight className="h-3 w-3 opacity-50" />}
                                        </Link>
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </nav>

                {/* Footer */}
                <div className="p-3 border-t border-[var(--re-border-default)]">
                    <Link href="/dashboard/settings" className="block px-3 py-2.5 rounded-xl bg-[var(--re-brand)]/5 border border-[var(--re-brand)]/10 hover:border-[var(--re-brand)]/30 transition-colors">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Plan</div>
                                <div className="text-xs font-semibold mt-0.5">Manage Plan</div>
                            </div>
                            <div className="w-6 h-6 rounded-md bg-[var(--re-brand)]/10 flex items-center justify-center">
                                <Zap className="h-3 w-3 text-[var(--re-brand)]" />
                            </div>
                        </div>
                        <div className="text-[10px] text-muted-foreground mt-1">View billing &amp; usage</div>
                    </Link>
                    <div className="flex items-center gap-2 mt-2">
                        <Link
                            href="/onboarding"
                            className="flex-1 text-[11px] text-center py-1.5 rounded-lg text-[var(--re-text-disabled)] hover:text-[var(--re-text-muted)] hover:bg-white/[0.03] transition-colors"
                        >
                            Onboarding
                        </Link>
                        <button
                            onClick={() => { clearCredentials(); router.push('/login'); }}
                            className="flex items-center justify-center gap-1 flex-1 py-1.5 rounded-lg text-[11px] text-[var(--re-text-disabled)] hover:text-destructive hover:bg-destructive/5 transition-colors"
                        >
                            <LogOut className="h-3 w-3" />
                            Sign Out
                        </button>
                    </div>
                </div>
            </aside>

            {/* Mobile top nav */}
            <div className="md:hidden fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-lg supports-[backdrop-filter]:bg-background/60 border-b border-[var(--re-border-default)]" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
                <nav aria-label="Dashboard quick navigation" className="flex items-center gap-1.5 px-3 py-1.5 overflow-x-auto no-scrollbar scrollbar-none">
                    {ALL_NAV_ITEMS.slice(0, 8).map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`flex items-center gap-1.5 px-3 min-h-[36px] rounded-full text-xs font-medium whitespace-nowrap border transition-all active:scale-[0.96] ${isActive
                                        ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)] shadow-[0_0_12px_rgba(16,185,129,0.3)]'
                                        : 'border-[var(--re-border-default)] text-[var(--re-text-muted)]'
                                    }`}
                            >
                                <Icon className="h-3.5 w-3.5" />
                                {item.label}
                            </Link>
                        );
                    })}
                </nav>
            </div>

            {/* Main content */}
            <main className="flex-1 md:pt-0 pt-[52px] overflow-y-auto">
                <DashboardBreadcrumb />
                {children}
            </main>
        </div>
        </div>
    );
}
