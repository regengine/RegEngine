'use client';
import { usePathname } from 'next/navigation';
import { matchesRoutePrefix } from '@/lib/app-routes';
// These layouts mount DashboardLayout; other routes use the root page landmark.
const DASHBOARD_SHELL_ROUTES = ['/dashboard', '/admin', '/sysadmin', '/settings', '/rules', '/records', '/exceptions', '/requests', '/identity', '/review', '/audit', '/controls', '/trace', '/compliance', '/ingest', '/remediation'];
export function SkipLink() {
    const pathname = usePathname();
    return <a href={matchesRoutePrefix(pathname ?? '', DASHBOARD_SHELL_ROUTES) ? '#dashboard-main-content' : '#main-content'}
        className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[var(--re-brand)] focus:text-[var(--re-surface-base)] focus:text-sm focus:font-semibold focus:outline-none"
        onClick={(event) => {
            const target = document.getElementById(event.currentTarget.hash.slice(1)) ?? document.getElementById('main-content');
            if (target) { event.preventDefault(); target.focus(); target.scrollIntoView?.(); }
        }}>Skip to content</a>;
}
