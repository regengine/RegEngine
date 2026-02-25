'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronRight, LayoutDashboard } from 'lucide-react';

const LABEL_MAP: Record<string, string> = {
    compliance: 'Compliance',
    alerts: 'Alerts',
    'recall-report': 'Recall Report',
    suppliers: 'Suppliers',
    products: 'Products',
    'audit-log': 'Audit Log',
    notifications: 'Notifications',
    team: 'Team',
    settings: 'Settings',
};

export function DashboardBreadcrumb() {
    const pathname = usePathname();
    const segments = pathname.split('/').filter(Boolean);

    // Don't show on /dashboard root
    if (segments.length <= 1) return null;

    const subPage = segments[segments.length - 1];
    const label = LABEL_MAP[subPage] || subPage.charAt(0).toUpperCase() + subPage.slice(1);

    return (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-4 px-4 pt-4">
            <Link href="/dashboard" className="flex items-center gap-1 hover:text-foreground transition-colors">
                <LayoutDashboard className="h-3 w-3" />
                Dashboard
            </Link>
            <ChevronRight className="h-3 w-3" />
            <span className="text-foreground font-medium">{label}</span>
        </div>
    );
}
