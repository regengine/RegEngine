/**
 * Preview-only blank-submit validation screenshots for /login and /signup.
 *
 * This project exists only when VISUAL_ALLOW_FORM_SUBMIT=1 (preview
 * deploys). It clicks submit on EMPTY forms and screenshots the validation
 * state. It never fills any field, never submits any data, and never
 * creates an account.
 */
import { expect, test } from '@playwright/test';
import { screenshotMasks, stabilize } from './helpers';

test.skip(
    process.env.VISUAL_ALLOW_FORM_SUBMIT !== '1',
    'preview-forms runs only with VISUAL_ALLOW_FORM_SUBMIT=1',
);

test.describe.configure({ mode: 'parallel' });

// Blank submits run ONLY against Vercel Preview deploys. This guard fails
// the test (never skips) when the baseURL host is anything else — including
// production — regardless of VISUAL_ALLOW_FORM_SUBMIT.
test.beforeEach(() => {
    const baseURL = test.info().project.use.baseURL ?? '';
    let hostname = '';
    try {
        hostname = new URL(baseURL).hostname;
    } catch {
        hostname = '';
    }
    if (!hostname.endsWith('.vercel.app')) {
        throw new Error(
            `preview-forms refuses to submit: baseURL host "${hostname || baseURL || '(empty)'}" ` +
                'does not end with .vercel.app. Blank submits run only against Vercel Preview deploys.',
        );
    }
});

test('blank submit on login shows validation', async ({ page }) => {
    await stabilize(page, '/login');
    await page.getByRole('button', { name: /^continue/i }).first().click();
    await page.waitForTimeout(1000);
    // Blank submit must stay on the login page (nothing created, no navigation).
    await expect(page).toHaveURL(/\/login/);
    await expect(page).toHaveScreenshot('form__login-blank', {
        mask: screenshotMasks(page),
    });
});

test('blank submit on signup shows validation', async ({ page }) => {
    await stabilize(page, '/signup');
    await page.getByRole('button', { name: /request access/i }).first().click();
    await page.waitForTimeout(1000);
    // Blank submit must stay on the signup page (nothing created, no navigation).
    await expect(page).toHaveURL(/\/signup/);
    await expect(page).toHaveScreenshot('form__signup-blank', {
        mask: screenshotMasks(page),
    });
});
