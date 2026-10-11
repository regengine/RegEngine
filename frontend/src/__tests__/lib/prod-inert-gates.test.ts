/**
 * WS-10 item 4 — explicit tests that the two dev-convenience surfaces are
 * production-inert:
 *
 *   1. allowDevComplianceSnapshotFallback() must return true only when the
 *      explicit REGENGINE_ENABLE_DEV_COMPLIANCE_SNAPSHOTS flag is set, and
 *      false in production no matter what, so the in-memory dev snapshot
 *      store (hardcoded COMPLIANT payloads) can never serve data to a
 *      production tenant.
 *   2. /auth/sso/mock must remain a static handoff screen: it renders a
 *      return-to-login link and has no ability to mint a session (no
 *      cookies, no API handler in its route directory).
 */
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

const ENV_KEYS = ['REGENGINE_ENABLE_DEV_COMPLIANCE_SNAPSHOTS', 'NODE_ENV'] as const;
const savedEnv: Record<string, string | undefined> = {};
for (const key of ENV_KEYS) savedEnv[key] = process.env[key];

async function gateWithEnv(flag?: string, nodeEnv?: string) {
    if (flag === undefined) delete process.env.REGENGINE_ENABLE_DEV_COMPLIANCE_SNAPSHOTS;
    else process.env.REGENGINE_ENABLE_DEV_COMPLIANCE_SNAPSHOTS = flag;
    if (nodeEnv === undefined) delete (process.env as Record<string, unknown>).NODE_ENV;
    else (process.env as Record<string, string>).NODE_ENV = nodeEnv;
    const { allowDevComplianceSnapshotFallback } = await import('@/lib/dev-compliance-snapshots');
    return allowDevComplianceSnapshotFallback();
}

describe('allowDevComplianceSnapshotFallback is prod-inert', () => {
    afterEach(() => {
        for (const key of ENV_KEYS) {
            const value = savedEnv[key];
            if (value === undefined) delete (process.env as Record<string, unknown>)[key];
            else (process.env as Record<string, string>)[key] = value;
        }
    });

    it('returns false in production even when the flag is set', async () => {
        expect(await gateWithEnv('1', 'production')).toBe(false);
    });

    it('returns false in staging without the flag', async () => {
        expect(await gateWithEnv(undefined, 'staging')).toBe(false);
    });

    it('fails closed when nothing is set at all', async () => {
        expect(await gateWithEnv(undefined, undefined)).toBe(false);
    });

    it('stays off in development and test unless the explicit flag is set', async () => {
        // Environment names alone must never enable hardcoded COMPLIANT data.
        expect(await gateWithEnv(undefined, 'development')).toBe(false);
        expect(await gateWithEnv(undefined, 'test')).toBe(false);
        expect(await gateWithEnv('', 'development')).toBe(false);
        expect(await gateWithEnv('0', 'development')).toBe(false);
    });

    it('allows the fallback only with the explicit flag outside production', async () => {
        expect(await gateWithEnv('1', 'development')).toBe(true);
        expect(await gateWithEnv('1', 'test')).toBe(true);
    });
});

describe('/auth/sso/mock is prod-inert', () => {
    const routeDir = path.resolve(__dirname, '../../app/auth/sso/mock');

    it('renders a static handoff that only links back to /login', async () => {
        const { render } = await import('@testing-library/react');
        const { default: MockSsoRedirectPage } = await import('@/app/auth/sso/mock/page');
        const element = await MockSsoRedirectPage({
            searchParams: Promise.resolve({ organization_id: 'org-e2e' }),
        });
        const { container } = render(element);
        const links = Array.from(container.querySelectorAll('a')).map((a) =>
            a.getAttribute('href'),
        );
        expect(links).toEqual(['/login']);
        // No forms or buttons that submit anywhere — nothing can complete
        // an auth flow from this screen.
        expect(container.querySelector('form')).toBeNull();
    });

    it('has no route handler and touches no session primitives', () => {
        const entries = readdirSync(routeDir);
        // A route.ts here would turn the mock screen into an API surface.
        expect(entries).not.toContain('route.ts');
        expect(entries).not.toContain('route.tsx');

        const source = readFileSync(path.join(routeDir, 'page.tsx'), 'utf8');
        // No cookie/session access: the screen cannot mint or mutate auth
        // state in any environment, which is what makes it prod-inert.
        expect(source).not.toMatch(/next\/headers|cookies\(|set-cookie|fetch\(/i);
    });
});
