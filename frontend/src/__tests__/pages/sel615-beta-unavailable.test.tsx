import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import SettingsPage from '@/app/dashboard/settings/page';
import ProductsPage from '@/app/dashboard/products/page';
import AuditLogPage from '@/app/dashboard/audit-log/page';
import NotificationsPage from '@/app/dashboard/notifications/page';

const fetchMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/fetch-with-csrf', () => ({ fetchWithCsrf: (...args: unknown[]) => fetchMock(...args) }));
vi.mock('@/lib/api-config', () => ({ getServiceURL: () => '/api/ingestion' }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ isAuthenticated: true, user: null }) }));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId: 't', isSystemTenant: false }) }));
vi.mock('@/hooks/use-billing', () => ({ useCurrentSubscription: () => ({ data: null, isLoading: false, isError: false }) }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ useDashboardRefresh: vi.fn() }));

beforeEach(() => fetchMock.mockReset());

for (const [name, Page, primaryPath] of [
    ['Settings', SettingsPage, '/api/v1/settings/t'],
    ['Products', ProductsPage, '/api/v1/products/t'],
    ['Audit Log', AuditLogPage, '/api/v1/audit-log/t'],
    ['Notifications', NotificationsPage, '/api/v1/notifications/t/preferences'],
] as const) {
    describe(name, () => {
        function renderPage() {
            const client = new QueryClient({ defaultOptions: { queries: { retry: false, retryDelay: 0 } } });
            render(<QueryClientProvider client={client}><Page /></QueryClientProvider>);
        }

        function expectProfileBlocked() {
            if (name === 'Settings') {
                expect(screen.getByRole('button', { name: 'Save Changes' })).toBeDisabled();
                expect(screen.queryByLabelText('Company Type')).not.toBeInTheDocument();
            }
        }

        it.each([404, 403])('shows Beta unavailable for HTTP %s', async status => {
            fetchMock.mockResolvedValue(new Response(null, { status }));
            renderPage();
            expect(await screen.findByText(/not yet available in RegEngine Beta/)).toBeVisible();
            expect(screen.queryByText(/Couldn't load|We could not load/)).not.toBeInTheDocument();
            expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument();
            expectProfileBlocked();
            expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(primaryPath), expect.anything());
        });

        it.each(['server', 'network'] as const)('keeps ErrorState and working retry for %s failure', async failure => {
            if (failure === 'server') fetchMock.mockResolvedValue(new Response(null, { status: 503 }));
            else fetchMock.mockResolvedValue(Response.error());
            renderPage();
            expect(await screen.findByRole('alert')).toHaveTextContent("Couldn't load this");
            expect(screen.queryByText(/not yet available in RegEngine Beta/)).not.toBeInTheDocument();
            expect(screen.getByRole('link', { name: 'Contact support' })).toBeVisible();
            expectProfileBlocked();
            const callsBeforeRetry = fetchMock.mock.calls.filter(([url]) => url.includes(primaryPath)).length;
            await userEvent.setup().click(screen.getByRole('button', { name: 'Retry' }));
            await waitFor(() => expect(fetchMock.mock.calls.filter(([url]) => url.includes(primaryPath)).length).toBeGreaterThan(callsBeforeRetry));
        });
    });
}
