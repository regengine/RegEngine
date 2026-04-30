'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { DashboardBreadcrumb } from '@/components/dashboard/breadcrumb';
import { DashboardErrorBoundary } from '@/components/dashboard/error-boundary';
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
    ChevronDown,
    LogOut,
    Zap,
    AlertTriangle,
    FileCheck,
    Scale,
    Fingerprint,
    ClipboardList,
    Eye,
    FlaskConical,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NavItem {
    label: string;
    href: string;
    icon: React.ComponentType<{ className?: string }>;
}

interface CollapsibleSection {
    key: string;
    title: string;
    items: NavItem[];
}

// ---------------------------------------------------------------------------
// Navigation data
// ---------------------------------------------------------------------------

/** Always-visible top-level items (max 5) */
const TOP_ITEMS: NavItem[] = [
    { label: 'Overview', href: '/dashboard', icon: Activity },
    { label: 'Compliance', href: '/dashboard/compliance', icon: BarChart3 },
    { label: 'Alerts', href: '/dashboard/alerts', icon: Bell },
    { label: 'Import Data', href: '/ingest', icon: FileSpreadsheet },
    { label: 'Export', href: '/dashboard/export-jobs', icon: Archive },
];

/** Collapsible sections (closed by default) */
const COLLAPSIBLE_SECTIONS: CollapsibleSection[] = [
    {
        key: 'data-inflow',
        title: 'Data Inflow',
        items: [
            { label: 'CSV/API Import', href: '/ingest', icon: FileSpreadsheet },
            { label: 'Inflow Lab', href: '/dashboard/inflow-lab', icon: FlaskConical },
        ],
    },
    {
        key: 'fda-response',
        title: 'FDA Response',
        items: [
            { label: 'FDA Export', href: '/dashboard/export-jobs', icon: Archive },
            { label: 'Recall Drills', href: '/dashboard/recall-drills', icon: Zap },
            { label: 'Recall Report', href: '/dashboard/recall-report', icon: ShieldCheck },
        ],
    },
    {
        key: 'supply-chain',
        title: 'Supply Chain',
        items: [
            { label: 'Suppliers', href: '/dashboard/suppliers', icon: Users },
            { label: 'Products', href: '/dashboard/products', icon: Package },
            { label: 'Receiving', href: '/dashboard/receiving', icon: Truck },
            { label: 'Scan', href: '/dashboard/scan', icon: Scan },
        ],
    },
    {
        key: 'control-plane',
        title: 'Control Plane',
        items: [
            { label: 'Rules', href: '/rules', icon: Scale },
            { label: 'Records', href: '/records', icon: FileCheck },
            { label: 'Exceptions', href: '/exceptions', icon: AlertTriangle },
            { label: 'Requests', href: '/requests', icon: ClipboardList },
            { label: 'Identity', href: '/identity', icon: Fingerprint },
            { label: 'Review', href: '/review', icon: Eye },
            { label: 'Audit', href: '/dashboard/audit-log', icon: ScrollText },
            { label: 'Readiness', href: '/fsma', icon: ShieldCheck },
            { label: 'Incidents', href: '/dashboard/issues', icon: AlertTriangle },
            { label: 'Controls', href: '/compliance/profile', icon: FileText },
        ],
    },
    {
        key: 'settings',
        title: 'Settings',
        items: [
            { label: 'Settings', href: '/dashboard/settings', icon: Settings },
            { label: 'Team', href: '/dashboard/team', icon: UserCog },
            { label: 'Notifications', href: '/dashboard/notifications', icon: Bell },
            { label: 'Integrations', href: '/dashboard/integrations', icon: Link2 },
            { label: 'Heartbeat', href: '/dashboard/heartbeat', icon: Activity },
            { label: 'Audit Log', href: '/dashboard/audit-log', icon: ScrollText },
        ],
    },
];

/** Mobile nav — the 5 always-visible items only */
const MOBILE_NAV_ITEMS = TOP_ITEMS;

// ---------------------------------------------------------------------------
// localStorage helpers for expansion state
// ---------------------------------------------------------------------------

const STORAGE_KEY = 're-nav-sections';

function loadExpandedSections(): Record<string, boolean> {
    if (typeof window === 'undefined') return {};
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : {};
    } catch {
        return {};
    }
}

function saveExpandedSections(state: Record<string, boolean>) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
        // silent – quota exceeded, private browsing, etc.
    }
}

// ---------------------------------------------------------------------------
// Determine which sections should auto-expand based on the current route
// ---------------------------------------------------------------------------

function sectionsWithActiveRoute(pathname: string): Set<string> {
    const active = new Set<string>();
    for (const section of COLLAPSIBLE_SECTIONS) {
        for (const item of section.items) {
            if (pathname === item.href || pathname.startsWith(item.href + '/')) {
                active.add(section.key);
            }
        }
    }
    return active;
}

// ---------------------------------------------------------------------------
// CollapsibleNavSection component
// ---------------------------------------------------------------------------

