import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DashboardPage from '@/app/dashboard/page';
import RecallDrillsPage from '@/app/dashboard/recall-drills/page';
import ExportJobsPage from '@/app/dashboard/export-jobs/page';

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ user: { id: 'user-1', is_sysadmin: false }, isHydrated: true, isAuthenticated: true }),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => ({ tenantId: 'tenant-1', isTenantReady: false }),
}));

vi.mock('@/hooks/use-api', () => ({
    useQAHealth: () => ({ data: null, isLoading: false, error: null }),
    useSystemStatus: () => ({ data: { overall_status: 'healthy', services: [] }, isLoading: false }),
    useSystemMetrics: () => ({ data: { open_alerts: 3, events_ingested: 1 }, isLoading: false }),
}));

vi.mock('@/hooks/use-onboarding', () => ({
    useOnboardingStatus: () => ({ data: null }),
}));

vi.mock('@/components/dashboard/system-health-widget', () => ({ SystemHealthWidget: () => null }));
vi.mock('@/components/dashboard/scan-history-widget', () => ({ ScanHistoryWidget: () => null }));
vi.mock('@/components/dashboard/getting-started-card', () => ({ GettingStartedCard: () => null }));

function renderPage(page: React.ReactElement) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={queryClient}>{page}</QueryClientProvider>);
}

function linksTo(href: string) {
    return screen.queryAllByRole('link').filter((link) => link.getAttribute('href') === href);
}

describe('disabled dashboard features', () => {
    beforeEach(() => vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', ''));
    afterEach(() => vi.unstubAllEnvs());

    it('hides alerts and heartbeat links and replaces the alert count when the feature is off', () => {
        renderPage(<DashboardPage />);

        expect(linksTo('/dashboard/alerts')).toHaveLength(0);
        expect(linksTo('/dashboard/heartbeat')).toHaveLength(0);
        expect(screen.getByText('Alerts are off')).toBeInTheDocument();
        expect(screen.queryByText('3 open compliance alerts')).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Recall drills (coming soon)' })).toHaveAttribute('href', '/dashboard/recall-drills');
    });

    it('shows alerts and heartbeat when the existing feature flag is on', () => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
        renderPage(<DashboardPage />);

        expect(linksTo('/dashboard/alerts').length).toBeGreaterThan(0);
        expect(linksTo('/dashboard/heartbeat')).toHaveLength(1);
        expect(screen.queryByText('Alerts are off')).not.toBeInTheDocument();
        expect(screen.getByText('3 open compliance alerts')).toBeInTheDocument();
    });

    it.each([
        ['recall drills', <RecallDrillsPage key="recall-drills" />, 'Start drill'],
        ['export jobs', <ExportJobsPage key="export-jobs" />, 'Save export job'],
    ])('explains unavailable %s and links to working intake paths', async (_name, page, disabledAction) => {
        renderPage(page);

        expect(await screen.findByText(/still in development/i)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'CSV upload' })).toHaveAttribute('href', '/ingest');
        expect(screen.getByRole('link', { name: 'JSON events API' })).toHaveAttribute('href', '/developers');
        expect(screen.getByRole('button', { name: new RegExp(`${disabledAction} \\(coming soon\\)`, 'i') })).toBeDisabled();
        expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    });
});
