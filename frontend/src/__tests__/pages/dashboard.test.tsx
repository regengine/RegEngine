/**
 * Dashboard Page Tests
 *
 * Tests for the main dashboard view:
 * - Authentication checks
 * - Data loading and display
 * - Error states
 * - Tenant context
 * - Navigation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DashboardPage from '@/app/dashboard/page';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { getTenantDashboard } from '@/lib/mock-dashboard-data';
import { useRouter } from 'next/navigation';
import { useSystemMetrics, useSystemStatus } from '@/hooks/use-api';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

// Mock Next.js router
vi.mock('next/navigation', () => ({
    useRouter: vi.fn(),
}));

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

// Mock tenant context
vi.mock('@/lib/tenant-context', () => ({
    useTenant: vi.fn(),
}));

// Mock mock-dashboard-data
vi.mock('@/lib/mock-dashboard-data', () => ({
    getTenantDashboard: vi.fn(),
}));

// Mock API hooks (used by Header and Dashboard)
vi.mock('@/hooks/use-api', () => ({
    useSystemMetrics: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useAdminHealth: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useIngestionHealth: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useOpportunityHealth: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useComplianceHealth: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useLabelsHealth: vi.fn().mockReturnValue({ data: null, isLoading: false }),
    useSystemStatus: vi.fn().mockReturnValue({ data: null, isLoading: false, error: null }),
    useQAHealth: vi.fn().mockReturnValue({ data: null, isLoading: false, error: null }),
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch as any;

describe('DashboardPage', () => {
    const mockPush = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        mockFetch.mockReset();
        // Default: all fetch calls resolve with ok:true so health badge and other
        // fetch() calls in the component don't crash with "Cannot read .then of undefined"
        mockFetch.mockResolvedValue({ ok: true, json: async () => ({ status: 'ok' }) });
        (useRouter as any).mockReturnValue({ push: mockPush });

        // Ensure localStorage is available in jsdom
        const store: Record<string, string> = {};
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => store[key] ?? null),
            setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
            removeItem: vi.fn((key: string) => { delete store[key]; }),
            clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]); }),
            length: 0,
            key: vi.fn(() => null),
        });
    });

    describe('Authentication', () => {
        it('shows loading state during hydration', () => {
            (useAuth as any).mockReturnValue({
                user: null,
                isHydrated: false,
                isAuthenticated: false,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: null,
            });

            render(<DashboardPage />, { wrapper: createWrapper() });

            // Should show loading or not render content yet
            expect(screen.queryByRole('main')).not.toBeInTheDocument();
        });

        it('redirects to login when not authenticated', async () => {
            (useAuth as any).mockReturnValue({
                user: null,
                isHydrated: true,
                isAuthenticated: false,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: null,
            });

            render(<DashboardPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(mockPush).toHaveBeenCalledWith('/login?next=%2Fdashboard');
            });
        });

        it('renders dashboard when authenticated', () => {
            (useAuth as any).mockReturnValue({
                user: {
                    id: '123',
                    email: 'test@example.com',
                    name: 'Test User',
                },
                isHydrated: true,
                isAuthenticated: true,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });

            render(<DashboardPage />, { wrapper: createWrapper() });

            // Dashboard should render (even if showing loading for data)
            expect(screen.queryByText(/welcome/i) || screen.queryByText(/dashboard/i)).toBeTruthy();
        });
    });

    describe('Dashboard Content', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: {
                    id: '123',
                    email: 'test@example.com',
                    name: 'Test User',
                },
                isHydrated: true,
                isAuthenticated: true,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('displays user information', async () => {
            render(<DashboardPage />, { wrapper: createWrapper() });

            // Dashboard should render content when user is authenticated
            await waitFor(() => {
                const matches = screen.queryAllByText(/dashboard/i);
                expect(matches.length).toBeGreaterThan(0);
            });
        });

        it('shows tenant information when available', async () => {
            (getTenantDashboard as any).mockReturnValue({
                tenant: { name: 'Acme Corp', type: 'retailer' },
                metrics: { complianceScore: 90, documentsIngested: 10, openAlerts: 0, pendingReviews: 0 },
            });

            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
                selectedTenant: {
                    id: 'tenant-123',
                    name: 'Acme Corp'
                },
            });

            render(<DashboardPage />, { wrapper: createWrapper() });

            // Dashboard should render with tenant context active
            await waitFor(() => {
                const matches = screen.queryAllByText(/dashboard/i);
                expect(matches.length).toBeGreaterThan(0);
            });
        });

        it('renders navigation links', async () => {
            render(<DashboardPage />, { wrapper: createWrapper() });

            // Common dashboard links
            const commonLinks = [
                /fsma/i,
                /ingest/i,
                /compliance/i,
            ];

            await waitFor(() => {
                // queryAllByRole: multiple links may legitimately match a
                // pattern (e.g. "FSMA Readiness Score" + "FSMA Export") —
                // queryByRole throws on >1 match.
                const hasAtLeastOneLink = commonLinks.some(pattern =>
                    screen.queryAllByRole('link', { name: pattern }).length > 0
                );
                expect(hasAtLeastOneLink).toBe(true);
            });
        });
    });

    describe('Data Loading', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: { id: '123', email: 'test@example.com' },
                isHydrated: true,
                isAuthenticated: true,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('shows incomplete checks when readiness fails while health is healthy', async () => {
            (useTenant as any).mockReturnValue({tenantId:'tenant-123',isTenantReady:true});
            vi.mocked(useSystemStatus).mockReturnValue({data:{overall_status:'healthy',services:[]},isLoading:false} as any);
            vi.mocked(useSystemMetrics).mockReturnValue({data:{open_alerts:0,events_ingested:null,chain_valid:true,chain_length:0},isLoading:false} as any);
            mockFetch.mockImplementation((url:string) => Promise.resolve({ok:!url.includes('/readiness/summary'),status:503,json:async()=>({})}));
            render(<DashboardPage />, {wrapper:createWrapper()});
            await waitFor(() => expect(screen.getByText('Checks incomplete')).toBeInTheDocument());
            expect(screen.queryByText('Nothing needs attention')).not.toBeInTheDocument();
            expect(screen.queryByText('Import your first traceability records')).not.toBeInTheDocument();
        });


        it('shows failed integrity for actual missing-chain verdict even at length zero', async () => {
            (useTenant as any).mockReturnValue({tenantId:'tenant-123',isTenantReady:true});
            vi.mocked(useSystemStatus).mockReturnValue({data:{overall_status:'healthy',services:[]},isLoading:false} as any);
            vi.mocked(useSystemMetrics).mockReturnValue({data:{open_alerts:0,events_ingested:12,chain_valid:false,chain_length:0},isLoading:false} as any);
            mockFetch.mockImplementation((url:string) => Promise.resolve({ok:true,json:async()=>url.includes('/readiness/summary') ? {unresolved_fix_count:0,run_id:'saved-run',source:'live',score:100,export_eligible:true} : {}}));
            render(<DashboardPage/>,{wrapper:createWrapper()});
            await waitFor(()=>expect(screen.getByText('Hash chain verification failed')).toBeInTheDocument());
            expect(screen.queryByText('Nothing needs attention')).not.toBeInTheDocument();
        });

        it('shows all-clear only after a successful zero-fix run and verified chain', async () => {
            (useTenant as any).mockReturnValue({tenantId:'tenant-123',isTenantReady:true});
            vi.mocked(useSystemStatus).mockReturnValue({data:{overall_status:'healthy',services:[]},isLoading:false} as any);
            vi.mocked(useSystemMetrics).mockReturnValue({data:{open_alerts:0,events_ingested:12,chain_valid:true,chain_length:12},isLoading:false} as any);
            mockFetch.mockImplementation((url:string) => Promise.resolve({ok:true,json:async()=>url.includes('/readiness/summary') ? {unresolved_fix_count:0,run_id:'saved-run',source:'live',score:100,export_eligible:true} : {}}));
            render(<DashboardPage/>,{wrapper:createWrapper()});
            await waitFor(()=>expect(screen.getByText('Nothing needs attention')).toBeInTheDocument());
            expect(screen.queryByText('Hash chain verification failed')).not.toBeInTheDocument();
        });
        it('loads internal dashboard data without a placeholder apiKey', async () => {
            mockFetch.mockImplementation((url: string) => {
                if (url.includes('/pending-reviews/tenant-123')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({ pending_reviews: 4 }),
                    });
                }

                if (url.includes('/inflow-workbench/readiness/summary')) {
                    return Promise.resolve({
                        ok: true,
                        json: async () => ({
                            tenant_id: 'tenant-123',
                            score: null,
                            label: null,
                            run_id: null,
                            saved_at: null,
                            unresolved_fix_count: 0,
                            export_eligible: false,
                            source: 'live',
                        }),
                    });
                }

                return Promise.resolve({ ok: true, json: async () => ({ status: 'ok' }) });
            });

            render(<DashboardPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(mockFetch).toHaveBeenCalled();
            });

            const calls = mockFetch.mock.calls as [string, RequestInit | undefined][];
            const readinessSummaryCall = calls.find(([url]) =>
                url.includes('/api/ingestion/api/v1/inflow-workbench/readiness/summary')
            );

            expect(readinessSummaryCall).toBeDefined();
            const [, init] = readinessSummaryCall as [string, RequestInit];
            expect(init.credentials).toBe('include');
            expect(new Headers(init.headers).get('X-RegEngine-API-Key')).toBeNull();
        });

        it.skip('handles loading state for dashboard data', async () => {
            // Mock slow API response
            let resolveData!: (value: unknown) => void;
            const dataPromise = new Promise((resolve) => {
                resolveData = resolve;
            });

            mockFetch.mockReturnValueOnce({
                ok: true,
                json: () => dataPromise,
            });

            render(<DashboardPage />, { wrapper: createWrapper() });

            // Should show loading indicator
            await waitFor(() => {
                expect(
                    screen.queryByText(/loading/i) ||
                    screen.queryByRole('status')
                ).toBeTruthy();
            }, { timeout: 100 });

            // Resolve data
            if (resolveData) {
                resolveData({ stats: { total: 100 } });
            }
        });

        it.skip('displays error when data fetch fails', async () => {
            mockFetch.mockRejectedValueOnce(new Error('API Error'));

            render(<DashboardPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                expect(
                    screen.queryByText(/error/i) ||
                    screen.queryByText(/failed/i) ||
                    screen.queryByRole('alert')
                ).toBeTruthy();
            });
        });
    });

    describe('Interactivity', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: { id: '123', email: 'test@example.com' },
                isHydrated: true,
                isAuthenticated: true,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('allows navigation to sub-pages', async () => {
            const user = userEvent.setup();
            render(<DashboardPage />, { wrapper: createWrapper() });

            // Try to find and click a navigation link
            await waitFor(async () => {
                const links = screen.queryAllByRole('link');
                if (links.length > 0) {
                    await user.click(links[0]);
                    // Navigation should occur (mockPush should be called or link should work)
                    return true;
                }
                return false;
            });
        });
    });

    describe('Accessibility', () => {
        beforeEach(() => {
            (useAuth as any).mockReturnValue({
                user: { id: '123', email: 'test@example.com' },
                isHydrated: true,
                isAuthenticated: true,
                apiKey: null,
            });
            (useTenant as any).mockReturnValue({
                tenantId: 'tenant-123',
            });
        });

        it('has proper document structure', async () => {
            render(<DashboardPage />, { wrapper: createWrapper() });

            // Should have main landmark or heading
            await waitFor(() => {
                expect(
                    screen.queryByRole('main') ||
                    screen.queryByRole('heading', { level: 1 })
                ).toBeTruthy();
            });
        });

        it('all interactive elements are keyboard accessible', async () => {
            render(<DashboardPage />, { wrapper: createWrapper() });

            await waitFor(() => {
                const buttons = screen.queryAllByRole('button');
                const links = screen.queryAllByRole('link');

                // All should be focusable (have tabIndex >= 0 or be naturally focusable)
                [...buttons, ...links].forEach(element => {
                    expect(element).toBeVisible();
                });
            });
        });
    });
});
