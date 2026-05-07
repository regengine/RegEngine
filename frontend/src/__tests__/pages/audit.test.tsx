import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import AuditReviewPage from '@/app/audit/page';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

const mockUseAuth = vi.fn();

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/components/control-plane/demo-banner', () => ({
    DemoBanner: () => null,
}));

vi.mock('@/components/layout/page-container', () => ({
    PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/ui/card', () => ({
    Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    CardDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    CardTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/ui/badge', () => ({
    Badge: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/ui/skeleton', () => ({
    Skeleton: () => <div>Loading...</div>,
}));

vi.mock('@/components/ui/progress', () => ({
    Progress: () => <div data-testid="progress" />,
}));

vi.mock('lucide-react', () => {
    const stub = (props: any) => <svg {...props} />;
    return {
        CheckCircle: stub,
        Eye: stub,
        FileText: stub,
        Hash: stub,
        Shield: stub,
        AlertTriangle: stub,
        XCircle: stub,
        Database: stub,
        Timer: stub,
        Lock: stub,
    };
});

describe('AuditReviewPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            tenantId: 'tenant-123',
        });
        global.fetch = vi.fn().mockImplementation((url: string) => {
            if (url.includes('/summary')) {
                return Promise.resolve({
                    ok: true,
                    json: async () => ({
                        records: { total_canonical_events: 24, ingestion_sources: { edi: 24 } },
                        compliance: { total_evaluations: 120, pass_rate_percent: 92.5, passed: 111, failed: 5, warned: 4 },
                        exceptions: { total: 3, open: 1, critical_open: 0 },
                        requests: { total: 2, submitted: 1, active: 1 },
                        chain_integrity: { chain_length: 24, status: 'VERIFIED' },
                        generated_at: '2026-05-07T00:00:00.000Z',
                    }),
                });
            }
            if (url.includes('/rules')) {
                return Promise.resolve({
                    ok: true,
                    json: async () => ({
                        rules: [
                            {
                                rule_id: 'rule-1',
                                title: 'Record completeness audit',
                                severity: 'warning',
                                evaluation_stats: { total: 120, pass_rate_percent: 92.5 },
                            },
                        ],
                    }),
                });
            }
            return Promise.resolve({ ok: false, json: async () => ({ detail: 'Unexpected request' }) });
        });
    });

    it('uses cookie-backed audit routes without tenant or API-key overrides', async () => {
        render(<AuditReviewPage />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledTimes(2);
        });

        const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls as [string, RequestInit | undefined][];
        const urls = calls.map(([url]) => url);

        expect(urls).toEqual([
            '/api/ingestion/api/v1/audit/summary',
            '/api/ingestion/api/v1/audit/rules',
        ]);
        expect(urls.some(url => url.includes('tenant_id='))).toBe(false);

        for (const [, init] of calls) {
            expect(init?.credentials).toBe('include');
            expect(new Headers(init?.headers).get('X-RegEngine-API-Key')).toBeNull();
        }
    });

    it('does not fetch when auth is unavailable', () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
            tenantId: null,
        });
        global.fetch = vi.fn();

        render(<AuditReviewPage />, { wrapper: createWrapper() });

        expect(global.fetch).not.toHaveBeenCalled();
    });
});
