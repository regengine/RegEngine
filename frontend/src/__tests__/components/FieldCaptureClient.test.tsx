import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FieldCaptureClient } from '@/components/mobile/FieldCaptureClient';

const mocks = vi.hoisted(() => ({
    fetchWithCsrf: vi.fn(),
    parseGS1: vi.fn(),
    savePhoto: vi.fn(),
    saveScan: vi.fn(),
    toast: vi.fn(),
    useAuth: vi.fn(),
    ingestFileMutation: {
        mutateAsync: vi.fn(),
    },
}));

vi.mock('next/link', () => ({
    default: ({ children, href, ...props }: any) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

vi.mock('next/dynamic', () => ({
    default: () =>
        ({ onScan }: { onScan: (rawScan: string) => void }) => (
            <button type="button" onClick={() => onScan('raw-scan')}>
                Trigger mock scan
            </button>
        ),
}));

vi.mock('@/components/mobile/ImageCapture', () => ({
    ImageCapture: ({ onCapture }: { onCapture: (data: string) => void }) => (
        <button type="button" onClick={() => onCapture('data:image/jpeg;base64,ZmFrZQ==')}>
            Trigger mock capture
        </button>
    ),
}));

vi.mock('@/components/ui/use-toast', () => ({
    useToast: () => ({ toast: mocks.toast }),
}));

vi.mock('@/hooks/use-api', () => ({
    useIngestFile: () => mocks.ingestFileMutation,
}));

vi.mock('@/hooks/use-sync', () => ({
    useSync: () => ({
        isOnline: true,
        isSyncing: false,
    }),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mocks.useAuth(),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => 'https://ingestion.test',
}));

vi.mock('@/lib/db', () => ({
    savePhoto: (...args: any[]) => mocks.savePhoto(...args),
    saveScan: (...args: any[]) => mocks.saveScan(...args),
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => mocks.fetchWithCsrf(...args),
}));

vi.mock('@/lib/gs1-parser', () => ({
    parseGS1: (...args: any[]) => mocks.parseGS1(...args),
}));

function jsonResponse(payload: unknown, init?: ResponseInit) {
    return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'content-type': 'application/json' },
        ...init,
    });
}

function setCaptureUrl(search: string) {
    window.history.replaceState({}, '', `/mobile/capture${search}`);
}

describe('FieldCaptureClient tenant hinting', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.useAuth.mockReturnValue({
            apiKey: null,
            isAuthenticated: true,
            tenantId: null,
        });
        mocks.parseGS1.mockReturnValue({
            gtin: '00012345678905',
            tlc: 'LOT-123',
            serial: undefined,
            expiryDate: undefined,
            packDate: undefined,
            isValidGTIN: true,
        });
    });

    it('uses the URL tenant hint for catalog and ingest requests when auth has no tenant yet', async () => {
        setCaptureUrl('?tenant_id=hinted-tenant');
        mocks.fetchWithCsrf
            .mockResolvedValueOnce(jsonResponse({ products: [] }))
            .mockResolvedValueOnce(new Response(null, { status: 202 }));

        const user = userEvent.setup();
        render(<FieldCaptureClient />);

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenCalled();
        });
        const [catalogUrl, catalogInit] = mocks.fetchWithCsrf.mock.calls[0] as [string, RequestInit];
        const catalogHeaders = new Headers(catalogInit?.headers);
        expect(catalogUrl).toBe('https://ingestion.test/api/v1/products/hinted-tenant');
        expect(catalogInit?.credentials).toBe('include');
        expect(catalogHeaders.get('Content-Type')).toBe('application/json');
        expect(catalogHeaders.get('X-RegEngine-API-Key')).toBeNull();
        expect(catalogHeaders.get('X-Tenant-ID')).toBeNull();

        await user.click(screen.getByRole('button', { name: 'Trigger mock scan' }));

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(2);
        });

        const ingestInit = mocks.fetchWithCsrf.mock.calls[1]?.[1] as RequestInit;
        const ingestHeaders = new Headers(ingestInit.headers);
        expect(mocks.fetchWithCsrf.mock.calls[1]?.[0]).toBe('https://ingestion.test/api/v1/webhooks/ingest');
        expect(ingestInit.credentials).toBe('include');
        expect(ingestHeaders.get('Content-Type')).toBe('application/json');
        expect(ingestHeaders.get('X-RegEngine-API-Key')).toBeNull();
        expect(ingestHeaders.get('X-Tenant-ID')).toBeNull();
        expect(JSON.parse(String(ingestInit.body))).toMatchObject({
            tenant_id: 'hinted-tenant',
            events: [
                expect.objectContaining({
                    cte_type: 'shipping',
                    traceability_lot_code: 'LOT-123',
                }),
            ],
        });
    });

    it('prefers the authenticated tenant over the URL hint once auth is established', async () => {
        setCaptureUrl('?tenant_id=hinted-tenant');
        mocks.useAuth.mockReturnValue({
            apiKey: null,
            isAuthenticated: true,
            tenantId: 'auth-tenant',
        });
        mocks.fetchWithCsrf
            .mockResolvedValueOnce(jsonResponse({ products: [] }))
            .mockResolvedValueOnce(new Response(null, { status: 202 }));

        const user = userEvent.setup();
        render(<FieldCaptureClient />);

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenNthCalledWith(
                1,
                'https://ingestion.test/api/v1/products/auth-tenant',
                expect.any(Object),
            );
        });

        await user.click(screen.getByRole('button', { name: 'Trigger mock scan' }));

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(2);
        });

        const ingestInit = mocks.fetchWithCsrf.mock.calls[1]?.[1] as RequestInit;
        const ingestHeaders = new Headers(ingestInit.headers);
        expect(ingestInit.credentials).toBe('include');
        expect(ingestHeaders.get('X-RegEngine-API-Key')).toBeNull();
        expect(ingestHeaders.get('X-Tenant-ID')).toBeNull();
        expect(JSON.parse(String(ingestInit.body))).toMatchObject({
            tenant_id: 'auth-tenant',
        });
    });

    it('falls back to cookie-backed file upload when label vision is unavailable', async () => {
        setCaptureUrl('?tenant_id=hinted-tenant');
        mocks.fetchWithCsrf
            .mockResolvedValueOnce(jsonResponse({ products: [] }))
            .mockResolvedValueOnce(new Response('fake-image', {
                status: 200,
                headers: { 'content-type': 'image/jpeg' },
            }))
            .mockResolvedValueOnce(new Response('vision unavailable', { status: 503 }));
        mocks.ingestFileMutation.mutateAsync.mockResolvedValue({ job_id: 'job-123' });

        const user = userEvent.setup();
        render(<FieldCaptureClient />);

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(1);
        });

        await user.click(screen.getByRole('tab', { name: /photo/i }));
        await user.click(screen.getByRole('button', { name: 'Trigger mock capture' }));

        await waitFor(() => {
            expect(mocks.ingestFileMutation.mutateAsync).toHaveBeenCalledTimes(1);
        });

        const uploadArgs = mocks.ingestFileMutation.mutateAsync.mock.calls[0]?.[0] as {
            apiKey?: string | null;
            file: File;
            sourceSystem: string;
        };
        expect(uploadArgs.sourceSystem).toBe('mobile_capture_pwa');
        expect(uploadArgs.file).toBeInstanceOf(File);
        expect('apiKey' in uploadArgs).toBe(false);
    });
});
