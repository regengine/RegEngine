/**
 * React Hook Tests - use-control-plane
 *
 * Tests for the FSMA 204 Compliance Control Plane hooks:
 * - cpFetch proxy routing via /api/ingestion
 * - Query hooks: useRules, useExceptions, useCanonicalEvents, useRequestCases, useEntities, useIdentityReviews
 * - Mutation hooks: useResolveException, useCreateRequestCase, useSeedRules
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// Mock useAuth to provide apiKey (cookie-managed placeholder satisfies !!apiKey checks)
vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(() => ({
        apiKey: 'cookie-managed',
        user: { id: '1', email: 'test@example.com' },
        accessToken: 'cookie-managed',
        isAuthenticated: true,
    })),
}));

// Mock polling config to avoid env var issues in tests
vi.mock('@/lib/polling-config', () => ({
    POLL_CONTROL_PLANE_MS: false,
    POLL_DATA_MS: false,
    POLL_METRICS_MS: false,
}));

import {
    useRules,
    useExceptions,
    useCanonicalEvents,
    useRequestCases,
    useEntities,
    useIdentityReviews,
    useResolveException,
    useCreateRequestCase,
    useSeedRules,
} from '@/hooks/use-control-plane';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });
    return ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

const TENANT_ID = 'tenant-test-001';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('use-control-plane hooks', () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
        vi.clearAllMocks();
    });

    afterEach(() => {
        global.fetch = originalFetch;
    });

    // -----------------------------------------------------------------------
    // cpFetch proxy behavior
    // -----------------------------------------------------------------------

    describe('cpFetch proxy routing', () => {
        it('routes requests through /api/ingestion proxy', async () => {
            const realData = {
                cases: [
                    { case_id: 'real-exc-1', severity: 'warning', status: 'resolved' },
                    { case_id: 'real-exc-2', severity: 'critical', status: 'open' },
                ],
                total: 2,
            };

            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(realData),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useExceptions(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            // Verify the request went through the ingestion proxy
            const url = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
            expect(url).toContain('/api/ingestion/');

            expect(result.current.data?.__isDemo).toBe(false);
            expect(result.current.data?.cases).toHaveLength(2);
            expect(result.current.data?.cases[0].case_id).toBe('real-exc-1');
        });

        it('sets isError when API fails (no demo fallback)', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: false,
                status: 500,
                json: () => Promise.resolve({ detail: 'Internal Server Error' }),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useExceptions(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isError).toBe(true));
        });

        it('sets isError on network failure', async () => {
            global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

            const wrapper = createWrapper();
            const { result } = renderHook(() => useExceptions(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isError).toBe(true));
        });
    });

    // -----------------------------------------------------------------------
    // Query hooks
    // -----------------------------------------------------------------------

    describe('useRules', () => {
        it('fetches rules from live API via proxy', async () => {
            const liveRules = {
                rules: [{ rule_id: 'r-1', title: 'Live Rule', severity: 'warning', category: 'lot_linkage' }],
                total: 1,
            };
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(liveRules),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useRules(), { wrapper });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(result.current.data?.__isDemo).toBe(false);
            expect(result.current.data?.rules[0].rule_id).toBe('r-1');
        });

        it('sets isError when rules API fails', async () => {
            global.fetch = vi.fn().mockRejectedValue(new Error('offline'));

            const wrapper = createWrapper();
            const { result } = renderHook(() => useRules(), { wrapper });

            await waitFor(() => expect(result.current.isError).toBe(true));
        });
    });

    describe('useExceptions', () => {
        it('passes severity and status filters as query params', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ cases: [], total: 0 }),
            });

            const wrapper = createWrapper();
            renderHook(
                () => useExceptions(TENANT_ID, { severity: 'critical', status: 'open' }),
                { wrapper },
            );

            await waitFor(() => expect(global.fetch).toHaveBeenCalled());

            const url = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
            expect(url).toContain('severity=critical');
            expect(url).toContain('status=open');
            expect(url).toContain(`tenant_id=${TENANT_ID}`);
        });

        it('is disabled when tenantId is empty', () => {
            global.fetch = vi.fn();

            const wrapper = createWrapper();
            const { result } = renderHook(() => useExceptions(''), { wrapper });

            expect(result.current.fetchStatus).toBe('idle');
            expect(global.fetch).not.toHaveBeenCalled();
        });
    });

    describe('useCanonicalEvents', () => {
        it('fetches events from live API via proxy', async () => {
            const liveEvents = {
                events: [{ event_id: 'evt-1', event_type: 'receiving', status: 'validated' }],
                total: 1,
            };
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(liveEvents),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useCanonicalEvents(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(result.current.data?.__isDemo).toBe(false);
            expect(result.current.data?.events).toHaveLength(1);
            expect(result.current.data?.events[0].event_id).toBe('evt-1');
        });

        it('passes filter params to API', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ events: [], total: 0 }),
            });

            const wrapper = createWrapper();
            renderHook(
                () => useCanonicalEvents(TENANT_ID, { tlc: 'LOT-123', event_type: 'receiving', limit: 50 }),
                { wrapper },
            );

            await waitFor(() => expect(global.fetch).toHaveBeenCalled());

            const url = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
            expect(url).toContain('tlc=LOT-123');
            expect(url).toContain('event_type=receiving');
            expect(url).toContain('limit=50');
        });
    });

    describe('useRequestCases', () => {
        it('returns live data when API is available', async () => {
            const liveCases = {
                cases: [{ request_case_id: 'req-live-1', requesting_party: 'Walmart', package_status: 'assembled' }],
                total: 1,
            };
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(liveCases),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useRequestCases(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(result.current.data?.__isDemo).toBe(false);
            expect(result.current.data?.cases[0].requesting_party).toBe('Walmart');
        });

        it('sets isError when request cases API fails', async () => {
            global.fetch = vi.fn().mockRejectedValue(new Error('offline'));

            const wrapper = createWrapper();
            const { result } = renderHook(() => useRequestCases(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isError).toBe(true));
        });
    });

    describe('useEntities', () => {
        it('passes entity_type filter', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ entities: [], total: 0 }),
            });

            const wrapper = createWrapper();
            renderHook(() => useEntities(TENANT_ID, 'facility'), { wrapper });

            await waitFor(() => expect(global.fetch).toHaveBeenCalled());

            const url = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
            expect(url).toContain('entity_type=facility');
        });

        it('fetches entities from live API', async () => {
            const liveEntities = {
                entities: [{ entity_id: 'ent-1', entity_type: 'facility' }],
                total: 1,
            };
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(liveEntities),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useEntities(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(result.current.data?.__isDemo).toBe(false);
            expect(result.current.data?.entities).toHaveLength(1);
        });
    });

    describe('useIdentityReviews', () => {
        it('fetches reviews from live API', async () => {
            const liveReviews = {
                reviews: [{ review_id: 'rev-1', status: 'pending' }],
                total: 1,
            };
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve(liveReviews),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useIdentityReviews(TENANT_ID), { wrapper });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(result.current.data?.__isDemo).toBe(false);
            expect(result.current.data?.reviews).toHaveLength(1);
        });

        it('is disabled when tenantId is empty', () => {
            global.fetch = vi.fn();

            const wrapper = createWrapper();
            const { result } = renderHook(() => useIdentityReviews(''), { wrapper });

            expect(result.current.fetchStatus).toBe('idle');
            expect(global.fetch).not.toHaveBeenCalled();
        });
    });

    // -----------------------------------------------------------------------
    // Mutation hooks
    // -----------------------------------------------------------------------

    describe('useResolveException', () => {
        it('sends PATCH request with resolution data', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ case_id: 'exc-1', status: 'resolved' }),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useResolveException(TENANT_ID), { wrapper });

            await act(async () => {
                result.current.mutate({
                    caseId: 'exc-1',
                    resolutionSummary: 'Supplier provided missing TLC',
                    resolvedBy: 'sarah.chen',
                });
            });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(global.fetch).toHaveBeenCalledTimes(1);
            const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(url).toContain('/api/ingestion/api/v1/exceptions/exc-1/resolve');
            expect(url).toContain(`tenant_id=${TENANT_ID}`);
            expect(options.method).toBe('PATCH');

            const body = JSON.parse(options.body);
            expect(body.resolution_summary).toBe('Supplier provided missing TLC');
            expect(body.resolved_by).toBe('sarah.chen');
        });

        it('sets isError on API failure', async () => {
            global.fetch = vi.fn().mockRejectedValue(new Error('Network error'));

            const wrapper = createWrapper();
            const { result } = renderHook(() => useResolveException(TENANT_ID), { wrapper });

            await act(async () => {
                result.current.mutate({
                    caseId: 'exc-1',
                    resolutionSummary: 'Fix applied',
                    resolvedBy: 'admin',
                });
            });

            await waitFor(() => expect(result.current.isError).toBe(true));
        });
    });

    describe('useCreateRequestCase', () => {
        it('sends POST request to create a request case', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ request_case_id: 'req-new', package_status: 'pending' }),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useCreateRequestCase(TENANT_ID), { wrapper });

            await act(async () => {
                result.current.mutate({
                    requesting_party: 'FDA',
                    scope_type: 'product_recall',
                    scope_description: 'Romaine lettuce E. coli',
                    affected_lots: ['LOT-A', 'LOT-B'],
                    response_hours: 24,
                });
            });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(global.fetch).toHaveBeenCalledTimes(1);
            const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(url).toContain('/api/ingestion/api/v1/requests');
            expect(url).toContain(`tenant_id=${TENANT_ID}`);
            expect(options.method).toBe('POST');

            const body = JSON.parse(options.body);
            expect(body.requesting_party).toBe('FDA');
            expect(body.scope_type).toBe('product_recall');
            expect(body.affected_lots).toEqual(['LOT-A', 'LOT-B']);
        });
    });

    describe('useSeedRules', () => {
        it('sends POST request to seed rules', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ seeded: 12 }),
            });

            const wrapper = createWrapper();
            const { result } = renderHook(() => useSeedRules(), { wrapper });

            await act(async () => {
                result.current.mutate();
            });

            await waitFor(() => expect(result.current.isSuccess).toBe(true));

            expect(global.fetch).toHaveBeenCalledTimes(1);
            const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(url).toContain('/api/ingestion/api/v1/rules/seed');
            expect(options.method).toBe('POST');
        });

        it('sets isError on failure', async () => {
            global.fetch = vi.fn().mockRejectedValue(new Error('Forbidden'));

            const wrapper = createWrapper();
            const { result } = renderHook(() => useSeedRules(), { wrapper });

            await act(async () => {
                result.current.mutate();
            });

            await waitFor(() => expect(result.current.isError).toBe(true));
        });
    });

    // -----------------------------------------------------------------------
    // Fetch headers
    // -----------------------------------------------------------------------

    describe('cpFetch headers', () => {
        it('sends credentials include and Content-Type header', async () => {
            global.fetch = vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ rules: [], total: 0 }),
            });

            const wrapper = createWrapper();
            renderHook(() => useRules(), { wrapper });

            await waitFor(() => expect(global.fetch).toHaveBeenCalled());

            const options = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][1];
            expect(options.credentials).toBe('include');
            expect(options.headers['Content-Type']).toBe('application/json');
        });
    });
});
