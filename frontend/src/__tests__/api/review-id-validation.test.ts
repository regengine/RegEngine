/**
 * #2907 — the review approve/reject proxies interpolated the caller-controlled
 * `[id]` segment straight into the upstream admin URL with no validation, while
 * attaching the server's admin credential. A segment containing `?`, `#` or an
 * encoded `/` rewrites which upstream endpoint the request reaches.
 */
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { POST as approve } from '@/app/api/review/[id]/approve/route';
import { POST as reject } from '@/app/api/review/[id]/reject/route';
import type { NextRequest } from 'next/server';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'http://admin.test',
}));

const VALID_ID = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';

function makeRequest(): NextRequest {
    return {
        method: 'POST',
        url: 'http://localhost/api/review/x/approve',
        headers: new Headers(),
        cookies: {
            get: vi.fn(() => undefined),
            getAll: vi.fn(() => []),
        },
    } as unknown as NextRequest;
}

const mockFetch = vi.fn();

describe.each([
    ['approve', approve] as const,
    ['reject', reject] as const,
])('review %s proxy — [id] segment validation (#2907)', (action, handler) => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', mockFetch);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it.each([
        ['path traversal via a decoded slash', '../../admin/keys'],
        ['a bare slash', 'a/b'],
        ['an encoded slash', `${VALID_ID}%2Fapprove`],
        ['query injection needing no encoding trick', `${VALID_ID}?q=1`],
        ['fragment injection', `${VALID_ID}#frag`],
        ['an empty segment', ''],
        ['arbitrary junk', 'not-a-uuid'],
    ])('rejects %s with 400 and issues no upstream request', async (_label, id) => {
        const response = await handler(makeRequest(), { params: Promise.resolve({ id }) });

        expect(response.status).toBe(400);
        await expect(response.json()).resolves.toMatchObject({
            error: 'Invalid review identifier',
        });
        // Invalid IDs must fail before any upstream request.
        expect(mockFetch).not.toHaveBeenCalled();
    });

    it('still forwards a valid UUID to the intended upstream path', async () => {
        mockFetch.mockResolvedValue(Response.json({ status: `${action}d`, review_id: VALID_ID }));

        const response = await handler(makeRequest(), {
            params: Promise.resolve({ id: VALID_ID }),
        });

        expect(response.status).toBe(200);
        expect(mockFetch).toHaveBeenCalledTimes(1);
        // endsWith, not toBe: ADMIN_SERVICE_URL may be set in the ambient env
        // and takes precedence over the mocked getServerServiceURL.
        expect(mockFetch.mock.calls[0][0]).toMatch(
            new RegExp(`/v1/admin/review/flagged-extractions/${VALID_ID}/${action}$`),
        );
    });

    it('normalises an uppercase UUID rather than interpolating it raw', async () => {
        mockFetch.mockResolvedValue(Response.json({}));

        await handler(makeRequest(), {
            params: Promise.resolve({ id: VALID_ID.toUpperCase() }),
        });

        expect(mockFetch.mock.calls[0][0]).toMatch(
            new RegExp(`/v1/admin/review/flagged-extractions/${VALID_ID}/${action}$`),
        );
    });
});
