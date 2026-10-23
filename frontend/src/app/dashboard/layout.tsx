'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { QueryClientContext } from '@tanstack/react-query';
import { DashboardBreadcrumb } from '@/components/dashboard/breadcrumb';
import { DashboardErrorBoundary } from '@/components/dashboard/error-boundary';
import { Container } from '@/components/layout/container';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { ThemeToggle } from '@/components/layout/theme-toggle';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Skeleton } from '@/components/ui/skeleton';
import { TimedSkeleton } from '@/components/ui/timed-skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { useSystemStatus } from '@/hooks/use-api';
import { useAuth } from '@/lib/auth-context';
import { clsx } from 'clsx';
import { experimentalFeaturesEnabled, isExperimentalPageEnabled } from '@/lib/experimental-features';
import type { LucideIcon } from 'lucide-react';
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
    Menu,
    X,
    Zap,
    AlertTriangle,
    FileCheck,
    Scale,
    Fingerprint,
    ClipboardList,
    Route,
    FlaskConical,
    Bot,
    ShieldAlert,
    Code2,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface NavItem {
    label: string;
    href: string;
    icon: LucideIcon;
    sysadminOnly?: boolean;
    /** Hidden unless NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES is set (backend router auto-disabled in prod) */
    experimental?: boolean;
    /** Gated app page that also honors its per-tool override (see isExperimentalPageEnabled) */
    experimentalPage?: boolean;
}

interface CollapsibleSection {
    key: string;
    title: string;
    items: NavItem[];
}

// ---------------------------------------------------------------------------
// Navigation data
// ---------------------------------------------------------------------------

/**
 * Always-visible top-level items (max 5). Labels are kept short because they
 * also fill the mobile tab bar; each is the leading words of its page title.
 */
const TOP_ITEMS: NavItem[] = [
    { label: 'Overview', href: '/dashboard', icon: Activity },
    { label: 'Trace', href: '/trace', icon: Route },
    { label: 'Inflow Lab', href: '/dashboard/inflow-lab', icon: FlaskConical, experimentalPage: true },
    { label: 'Compliance', href: '/dashboard/compliance', icon: BarChart3 },
    { label: 'Alerts', href: '/dashboard/alerts', icon: Bell, experimentalPage: true },
];

/**
 * Collapsible sections (closed by default). Each label is the title of the
 * page it opens, so a click never lands somewhere differently named.
 * Curator Review (/review) validates ML regulatory extractions, not
 * traceability records, so it is reachable by URL but not listed here.
 */
const COLLAPSIBLE_SECTIONS: CollapsibleSection[] = [
    {
        key: 'data-inflow',
        title: 'Intake',
        items: [
            { label: 'Document Ingestion', href: '/ingest', icon: FileSpreadsheet },
            { label: 'Integrations', href: '/dashboard/integrations', icon: Link2 },
        ],
    },
    {
        key: 'fda-response',
        title: 'Response',
        items: [
            { label: 'Scheduled Exports', href: '/dashboard/export-jobs', icon: Archive },
            { label: 'Recall Drills', href: '/dashboard/recall-drills', icon: Zap },
            { label: 'Recall Report', href: '/dashboard/recall-report', icon: ShieldCheck },
        ],
    },
    {
        key: 'supply-chain',
        title: 'Sources',
        items: [
            { label: 'Supplier Management', href: '/dashboard/suppliers', icon: Users },
            { label: 'Product Catalog', href: '/dashboard/products', icon: Package },
            { label: 'Receiving Dock', href: '/dashboard/receiving', icon: Truck },
            { label: 'Field Capture', href: '/dashboard/scan', icon: Scan, experimental: true },
        ],
    },
    {
        key: 'control-plane',
        title: 'Governance',
        items: [
            { label: 'Compliance Rules', href: '/rules', icon: Scale },
            { label: 'Canonical Records', href: '/records', icon: FileCheck },
            { label: 'Exception Queue', href: '/exceptions', icon: AlertTriangle },
            { label: 'Request-Response Workflow', href: '/requests', icon: ClipboardList },
            { label: 'Identity Resolution', href: '/identity', icon: Fingerprint, experimentalPage: true },
            { label: 'Agent reviews', href: '/dashboard/agent-reviews', icon: Bot },
            { label: 'QA Health', href: '/dashboard/qa-health', icon: ShieldAlert, sysadminOnly: true },
            { label: 'Audit Log', href: '/dashboard/audit-log', icon: ScrollText },
            { label: 'FSMA 204 Dashboard', href: '/fsma', icon: ShieldCheck, experimental: true },
            { label: 'Issues', href: '/dashboard/issues', icon: AlertTriangle },
            { label: 'Product Profile', href: '/compliance/profile', icon: FileText },
        ],
    },
    {
        key: 'settings',
        title: 'Settings',
        items: [
            { label: 'Account Settings', href: '/dashboard/settings', icon: Settings },
            { label: 'Team Management', href: '/dashboard/settings/users', icon: UserCog },
            { label: 'Notification Preferences', href: '/dashboard/notifications', icon: Bell },
            { label: 'Daily Heartbeat', href: '/dashboard/heartbeat', icon: Activity, experimentalPage: true },
            { label: 'Developer portal', href: '/developer/portal', icon: Code2 },
        ],
    },
];

