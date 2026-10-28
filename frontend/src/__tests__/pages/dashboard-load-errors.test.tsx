import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorState } from '@/components/ui/error-state';
import { apiError } from '@/lib/api-error';
import AlertsPage from '@/app/dashboard/alerts/page';
import ProductsPage from '@/app/dashboard/products/page';
import AuditLogPage from '@/app/dashboard/audit-log/page';
import NotificationsPage from '@/app/dashboard/notifications/page';
import CompliancePage from '@/app/dashboard/compliance/page';
import RecallReportPage from '@/app/dashboard/recall-report/page';
import QAHealthPage from '@/app/dashboard/qa-health/page';
import SettingsPage from '@/app/dashboard/settings/page';
import { AgentReviewDashboard } from '@/components/dashboard/agent-review-dashboard';
import { CuratorReview } from '@/components/dashboard/curator-review';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const reviewRefetchMock = vi.hoisted(() => vi.fn());
const useReviewItemsMock = vi.hoisted(() => vi.fn());
const authMock = vi.hoisted(() => vi.fn());
const useQAHealthMock = vi.hoisted(() => vi.fn());
const useCuratorItemsMock = vi.hoisted(() => vi.fn());
const useSubscriptionMock = vi.hoisted(() => vi.fn());
const fetchComplianceScoreMock = vi.hoisted(() => vi.fn());
const fetchWorkbenchSummaryMock = vi.hoisted(() => vi.fn());
const fetchRecallReportMock = vi.hoisted(() => vi.fn());
const fetchAlertsMock = vi.hoisted(() => vi.fn());
const tenantMock = vi.hoisted(() => ({ tenantId: 't' as string | null }));

