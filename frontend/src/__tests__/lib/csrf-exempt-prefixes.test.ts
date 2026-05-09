/**
 * FE-AUDIT-005: CSRF exempt-prefix list snapshot guard.
 *
 * The CSRF exempt list mixes directory prefixes (e.g. `/api/auth/`,
 * `/api/webhooks/`) with exact paths (e.g. `/api/tools/verify`). Any
 * future handler placed under a directory prefix is silently exempted
 * from CSRF protection without a deliberate decision. This snapshot
 * test forces drift to be reviewed: adding or removing an entry
 * requires updating BOTH the list AND this snapshot, in the same PR.
 *
 * If you're updating this snapshot, document in the PR body why each
 * new entry is safe — i.e. why it cannot be reached by an
 * authenticated user's browser without explicit user intent, OR why
 * the endpoint authenticates by a non-cookie scheme (HMAC for
 * webhooks, opaque tokens for invite acceptance).
 */
import { describe, expect, it } from 'vitest';
import { CSRF_EXEMPT_PREFIXES } from '@/lib/csrf';

const EXPECTED_CSRF_EXEMPT_PREFIXES = [
    '/api/auth/',
    '/api/admin/auth/',
    '/api/admin/v1/auth/accept-invite',
    '/api/webhooks/',
    '/api/v1/webhooks/',
    '/api/ingestion/api/v1/sandbox/',
    '/api/inflow-lab/',
    '/api/tools/check-access',
    '/api/tools/verify',
];

describe('CSRF exempt prefix list (FE-AUDIT-005)', () => {
    it('matches the reviewed snapshot', () => {
        expect([...CSRF_EXEMPT_PREFIXES]).toEqual(EXPECTED_CSRF_EXEMPT_PREFIXES);
    });

    it('preserves entry ordering (order signals review intent)', () => {
        // The file is grouped: auth → webhooks → public sandbox → public tools.
        // Re-ordering breaks the readability of the diff a reviewer sees when
        // the snapshot is updated.
        for (let i = 0; i < EXPECTED_CSRF_EXEMPT_PREFIXES.length; i++) {
            expect(CSRF_EXEMPT_PREFIXES[i]).toBe(EXPECTED_CSRF_EXEMPT_PREFIXES[i]);
        }
    });
});
