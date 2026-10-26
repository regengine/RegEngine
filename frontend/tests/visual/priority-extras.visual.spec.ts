/**
 * Priority-page extras: mobile nav-open state, main-CTA focus ring, and
 * tablet snapshots for home + pricing.
 */
import { expect, test } from '@playwright/test';
import { routes, screenshotMasks, screenshotName, stabilize } from './helpers';

test.describe.configure({ mode: 'parallel' });

test.describe('mobile nav open', () => {
    test.use({
        viewport: { width: 390, height: 844 },
        isMobile: true,
        hasTouch: true,
    });

    for (const route of routes.priority) {
        test(`nav ${route}`, async ({ page }, testInfo) => {
            await stabilize(page, route);
            const candidates = [
                page.getByRole('button', { name: /open menu/i }),
                page.getByRole('button', { name: /menu/i }),
                page.locator('header button[aria-expanded]'),
            ];
            let opened = false;
            for (const button of candidates) {
                try {
                    await button.first().waitFor({ state: 'visible', timeout: 2000 });
                    await button.first().click();
                    opened = true;
                    break;
                } catch {
                    // Try the next candidate.
                }
            }
            if (!opened) {
                // Chromeless pages (/login, /signup) legitimately have no menu.
                testInfo.annotations.push({
                    type: 'no-menu-button',
                    description: route,
                });
                return;
            }
            await page.waitForTimeout(500);
            await expect(page).toHaveScreenshot(`nav-open__${screenshotName(route)}`, {
                mask: screenshotMasks(page),
            });
        });
    }
});

test.describe('main CTA focus ring', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    for (const route of routes.priority) {
        test(`cta ${route}`, async ({ page }, testInfo) => {
            await stabilize(page, route);
            const hrefCta = page
                .locator(
                    'main a[href*="/signup"], main a[href*="/contact"], ' +
                        'main a[href*="/pricing"]',
                )
                .first();
            const textCta = page
                .getByRole('link', { name: /get started|sign up|contact|demo|pricing|try/i })
                .first();
            let focused = false;
            for (const cta of [hrefCta, textCta]) {
                try {
                    await cta.waitFor({ state: 'visible', timeout: 2000 });
                    await cta.focus();
                    focused = true;
                    break;
                } catch {
                    // Try the next candidate.
                }
            }
            if (!focused) {
                testInfo.annotations.push({
                    type: 'no-main-cta',
                    description: route,
                });
                return;
            }
            await expect(page).toHaveScreenshot(`cta-focus__${screenshotName(route)}`, {
                mask: screenshotMasks(page),
            });
        });
    }
});

test.describe('tablet', () => {
    test.use({ viewport: { width: 768, height: 1024 } });

    for (const route of ['/', '/pricing']) {
        test(`tablet ${route}`, async ({ page }) => {
            await stabilize(page, route);
            await expect(page).toHaveScreenshot(`tablet__${screenshotName(route)}`, {
                fullPage: true,
                mask: screenshotMasks(page),
            });
        });
    }
});
