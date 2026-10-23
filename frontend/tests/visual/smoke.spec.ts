/**
 * Smoke monitoring for every public route: fails on page errors,
 * same-origin console errors, same-origin responses >= 400, and empty
 * pages. Third-party failures and third-party console noise are attached
 * to the report (and annotated) but never fail.
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
        const consoleErrorsNoUrl: string[] = [];
        const thirdPartyConsole: string[] = [];
        const badSameOrigin: string[] = [];
        const badThirdParty: string[] = [];

        page.on('pageerror', (error) => {
            pageErrors.push(String(error).slice(0, 500));
        });
        page.on('console', (message) => {
            if (message.type() !== 'error') return;
            const text = message.text().slice(0, 500);
            const locationUrl = message.location().url;
            if (!locationUrl) {
                // Classified after load: attributable to a failed same-origin
                // response (fail) or unattributed noise (annotate).
                consoleErrorsNoUrl.push(text);
                return;
            }
            let sameOrigin = false;
            try {
                sameOrigin = new URL(locationUrl).origin === baseOrigin;
            } catch {
                sameOrigin = false;
            }
            if (sameOrigin) consoleErrors.push(text);
            else thirdPartyConsole.push(`${text} (${locationUrl.slice(0, 200)})`);
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

        // URL-less console errors count as same-origin only when this page
        // actually saw a failed same-origin response; otherwise they are
        // unattributed noise and must not fail the test.
        if (badSameOrigin.length > 0) consoleErrors.push(...consoleErrorsNoUrl);
        else thirdPartyConsole.push(...consoleErrorsNoUrl);

        await testInfo.attach('smoke-findings', {
            body: JSON.stringify(
                {
                    route,
                    finalUrl: page.url(),
                    visibleChars: text.length,
                    mainLandmarks: mainCount,
                    pageErrors,
                    consoleErrors,
                    thirdPartyConsole,
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
        if (thirdPartyConsole.length > 0) {
            testInfo.annotations.push({
                type: 'third-party-console',
                description: `${thirdPartyConsole.length} (see smoke-findings attachment)`,
            });
        }

        expect(pageErrors, `${route}: page errors`).toEqual([]);
        expect(consoleErrors, `${route}: same-origin console errors`).toEqual([]);
        expect(badSameOrigin, `${route}: same-origin responses >= 400`).toEqual([]);
        expect(mainCount, `${route}: no main landmark`).toBeGreaterThan(0);
        expect(
            text.length,
            `${route}: visible text under ${EMPTY_PAGE_MIN_CHARS} chars`,
        ).toBeGreaterThanOrEqual(EMPTY_PAGE_MIN_CHARS);
    });
}
