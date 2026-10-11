import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';

import { acknowledgeAlert, fetchAlerts, generateSOP, newIdempotencyKey } from '@/lib/api-hooks';

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchWithCsrf);

function okResponse(body: unknown = {}) {
    return { ok: true, status: 200, statusText: 'OK', json: async () => body } as Response;
}

function serverError() {
    return { ok: false, status: 500, statusText: 'Server Error', json: async () => ({}) } as Response;
}

function sentKeys(): (string | null)[] {
    return mockedFetch.mock.calls.map(([, options]) => {
        const headers = new Headers((options?.headers ?? {}) as HeadersInit);
        return headers.get('Idempotency-Key');
    });
}

beforeEach(() => {
    mockedFetch.mockReset();
});

describe('apiFetch idempotency keys', () => {
    it('reuses one key across retry attempts of a POST', async () => {
        mockedFetch.mockResolvedValueOnce(serverError()).mockResolvedValueOnce(okResponse({}));

        await acknowledgeAlert('tenant-1', null, 'alert-1');

        expect(mockedFetch).toHaveBeenCalledTimes(2);
        const keys = sentKeys();
        expect(keys[0]).toBeTruthy();
        expect(keys[1]).toBe(keys[0]);
    });

    it('mints a fresh key per logical call', async () => {
        mockedFetch.mockResolvedValue(okResponse({}));

        await acknowledgeAlert('tenant-1', null, 'alert-1');
        await acknowledgeAlert('tenant-1', null, 'alert-1');

        const keys = sentKeys();
        expect(keys[0]).toBeTruthy();
        expect(keys[1]).toBeTruthy();
        expect(keys[1]).not.toBe(keys[0]);
    });

    it('sends a key on POST calls with a JSON body', async () => {
        mockedFetch.mockResolvedValue(okResponse({}));

        await generateSOP('api-key', {
            company_name: 'Acme',
            company_type: 'distributor',
            primary_contact: 'Jane',
            products: ['lettuce'],
            facilities: ['WH-1'],
        });

        const keys = sentKeys();
        expect(keys).toHaveLength(1);
        expect(keys[0]).toBeTruthy();
    });

    it('sends no key on GET requests', async () => {
        mockedFetch.mockResolvedValue(okResponse([]));

        await fetchAlerts('tenant-1');

        expect(mockedFetch).toHaveBeenCalledTimes(1);
        expect(sentKeys()[0]).toBeNull();
    });

    it('newIdempotencyKey mints unique keys', () => {
        expect(newIdempotencyKey()).toBeTruthy();
        expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
    });
});
