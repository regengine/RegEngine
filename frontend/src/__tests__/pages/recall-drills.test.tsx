/**
 * Recall Drills Page Tests
 *
 * Tests for the recall drill workspace:
 * - Loading state
 * - Data rendering when fetch succeeds
 * - Error state when drill start fails
 * - Empty state when no drills exist
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RecallDrillsPage from '@/app/dashboard/recall-drills/page';

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
    usePathname: () => '/dashboard/recall-drills',
    useSearchParams: () => new URLSearchParams(),
}));

const mockUseAuth = vi.fn();
vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('lucide-react', () => {
    const stub = (props: any) => <svg {...props} />;
    return {
        PlayCircle: stub,
        ShieldAlert: stub,
        TimerReset: stub,
        FileText: stub,
        Link2Off: stub,
    };
});

// ── Helpers ──

const SAMPLE_DRILLS = [
    {
        id: 'drill-1',
        scenario: 'Weekend retailer trace-back',
        lots: ['TOM-0226-F3-001', 'LET-0310-WH-21'],
        dateRange: '2026-03-01 to 2026-03-12',
        status: 'completed',
        elapsed: '3h 42m',
        artifacts: ['FDA package', 'manifest.json'],
        warnings: ['2 lots had partial CTE data'],
    },
    {
        id: 'drill-2',
        scenario: 'Holiday supply chain drill',
        lots: ['SPR-0401-GR-05'],
        dateRange: '2026-02-15 to 2026-02-28',
        status: 'in_progress',
        elapsed: '1h 10m',
        artifacts: ['EPCIS export'],
        warnings: [],
    },
];

function mockFetchSuccess(drills = SAMPLE_DRILLS) {
    global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => ({ drills }),
    });
}

describe('RecallDrillsPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            apiKey: 'test-api-key',
            isAuthenticated: true,
            tenantId: 'tenant-123',
        });
    });

    it('renders loading state initially', () => {
        global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        expect(screen.getByText('Loading drill history...')).toBeInTheDocument();
    });

    it('renders drill runs when fetch succeeds', async () => {
        mockFetchSuccess();
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('Weekend retailer trace-back')).toBeInTheDocument();
        });
        expect(screen.getByText('Holiday supply chain drill')).toBeInTheDocument();
        expect(screen.getByText(/3h 42m/)).toBeInTheDocument();
    });

    it('renders empty state when no drills exist', async () => {
        mockFetchSuccess([]);
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('No drills yet')).toBeInTheDocument();
        });
    });

    it('renders page heading', () => {
        global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        expect(screen.getByText('Recall Drill Workspace')).toBeInTheDocument();
    });

    it('renders warnings for drills that have them', async () => {
        mockFetchSuccess();
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('2 lots had partial CTE data')).toBeInTheDocument();
        });
    });

    it('renders error state when starting a drill fails', async () => {
        // First call: load succeeds with existing drills
        // Second call: POST fails
        global.fetch = vi.fn()
            .mockResolvedValueOnce({ ok: true, json: async () => ({ drills: SAMPLE_DRILLS }) })
            .mockResolvedValueOnce({ ok: false, status: 500 });

        const user = userEvent.setup();
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('Weekend retailer trace-back')).toBeInTheDocument();
        });

        const startButton = screen.getByRole('button', { name: /start drill/i });
        await user.click(startButton);

        await waitFor(() => {
            // The page surfaces the mutation error message directly
            expect(screen.getByText(/could not start the drill|failed to start drill/i)).toBeInTheDocument();
        });
    });
});
