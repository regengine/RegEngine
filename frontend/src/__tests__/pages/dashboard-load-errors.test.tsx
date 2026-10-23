import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorState } from '@/components/ui/error-state';
import ProductsPage from '@/app/dashboard/products/page';
import AuditLogPage from '@/app/dashboard/audit-log/page';
import NotificationsPage from '@/app/dashboard/notifications/page';
import CompliancePage from '@/app/dashboard/compliance/page';
import RecallReportPage from '@/app/dashboard/recall-report/page';
import QAHealthPage from '@/app/dashboard/qa-health/page';
import SettingsPage from '@/app/dashboard/settings/page';
import { AgentReviewDashboard } from '@/components/dashboard/agent-review-dashboard';
import { CuratorReview } from '@/components/dashboard/curator-review';

const queryOverride = vi.hoisted(() => ({ current: null as null | (() => unknown) }));
const queryRefetchMock = vi.hoisted(() => vi.fn());
const reviewRefetchMock = vi.hoisted(() => vi.fn());
const useReviewItemsMock = vi.hoisted(() => vi.fn());
const authMock = vi.hoisted(() => vi.fn());
const useQAHealthMock = vi.hoisted(() => vi.fn());
const useCuratorItemsMock = vi.hoisted(() => vi.fn());
const useSubscriptionMock = vi.hoisted(() => vi.fn());
vi.mock('@tanstack/react-query', async (importOriginal) => {
    const actual = await importOriginal<typeof import('@tanstack/react-query')>();
    return {
        ...actual,
        useQuery: (options: Parameters<typeof actual.useQuery>[0]) =>
            queryOverride.current ? queryOverride.current() : actual.useQuery(options),
    };
});
vi.mock('@/lib/auth-context', () => ({ useAuth: () => authMock() }));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId: null, isSystemTenant: false }) }));
vi.mock('@/hooks/use-api', () => ({ useQAHealth: () => useQAHealthMock() }));
vi.mock('@/hooks/use-review', () => ({
    useReviewItems: () => useCuratorItemsMock(),
    useApproveReviewItem: () => ({ mutateAsync: vi.fn(), isPending: false }),
    useRejectReviewItem: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/use-billing', () => ({ useCurrentSubscription: () => useSubscriptionMock() }));
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

function useProductQuery() {
    const [data, setData] = useState<{ products: never[]; categories: never[] } | undefined>();
    return {
        data,
        error: data ? null : new Error('request failed'),
        isLoading: false,
        refetch: () => setData({ products: [], categories: [] }),
    };
}

function useAuditQuery() {
    const [data, setData] = useState<{ entries: never[] } | undefined>();
    return {
        data,
        error: data ? null : new Error('request failed'),
        isLoading: false,
        refetch: () => setData({ entries: [] }),
    };
}

beforeEach(() => {
    queryOverride.current = null;
    queryRefetchMock.mockReset();
    reviewRefetchMock.mockReset();
    authMock.mockReturnValue({ isAuthenticated: true, hasTenantSession: true, hasAdminSession: true, isHydrated: true, user: { is_sysadmin: false } });
});

describe('shared dashboard load errors', () => {
    it('offers in-page retry and support when no request ID is available', async () => {
        const onRetry = vi.fn();
        const user = userEvent.setup();
        const { rerender } = render(<ErrorState message="We could not load this page." onRetry={onRetry} />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByText(/Request ID:/)).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Contact support' })).toHaveAttribute('href', '/settings/support');
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(onRetry).toHaveBeenCalledOnce();

        rerender(<ErrorState message="We could not load this page." onRetry={onRetry} retrying />);
        expect(screen.getByRole('button', { name: 'Retry' })).toBeDisabled();
    });

    it('keeps Add Product unavailable until a failed catalog request succeeds on Retry', async () => {
        queryOverride.current = useProductQuery;
        const user = userEvent.setup();
        renderWithQuery(<ProductsPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.getByRole('button', { name: 'Add Product' })).toBeDisabled();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(screen.getByRole('button', { name: 'Add Product' })).toBeEnabled());
    });

    it('hides audit integrity claims and export until the log loads on Retry', async () => {
        queryOverride.current = useAuditQuery;
        const user = userEvent.setup();
        renderWithQuery(<AuditLogPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByText(/Immutable, SHA-256 verified/)).not.toBeInTheDocument();
        expect(screen.queryByText('Hash-chained')).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: 'Export' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        await waitFor(() => expect(screen.getByText(/Immutable, SHA-256 verified/)).toBeInTheDocument());
    });

    it('offers Retry and support for notification preferences without Save Changes', async () => {
        queryOverride.current = () => ({ data: null, error: new Error('request failed'), isLoading: false, isFetching: false, refetch: queryRefetchMock });
        const user = userEvent.setup();
        renderWithQuery(<NotificationsPage />);

        expect(await screen.findByRole('alert', {}, { timeout: 5000 })).toHaveTextContent('We could not load this page.');
        expect(screen.getByRole('link', { name: 'Contact support' })).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'Save Changes' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(queryRefetchMock).toHaveBeenCalledOnce();
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
        queryOverride.current = () => ({ data: null, error: new Error('server error'), isLoading: false, refetch: queryRefetchMock });
        const user = userEvent.setup();
        renderWithQuery(<CompliancePage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(queryRefetchMock).toHaveBeenCalled();
    });

    it('lets recall report retry a failed request in place', async () => {
        queryOverride.current = () => ({ data: null, error: new Error('server error'), isLoading: false, refetch: queryRefetchMock });
        const user = userEvent.setup();
        renderWithQuery(<RecallReportPage />);

        expect(await screen.findByRole('alert')).toHaveTextContent('We could not load this page.');
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(queryRefetchMock).toHaveBeenCalledOnce();
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
        queryOverride.current = () => ({ data: null, error: null, isLoading: false, refetch: queryRefetchMock });
        const user = userEvent.setup();
        renderWithQuery(<SettingsPage />);

        expect(screen.getByRole('alert')).toHaveTextContent('We could not load this page.');
        expect(screen.queryByRole('button', { name: 'Manage Plan' })).not.toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Retry' }));
        expect(refetch).toHaveBeenCalledOnce();
    });
});