function CollapsibleNavSection({
    section,
    expanded,
    onToggle,
    pathname,
}: {
    section: CollapsibleSection;
    expanded: boolean;
    onToggle: () => void;
    pathname: string;
}) {
    const contentRef = React.useRef<HTMLDivElement>(null);
    const [height, setHeight] = React.useState<number | undefined>(undefined);

    // Measure content height for smooth animation
    React.useEffect(() => {
        if (contentRef.current) {
            setHeight(contentRef.current.scrollHeight);
        }
    }, [expanded, section.items.length]);

    return (
        <div className="mt-1">
            {/* Section header — clickable toggle */}
            <button
                type="button"
                onClick={onToggle}
                className="flex w-full items-center gap-1.5 px-5 py-1.5 group cursor-pointer select-none"
                aria-expanded={expanded}
            >
                {expanded ? (
                    <ChevronDown className="h-3 w-3 text-[var(--re-text-disabled)] transition-transform duration-200" />
                ) : (
                    <ChevronRight className="h-3 w-3 text-[var(--re-text-disabled)] transition-transform duration-200" />
                )}
                <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-[var(--re-text-muted)]">
                    {section.title}
                </span>
            </button>

            {/* Collapsible items */}
            <div
                className="overflow-hidden transition-all duration-200"
                style={{ maxHeight: expanded ? (height ?? 1000) : 0, opacity: expanded ? 1 : 0 }}
            >
                <div ref={contentRef} className="px-2.5 pl-5 space-y-0.5 pb-1" role="list">
                    {section.items.map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href + item.label}
                                href={item.href}
                                role="listitem"
                                tabIndex={expanded ? 0 : -1}
                                aria-current={isActive ? 'page' : undefined}
                                className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] transition-all min-h-[36px] ${
                                    isActive
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
        </div>
    );
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { clearCredentials, demoMode, isAuthenticated, isHydrated } = useAuth();

    // ------ Collapsible section state with localStorage persistence ------
    const [expandedSections, setExpandedSections] = React.useState<Record<string, boolean>>({});
    const initializedRef = React.useRef(false);

    // Hydrate from localStorage + auto-expand sections containing the active route
    React.useEffect(() => {
        if (!initializedRef.current) {
            const stored = loadExpandedSections();
            const active = sectionsWithActiveRoute(pathname);
            // Merge: stored state wins, but active sections always open
            const merged: Record<string, boolean> = { ...stored };
            active.forEach((key) => {
                merged[key] = true;
            });
            setExpandedSections(merged);
            initializedRef.current = true;
        } else {
            // On subsequent route changes, auto-expand sections with active items
            const active = sectionsWithActiveRoute(pathname);
            if (active.size > 0) {
                setExpandedSections((prev) => {
                    const next = { ...prev };
                    let changed = false;
                    active.forEach((key) => {
                        if (!next[key]) {
                            next[key] = true;
                            changed = true;
                        }
                    });
                    return changed ? next : prev;
                });
            }
        }
    }, [pathname]);

    // Persist to localStorage when expansion state changes
    React.useEffect(() => {
        if (initializedRef.current) {
            saveExpandedSections(expandedSections);
        }
    }, [expandedSections]);

    const toggleSection = React.useCallback((key: string) => {
        setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
    }, []);

    // ------ Route-level auth guard ------
    React.useEffect(() => {
        if (isHydrated && !isAuthenticated) {
            router.push(`/login?next=${encodeURIComponent(pathname)}`);
        }
    }, [isHydrated, isAuthenticated, router, pathname]);

    // Don't render dashboard chrome until auth is resolved
    if (!isHydrated || !isAuthenticated) {
        return null;
    }

    return (
        <div className="flex flex-col min-h-screen">
            {/* MEDIUM #11: Demo mode visual indicator */}
            {demoMode && (
                <div className="bg-re-warning-muted0/90 text-black text-xs font-medium text-center py-1.5 px-4 flex items-center justify-center gap-2 z-50">
                    <span>⚠️ Sandbox Mode — using sample data for demonstration.</span>
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
                    {/* Always-visible top items */}
                    <div className="px-2.5 space-y-0.5" role="list">
                        {TOP_ITEMS.map((item) => {
                            const Icon = item.icon;
                            const isActive = pathname === item.href;
                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    role="listitem"
                                    aria-current={isActive ? 'page' : undefined}
                                    className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] transition-all min-h-[36px] ${
                                        isActive
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

                    {/* Divider between top items and collapsible sections */}
                    <div className="mx-4 my-3 border-t border-[var(--re-border-default)]" />

                    {/* Collapsible sections */}
                    {COLLAPSIBLE_SECTIONS.map((section) => (
                        <CollapsibleNavSection
                            key={section.key}
                            section={section}
                            expanded={!!expandedSections[section.key]}
                            onToggle={() => toggleSection(section.key)}
                            pathname={pathname}
                        />
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

            {/* Mobile top nav — limited to 5 always-visible items */}
            <div className="md:hidden fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-lg supports-[backdrop-filter]:bg-background/60 border-b border-[var(--re-border-default)]" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
                <nav aria-label="Dashboard quick navigation" className="flex items-center gap-1.5 px-3 py-1.5 overflow-x-auto no-scrollbar scrollbar-none">
                    {MOBILE_NAV_ITEMS.map((item) => {
                        const Icon = item.icon;
                        const isActive = pathname === item.href;
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                className={`flex items-center gap-1.5 px-3 min-h-[36px] rounded-full text-xs font-medium whitespace-nowrap border transition-all active:scale-[0.96] ${
                                    isActive
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
                <DashboardErrorBoundary>
                    {children}
                </DashboardErrorBoundary>
            </main>
        </div>
        </div>
    );
}