/** Mobile nav - the 5 always-visible items only */
const MOBILE_NAV_ITEMS = TOP_ITEMS;

function isNavItemVisible(item: NavItem, isSysadmin: boolean): boolean {
    if (item.sysadminOnly && !isSysadmin) return false;
    if (item.experimental && !experimentalFeaturesEnabled()) return false;
    if (item.experimentalPage && !isExperimentalPageEnabled(item.href)) return false;
    return true;
}

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
        // silent - quota exceeded, private browsing, etc.
    }
}

// ---------------------------------------------------------------------------
// Determine which sections should auto-expand based on the current route
// ---------------------------------------------------------------------------

function visibleSections(isSysadmin: boolean): CollapsibleSection[] {
    return COLLAPSIBLE_SECTIONS.map((section) => ({
        ...section,
        items: section.items.filter((item) => isNavItemVisible(item, isSysadmin)),
    }));
}

function sectionsWithActiveRoute(pathname: string, sections: CollapsibleSection[]): Set<string> {
    const active = new Set<string>();
    for (const section of sections) {
        for (const item of section.items) {
            if (isNavItemActive(pathname, item.href)) {
                active.add(section.key);
            }
        }
    }
    return active;
}

function isNavItemActive(pathname: string, href: string): boolean {
    // Hubs whose sub-routes have their own nav items match exactly, so only
    // one item is marked current (e.g. Team Management, not Account Settings).
    if (href === '/dashboard' || href === '/dashboard/settings') {
        return pathname === href;
    }

    if (href === '/compliance/profile') {
        return pathname === href || pathname.startsWith('/compliance/');
    }

    return pathname === href || pathname.startsWith(`${href}/`);
}

// ---------------------------------------------------------------------------
// Shared recipes (SPEC §3.3)
// ---------------------------------------------------------------------------

const FOCUS_RING =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-1 focus-visible:ring-offset-re-ring-offset';

/** 36px row, inset tint when active, 2px brand rail on the left edge. */
function navItemClass(active: boolean) {
    return clsx(
        'relative flex h-9 items-center gap-2.5 rounded-md px-3 text-ui transition-colors duration-120 motion-reduce:transition-none',
        FOCUS_RING,
        active
            ? 'bg-re-surface-inset font-medium text-re-text-primary before:absolute before:inset-y-1.5 before:left-0 before:w-0.5 before:rounded-full before:bg-re-brand before:content-[""]'
            : 'text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary',
    );
}

const footerLinkClass = clsx(
    'flex items-center rounded-md px-3 py-1.5 text-small text-re-text-secondary transition-colors duration-120 hover:bg-re-surface-inset hover:text-re-text-primary motion-reduce:transition-none',
    FOCUS_RING,
);