vi.mock('@/lib/fetch-with-csrf', () => ({ fetchWithCsrf: (...args: unknown[]) => fetchWithCsrfMock(...args) }));
vi.mock('@/lib/api-config', () => ({ getServiceURL: () => '/api/ingestion' }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => authMock() }));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId: tenantMock.tenantId, isSystemTenant: false }) }));
vi.mock('@/hooks/use-api', () => ({ useQAHealth: () => useQAHealthMock() }));
vi.mock('@/hooks/use-review', () => ({
    useReviewItems: () => useCuratorItemsMock(),
    useApproveReviewItem: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useRejectReviewItem: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/use-billing', () => ({ useCurrentSubscription: () => useSubscriptionMock() }));
vi.mock('@/lib/api-hooks', () => ({
    fetchComplianceScore: () => fetchComplianceScoreMock(),
    fetchWorkbenchReadinessSummary: () => fetchWorkbenchSummaryMock(),
    fetchRecallReport: () => fetchRecallReportMock(),
    fetchAlerts: (...args: unknown[]) => fetchAlertsMock(...args),
    acknowledgeAlert: vi.fn(),
}));
vi.mock('@/hooks/use-agent-reviews', () => ({
    useAgentReviewItems: () => useReviewItemsMock(),
    useAgentReviewDecision: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ useDashboardRefresh: vi.fn() }));
vi.mock('next/link', () => ({ default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a> }));
vi.mock('framer-motion', () => ({
    motion: { div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div>{children}</div> },
    AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

function renderWithQuery(ui: React.ReactElement) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const failedResponse = Response.error();

afterEach(() => vi.unstubAllEnvs());

beforeEach(() => {
    fetchWithCsrfMock.mockReset();
    fetchComplianceScoreMock.mockReset();
    fetchWorkbenchSummaryMock.mockReset();
    fetchRecallReportMock.mockReset();
    fetchAlertsMock.mockReset();
    tenantMock.tenantId = 't';
    authMock.mockReturnValue({ isAuthenticated: true, hasTenantSession: true, hasAdminSession: true, isHydrated: true, user: { is_sysadmin: false } });
    fetchWorkbenchSummaryMock.mockResolvedValue(null);
});

describe('shared dashboard load errors', () => {
    it('offers in-page retry, support, and an available request ID', async () => {
        const onRetry = vi.fn();
        const user = userEvent.setup();
        const requestId = crypto.randomUUID();
        const { rerender } = render(<ErrorState message="We could not load this page." onRetry={onRetry} requestId={requestId} />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.getByText(`Request ID: ${requestId}`)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Contact support' })).toHaveAttribute('href', '/settings/support');
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(onRetry).toHaveBeenCalledOnce();

        rerender(<ErrorState message="We could not load this page." onRetry={onRetry} requestId={requestId} retrying />);
        expect(screen.getByRole('button', { name: 'Retrying…' })).toBeDisabled();
    });

    it('omits the request ID when none is available', () => {
        render(<ErrorState message="We could not load this page." onRetry={vi.fn()} />);
        expect(screen.queryByText(/Request ID:/)).not.toBeInTheDocument();
    });

    it('shows the alerts error state with retry, support, and the request ID', async () => {
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
        const alertsRequestId = crypto.randomUUID();
        fetchAlertsMock.mockRejectedValue(apiError(500, 'Internal Server Error', alertsRequestId));
        const user = userEvent.setup();
        renderWithQuery(<AlertsPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load your alerts.');
        expect(screen.getByText(`Request ID: ${alertsRequestId}`)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Contact support' })).toHaveAttribute('href', '/settings/support');
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(fetchAlertsMock).toHaveBeenCalledTimes(2));
    });

    it('shows the failed response request ID on the products error state', async () => {
        const productsRequestId = crypto.randomUUID();
        fetchWithCsrfMock.mockResolvedValue(
            new Response(JSON.stringify({ detail: 'boom' }), {
                status: 500,
                headers: { 'x-request-id': productsRequestId },
            }),
        );
        renderWithQuery(<ProductsPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.getByText(`Request ID: ${productsRequestId}`)).toBeInTheDocument();
    });

    it('shows the API client request ID on QA health failures', () => {
        const refetch = vi.fn();
        authMock.mockReturnValue({ user: { is_sysadmin: true }, isHydrated: true });
        const qaRequestId = crypto.randomUUID();
        const qaError = Object.assign(new Error('Request failed'), {
            response: { status: 500, headers: { 'x-request-id': qaRequestId }, data: {} },
        });
        useQAHealthMock.mockReturnValue({ data: null, isLoading: false, error: qaError, refetch, isRefetching: false });
        render(<QAHealthPage />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.getByText(`Request ID: ${qaRequestId}`)).toBeInTheDocument();
    });

    it('keeps Add Product unavailable until a failed catalog request succeeds on Retry', async () => {
        fetchWithCsrfMock
            .mockResolvedValueOnce(failedResponse)
            .mockResolvedValueOnce(Response.json({ products: [], categories: [] }));
        const user = userEvent.setup();
        renderWithQuery(<ProductsPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.getByRole('button', { name: 'Add Product' })).toBeDisabled();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(screen.getByRole('button', { name: 'Add Product' })).toBeEnabled());
        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(2);
    });

    it('hides audit integrity claims and export until the log loads on Retry', async () => {
        const entry = {
            id: crypto.randomUUID(),
            timestamp: new Date().toISOString(),
            event_type: 'api_call',
            category: '',
            actor: '',
            action: '',
            resource: '',
            details: {},
            ip_address: '',
            hash: '',
        };
        const entries = [entry];
        fetchWithCsrfMock
            .mockResolvedValueOnce(failedResponse)
            .mockResolvedValueOnce(Response.json({ tenant_id: 't', entries, total: entries.length }));
        const user = userEvent.setup();
        renderWithQuery(<AuditLogPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByText(/Immutable, SHA-256 verified/)).not.toBeInTheDocument();
        expect(screen.queryByText('Hash-chained')).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Export' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(screen.getByText(/Immutable, SHA-256 verified/)).toBeInTheDocument());
        expect(screen.getByText('Hash-chained')).toBeInTheDocument();
        expect(screen.getByRole('searchbox', { name: 'Search actions, actors, resources' })).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Export' })).toBeInTheDocument();
        expect(screen.getByText('API Call').closest('li')).toBeInTheDocument();
        expect(fetchWithCsrfMock).toHaveBeenCalledTimes(2);
    });

    it('offers Retry and support for notification preferences without Save Changes', async () => {
        fetchWithCsrfMock.mockResolvedValue(failedResponse);
        const user = userEvent.setup();
        renderWithQuery(<NotificationsPage />);

        expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('We could not load this page.');
        expect(screen.getByRole('link', { name: 'Contact support' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Save Changes' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalledTimes(3), { timeout: 5000 });
    });

    it('does not show zero review metrics when the dashboard queue fails', async () => {
        useReviewItemsMock.mockReturnValue({
            data: null,
            error: new Error('request failed'),
            isLoading: false,
            isFetching: false,
            refetch: reviewRefetchMock,
        });
        const user = userEvent.setup();
        render(<AgentReviewDashboard />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByText('Needs review')).not.toBeInTheDocument();
        expect(screen.queryByText('0 total')).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(reviewRefetchMock).toHaveBeenCalledOnce();
    });

    it('lets compliance retry its failed score request in place', async () => {
        fetchComplianceScoreMock.mockRejectedValue(new Error('server error'));
        const user = userEvent.setup();
        renderWithQuery(<CompliancePage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load the compliance score.');
        // SEL-616: score failure must not blank Import readiness / setup paths
        expect(await screen.findByText('Import readiness')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(fetchComplianceScoreMock).toHaveBeenCalledTimes(2));
    });

    it('keeps Import readiness visible when score and readiness both fail (SEL-616)', async () => {
        fetchComplianceScoreMock.mockRejectedValue(apiError(401, 'Unauthorized', crypto.randomUUID()));
        fetchWorkbenchSummaryMock.mockRejectedValue(apiError(503, 'Service Unavailable', crypto.randomUUID()));
        renderWithQuery(<CompliancePage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load the compliance score.');
        expect(await screen.findByText('Import readiness')).toBeInTheDocument();
        expect(screen.getByText(/Import readiness is unavailable right now/i)).toBeInTheDocument();
        expect(screen.queryByText('We could not load this page.')).not.toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Retry import readiness' })).toBeInTheDocument();
    });

    it('lets recall report retry a failed request in place', async () => {
        fetchRecallReportMock.mockRejectedValue(new Error('server error'));
        const user = userEvent.setup();
        renderWithQuery(<RecallReportPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(fetchRecallReportMock.mock.calls.length).toBeGreaterThan(1));
    });

    it('lets a sysadmin retry QA health without showing stale data', async () => {
        const refetch = vi.fn();
        authMock.mockReturnValue({ user: { is_sysadmin: true }, isHydrated: true });
        useQAHealthMock.mockReturnValue({ data: null, isLoading: false, error: new Error('server error'), refetch, isRefetching: false });
        const user = userEvent.setup();
        render(<QAHealthPage />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByText('Release gate passing')).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(refetch).toHaveBeenCalledOnce();
    });

    it('lets curator review retry without showing review decisions', async () => {
        const refetch = vi.fn();
        useCuratorItemsMock.mockReturnValue({ data: null, isLoading: false, error: new Error('server error'), refetch, isFetching: false });
        const user = userEvent.setup();
        render(<CuratorReview />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(refetch).toHaveBeenCalledOnce();
    });

    it('blocks Manage Plan when billing data fails and offers a retry', async () => {
        const refetch = vi.fn();
        useSubscriptionMock.mockReturnValue({ data: null, isLoading: false, isError: true, refetch, isFetching: false });
        fetchWithCsrfMock.mockResolvedValue(failedResponse);
        const user = userEvent.setup();
        renderWithQuery(<SettingsPage />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByRole('button', { name: 'Manage Plan' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(refetch).toHaveBeenCalledOnce();
    });
});
