/**
 * Recall Report Page Tests
 *
 * Tests for the recall investigation / readiness report:
 * - Renders heading and demo scenario
 * - Renders dimension scores
 * - Falls back to demo data when API is unavailable
 * - Auth guard (skips fetch without credentials)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RecallReportPage from '@/app/dashboard/recall-report/page';

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
    usePathname: () => '/dashboard/recall-report',
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

const mockFetchRecallReport = vi.fn();
vi.mock('@/lib/api-hooks', () => ({
    fetchRecallReport: (...args: any[]) => mockFetchRecallReport(...args),
}));

// Mock framer-motion
vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
        span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
        circle: (props: any) => <circle {...props} />,
    },
    AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock Breadcrumbs
vi.mock('@/components/layout/breadcrumbs', () => ({
    Breadcrumbs: ({ items }: any) => (
        <nav aria-label="breadcrumb">
            {items.map((item: any, i: number) => (
                <span key={i}>{item.label}</span>
            ))}
        </nav>
    ),
}));

// Mock next/link
vi.mock('next/link', () => ({
    default: ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

vi.mock('lucide-react', () => {
    const stub = (props: any) => <svg {...props} />;
    return {
        Download: stub,
        Timer: stub,
        Database: stub,
        ShieldCheck: stub,
        Users: stub,
        Upload: stub,
        GraduationCap: stub,
        AlertTriangle: stub,
        ArrowUp: stub,
        ArrowRight: stub,
        Play: stub,
        Package: stub,
        MapPin: stub,
        Clock: stub,
        CheckCircle2: stub,
        XCircle: stub,
        ShoppingCart: stub,
        Zap: stub,
        Info: stub,
        ChevronDown: stub,
        ChevronUp: stub,
    };
});

// Mock api-config for dynamic import
vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => 'http://localhost:8002',
}));

describe('RecallReportPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({ apiKey: 'test-api-key', isAuthenticated: true });
        mockUseTenant.mockReturnValue({ tenantId: 'tenant-123', isSystemTenant: false });
        // Default: API returns empty, so demo scenario is used
        mockFetchRecallReport.mockResolvedValue(null);
    });

    it('renders page heading', async () => {
        render(<RecallReportPage />, { wrapper: createWrapper() });

        expect(screen.getByText('Recall Investigation')).toBeInTheDocument();
    });

    it('renders demo investigation scenario data', async () => {
        render(<RecallReportPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText(/Romaine Lettuce/)).toBeInTheDocument();
        });
    });

    it('renders readiness dimension scores', async () => {
        render(<RecallReportPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText('Trace Speed')).toBeInTheDocument();
        });
        expect(screen.getByText('Data Completeness')).toBeInTheDocument();
        expect(screen.getByText('Chain Integrity')).toBeInTheDocument();
        expect(screen.getByText('Supplier Coverage')).toBeInTheDocument();
    });

    it('renders affected lots table', async () => {
        render(<RecallReportPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(screen.getByText(/LOT-ROM-2026-0312A/)).toBeInTheDocument();
        });
    });

    it('falls back to demo when API returns empty data', async () => {
        mockFetchRecallReport.mockResolvedValue({});
        render(<RecallReportPage />, { wrapper: createWrapper() });

        // Should still show the demo scenario since empty object triggers demo fallback
        await waitFor(() => {
            expect(screen.getByText(/Romaine Lettuce/)).toBeInTheDocument();
        });
    });

    it('falls back to demo when API call fails', async () => {
        mockFetchRecallReport.mockRejectedValue(new Error('API unavailable'));
        render(<RecallReportPage />, { wrapper: createWrapper() });

        // Should still show the demo scenario
        await waitFor(() => {
            expect(screen.getByText(/Romaine Lettuce/)).toBeInTheDocument();
        });
    });

    it('does not fetch when credentials are missing', () => {
        mockUseAuth.mockReturnValue({ apiKey: null, isAuthenticated: false });
        mockUseTenant.mockReturnValue({ tenantId: null, isSystemTenant: true });

        render(<RecallReportPage />, { wrapper: createWrapper() });

        expect(mockFetchRecallReport).not.toHaveBeenCalled();
    });
});
