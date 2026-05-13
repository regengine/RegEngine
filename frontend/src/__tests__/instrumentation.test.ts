/**
 * RE-SEC-005: Production startup assertions for CSRF/JWT key separation.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const ORIGINAL_ENV = { ...process.env };

function mutableEnv(): Record<string, string | undefined> {
    return process.env as unknown as Record<string, string | undefined>;
}

function resetEnv() {
    delete process.env.CSRF_SECRET;
    delete process.env.JWT_SIGNING_KEY;
    delete process.env.AUTH_SECRET_KEY;
    delete mutableEnv().NODE_ENV;
    delete process.env.NEXT_RUNTIME;
    delete process.env.SENTRY_DSN;
    delete process.env.NEXT_PUBLIC_SENTRY_DSN;
}

// Avoid Sentry side effects.
vi.mock('@sentry/nextjs', () => ({
    captureRequestError: vi.fn(),
    init: vi.fn(),
}));

async function freshRegister() {
    vi.resetModules();
    const mod = await import('@/instrumentation');
    return mod.register;
}

describe('instrumentation register() — secret separation assertions (RE-SEC-005)', () => {
    beforeEach(() => {
        resetEnv();
    });

    afterEach(() => {
        resetEnv();
        Object.assign(process.env, ORIGINAL_ENV);
        vi.restoreAllMocks();
    });

    it('production + CSRF_SECRET unset → throws', async () => {
        mutableEnv().NODE_ENV = 'production';
        process.env.JWT_SIGNING_KEY = 'jwt-key';
        // CSRF_SECRET intentionally absent
        const register = await freshRegister();
        await expect(register()).rejects.toThrow(/CSRF_SECRET must be set/);
    });

    it('production + CSRF_SECRET === JWT_SIGNING_KEY → throws', async () => {
        mutableEnv().NODE_ENV = 'production';
        process.env.CSRF_SECRET = 'same-key'; // pragma: allowlist secret
        process.env.JWT_SIGNING_KEY = 'same-key';
        const register = await freshRegister();
        await expect(register()).rejects.toThrow(/distinct \(key separation\)/);
    });

    it('production + CSRF_SECRET === AUTH_SECRET_KEY → throws', async () => {
        mutableEnv().NODE_ENV = 'production';
        process.env.CSRF_SECRET = 'legacy-shared'; // pragma: allowlist secret
        process.env.JWT_SIGNING_KEY = 'jwt-key';
        process.env.AUTH_SECRET_KEY = 'legacy-shared';
        const register = await freshRegister();
        await expect(register()).rejects.toThrow(/must not equal legacy AUTH_SECRET_KEY/);
    });

    it('production + distinct CSRF_SECRET and JWT_SIGNING_KEY → resolves', async () => {
        mutableEnv().NODE_ENV = 'production';
        process.env.CSRF_SECRET = 'csrf-only-secret'; // pragma: allowlist secret
        process.env.JWT_SIGNING_KEY = 'jwt-only-secret';
        const register = await freshRegister();
        await expect(register()).resolves.toBeUndefined();
    });

    it('non-production → resolves regardless of secret config', async () => {
        mutableEnv().NODE_ENV = 'development';
        // No secrets set at all.
        const register = await freshRegister();
        await expect(register()).resolves.toBeUndefined();
    });
});
