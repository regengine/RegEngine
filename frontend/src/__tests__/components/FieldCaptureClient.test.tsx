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
    online: true,
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
        isOnline: mocks.online,
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
    newScanIdempotencyKey: () => 'test-idempotency-key',
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

describe('FieldCaptureClient tenant handling', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.online = true;
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

    it('refuses scans and ignores the URL tenant hint when the session has no tenant', async () => {
        setCaptureUrl('?tenant_id=hinted-tenant');

        const user = userEvent.setup();
        render(<FieldCaptureClient />);

        // The refusal is visible without triggering a scan.
        expect(await screen.findByRole('alert')).toHaveTextContent(/tenant required/i);

        // No catalog fetch happens without a session tenant.
        expect(mocks.fetchWithCsrf).not.toHaveBeenCalled();

        await user.click(screen.getByRole('button', { name: 'Trigger mock scan' }));

        // The scan is refused: nothing is ingested and nothing is queued.
        expect(mocks.fetchWithCsrf).not.toHaveBeenCalled();
        expect(mocks.saveScan).not.toHaveBeenCalled();
        expect(mocks.toast).toHaveBeenCalledWith(
            expect.objectContaining({ title: 'Tenant required' }),
        );
    });

    it('does not ingest photo captures without a session tenant', async () => {
        setCaptureUrl('?tenant_id=hinted-tenant');
        mocks.fetchWithCsrf.mockResolvedValue(
            new Response('fake-image', {
                status: 200,
                headers: { 'content-type': 'image/jpeg' },
            }),
        );

        const user = userEvent.setup();
        render(<FieldCaptureClient />);

        await user.click(screen.getByRole('tab', { name: /photo/i }));
        await user.click(screen.getByRole('button', { name: 'Trigger mock capture' }));

        await waitFor(() => {
            expect(mocks.savePhoto).toHaveBeenCalledTimes(1);
        });
        expect(mocks.ingestFileMutation.mutateAsync).not.toHaveBeenCalled();
        expect(mocks.toast).toHaveBeenCalledWith(
            expect.objectContaining({ title: 'Tenant required' }),
        );
    });

    it('ingests with the session tenant and a stable idempotency key', async () => {
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
            expect(mocks.fetchWithCsrf).toHaveBeenCalled();
        });
        const [catalogUrl] = mocks.fetchWithCsrf.mock.calls[0] as [string, RequestInit];
        expect(catalogUrl).toBe('https://ingestion.test/api/v1/products/auth-tenant');

        await user.click(screen.getByRole('button', { name: 'Trigger mock scan' }));

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(2);
        });

        const ingestInit = mocks.fetchWithCsrf.mock.calls[1]?.[1] as RequestInit;
        const ingestHeaders = new Headers(ingestInit.headers);
        expect(mocks.fetchWithCsrf.mock.calls[1]?.[0]).toBe('https://ingestion.test/api/v1/webhooks/ingest');
        expect(ingestInit.credentials).toBe('include');
        expect(ingestHeaders.get('Content-Type')).toBe('application/json');
        expect(ingestHeaders.get('Idempotency-Key')).toBe('test-idempotency-key');
        expect(ingestHeaders.get('X-RegEngine-API-Key')).toBeNull();
        expect(ingestHeaders.get('X-Tenant-ID')).toBeNull();
        expect(JSON.parse(String(ingestInit.body))).toMatchObject({
            tenant_id: 'auth-tenant',
            events: [
                expect.objectContaining({
                    cte_type: 'shipping',
                    traceability_lot_code: 'LOT-123',
                }),
            ],
        });
        expect(mocks.saveScan).not.toHaveBeenCalled();
    });

    it('queues offline scans with the same tenant and idempotency key', async () => {
        setCaptureUrl('');
        mocks.online = false;
        mocks.useAuth.mockReturnValue({
            apiKey: null,
            isAuthenticated: true,
            tenantId: 'auth-tenant',
        });
        mocks.fetchWithCsrf.mockResolvedValueOnce(jsonResponse({ products: [] }));

        const user = userEvent.setup();
        render(<FieldCaptureClient />);

        await user.click(screen.getByRole('button', { name: 'Trigger mock scan' }));

        await waitFor(() => {
            expect(mocks.saveScan).toHaveBeenCalledTimes(1);
        });
        const [content, payload, cteType, idempotencyKey] = mocks.saveScan.mock.calls[0] as [
            string,
            Record<string, unknown>,
            string,
            string,
        ];
        expect(content).toBe('raw-scan');
        expect(cteType).toBe('shipping');
        expect(idempotencyKey).toBe('test-idempotency-key');
        expect(payload).toMatchObject({ tenant_id: 'auth-tenant' });
        expect(mocks.toast).toHaveBeenCalledWith(
            expect.objectContaining({ title: 'Saved Offline' }),
        );
    });

    it('falls back to cookie-backed file upload when label vision is unavailable', async () => {
        setCaptureUrl('');
        mocks.useAuth.mockReturnValue({
            apiKey: null,
            isAuthenticated: true,
            tenantId: 'auth-tenant',
        });
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
