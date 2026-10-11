import { afterEach, describe, expect, it, vi } from 'vitest';

import {
    acknowledgeAlert,
    completeOnboardingStep,
    fetchAlerts,
    fetchDrillStatus,
    sendPortalLink,
} from '@/lib/api-hooks';
import { apiClient } from '@/lib/api-client';

function jsonResponse(status: number, body: unknown = {}) {
    return {
        ok: status >= 200 && status < 300,
        status,
        statusText: status === 200 ? 'OK' : 'Error',
        json: () => Promise.resolve(body),
        text: () => Promise.resolve(JSON.stringify(body)),
        blob: () => Promise.resolve(new Blob([JSON.stringify(body)])),
        headers: { forEach: (_cb: (value: string, key: string) => void) => {} },
    };
}

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('apiFetch idempotent-only retries', () => {
    it('retries a failing GET and returns the recovered response', async () => {
        const fetchMock = vi.fn()
            .mockResolvedValueOnce(jsonResponse(500))
            .mockResolvedValueOnce(jsonResponse(500))
            .mockResolvedValueOnce(jsonResponse(200, { items: [] }));
        vi.stubGlobal('fetch', fetchMock);

        const data = await fetchAlerts('tenant-1');

        expect(data).toEqual({ items: [] });
        expect(fetchMock).toHaveBeenCalledTimes(3);
    });

    it('attempts a failing POST exactly once', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500));
        vi.stubGlobal('fetch', fetchMock);

        await expect(acknowledgeAlert('tenant-1', null, 'alert-1')).rejects.toThrow();
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it('does not retry other non-idempotent drill and onboarding writes', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(500));
        vi.stubGlobal('fetch', fetchMock);

        await expect(sendPortalLink('t', 'k', 's')).rejects.toThrow();
        await expect(completeOnboardingStep('t', 'k', 'step')).rejects.toThrow();
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });
});

describe('client path id encoding', () => {
    it('encodes tenant and alert ids in alert paths', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
        vi.stubGlobal('fetch', fetchMock);

        await fetchAlerts('tenant/a b');
        expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/alerts/tenant%2Fa%20b');

        fetchMock.mockRejectedValueOnce(new Error('no retry'));
        await expect(
            acknowledgeAlert('tenant/a', null, 'alert/1'),
        ).rejects.toThrow();
        expect(fetchMock.mock.calls[1][0]).toContain(
            '/api/v1/alerts/tenant%2Fa/alert%2F1/acknowledge',
        );
    });

    it('encodes supplier, step, and drill ids', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, {}));
        vi.stubGlobal('fetch', fetchMock);

        await sendPortalLink('t/1', 'k', 's/2').catch(() => {});
        expect(fetchMock.mock.calls[0][0]).toContain('/api/v1/suppliers/t%2F1/s%2F2/send-link');

        await completeOnboardingStep('t/1', 'k', 'step/2').catch(() => {});
        expect(fetchMock.mock.calls[1][0]).toContain('/api/v1/onboarding/t%2F1/step/step%2F2');

        await fetchDrillStatus('k', 'drill/3');
        expect(fetchMock.mock.calls[2][0]).toContain('/api/v1/audit/drill/drill%2F3');
    });

    it('encodes the key id in the revoke-key path', async () => {
        const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, null));
        vi.stubGlobal('fetch', fetchMock);

        await apiClient.revokeAPIKey('key/1 2');

        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(String(fetchMock.mock.calls[0][0])).toContain('/v1/admin/keys/key%2F1%202');
    });
});
