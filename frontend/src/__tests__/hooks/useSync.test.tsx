import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());
const mockToast = vi.hoisted(() => vi.fn());
const mockMutateAsync = vi.hoisted(() => vi.fn());
const dbMocks = vi.hoisted(() => ({
    markScanSynced: vi.fn(),
    markPhotoSynced: vi.fn(),
    markScanSyncFailed: vi.fn(),
    markPhotoSyncFailed: vi.fn(),
    getPendingUploads: vi.fn(),
    cleanupOfflineRecords: vi.fn(),
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/components/ui/use-toast', () => ({
    useToast: () => ({ toast: mockToast }),
}));

vi.mock('@/hooks/use-api', () => ({
    useIngestFile: () => ({
        mutateAsync: (...args: any[]) => mockMutateAsync(...args),
    }),
}));

vi.mock('@/lib/db', () => ({
    markScanSynced: (...args: any[]) => dbMocks.markScanSynced(...args),
    markPhotoSynced: (...args: any[]) => dbMocks.markPhotoSynced(...args),
    markScanSyncFailed: (...args: any[]) => dbMocks.markScanSyncFailed(...args),
    markPhotoSyncFailed: (...args: any[]) => dbMocks.markPhotoSyncFailed(...args),
    getPendingUploads: (...args: any[]) => dbMocks.getPendingUploads(...args),
    cleanupOfflineRecords: (...args: any[]) => dbMocks.cleanupOfflineRecords(...args),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/ingestion',
}));

import { buildOfflineScanIdempotencyKey, useSync } from '@/hooks/use-sync';

function setOnlineState(isOnline: boolean) {
    Object.defineProperty(window.navigator, 'onLine', {
        configurable: true,
        value: isOnline,
    });
}

