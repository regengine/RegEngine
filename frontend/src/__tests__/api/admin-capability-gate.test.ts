/**
 * #2825 — a client-settable value must not unlock the server-held
 * `ADMIN_MASTER_KEY`.
 *
 * `hasAdminCapability` granted admin capability on the mere PRESENCE of a
 * `re_admin_key` cookie or an `x-admin-key` header, and neither is a secret the
 * caller had to know:
 *
 *   - the cookie: `POST /api/session` writes whatever `admin_key` string the
 *     body carries, with no validation (`app/api/session/route.ts`);
 *   - the header: needs no `/api/session` call at all — one request header.
 *
 * The three review proxies then call `getAdminMasterKey()` and put the REAL
 * `ADMIN_MASTER_KEY` on the wire. Today the backend review endpoints
 * (`services/admin/app/review_routes.py`) authenticate with
 * `X-RegEngine-API-Key`, not `X-Admin-Key`, so nothing is exposed yet — but
 * that is a coincidence of a separate bug, not a defense. Whoever repairs the
 * header mismatch turns this into live privilege escalation.
 *
 * The gate now requires the presented value to actually BE the admin master
 * key, compared in constant time. An operator who pasted the genuine key into
 * `/admin` still passes; a forged value gets nothing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

import { hasAdminCapability, requireAdminCapability } from '@/lib/api-proxy';
import { GET as REVIEW_ITEMS_GET } from '@/app/api/review/items/route';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

/** Synthetic stand-in for ADMIN_MASTER_KEY — never a real value. */
const REAL_ADMIN_KEY = 'synthetic-admin-master-key-for-tests'; // pragma: allowlist secret
/** What an attacker can put in the cookie or header for free. */
const FORGED_ADMIN_KEY = 'anything'; // pragma: allowlist secret

const ORIGINAL_ADMIN_MASTER_KEY = process.env.ADMIN_MASTER_KEY;

function makeRequest(
    cookies: Record<string, string> = {},
    headers: Record<string, string> = {},
): NextRequest {
    return {
        url: 'http://localhost/api/review/items',
        headers: new Headers(headers),
        cookies: {
            get: (name: string) => {
                const value = cookies[name];
                return value ? { name, value } : undefined;
            },
            getAll: () => Object.entries(cookies).map(([name, value]) => ({ name, value })),
        },
    } as unknown as NextRequest;
}

beforeEach(() => {
    vi.clearAllMocks();
    process.env.ADMIN_MASTER_KEY = REAL_ADMIN_KEY;
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    if (ORIGINAL_ADMIN_MASTER_KEY === undefined) delete process.env.ADMIN_MASTER_KEY;
    else process.env.ADMIN_MASTER_KEY = ORIGINAL_ADMIN_MASTER_KEY;
});

describe('#2825 — admin capability is not conferred by a client-settable value', () => {
    it('rejects a forged re_admin_key cookie', () => {
        const request = makeRequest({ re_admin_key: FORGED_ADMIN_KEY });
        expect(hasAdminCapability(request)).toBe(false);
        expect(requireAdminCapability(request)?.status).toBe(403);
    });

    it('rejects a forged x-admin-key header — no /api/session call needed', () => {
        const request = makeRequest({}, { 'x-admin-key': FORGED_ADMIN_KEY });
        expect(hasAdminCapability(request)).toBe(false);
        expect(requireAdminCapability(request)?.status).toBe(403);
    });

    it('still admits an operator who holds the genuine admin master key', () => {
        expect(hasAdminCapability(makeRequest({ re_admin_key: REAL_ADMIN_KEY }))).toBe(true);
        expect(hasAdminCapability(makeRequest({}, { 'x-admin-key': REAL_ADMIN_KEY }))).toBe(true);
    });

    it('grants nothing when the server has no admin master key configured', () => {
        delete process.env.ADMIN_MASTER_KEY;
        expect(hasAdminCapability(makeRequest({ re_admin_key: FORGED_ADMIN_KEY }))).toBe(false);
        expect(hasAdminCapability(makeRequest({}, { 'x-admin-key': '' }))).toBe(false);
    });

    it('does not treat a prefix of the real key as the real key', () => {
        const prefix = REAL_ADMIN_KEY.slice(0, 8);
        expect(hasAdminCapability(makeRequest({ re_admin_key: prefix }))).toBe(false);
        expect(hasAdminCapability(makeRequest({}, { 'x-admin-key': `${REAL_ADMIN_KEY}x` }))).toBe(false);
    });

    it('does not put ADMIN_MASTER_KEY on the wire for a forged x-admin-key caller', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ items: [] }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const response = await REVIEW_ITEMS_GET(
            makeRequest({}, { 'x-admin-key': FORGED_ADMIN_KEY }),
        );

        // Pre-fix: 200, with one upstream call carrying X-Admin-Key: <real key>.
        expect(fetchMock).not.toHaveBeenCalled();
        expect(response.status).toBe(403);
    });

    it('does not put ADMIN_MASTER_KEY on the wire for a forged re_admin_key cookie', async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ items: [] }), {
                status: 200,
                headers: { 'content-type': 'application/json' },
            }),
        );
        vi.stubGlobal('fetch', fetchMock);

        const response = await REVIEW_ITEMS_GET(
            makeRequest({ re_admin_key: FORGED_ADMIN_KEY }),
        );

        expect(fetchMock).not.toHaveBeenCalled();
        expect(response.status).toBe(403);
    });
});
