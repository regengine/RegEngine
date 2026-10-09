/**
 * Admin-proxy challenge-verify path alignment.
 *
 * The unauthenticated challenge-ID pattern in the admin catch-all proxy must
 * match the strict-UUID challenge-verify CSRF exemption in lib/csrf.ts
 * (CSRF_EXEMPT_RULES). A looser proxy pattern would forward non-UUID
 * challenge IDs without a session while the CSRF gate still rejects them,
 * or vice versa. This test pins both sides to the same strict-UUID shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@/lib/api-config', () => ({
    getServerServiceURL: () => 'https://admin.regengine.test',
}));

vi.mock('@/lib/admin-targets', () => ({
    getAdminTargets: () => ['https://admin.regengine.test'],
    shouldRetryAdminProxyResponse: () => false,
}));

import { POST as proxyAdminPost } from '@/app/api/admin/[...path]/route';
import { isCsrfExempt } from '@/lib/csrf';

const fetchMock = vi.fn();

// Strict UUID (version 4, variant 8): matches both the proxy pattern and
// the CSRF exemption regex.
const STRICT_UUID = '11111111-1111-4111-8111-111111111111';
// 36 hex-and-dash chars but not a strict UUID (version nibble "f" is not in
// [1-5], variant nibble "f" is not in [89abAB]). The old loose
// [0-9a-fA-F-]{36} proxy pattern accepted this; the aligned pattern must not.
const NON_UUID_36 = 'ffffffff-ffff-ffff-ffff-ffffffffffff';

function challengeVerifyRequest(challengeId: string): NextRequest {
    return new NextRequest(
        `https://app.regengine.test/api/admin/auth/challenges/${challengeId}/verify`,
        {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ code: '123456' }),
        },
    );
}

function postChallengeVerify(challengeId: string) {
    return proxyAdminPost!(
        challengeVerifyRequest(challengeId),
        {
            params: Promise.resolve({
                path: ['auth', 'challenges', challengeId, 'verify'],
            }),
        },
    );
}

describe('admin-proxy challenge-verify path alignment', () => {
    beforeEach(() => {
        fetchMock.mockReset();
        fetchMock.mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        }));
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
        vi.unstubAllEnvs();
    });

    it('proxies a strict-UUID challenge verify without a session (pre-auth ceremony)', async () => {
        const response = await postChallengeVerify(STRICT_UUID);

        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(fetchMock.mock.calls[0][0]).toBe(
            `https://admin.regengine.test/auth/challenges/${STRICT_UUID}/verify`,
        );
    });

    it('rejects a non-UUID challenge verify without a session instead of proxying it', async () => {
        const response = await postChallengeVerify(NON_UUID_36);

        expect(response.status).toBe(401);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it('agrees with the CSRF exemption on both challenge-ID shapes', async () => {
        expect(
            isCsrfExempt(`/api/admin/auth/challenges/${STRICT_UUID}/verify`, 'POST'),
        ).toBe(true);
        expect(
            isCsrfExempt(`/api/admin/auth/challenges/${NON_UUID_36}/verify`, 'POST'),
        ).toBe(false);
    });
});
