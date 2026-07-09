import { expect, test } from '@playwright/test';

import {
    enableVirtualAuthenticator,
    expectHydratedSession,
    loginWithEmailOtp,
    resetOtpOutbox,
    seedPasswordlessUser,
} from './auth-helpers';

test('email OTP login hydrates profile and requires passkey step-up for admin policy', async ({ context, page }) => {
    const email = `playwright+${Date.now()}@example.com`;
    resetOtpOutbox();
    seedPasswordlessUser(email);

    await loginWithEmailOtp(page, context, email);
    await expectHydratedSession(page, email, 'email_otp');
    await expect(page.getByLabel('Signed in user')).toContainText(email);

    await page.goto('/settings/security');
    await expect(page.getByRole('heading', { name: /security settings/i })).toBeVisible();
    await expect(page.getByText('email_otp')).toBeVisible();
    await page.getByRole('button', { name: /verify admin policy access/i }).click();

    await expect(page.getByRole('dialog', { name: /authenticate with your passkey/i })).toBeVisible();
    await expect(page.getByText(/requires a high-assurance session/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /authenticate with passkey/i })).toBeVisible();
});

test('WebAuthn step-up registers a passkey and completes the admin policy action', async ({ context, page }) => {
    const email = `playwright-webauthn+${Date.now()}@example.com`;
    resetOtpOutbox();
    seedPasswordlessUser(email, { isSysadmin: true });

    await loginWithEmailOtp(page, context, email);
    await expectHydratedSession(page, email, 'email_otp');

    await page.goto('/settings/security');
    await expect(page.getByRole('heading', { name: /security settings/i })).toBeVisible();

    const authenticator = await enableVirtualAuthenticator(page);
    try {
        await page.getByRole('button', { name: /register passkey/i }).click();
        await expect(
            page.getByRole('status').filter({ hasText: /passkey registered/i }),
        ).toBeVisible({ timeout: 15_000 });

        await page.getByRole('button', { name: /verify admin policy access/i }).click();
        const stepUpDialog = page.getByRole('dialog', { name: /authenticate with your passkey/i });
        await expect(stepUpDialog).toBeVisible();
        await expect(stepUpDialog.getByLabel(/email address/i)).toHaveValue(email);

        await stepUpDialog.getByRole('button', { name: /authenticate with passkey/i }).click();
        await expect(stepUpDialog).toBeHidden({ timeout: 15_000 });
        await expect(page).toHaveURL(/\/settings\/security$/);
        await expectHydratedSession(page, email, 'webauthn');
        // StepUpModal does window.location.reload() on success, so these
        // assertions race a fresh next-dev cold recompile of /settings/security.
        // The inline timeout must cover that first-render latency (the global
        // expect timeout does not apply once an inline one is set); the session
        // itself is already confirmed webauthn above.
        await expect(page.getByText('webauthn')).toBeVisible({ timeout: 30_000 });
        await expect(page.getByText('Ready')).toBeVisible();

        await page.getByRole('button', { name: /verify admin policy access/i }).click();
        await expect(
            page.getByRole('status').filter({
                hasText: /high-assurance organization policy access confirmed/i,
            }),
        ).toBeVisible({ timeout: 20_000 });
    } finally {
        await authenticator.remove();
    }
});
