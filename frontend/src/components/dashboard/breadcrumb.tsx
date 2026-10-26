'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight } from 'lucide-react';

/**
 * Human labels for dashboard sub-routes. Without an entry a slug falls back to
 * naive capitalisation ("agent-reviews" → "Agent-reviews"), so every route the
 * console links to gets a real label here.
 */
const LABEL_MAP: Record<string, string> = {
    compliance: 'Compliance',
    alerts: 'Alerts',
    'agent-reviews': 'Agent reviews',
    'audit-log': 'Audit Log',
    'export-jobs': 'Scheduled Exports',
    heartbeat: 'Daily Heartbeat',
    integrations: 'Integrations',
    issues: 'Issues',
    notifications: 'Notification Preferences',
    products: 'Product Catalog',
    'qa-health': 'QA Health',
    'recall-drills': 'Recall Drills',
    'recall-report': 'Recall Report',
    'recall-response': 'Recall Response',
    receiving: 'Receiving Dock',
    scan: 'Field Capture',
    settings: 'Account Settings',
    suppliers: 'Supplier Management',
    team: 'Team Management',
    users: 'Team Management',
};

export function DashboardBreadcrumb() {
    const pathname = usePathname();
    const segments = pathname.split('/').filter(Boolean);

    // Don't show on /dashboard root
    if (segments.length <= 1) return null;

    const subPage = segments[segments.length - 1];
    const label = LABEL_MAP[subPage] || subPage.charAt(0).toUpperCase() + subPage.slice(1);

    return (
        <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-small text-re-text-muted">
            <Link
                href="/dashboard"
                className="rounded-sm text-re-text-muted transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
            >
                Dashboard
            </Link>
            <ChevronRight className="h-3 w-3 shrink-0 text-re-text-disabled" strokeWidth={1.75} aria-hidden="true" />
            <span aria-current="page" className="truncate font-medium text-re-text-primary">
                {label}
            </span>
        </nav>
    );
}
