/**
 * createClient timeout contract: the internal timeout aborts with a
 * TimeoutError so callers can tell it apart from a caller cancel, which
 * forwards the caller's own abort reason (AbortError on a bare abort()).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-config', () => ({
    getServiceURL: (service: string) => `/api/${service}`,
}));

vi.mock('@/lib/csrf', () => ({
    CSRF_PROTECTED_METHODS: new Set(['POST', 'PUT', 'PATCH', 'DELETE']),
    getCsrfHeaders: () => ({ 'X-CSRF-Token': 'csrf-token' }),
}));

// fetch stub that hangs until aborted, then rejects with the abort reason,
// like a real fetch against a slow backend.
function hangingFetch() {
    return vi.fn().mockImplementation(
        (_url: string, init?: { signal?: AbortSignal }) =>
            new Promise<Response>((_resolve, reject) => {
                const signal = init?.signal;
                if (!signal) return;
                if (signal.aborted) {
                    reject(signal.reason);
                    return;
                }
                signal.addEventListener('abort', () => reject(signal.reason), { once: true });
            }),
    );
}

async function importFreshClient() {
    vi.resetModules();
    vi.stubGlobal('fetch', hangingFetch());
    return import('@/lib/api-client');
}

describe('apiClient internal timeout reason', () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.unstubAllGlobals();
    });

    it('rejects with TimeoutError when the internal 8s timeout fires', async () => {
        const { apiClient } = await importFreshClient();
        const pending = apiClient.getIngestionJob(crypto.randomUUID());
        const assertion = expect(pending).rejects.toMatchObject({ name: 'TimeoutError' });
        await vi.advanceTimersByTimeAsync(8000);
        await assertion;
    });

    it('rejects with the caller reason (AbortError) on caller cancel', async () => {
        const { apiClient } = await importFreshClient();
        const controller = new AbortController();
        const pending = apiClient.getIngestionJob(crypto.randomUUID(), { signal: controller.signal });
        const assertion = expect(pending).rejects.toMatchObject({ name: 'AbortError' });
        controller.abort();
        await assertion;
        expect(controller.signal.aborted).toBe(true);
    });
});
