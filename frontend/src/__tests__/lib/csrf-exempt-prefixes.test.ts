import { describe, expect, it } from 'vitest';

import { CSRF_EXEMPT_RULES, isCsrfExempt } from '@/lib/csrf';

describe('reviewed CSRF route-and-method exemptions', () => {
    it('keeps the reviewed rule inventory explicit', () => {
        expect(CSRF_EXEMPT_RULES).toMatchSnapshot();
    });

    it('exempts only the pre-auth passwordless and passkey mutations', () => {
        expect(isCsrfExempt('/api/admin/auth/challenges', 'POST')).toBe(true);
        expect(
            isCsrfExempt(
                '/api/admin/auth/challenges/11111111-1111-4111-8111-111111111111/verify',
                'POST',
            ),
        ).toBe(true);
        expect(isCsrfExempt('/api/admin/auth/webauthn/login/verify', 'POST')).toBe(true);

        expect(isCsrfExempt('/api/admin/auth/challenges', 'DELETE')).toBe(false);
        expect(isCsrfExempt('/api/admin/auth/challenges/not-a-uuid/verify', 'POST')).toBe(false);
        expect(isCsrfExempt('/api/admin/auth/challenges/extra', 'POST')).toBe(false);
    });

    it('does not expose the retired timing-sensitive email-code routes', () => {
        expect(isCsrfExempt('/api/admin/auth/email-code/request', 'POST')).toBe(false);
        expect(isCsrfExempt('/api/admin/auth/email-code/confirm', 'POST')).toBe(false);
    });

    it('protects every known cookie-authenticated auth mutation', () => {
        const protectedMutations = [
            '/api/session',
            '/api/admin/auth/logout',
            '/api/admin/auth/logout-all',
            '/api/admin/auth/session/logout',
            '/api/admin/auth/webauthn/register/generate-options',
            '/api/admin/auth/webauthn/register/verify',
            '/api/admin/v1/admin/keys',
            '/api/admin/v1/admin/tenants',
            '/api/review/items/11111111-1111-4111-8111-111111111111/approve',
            '/api/inflow-lab/api/demo-fixtures/leafy/load',
            '/api/inflow-lab/api/simulate/reset',
        ];

        for (const path of protectedMutations) {
            expect(isCsrfExempt(path, 'POST'), path).toBe(false);
        }
    });

    it('enforces exact-path and segment boundaries', () => {
        expect(isCsrfExempt('/api/tools/verify', 'POST')).toBe(true);
        expect(isCsrfExempt('/api/tools/verify-extra', 'POST')).toBe(false);
        expect(isCsrfExempt('/api/webhooks/stripe', 'POST')).toBe(true);
        expect(isCsrfExempt('/api/webhooks-malicious/stripe', 'POST')).toBe(false);
        expect(isCsrfExempt('/api/webhooks/stripe', 'GET')).toBe(false);
    });

    it('exempts only POST to the public contact form', () => {
        expect(isCsrfExempt('/api/contact', 'POST')).toBe(true);
        expect(isCsrfExempt('/api/contact/x', 'POST')).toBe(false);
        expect(isCsrfExempt('/api/contact', 'GET')).toBe(false);
    });
});
