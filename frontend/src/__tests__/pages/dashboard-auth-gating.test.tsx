import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseTenant = vi.hoisted(() => vi.fn());
const mockUseCurrentSubscription = vi.hoisted(() => vi.fn());

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: Infinity },
            mutations: { retry: false, gcTime: Infinity },
        },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

vi.mock('@/hooks/use-billing', () => ({
    useCurrentSubscription: (...args: any[]) => mockUseCurrentSubscription(...args),
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
    useDashboardRefresh: () => undefined,
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/ingestion',
}));

vi.mock('next/link', () => ({
    default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, layout, transition, ...props }: any) => <div {...props}>{children}</div>,
        span: ({ children, layout, transition, ...props }: any) => <span {...props}>{children}</span>,
    },
}));

vi.mock('@/components/ui/card', () => ({
    Card: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardContent: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardHeader: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardTitle: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardDescription: ({ children, ...props }: any) => <div {...props}>{children}</div>,
}));

vi.mock('@/components/ui/button', () => ({
    Button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/ui/badge', () => ({
    Badge: ({ children, ...props }: any) => <span {...props}>{children}</span>,
}));

vi.mock('@/components/ui/input', () => ({
    Input: (props: any) => <input {...props} />,
}));

vi.mock('@/components/ui/spinner', () => ({
    Spinner: () => <div>Loading...</div>,
}));

vi.mock('@/components/layout/breadcrumbs', () => ({
    Breadcrumbs: () => <nav aria-label="breadcrumb" />,
}));

vi.mock('lucide-react', () => {
    const Stub = (props: any) => <svg {...props} />;
    return {
        AlertTriangle: Stub,
        Settings: Stub,
        Building2: Stub,
        Key: Stub,
        Database: Stub,
        Plug: Stub,
        Save: Stub,
        CheckCircle2: Stub,
        Copy: Stub,
        Eye: Stub,
        EyeOff: Stub,
        CreditCard: Stub,
        BarChart3: Stub,
        Shield: Stub,
        RefreshCw: Stub,
        Clock: Stub,
        ExternalLink: Stub,
        ChevronRight: Stub,
        Zap: Stub,
        Globe: Stub,
        ArrowRight: Stub,
        Lock: Stub,
        Loader2: Stub,
        Bell: Stub,
        Mail: Stub,
        MessageSquare: Stub,
        Webhook: Stub,
        Smartphone: Stub,
        ArrowUp: Stub,
        Package: Stub,
        Plus: Stub,
        ShieldCheck: Stub,
        Tag: Stub,
        Barcode: Stub,
        Users: Stub,
        Activity: Stub,
        Leaf: Stub,
        UserCog: Stub,
        Crown: Stub,
        Edit3: Stub,
        Trash2: Stub,
        X: Stub,
    };
});

function mockAuthenticatedSession() {
    mockUseAuth.mockReturnValue({
        user: { id: 'user-1', email: 'owner@example.com' },
        isAuthenticated: true,
        apiKey: null,
    });
    mockUseTenant.mockReturnValue({ tenantId: 'tenant-123', isSystemTenant: false });
    mockUseCurrentSubscription.mockReturnValue({
        data: null,
        isLoading: false,
        isError: false,
    });
}

function expectNoApiKeyHeader(callIndex = 0) {
    const [, init] = fetchWithCsrfMock.mock.calls[callIndex] as [string, RequestInit | undefined];
    const headers = new Headers(init?.headers);
    expect(headers.get('X-RegEngine-API-Key')).toBeNull();
}

describe('dashboard auth gating cleanup', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.spyOn(AbortSignal, 'timeout').mockImplementation(() => new AbortController().signal);
        mockAuthenticatedSession();
    });

    it('settings page fetches integrations when authenticated even if apiKey is null', async () => {
        const { default: SettingsPage } = await import('@/app/dashboard/settings/page');
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({ integrations: [] }),
        });

        render(<SettingsPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/integrations/status/tenant-123',
                expect.objectContaining({
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                }),
            );
        });
        expectNoApiKeyHeader();
    });

    it('notifications page fetches preferences without relying on placeholder apiKey headers', async () => {
        const { default: NotificationPrefsPage } = await import('@/app/dashboard/notifications/page');
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: 'tenant-123',
                channels: [],
                alert_preferences: [],
                quiet_hours: { enabled: false, start_hour: 22, end_hour: 6, timezone: 'UTC', override_critical: true },
                escalation: { enabled: false, escalate_after_minutes: 30, escalate_to: 'admin' },
                digest_enabled: false,
                digest_frequency: 'daily',
                digest_time: '08:00',
            }),
        });

        render(<NotificationPrefsPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/notifications/tenant-123/preferences',
                expect.objectContaining({
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                }),
            );
        });
        expectNoApiKeyHeader();
    });

    it('products page fetches catalog through cookie-backed requests when apiKey is null', async () => {
        const { default: ProductCatalogPage } = await import('@/app/dashboard/products/page');
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: 'tenant-123',
                total: 1,
                ftl_covered: 1,
                categories: ['Leafy Greens'],
                products: [
                    {
                        id: 'product-1',
                        name: 'Spinach',
                        category: 'Leafy Greens',
                        ftl_covered: true,
                        sku: 'SPIN-001',
                        gtin: '',
                        description: '',
                        suppliers: [],
                        facilities: [],
                        cte_count: 2,
                        last_cte: null,
                        created_at: '2026-05-07T00:00:00.000Z',
                    },
                ],
            }),
        });

        render(<ProductCatalogPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/products/tenant-123',
                expect.objectContaining({
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                }),
            );
        });
        expectNoApiKeyHeader();
    });

    it('team page fetches members without requiring apiKey truthiness', async () => {
        const { default: TeamPage } = await import('@/app/dashboard/team/page');
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: 'tenant-123',
                total_members: 1,
                active_members: 1,
                pending_invites: 0,
                roles_breakdown: { admin: 1 },
                members: [
                    {
                        id: 'member-1',
                        name: 'Casey Chen',
                        email: 'casey@example.com',
                        role: 'admin',
                        status: 'active',
                        last_active: '5m ago',
                        invited_at: null,
                        avatar_initials: 'CC',
                    },
                ],
            }),
        });

        render(<TeamPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledWith(
                '/api/ingestion/api/v1/team/tenant-123',
                expect.objectContaining({
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                }),
            );
        });
        expectNoApiKeyHeader();
    });

    it('still blocks these pages when the user is not authenticated', async () => {
        const { default: TeamPage } = await import('@/app/dashboard/team/page');
        mockUseAuth.mockReturnValue({
            user: null,
            isAuthenticated: false,
            apiKey: null,
        });
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({}),
        });

        render(<TeamPage />, { wrapper: createWrapper() });

        expect(fetchWithCsrfMock).not.toHaveBeenCalled();
    });
});
