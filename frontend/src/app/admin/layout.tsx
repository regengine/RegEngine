import type { ReactNode } from 'react';
import DashboardLayout from '../dashboard/layout';

// Authenticated app route: render inside the shared dashboard shell so the
// page gets the sidebar, breadcrumb and error boundary like every other
// signed-in surface (it previously rendered bare after the marketing chrome
// was hidden by shouldHideMarketingChrome).
export default function AppShellLayout({ children }: { children: ReactNode }) {
    return <DashboardLayout>{children}</DashboardLayout>;
}
