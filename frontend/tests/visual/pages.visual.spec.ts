/**
 * Full-page screenshots for every public signed-out route (desktop + mobile),
 * plus redirect/404 assertions for retired routes and header/nav
 * bounding-box drift checks against layout-boxes.json.
 */
import { expect, test } from '@playwright/test';
import { appendFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import {
    BOX_TOLERANCE_PX,
    routes,
    screenshotMasks,
    screenshotName,
    stabilize,
} from './helpers';
import boxesData from './layout-boxes.json';

test.describe.configure({ mode: 'parallel' });

interface Box {
    x: number;
    y: number;
    width: number;
    height: number;
}

const expectedBoxes = boxesData as unknown as Record<string, Box | string>;

function isBox(value: Box | string | undefined): value is Box {
    return (
        !!value &&
        typeof value === 'object' &&
        ['x', 'y', 'width', 'height'].every(
            (key) => typeof (value as unknown as Record<string, unknown>)[key] === 'number',
        )
    );
}

test.describe('public pages', () => {
    for (const route of routes.public) {
        test(`page ${route}`, async ({ page }, testInfo) => {
            await stabilize(page, route);
            testInfo.annotations.push({
                type: 'final-url',
                description: page.url(),
            });

            // Header/nav bounding-box drift check (never fails on missing data).
            const header = page.locator('header').first();
            const chrome = (await header.count()) > 0 ? header : page.locator('nav').first();
            const actual = (await chrome.count()) > 0 ? await chrome.boundingBox() : null;
            const key = `${testInfo.project.name}:${route}`;
            const expected = expectedBoxes[key];

            if (process.env.VISUAL_UPDATE_BOXES === '1' && actual) {
                const outDir = path.resolve(__dirname, '..', '..', 'test-results-visual');
                mkdirSync(outDir, { recursive: true });
                // One JSON object per line; concurrent appends are O_APPEND-safe.
                // Merge after the run (see README "Layout boxes").
                appendFileSync(
                    path.join(outDir, 'layout-boxes.candidate.json'),
                    `${JSON.stringify({ [key]: actual })}\n`,
                );
            }

            if (!isBox(expected)) {
                await testInfo.attach('layout-box-missing', {
                    body: JSON.stringify({ key, actual }, null, 2),
                    contentType: 'application/json',
                });
            } else if (!actual) {
                await testInfo.attach('layout-box-no-chrome', {
                    body: JSON.stringify({ key, note: 'no header/nav bounding box' }),
                    contentType: 'application/json',
                });
            } else {
                for (const dim of ['x', 'y', 'width', 'height'] as const) {
                    expect(
                        Math.abs(actual[dim] - expected[dim]),
                        `${key} header/nav ${dim}: expected ${expected[dim]}, got ${actual[dim]}`,
                    ).toBeLessThanOrEqual(BOX_TOLERANCE_PX);
                }
            }

            await expect(page).toHaveScreenshot(`${screenshotName(route)}.png`, {
                fullPage: true,
                mask: screenshotMasks(page),
            });
        });
    }
});

test.describe('retired routes redirect or 404', () => {
    for (const route of routes.expectRedirectOr404) {
        test(`gone ${route}`, async ({ page }, testInfo) => {
            const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
            const status = response?.status() ?? 0;
            const finalPath = new URL(page.url()).pathname;
            const redirectedAway =
                finalPath !== route || response?.request().redirectedFrom() !== null;
            testInfo.annotations.push({
                type: 'final-url',
                description: `${status} ${page.url()}`,
            });
            expect(
                redirectedAway || status === 404,
                `expected ${route} to 404 or redirect away, got ${status} at ${page.url()}`,
            ).toBe(true);
        });
    }
});