describe('useSync', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        setOnlineState(false);
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
            tenantId: 'tenant-123',
        });
        dbMocks.cleanupOfflineRecords.mockResolvedValue(undefined);
        dbMocks.markScanSynced.mockResolvedValue(undefined);
        dbMocks.markPhotoSynced.mockResolvedValue(undefined);
        dbMocks.markScanSyncFailed.mockResolvedValue(undefined);
        dbMocks.markPhotoSyncFailed.mockResolvedValue(undefined);
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [],
            photos: [],
        });
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
        });
        mockMutateAsync.mockResolvedValue({ job_id: 'job-123' });
    });

    it('replays pending scans through the cookie-backed ingest proxy without browser auth headers', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 1,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-123',
                        events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-123' }],
                    }),
                    timestamp: Date.now(),
                    cteType: 'receiving',
                    content: 'LOT-123',
                },
            ],
            photos: [],
        });

        const { result } = renderHook(() => useSync());

        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1));

        const [url, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        const headers = new Headers(init?.headers);
        expect(url).toBe('/api/ingestion/api/v1/webhooks/ingest');
        expect(init?.method).toBe('POST');
        expect(init?.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-RegEngine-API-Key')).toBeNull();
        expect(headers.get('X-Tenant-ID')).toBeNull();
    });

    it('uploads pending photos without requiring an apiKey argument', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [],
            photos: [
                {
                    id: 7,
                    blob: new Blob(['fake-photo'], { type: 'image/jpeg' }),
                    timestamp: Date.now(),
                },
            ],
        });

        const { result } = renderHook(() => useSync());

        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        await waitFor(() => expect(mockMutateAsync).toHaveBeenCalledTimes(1));

        const uploadArgs = mockMutateAsync.mock.calls[0]?.[0] as {
            apiKey?: string | null;
            file: File;
            sourceSystem: string;
        };
        expect(uploadArgs.file).toBeInstanceOf(File);
        expect(uploadArgs.sourceSystem).toBe('mobile_capture_pwa_offline');
        expect('apiKey' in uploadArgs).toBe(false);
    });

    it('does not sync when the user is signed out', async () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
            tenantId: 'tenant-123',
        });
        setOnlineState(true);

        const { result } = renderHook(() => useSync());

        await act(async () => {
            await result.current.manualSync();
        });

        expect(fetchWithCsrfMock).not.toHaveBeenCalled();
        expect(mockMutateAsync).not.toHaveBeenCalled();
        expect(dbMocks.getPendingUploads).not.toHaveBeenCalled();
    });

    it('sends a stable Idempotency-Key per scan so a lost response does not duplicate events', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 1,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-123',
                        events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-123' }],
                    }),
                    timestamp: Date.now(),
                    cteType: 'receiving',
                    content: 'LOT-123',
                },
                {
                    id: 2,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-123',
                        events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-456' }],
                    }),
                    timestamp: Date.now(),
                    cteType: 'receiving',
                    content: 'LOT-456',
                },
            ],
            photos: [],
        });

        const { result } = renderHook(() => useSync());

        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalledTimes(2));

        const firstHeaders = new Headers(fetchWithCsrfMock.mock.calls[0]?.[1]?.headers);
        const secondHeaders = new Headers(fetchWithCsrfMock.mock.calls[1]?.[1]?.headers);
        expect(firstHeaders.get('Idempotency-Key')).toBe('offline-scan-1');
        expect(secondHeaders.get('Idempotency-Key')).toBe('offline-scan-2');
    });

    it('reuses the same Idempotency-Key when a scan is retried after a failed attempt', async () => {
        const scan = {
            id: 3,
            payload: JSON.stringify({
                source: 'mobile_scanner_pwa',
                tenant_id: 'tenant-123',
                events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-789' }],
            }),
            timestamp: Date.now(),
            cteType: 'receiving',
            content: 'LOT-789',
        };
        dbMocks.getPendingUploads.mockResolvedValue({ scans: [scan], photos: [] });
        // First attempt: the response is lost in flight.
        fetchWithCsrfMock.mockRejectedValueOnce(new Error('network down'));

        const { result } = renderHook(() => useSync());

        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1));
        const retryHeaders = new Headers(fetchWithCsrfMock.mock.calls[0]?.[1]?.headers);
        expect(retryHeaders.get('Idempotency-Key')).toBe('offline-scan-3');
        expect(dbMocks.markScanSyncFailed).toHaveBeenCalledWith(3, expect.anything());

        // Retry: the same record must replay the same key.
        fetchWithCsrfMock.mockResolvedValue({ ok: true });
        await act(async () => {
            await result.current.manualSync();
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalledTimes(2));
        const secondHeaders = new Headers(fetchWithCsrfMock.mock.calls[1]?.[1]?.headers);
        expect(secondHeaders.get('Idempotency-Key')).toBe('offline-scan-3');
    });

    it('sends an Idempotency-Key for legacy scans built without a stored payload', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 4,
                    timestamp: Date.now(),
                    cteType: 'receiving',
                    content: 'LOT-000',
                },
            ],
            photos: [],
        });

        const { result } = renderHook(() => useSync());

        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalledTimes(1));
        const headers = new Headers(fetchWithCsrfMock.mock.calls[0]?.[1]?.headers);
        expect(headers.get('Idempotency-Key')).toBe('offline-scan-4');
    });

    it('buildOfflineScanIdempotencyKey is stable per record and unique across records', () => {
        const scan = { id: 5, content: 'LOT-5', timestamp: 1700000000000 };
        expect(buildOfflineScanIdempotencyKey(scan)).toBe('offline-scan-5');
        expect(buildOfflineScanIdempotencyKey({ ...scan })).toBe(
            buildOfflineScanIdempotencyKey(scan),
        );
        expect(buildOfflineScanIdempotencyKey({ ...scan, id: 6 })).not.toBe(
            buildOfflineScanIdempotencyKey(scan),
        );
        const fallback = { content: 'LOT-X', timestamp: 1700000000000 };
        expect(buildOfflineScanIdempotencyKey(fallback)).toBe(
            buildOfflineScanIdempotencyKey({ ...fallback }),
        );
    });

    it.fails('FE-004 does not replay a previous tenant photo after an account switch', async () => {
        // PhotoRecord/savePhoto currently persist no owner. The same IndexedDB
        // queue survives logout, so this fixture models a photo captured by A.
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [],
            photos: [{
                id: 9,
                blob: new Blob(['tenant-a-label'], { type: 'image/jpeg' }),
                timestamp: Date.now(),
            }],
        });
        mockUseAuth.mockReturnValue({ isAuthenticated: true, tenantId: 'tenant-a' });
        const previousAccount = renderHook(() => useSync());
        previousAccount.unmount();

        // A signs out while offline; B next opens field capture on the same
        // browser. No product code partitions or clears the photo queue.
        mockUseAuth.mockReturnValue({ isAuthenticated: true, tenantId: 'tenant-b' });
        const { result } = renderHook(() => useSync());
        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        // Ownerless legacy entries must be quarantined until ownership can be
        // established; never submit them with the next account's session.
        expect(mockMutateAsync).not.toHaveBeenCalled();
    });
});
