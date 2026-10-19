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
    // Mirror of the real scanIdempotencyKey contract: stored key wins,
    // otherwise a stable key derived from the record identity.
    scanIdempotencyKey: (scan: { id?: number; timestamp: number; idempotencyKey?: string }) =>
        scan.idempotencyKey ?? `offline-scan-${scan.id ?? 'local'}-${scan.timestamp}`,
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/ingestion',
}));

import { useSync } from '@/hooks/use-sync';

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
        const timestamp = 1_700_000_000_000;
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 1,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-123',
                        events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-123' }],
                    }),
                    timestamp,
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
        // Legacy record with no stored key gets a stable derived key.
        expect(headers.get('Idempotency-Key')).toBe(`offline-scan-1-${timestamp}`);
    });

    it('reuses the stored idempotency key so replays deduplicate against the live attempt', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 2,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-123',
                        events: [{ cte_type: 'shipping', traceability_lot_code: 'LOT-999' }],
                    }),
                    timestamp: 1_700_000_000_001,
                    cteType: 'shipping',
                    content: 'LOT-999',
                    idempotencyKey: 'scan-key-from-capture',
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

        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(new Headers(init?.headers).get('Idempotency-Key')).toBe('scan-key-from-capture');
        expect(dbMocks.markScanSynced).toHaveBeenCalledWith(2);
    });

    it('attaches a stable idempotency key to legacy raw-only scans', async () => {
        const timestamp = 1_700_000_000_002;
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 3,
                    timestamp,
                    cteType: 'receiving',
                    content: 'RAW-123',
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

        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(new Headers(init?.headers).get('Idempotency-Key')).toBe(`offline-scan-3-${timestamp}`);
        expect(JSON.parse(String(init?.body))).toMatchObject({
            source: 'mobile_scanner_pwa_offline',
            tenant_id: 'tenant-123',
        });
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

    it('quarantines a previous tenant scan instead of replaying it under the new session', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 3,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-a',
                        events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-A' }],
                    }),
                    timestamp: Date.now(),
                    cteType: 'receiving',
                    content: 'LOT-A',
                },
            ],
            photos: [],
        });
        mockUseAuth.mockReturnValue({ isAuthenticated: true, tenantId: 'tenant-b' });

        const { result } = renderHook(() => useSync());
        setOnlineState(true);
        await act(async () => {
            await result.current.manualSync();
        });

        expect(fetchWithCsrfMock).not.toHaveBeenCalled();
        expect(dbMocks.markScanSyncFailed).toHaveBeenCalledWith(
            3,
            expect.objectContaining({ message: expect.stringContaining('different tenant') }),
        );
        expect(dbMocks.markScanSynced).not.toHaveBeenCalled();
    });

    it('replays a scan whose stored tenant still matches the session', async () => {
        dbMocks.getPendingUploads.mockResolvedValue({
            scans: [
                {
                    id: 4,
                    payload: JSON.stringify({
                        source: 'mobile_scanner_pwa',
                        tenant_id: 'tenant-123',
                        events: [{ cte_type: 'receiving', traceability_lot_code: 'LOT-1' }],
                    }),
                    timestamp: Date.now(),
                    cteType: 'receiving',
                    content: 'LOT-1',
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
        expect(dbMocks.markScanSynced).toHaveBeenCalledWith(4);
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
