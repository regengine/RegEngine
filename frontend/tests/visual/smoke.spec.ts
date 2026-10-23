/**
 * Smoke monitoring for every public route: fails on page errors, console
 * errors, same-origin responses >= 400, and empty pages. Third-party
 * failures are attached to the report but never fail.
 */
import { expect, test } from '@playwright/test';
import { routes } from './helpers';

test.describe.configure({ mode: 'parallel' });

const EMPTY_PAGE_MIN_CHARS = 20;

for (const route of routes.public) {
    test(`smoke ${route}`, async ({ page }, testInfo) => {
        const baseOrigin = new URL(testInfo.project.use.baseURL ?? page.url()).origin;
        const pageErrors: string[] = [];
        const consoleErrors: string[] = [];
        const badSameOrigin: string[] = [];
        const badThirdParty: string[] = [];

        page.on('pageerror', (error) => {
            pageErrors.push(String(error).slice(0, 500));
        });
        page.on('console', (message) => {
            if (message.type() === 'error') {
                consoleErrors.push(message.text().slice(0, 500));
            }
        });
        page.on('response', (response) => {
            if (response.status() < 400) return;
            const entry = `${response.status()} ${response.request().method()} ${response.url()}`;
            let sameOrigin = false;
            try {
                sameOrigin = new URL(response.url()).origin === baseOrigin;
            } catch {
                sameOrigin = false;
            }
            if (sameOrigin) badSameOrigin.push(entry.slice(0, 500));
            else badThirdParty.push(entry.slice(0, 500));
        });

        await page.goto(route, { waitUntil: 'domcontentloaded' });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => undefined);
        await page.waitForTimeout(500);

        const text = (await page.locator('body').innerText()).trim();
        const mainCount = await page.locator('main, [role="main"], #main-content').count();

        await testInfo.attach('smoke-findings', {
            body: JSON.stringify(
                {
                    route,
                    finalUrl: page.url(),
                    visibleChars: text.length,
                    mainLandmarks: mainCount,
                    pageErrors,
                    consoleErrors,
                    badSameOrigin,
                    badThirdParty,
                },
                null,
                2,
            ),
            contentType: 'application/json',
        });
        if (badThirdParty.length > 0) {
            testInfo.annotations.push({
                type: 'third-party-failures',
                description: `${badThirdParty.length} (see smoke-findings attachment)`,
            });
        }

        expect(pageErrors, `${route}: page errors`).toEqual([]);
        expect(consoleErrors, `${route}: console errors`).toEqual([]);
        expect(badSameOrigin, `${route}: same-origin responses >= 400`).toEqual([]);
        expect(mainCount, `${route}: no main landmark`).toBeGreaterThan(0);
        expect(
            text.length,
            `${route}: visible text under ${EMPTY_PAGE_MIN_CHARS} chars`,
        ).toBeGreaterThanOrEqual(EMPTY_PAGE_MIN_CHARS);
    });
}
