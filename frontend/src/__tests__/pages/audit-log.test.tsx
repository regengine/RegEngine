import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AuditLogPage from '@/app/dashboard/audit-log/page';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
        },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

const mockUseAuth = vi.fn();
vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

const mockUseTenant = vi.fn();
vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

const mockListSupplierFacilities = vi.fn();
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        listSupplierFacilities: () => mockListSupplierFacilities(),
    },
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/ingestion',
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
    useDashboardRefresh: vi.fn(),
}));

vi.mock('@/components/layout/breadcrumbs', () => ({
    Breadcrumbs: ({ items }: { items: Array<{ label: string }> }) => (
        <nav aria-label="breadcrumb">
            {items.map((item) => (
                <span key={item.label}>{item.label}</span>
            ))}
        </nav>
    ),
}));

vi.mock('@/components/ui/spinner', () => ({
    Spinner: ({ size }: { size?: string }) => <div role="status">Loading {size}</div>,
}));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    },
    AnimatePresence: ({ children }: any) => <>{children}</>,
}));

vi.mock('lucide-react', () => {
    const stub = (props: any) => <svg {...props} />;
    return {
        ScrollText: stub,
        Database: stub,
        ShieldCheck: stub,
        Upload: stub,
        User: stub,
        Webhook: stub,
        AlertTriangle: stub,
        Filter: stub,
        Clock: stub,
        RefreshCw: stub,
        ChevronLeft: stub,
        ChevronRight: stub,
        ChevronDown: stub,
        Search: stub,
        Download: stub,
        Hash: stub,
        Info: stub,
        Shield: stub,
    };
});

function mockAuditFetch(entries = [
    {
        id: 'event-1',
        timestamp: '2026-05-07T01:00:00.000Z',
        event_type: 'export',
        category: 'compliance',
        actor: 'ops@example.com',
        action: 'Generated export',
        resource: 'FDA package',
        details: {},
        ip_address: '127.0.0.1',
        hash: 'a'.repeat(64),
    },
    {
        id: 'event-2',
        timestamp: '2026-05-07T02:00:00.000Z',
        event_type: 'api_call',
        category: 'integration',
        actor: 'worker',
        action: 'Submitted lot',
        resource: 'LOT-123',
        details: {},
        ip_address: '127.0.0.2',
        hash: 'b'.repeat(64),
    },
]) {
    global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
            tenant_id: 'tenant-123',
            total: entries.length,
            page: 1,
            page_size: 50,
            entries,
        }),
    }) as any;
}

describe('AuditLogPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            apiKey: null,
        });
        mockUseTenant.mockReturnValue({
            tenantId: 'tenant-123',
            isSystemTenant: false,
        });
        mockListSupplierFacilities.mockResolvedValue([]);
    });

    it('renders audit entries when the fetch succeeds', async () => {
        mockAuditFetch();
        render(<AuditLogPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('Generated export')).toBeInTheDocument();
        });
        expect(screen.getByText('Submitted lot')).toBeInTheDocument();
    });

    it('keeps the internal audit-log fetch cookie-backed and headerless', async () => {
        mockAuditFetch();
        render(<AuditLogPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalled();
        });

        const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit | undefined][];
        const [url, init] = calls[0]!;

        expect(url).toBe('/api/ingestion/api/v1/audit-log/tenant-123?page=1&page_size=50');
        expect(init?.credentials).toBe('include');
        expect(new Headers(init?.headers).get('Content-Type')).toBe('application/json');
        expect(new Headers(init?.headers).get('X-RegEngine-API-Key')).toBeNull();
    });

    it('renders only API-returned entries without injecting synthetic facility rows', async () => {
        mockAuditFetch([
            {
                id: 'event-1',
                timestamp: '2026-05-07T01:00:00.000Z',
                event_type: 'export',
                category: 'compliance',
                actor: 'ops@example.com',
                action: 'Generated export',
                resource: 'FDA package',
                details: {},
                ip_address: '127.0.0.1',
                hash: 'a'.repeat(64),
            },
        ]);
        mockListSupplierFacilities.mockResolvedValue([
            { id: 'facility-1', name: 'North Packing House' },
        ]);

        render(<AuditLogPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('Generated export')).toBeInTheDocument();
        });
        expect(screen.queryByText('facility_created')).not.toBeInTheDocument();
        expect(screen.queryByText('North Packing House')).not.toBeInTheDocument();
        expect(mockListSupplierFacilities).not.toHaveBeenCalled();
    });

    it('describes the empty audit log as hash-chained, not signed', async () => {
        mockAuditFetch([]);
        render(<AuditLogPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('No Audit Entries Yet')).toBeInTheDocument();
        });

        // Audit entries are SHA-256 hash-chained and guarded by append-only
        // triggers; no digital signature is applied, so copy must not say so.
        expect(screen.getByText(/SHA-256 hash-chained/i)).toBeInTheDocument();
        expect(screen.queryByText(/cryptographically signed/i)).not.toBeInTheDocument();
    });

    it('does not fetch when the user is signed out', () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
            apiKey: null,
        });
        mockUseTenant.mockReturnValue({
            tenantId: null,
            isSystemTenant: true,
        });
        global.fetch = vi.fn();

        render(<AuditLogPage />, { wrapper: createWrapper() });

        expect(screen.getByText('Sign in to view the audit log.')).toBeInTheDocument();
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