function NavLinkItem({
    item,
    pathname,
    role,
    tabIndex,
}: {
    item: NavItem;
    pathname: string;
    role?: string;
    tabIndex?: number;
}) {
    const Icon = item.icon;
    const isActive = isNavItemActive(pathname, item.href);
    return (
        <Link
            href={item.href}
            role={role}
            tabIndex={tabIndex}
            aria-current={isActive ? 'page' : undefined}
            className={navItemClass(isActive)}
        >
            <Icon className="h-4 w-4 flex-shrink-0" strokeWidth={1.75} aria-hidden="true" />
            <span className="flex-1 truncate">{item.label}</span>
        </Link>
    );
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
            {/* Section header - clickable toggle */}
            <button
                type="button"
                onClick={onToggle}
                className={clsx(
                    'flex w-full cursor-pointer select-none items-center gap-1.5 rounded-md px-3 py-2 text-label uppercase text-re-text-muted transition-colors duration-120 hover:text-re-text-secondary motion-reduce:transition-none',
                    FOCUS_RING,
                )}
                aria-expanded={expanded}
            >
                {expanded ? (
                    <ChevronDown className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                ) : (
                    <ChevronRight className="h-3 w-3 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                )}
                <span>{section.title}</span>
            </button>

            {/* Collapsible items */}
            <div
                className="overflow-hidden transition-all duration-200 motion-reduce:transition-none"
                style={{ maxHeight: expanded ? (height ?? 1000) : 0, opacity: expanded ? 1 : 0 }}
            >
                <div ref={contentRef} className="space-y-0.5 pb-1 pl-2" role="list">
                    {section.items.map((item) => (
                        <NavLinkItem
                            key={item.href + item.label}
                            item={item}
                            pathname={pathname}
                            role="listitem"
                            tabIndex={expanded ? 0 : -1}
                        />
                    ))}
                </div>
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------------
// Status strip (SPEC §3.3) - the single topbar
// ---------------------------------------------------------------------------

const HEALTH_BADGE: Record<string, { state: ComplianceState; label: string }> = {
    loading: { state: 'in-progress', label: 'Checking...' },
    operational: { state: 'compliant', label: 'Core Backend Reachable' },
    degraded: { state: 'at-risk', label: 'Degraded Performance' },
    disruption: { state: 'non-compliant', label: 'Services Unreachable' },
};

function formatSyncTime(timestamp: number): string {
    return `${new Date(timestamp).toISOString().slice(11, 16)}Z`;
}

function ServiceHealthReadout() {
    const { data: systemStatus, isLoading, dataUpdatedAt } = useSystemStatus();

    let key: keyof typeof HEALTH_BADGE = 'disruption';
    if (isLoading && !systemStatus) key = 'loading';
    else if (systemStatus?.overall_status === 'healthy') key = 'operational';
    else if (systemStatus?.overall_status === 'degraded') key = 'degraded';

    const badge = HEALTH_BADGE[key];

    return (
        <>
            <StatusBadge state={badge.state} label={badge.label} size="sm" className="hidden md:inline-flex" />
            {dataUpdatedAt ? (
                <time
                    dateTime={new Date(dataUpdatedAt).toISOString()}
                    className="hidden font-mono text-small text-re-text-muted lg:inline"
                >
                    {formatSyncTime(dataUpdatedAt)}
                </time>
            ) : null}
        </>
    );
}

/**
 * The health readout polls through React Query. Rendering the shell without a
 * QueryClientProvider (unit tests mount the layout directly) must not throw, so
 * the provider is probed before the hook is reached.
 */
function ServiceHealth() {
    const queryClient = React.useContext(QueryClientContext);
    if (!queryClient) return null;
    return <ServiceHealthReadout />;
}

// ---------------------------------------------------------------------------
// Layout
// ---------------------------------------------------------------------------

function DashboardShellSkeleton() {
    return (
        <div className="re-app-shell flex min-h-screen flex-col" aria-busy="true">
            <div className="flex flex-1">
                <aside className="hidden w-[244px] flex-shrink-0 flex-col border-r border-re-border-subtle bg-re-surface-elevated md:flex">
                    <div className="flex h-14 items-center border-b border-re-border-subtle px-4">
                        <Skeleton className="h-5 w-32" />
                    </div>
                    <div className="flex-1 space-y-1.5 p-3">
                        {[1, 2, 3, 4, 5, 6, 7].map((item) => (
                            <Skeleton key={item} className="h-9 rounded-md" />
                        ))}
                    </div>
                    <div className="space-y-1.5 border-t border-re-border-subtle p-3">
                        <Skeleton className="h-4 w-36" />
                        <Skeleton className="h-4 w-24" />
                    </div>
                </aside>
                <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex h-12 items-center gap-2 border-b border-re-border-subtle bg-re-surface-base px-3 md:h-11 md:px-4">
                        <Skeleton className="h-4 w-40" />
                        <div className="ml-auto flex items-center gap-2">
                            <Skeleton className="hidden h-5 w-32 rounded-full md:block" />
                            <Skeleton className="h-9 w-9 rounded-md" />
                        </div>
                    </div>
                    <div className="flex-1 pb-20 md:pb-0">
                        <Container width="app" className="py-6">
                            {/* Session hydration can stall on a slow backend; never spin forever. */}
                            <TimedSkeleton errorMessage="Your session check did not finish. Reload to try again.">
                                <div className="space-y-6">
                                    <Skeleton className="h-8 w-44" />
                                    <Skeleton className="h-[244px] rounded-lg" />
                                    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                                        <Skeleton className="h-[360px] rounded-lg lg:col-span-2" />
                                        <Skeleton className="h-[360px] rounded-lg" />
                                    </div>
                                </div>
                            </TimedSkeleton>
                        </Container>
                    </div>
                </div>
            </div>
            <div className="fixed inset-x-0 bottom-0 border-t border-re-border-subtle bg-re-surface-elevated pb-[env(safe-area-inset-bottom,0px)] md:hidden">
                <div className="flex h-14 items-stretch">
                    {[1, 2, 3, 4, 5].map((item) => (
                        <div key={item} className="flex flex-1 flex-col items-center justify-center gap-1">
                            <Skeleton className="h-5 w-5 rounded-md" />
                            <Skeleton className="h-2 w-10" />
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const router = useRouter();
    const { demoMode, isAuthenticated, isHydrated, logout, user } = useAuth();
    const isSysadmin = Boolean(user?.is_sysadmin);
    const navSections = React.useMemo(() => visibleSections(isSysadmin), [isSysadmin]);
    const topItems = React.useMemo(
        () => TOP_ITEMS.filter((item) => isNavItemVisible(item, isSysadmin)),
        [isSysadmin],
    );

    // ------ Collapsible section state with localStorage persistence ------
    const [expandedSections, setExpandedSections] = React.useState<Record<string, boolean>>({});
    const initializedRef = React.useRef(false);

    // ------ Mobile nav sheet ------
    const [mobileNavOpen, setMobileNavOpen] = React.useState(false);

    // Hydrate from localStorage + auto-expand sections containing the active route
    React.useEffect(() => {
        if (!initializedRef.current) {
            const stored = loadExpandedSections();
            const active = sectionsWithActiveRoute(pathname, navSections);
            // Merge: stored state wins, but active sections always open
            const merged: Record<string, boolean> = { ...stored };
            active.forEach((key) => {
                merged[key] = true;
            });
            setExpandedSections(merged);
            initializedRef.current = true;
        } else {
            // On subsequent route changes, auto-expand sections with active items
            const active = sectionsWithActiveRoute(pathname, navSections);
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
    }, [pathname, navSections]);

    // Persist to localStorage when expansion state changes
    React.useEffect(() => {
        if (initializedRef.current) {
            saveExpandedSections(expandedSections);
        }
    }, [expandedSections]);

    // The sheet is a navigation surface: following a link closes it.
    React.useEffect(() => {
        setMobileNavOpen(false);
    }, [pathname]);

    React.useEffect(() => {
        if (!mobileNavOpen) return;
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === 'Escape') setMobileNavOpen(false);
        };
        document.addEventListener('keydown', onKeyDown);
        return () => document.removeEventListener('keydown', onKeyDown);
    }, [mobileNavOpen]);

    const toggleSection = React.useCallback((key: string) => {
        setExpandedSections((prev) => ({ ...prev, [key]: !prev[key] }));
    }, []);

    // ------ Route-level auth guard ------
    React.useEffect(() => {
        if (isHydrated && !isAuthenticated) {
            router.push(`/login?next=${encodeURIComponent(pathname)}`);
        }
    }, [isHydrated, isAuthenticated, router, pathname]);

    if (!isHydrated || !isAuthenticated) {
        return <DashboardShellSkeleton />;
    }

    // Arrow keys traverse nav items (MEDIUM #12)
    const onNavKeyDown = (e: React.KeyboardEvent<HTMLElement>) => {
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
    };

    const sectionList = navSections.map((section) => (
        <CollapsibleNavSection
            key={section.key}
            section={section}
            expanded={!!expandedSections[section.key]}
            onToggle={() => toggleSection(section.key)}
            pathname={pathname}
        />
    ));

    return (
        <div className="re-app-shell flex min-h-screen flex-col">
            {demoMode && (
                <Callout tone="warning" className="rounded-none border-r-0 border-t-0 px-4 py-2 text-small">
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                        <span>No data yet. This workspace has no live records connected.</span>
                        <Link href="/ingest" className="underline hover:no-underline">
                            Connect real data to get started
                        </Link>
                    </span>
                </Callout>
            )}
            <div className="flex flex-1">
                {/* Sidebar */}
                <aside
                    aria-label="Dashboard sidebar"
                    className="hidden w-[244px] flex-shrink-0 flex-col border-r border-re-border-subtle bg-re-surface-elevated md:sticky md:top-0 md:flex md:h-screen"
                >
                    {/* Brand */}
                    <div className="flex h-14 flex-shrink-0 items-center border-b border-re-border-subtle px-4">
                        <Link href="/dashboard" className={clsx('flex items-center rounded-md', FOCUS_RING)}>
                            <RegEngineWordmark size="sm" />
                        </Link>
                    </div>

                    {/* Nav sections */}
                    {/* MEDIUM #12: Keyboard navigation - arrow keys traverse nav items */}
                    <nav
                        aria-label="Dashboard navigation"
                        className="flex-1 overflow-y-auto px-2 py-3"
                        role="navigation"
                        onKeyDown={onNavKeyDown}
                    >
                        {/* Always-visible top items */}
                        <div className="space-y-0.5" role="list">
                            {topItems.map((item) => (
                                <NavLinkItem key={item.href} item={item} pathname={pathname} role="listitem" />
                            ))}
                        </div>

                        {/* Divider between top items and collapsible sections */}
                        <div className="my-3 border-t border-re-border-subtle" />

                        {/* Collapsible sections */}
                        {sectionList}
                    </nav>

                    {/* Footer */}
                    <div className="flex-shrink-0 border-t border-re-border-subtle p-2">
                        {user?.email && (
                            <div
                                aria-label="Signed in user"
                                className="truncate px-3 py-1.5 font-mono text-small text-re-text-muted"
                                title={user.email}
                            >
                                {user.email}
                            </div>
                        )}
                        <div className="flex flex-col">
                            <Link href="/dashboard/settings" className={footerLinkClass}>
                                Settings & usage
                            </Link>
                            <Link href="/onboarding" className={footerLinkClass}>
                                Onboarding
                            </Link>
                            <button
                                type="button"
                                onClick={async () => {
                                    await logout();
                                    router.replace('/login');
                                }}
                                className={clsx(footerLinkClass, 'text-left')}
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </aside>

                <div className="flex min-w-0 flex-1 flex-col">
                    {/* Status strip - the only topbar (SPEC §3.3) */}
                    <header className="sticky top-0 z-[var(--re-z-sticky)] border-b border-re-border-subtle bg-re-surface-base/95 backdrop-blur">
                        <div className="flex h-12 items-center gap-2 px-3 md:h-11 md:px-4">
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="-ml-1 md:hidden"
                                aria-label="Open navigation menu"
                                aria-expanded={mobileNavOpen}
                                aria-controls="dashboard-mobile-nav"
                                onClick={() => setMobileNavOpen(true)}
                            >
                                <Menu className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                            </Button>
                            <Link
                                href="/dashboard"
                                className={clsx('flex shrink-0 items-center rounded-md md:hidden', FOCUS_RING)}
                            >
                                <RegEngineWordmark size="sm" />
                            </Link>
                            <DashboardBreadcrumb />
                            <div className="ml-auto flex min-w-0 items-center gap-2">
                                <ServiceHealth />
                                <ThemeToggle />
                                {user?.email && (
                                    <span
                                        className="hidden max-w-[200px] truncate font-mono text-small text-re-text-muted xl:inline"
                                        title={user.email}
                                    >
                                        {user.email}
                                    </span>
                                )}
                            </div>
                        </div>
                    </header>

                    {/* Main content. overflow-x keeps a wide table inside the
                        content column instead of widening the whole page. */}
                    <div className="min-w-0 flex-1 overflow-x-auto pb-20 md:pb-0">
                        <DashboardErrorBoundary>
                            {children}
                        </DashboardErrorBoundary>
                    </div>
                </div>
            </div>

            {/* Mobile bottom tab bar - same links, same order, new position */}
            <nav
                aria-label="Dashboard quick navigation"
                className="fixed inset-x-0 bottom-0 z-[var(--re-z-nav)] border-t border-re-border-subtle bg-re-surface-elevated pb-[env(safe-area-inset-bottom,0px)] md:hidden"
            >
                <div className="flex h-14 items-stretch">
                    {MOBILE_NAV_ITEMS.filter((item) => isNavItemVisible(item, isSysadmin)).map((item) => {
                        const Icon = item.icon;
                        const isActive = isNavItemActive(pathname, item.href);
                        return (
                            <Link
                                key={item.href}
                                href={item.href}
                                aria-current={isActive ? 'page' : undefined}
                                className={clsx(
                                    'flex min-h-[44px] min-w-[44px] flex-1 flex-col items-center justify-center gap-1 px-1 text-label transition-colors duration-120 motion-reduce:transition-none',
                                    FOCUS_RING,
                                    isActive ? 'font-medium text-re-brand' : 'text-re-text-muted',
                                )}
                            >
                                <Icon className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                                <span className="max-w-full truncate">{item.label}</span>
                            </Link>
                        );
                    })}
                </div>
            </nav>

            {/* Mobile nav sheet - TOP_ITEMS plus the collapsible sections */}
            {mobileNavOpen && (
                <div className="fixed inset-0 z-[var(--re-z-nav)] md:hidden">
                    <div
                        className="absolute inset-0 bg-re-surface-overlay"
                        aria-hidden="true"
                        onClick={() => setMobileNavOpen(false)}
                    />
                    <div
                        id="dashboard-mobile-nav"
                        role="dialog"
                        aria-modal="true"
                        aria-label="Dashboard navigation menu"
                        className="relative flex h-full w-[min(20rem,86vw)] flex-col border-r border-re-border-subtle bg-re-surface-elevated"
                    >
                        <div className="flex h-12 flex-shrink-0 items-center justify-between border-b border-re-border-subtle px-3">
                            <RegEngineWordmark size="sm" />
                            <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                aria-label="Close navigation menu"
                                onClick={() => setMobileNavOpen(false)}
                            >
                                <X className="h-5 w-5" strokeWidth={1.75} aria-hidden="true" />
                            </Button>
                        </div>
                        <div className="flex-1 overflow-y-auto px-2 py-3" onKeyDown={onNavKeyDown}>
                            <div className="space-y-0.5">
                                {topItems.map((item) => (
                                    <NavLinkItem key={item.href} item={item} pathname={pathname} />
                                ))}
                            </div>
                            <div className="my-3 border-t border-re-border-subtle" />
                            {sectionList}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
