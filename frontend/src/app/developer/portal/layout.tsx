import type { ReactNode } from 'react';
import DashboardLayout from '../../dashboard/layout';

// Authenticated app route: render inside the shared dashboard shell so the
// page gets the sidebar, breadcrumb and error boundary like every other
// signed-in surface (same pattern as app/admin/layout.tsx). DashboardLayout
// reads useAuth() and sends an unauthenticated visitor to
// /login?next=<this path>. /login forwards on the same useAuth()
// isAuthenticated flag, so the two cannot disagree and loop.
export default function DeveloperPortalLayout({ children }: { children: ReactNode }) {
    return <DashboardLayout>{children}</DashboardLayout>;
}
