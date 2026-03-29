/**
 * Issues & Blockers Page Tests
 *
 * Tests for the issues dashboard:
 * - Loading state (spinner)
 * - Data rendering when fetch succeeds
 * - Error state when fetch fails
 * - Empty state when no issues exist
 * - Auth guard (no fetch when unauthenticated)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import IssuesPage from '@/app/dashboard/issues/page';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

// ── Mocks ──

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
    usePathname: () => '/dashboard/issues',
    useSearchParams: () => new URLSearchParams(),
}));

const mockUseAuth = vi.fn();
vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

const mockUseTenant = vi.fn();
vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

// Mock framer-motion
vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
        span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    },
    AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock Breadcrumbs and Spinner
vi.mock('@/components/layout/breadcrumbs', () => ({
    Breadcrumbs: ({ items }: any) => (
        <nav aria-label="breadcrumb">
            {items.map((item: any, i: number) => (
                <span key={i}>{item.label}</span>
            ))}
        </nav>
    ),
}));

vi.mock('@/components/ui/spinner', () => ({
    Spinner: ({ size }: any) => <div role="status" aria-label="Loading">Loading...</div>,
}));

vi.mock('lucide-react', () => {
    const stub = (props: any) => <svg {...props} />;
    return {
        AlertTriangle: stub,
        ShieldAlert: stub,
        Clock: stub,
        XCircle: stub,
        CheckCircle2: stub,
        RefreshCw: stub,
        FileWarning: stub,
        Users: stub,
        Link2: stub,
        ChevronRight: stub,
        Timer: stub,
        Shield: stub,
    };
});

// Mock dynamic import of api-config
vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => 'http://localhost:8002',
}));

// ── Helpers ──

function mockDeadlinesAndBlockers(overrides: { deadlines?: any[]; blockerCheck?: any; pendingReviews?: any } = {}) {
    const deadlines = overrides.deadlines ?? [
        {
            request_case_id: 'case-1',
            package_status: 'incomplete',
            requesting_party: 'FDA Region 4',
            scope_description: 'Romaine lettuce trace-back',
            hours_remaining: 8,
            countdown_display: '8h remaining',
            urgency: 'critical',
            gap_count: 3,
            active_exception_count: 1,
        },
    ];

    const pendingReviews = overrides.pendingReviews ?? { supplier_data: 2, rule_changes: 1 };
    const blockerCheck = overrides.blockerCheck ?? {
        blockers: [{ type: 'critical_rule_failure', message: 'KDE missing on lot TOM-001' }],
        warnings: [{ type: 'data_gap', message: 'GLN not registered for supplier' }],
        blocker_count: 1,
        warning_count: 1,
    };

    global.fetch = vi.fn().mockImplementation((url: string) => {
        if (url.includes('/deadlines')) {
            return Promise.resolve({ ok: true, json: async () => ({ cases: deadlines }) });
        }
        if (url.includes('/pending-reviews')) {
            return Promise.resolve({ ok: true, json: async () => ({ breakdown: pendingReviews }) });
        }
        if (url.includes('/blockers')) {
            return Promise.resolve({ ok: true, json: async () => blockerCheck });
        }
        return Promise.resolve({ ok: false });
    });
}

describe('IssuesPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({ apiKey: 'test-api-key', isAuthenticated: true });
        mockUseTenant.mockReturnValue({ tenantId: 'tenant-123', isSystemTenant: false });
    });

    it('renders loading spinner initially', () => {
        // Fetch never resolves
        global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
        render(<IssuesPage />, { wrapper: createWrapper() });

        expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
    });

    it('renders page heading', () => {
        global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
        render(<IssuesPage />, { wrapper: createWrapper() });

        expect(screen.getByText('Issues & Blockers')).toBeInTheDocument();
    });

    it('renders data when fetches succeed', async () => {
        mockDeadlinesAndBlockers();
        render(<IssuesPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText(/FDA Region 4/)).toBeInTheDocument();
        });
        expect(screen.getByText(/KDE missing on lot TOM-001/)).toBeInTheDocument();
        expect(screen.getByText(/GLN not registered for supplier/)).toBeInTheDocument();
    });

    it('renders error state when data loading throws', async () => {
        // Override the api-config mock to throw, triggering the catch block
        const apiConfig = await import('@/lib/api-config');
        vi.spyOn(apiConfig, 'getServiceURL').mockImplementation(() => {
            throw new Error('Service unavailable');
        });

        render(<IssuesPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('Service unavailable')).toBeInTheDocument();
        });

        // Restore
        vi.mocked(apiConfig.getServiceURL).mockReturnValue('http://localhost:8002');
    });

    it('renders empty state when no issues found', async () => {
        mockDeadlinesAndBlockers({
            deadlines: [],
            blockerCheck: { blockers: [], warnings: [], blocker_count: 0, warning_count: 0 },
            pendingReviews: {},
        });
        render(<IssuesPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('No Issues Found')).toBeInTheDocument();
        });
    });

    it('does not fetch when apiKey is missing', () => {
        mockUseAuth.mockReturnValue({ apiKey: null, isAuthenticated: false });
        mockUseTenant.mockReturnValue({ tenantId: null, isSystemTenant: true });
        global.fetch = vi.fn();

        render(<IssuesPage />, { wrapper: createWrapper() });

        expect(global.fetch).not.toHaveBeenCalled();
    });
});
