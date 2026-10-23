import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DashboardLayout from '@/app/dashboard/layout';
import { useAuth } from '@/lib/auth-context';
import { usePathname, useRouter } from 'next/navigation';

vi.mock('@/hooks/use-api', () => ({
    useSystemStatus: () => ({ data: { overall_status: 'healthy' }, isLoading: false, dataUpdatedAt: 0 }),
}));

vi.mock('next/navigation', () => ({
    usePathname: vi.fn(),
    useRouter: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

vi.mock('@/components/dashboard/breadcrumb', () => ({
    DashboardBreadcrumb: () => <nav aria-label="Breadcrumb" />,
}));

vi.mock('@/components/dashboard/error-boundary', () => ({
    DashboardErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe('Dashboard navigation discoverability', () => {
    const mockPush = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        (useRouter as any).mockReturnValue({ push: mockPush });
        (usePathname as any).mockReturnValue('/dashboard/inflow-lab');
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: true,
            isHydrated: true,
            user: { id: 'u1', email: 'user@example.com', is_sysadmin: false, status: 'active' },
        });
        const store: Record<string, string> = {};
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => store[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                store[key] = value;
            }),
            removeItem: vi.fn((key: string) => {
                delete store[key];
            }),
            clear: vi.fn(() => {
                Object.keys(store).forEach((key) => delete store[key]);
            }),
            length: 0,
            key: vi.fn(() => null),
        });
    });

    it('limits the healthy banner to the monitored core backend', () => {
        render(
            <QueryClientProvider client={new QueryClient()}>
                <DashboardLayout><div>Inflow content</div></DashboardLayout>
            </QueryClientProvider>,
        );
        expect(screen.getByText('Core Backend Reachable')).toBeInTheDocument();
        expect(screen.queryByText('All Systems Operational')).not.toBeInTheDocument();
    });

    it('exposes Inflow Lab as a top-level active dashboard link', async () => {
        render(
            <DashboardLayout>
                <div>Inflow content</div>
            </DashboardLayout>,
        );

        const inflowLink = screen
            .getAllByText('Inflow Lab')
            .map((node) => node.closest('a'))
            .find((link) => link?.getAttribute('aria-current') === 'page');
        expect(inflowLink).not.toBeNull();
        expect(inflowLink).toHaveAttribute('href', '/dashboard/inflow-lab');
        expect(inflowLink).toHaveAttribute('aria-current', 'page');
        expect(screen.getByRole('button', { name: /Intake/i })).toBeInTheDocument();
        expect(screen.getAllByText('Document Ingestion')[0].closest('a')).toHaveAttribute('href', '/ingest');
    });

    it('puts Trace one click away as a top-level link to /trace', () => {
        (usePathname as any).mockReturnValue('/trace');

        render(
            <DashboardLayout>
                <div>Trace content</div>
            </DashboardLayout>,
        );

        const sidebar = within(screen.getByRole('navigation', { name: 'Dashboard navigation' }));
        const traceLink = sidebar.getByText('Trace').closest('a');
        expect(traceLink).toHaveAttribute('href', '/trace');
        expect(traceLink).toHaveAttribute('aria-current', 'page');

        const mobileBar = within(screen.getByRole('navigation', { name: 'Dashboard quick navigation' }));
        expect(mobileBar.getByText('Trace').closest('a')).toHaveAttribute('href', '/trace');
    });

    it('labels each nav item with the title of the page it opens', () => {
        render(
            <DashboardLayout>
                <div>Dashboard content</div>
            </DashboardLayout>,
        );

        const expected: Array<[string, string]> = [
            ['Document Ingestion', '/ingest'],
            ['Product Profile', '/compliance/profile'],
            ['Scheduled Exports', '/dashboard/export-jobs'],
            ['Team Management', '/dashboard/settings/users'],
            ['Account Settings', '/dashboard/settings'],
        ];
        for (const [label, href] of expected) {
            expect(screen.getByText(label).closest('a')).toHaveAttribute('href', href);
        }

        for (const stale of ['Import files', 'Controls', 'FDA Export', 'Team', 'Review']) {
            expect(screen.queryByText(stale)).not.toBeInTheDocument();
        }
        // Curator Review validates ML extractions, not traceability: off the nav.
        expect(document.querySelector('a[href="/review"]')).toBeNull();
        expect(document.querySelector('a[href="/settings/users"]')).toBeNull();
    });

    it('marks only Team Management current on the nested settings route', () => {
        (usePathname as any).mockReturnValue('/dashboard/settings/users');

        render(
            <DashboardLayout>
                <div>Team content</div>
            </DashboardLayout>,
        );

        expect(screen.getByText('Team Management').closest('a')).toHaveAttribute('aria-current', 'page');
        expect(screen.getByText('Account Settings').closest('a')).not.toHaveAttribute('aria-current');
    });

    it('shows QA Health navigation only to sysadmins', async () => {
        (usePathname as any).mockReturnValue('/dashboard/qa-health');
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: true,
            isHydrated: true,
            user: { id: 'u1', email: 'admin@example.com', is_sysadmin: true, status: 'active' },
        });

        render(
            <DashboardLayout>
                <div>QA Health content</div>
            </DashboardLayout>,
        );

        const qaLink = screen.getByText('QA Health').closest('a');
        expect(qaLink).toHaveAttribute('href', '/dashboard/qa-health');
        expect(qaLink).toHaveAttribute('aria-current', 'page');
    });

    it('hides QA Health navigation for non-sysadmins', async () => {
        (usePathname as any).mockReturnValue('/dashboard');
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: true,
            isHydrated: true,
            user: { id: 'u1', email: 'user@example.com', is_sysadmin: false, status: 'active' },
        });

        render(
            <DashboardLayout>
                <div>Dashboard content</div>
            </DashboardLayout>,
        );

        expect(screen.queryByText('QA Health')).not.toBeInTheDocument();
    });

    it('redirects unauthenticated visitors back to login with the Inflow Lab return path', async () => {
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: false,
            isHydrated: true,
        });

        render(
            <DashboardLayout>
                <div>Protected content</div>
            </DashboardLayout>,
        );

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith('/login?next=%2Fdashboard%2Finflow-lab');
        });
        expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    });
});
