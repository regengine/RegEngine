import type { NextRequest } from 'next/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'https://graph.example.test',
}));

import { DELETE, GET, PATCH, POST, PUT } from '@/app/api/graph/[...path]/route';

function makeRequest(): NextRequest {
    return {
        url: 'https://regengine.co/api/graph/trace/lot-1',
        headers: new Headers(),
        cookies: { get: () => undefined, getAll: () => [] },
    } as unknown as NextRequest;
}

afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
});

describe('graph proxy release gate', () => {
    it.each([
        ['GET', GET],
        ['POST', POST],
        ['PUT', PUT],
        ['PATCH', PATCH],
        ['DELETE', DELETE],
    ])('returns exact 404 for %s in production even if an experimental flag is present', async (_method, handler) => {
        vi.stubEnv('NODE_ENV', 'production');
        vi.stubEnv('REGENGINE_ENABLE_GRAPH_PROXY', '1');
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);

        const response = await handler(
            makeRequest(),
            { params: Promise.resolve({ path: ['trace', 'lot-1'] }) },
        );

        expect(response.status).toBe(404);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('returns exact 404 by default outside production', async () => {
        vi.stubEnv('NODE_ENV', 'development');
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);

        const response = await GET(
            makeRequest(),
            { params: Promise.resolve({ path: ['trace', 'lot-1'] }) },
        );

        expect(response.status).toBe(404);
        expect(fetchMock).not.toHaveBeenCalled();
    });
});
