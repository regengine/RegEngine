import { expect, test } from '@playwright/test';

import {
    loginWithEmailOtp,
    resetOtpOutbox,
    seedPasswordlessUser,
} from './auth-helpers';

test.describe('Security release gate', () => {
    test('email-code-only sysadmin cannot use high-assurance administration', async ({ context, page }) => {
        const email = `release-low-assurance@${Date.now()}.sysadmin.example`;
        resetOtpOutbox();
        seedPasswordlessUser(email, { isSysadmin: true });
        await loginWithEmailOtp(page, context, email);

        const response = await page.request.get('/api/admin/v1/admin/keys');

        expect(response.status()).toBe(403);
        const body = await response.json();
        expect(JSON.stringify(body)).toContain('requires_step_up');
    });

    test('session tenant cannot be replaced by a path assertion', async ({ context, page }) => {
        const run = Date.now();
        const tenantAEmail = `release-tenant-a@${run}.tenant-a.example`;
        const tenantBEmail = `release-tenant-b@${run}.tenant-b.example`;
        seedPasswordlessUser(tenantAEmail);
        const tenantB = seedPasswordlessUser(tenantBEmail);
        resetOtpOutbox();
        await loginWithEmailOtp(page, context, tenantAEmail);

        const response = await page.request.get(`/api/v1/compliance/status/${tenantB.tenant_id}`);

        expect(response.status()).toBe(403);
    });

    test('cross-origin cookie mutation is rejected by the CSRF gate', async ({ context, page }) => {
        const email = `release-csrf@${Date.now()}.csrf.example`;
        resetOtpOutbox();
        seedPasswordlessUser(email);
        await loginWithEmailOtp(page, context, email);

        const response = await page.request.post(
            '/api/review/00000000-0000-4000-8000-000000000000/approve',
            {
                data: {},
                headers: { Origin: 'https://attacker.invalid' },
            },
        );

        expect(response.status()).toBe(403);
    });

    test('release-disabled graph surface returns exact 404 for reads and writes', async ({ page }) => {
        const read = await page.request.get('/api/graph/release-gate-probe');
        const write = await page.request.post('/api/graph/release-gate-probe', { data: {} });

        expect(read.status()).toBe(404);
        expect(write.status()).toBe(404);
    });
});
