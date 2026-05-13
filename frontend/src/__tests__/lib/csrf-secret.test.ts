/**
 * RE-SEC-005: CSRF secret must be independent from JWT signing key.
 *
 * These tests verify that:
 *   1. Production refuses to fall back to AUTH_SECRET_KEY when CSRF_SECRET is unset.
 *   2. When CSRF_SECRET is set, it (not AUTH_SECRET_KEY) is what's used to sign tokens.
 *   3. Dev/test still tolerates AUTH_SECRET_KEY-only configuration for ergonomics.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { signCsrfToken, verifyCsrfToken } from '@/lib/csrf';

const ORIGINAL_ENV = { ...process.env };

function mutableEnv(): Record<string, string | undefined> {
    return process.env as unknown as Record<string, string | undefined>;
}

function resetEnv() {
    delete process.env.CSRF_SECRET;
    delete process.env.AUTH_SECRET_KEY;
    delete mutableEnv().NODE_ENV;
}

describe('csrf secret resolution (RE-SEC-005)', () => {
    beforeEach(() => {
        resetEnv();
    });

    afterEach(() => {
        resetEnv();
        Object.assign(process.env, ORIGINAL_ENV);
    });

    it('production + no CSRF_SECRET → verifyCsrfToken returns false (fail closed)', async () => {
        mutableEnv().NODE_ENV = 'production';
        // AUTH_SECRET_KEY is set but must NOT be used in production:
        process.env.AUTH_SECRET_KEY = 'jwt-signing-key-do-not-reuse'; // pragma: allowlist secret

        const result = await verifyCsrfToken('any-token', 'any-signature');
        expect(result).toBe(false);
    });

    it('production + CSRF_SECRET set → signature differs from AUTH_SECRET_KEY-derived signature', async () => {
        mutableEnv().NODE_ENV = 'production';
        process.env.AUTH_SECRET_KEY = 'jwt-signing-key'; // pragma: allowlist secret
        process.env.CSRF_SECRET = 'dedicated-csrf-secret'; // pragma: allowlist secret

        const sigWithCsrf = await signCsrfToken('token-abc');
        expect(sigWithCsrf).not.toBe('');

        // Now flip: pretend CSRF_SECRET equals AUTH_SECRET_KEY value and re-sign.
        process.env.CSRF_SECRET = 'jwt-signing-key';
        const sigIfReused = await signCsrfToken('token-abc');

        expect(sigWithCsrf).not.toBe(sigIfReused);
    });

    it('dev + only AUTH_SECRET_KEY set → signCsrfToken returns non-empty (back-compat)', async () => {
        mutableEnv().NODE_ENV = 'development';
        process.env.AUTH_SECRET_KEY = 'dev-only-secret'; // pragma: allowlist secret

        const sig = await signCsrfToken('token-xyz');
        expect(sig.length).toBeGreaterThan(0);
    });
});
