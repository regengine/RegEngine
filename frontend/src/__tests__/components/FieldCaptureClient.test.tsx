import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FieldCaptureClient } from '@/components/mobile/FieldCaptureClient';

const TEST_API_KEY = 'rge_test_key'; // pragma: allowlist secret

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
    ImageCapture: () => <div>Mock image capture</div>,
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
            apiKey: TEST_API_KEY,
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
            expect(mocks.fetchWithCsrf).toHaveBeenNthCalledWith(
                1,
                'https://ingestion.test/api/v1/products/hinted-tenant',
                expect.objectContaining({
                    headers: expect.objectContaining({
                        'Content-Type': 'application/json',
                        'X-RegEngine-API-Key': TEST_API_KEY,
                    }),
                }),
            );
        });

        await user.click(screen.getByRole('button', { name: 'Trigger mock scan' }));

        await waitFor(() => {
            expect(mocks.fetchWithCsrf).toHaveBeenNthCalledWith(
                2,
                'https://ingestion.test/api/v1/webhooks/ingest',
                expect.objectContaining({
                    method: 'POST',
                    headers: expect.objectContaining({
                        'Content-Type': 'application/json',
                        'X-RegEngine-API-Key': TEST_API_KEY,
                        'X-Tenant-ID': 'hinted-tenant',
                    }),
                }),
            );
        });

        const ingestInit = mocks.fetchWithCsrf.mock.calls[1]?.[1] as RequestInit;
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
            apiKey: TEST_API_KEY,
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
            expect(mocks.fetchWithCsrf).toHaveBeenNthCalledWith(
                2,
                'https://ingestion.test/api/v1/webhooks/ingest',
                expect.objectContaining({
                    headers: expect.objectContaining({
                        'X-Tenant-ID': 'auth-tenant',
                    }),
                }),
            );
        });

        const ingestInit = mocks.fetchWithCsrf.mock.calls[1]?.[1] as RequestInit;
        expect(JSON.parse(String(ingestInit.body))).toMatchObject({
            tenant_id: 'auth-tenant',
        });
    });
});
