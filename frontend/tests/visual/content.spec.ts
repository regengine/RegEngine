/**
 * Report-only content assertions over public pages. All findings use
 * expect.soft so one run surfaces every violation; see the HTML report.
 */
import { expect, test, type Page } from '@playwright/test';
import { routes, stabilize } from './helpers';

test.describe.configure({ mode: 'parallel' });

interface TextFinding {
    tag: string;
    text: string;
}

const BANNED_WORDS = /\b(edi|sftp|sample|demo|synthetic|sandbox|test data)\b/i;
const BANNED_WORDS_ALL = /\b(edi|sftp|sample|demo|synthetic|sandbox|test data)\b/gi;

async function visibleText(page: Page): Promise<string> {
    return page.locator('body').innerText();
}

function contexts(haystack: string, re: RegExp, radius = 40, limit = 10): string[] {
    const out: string[] = [];
    const global = new RegExp(re.source, re.flags.includes('g') ? re.flags : `${re.flags}g`);
    let match: RegExpExecArray | null;
    while ((match = global.exec(haystack)) !== null && out.length < limit) {
        const start = Math.max(0, match.index - radius);
        const end = Math.min(haystack.length, match.index + match[0].length + radius);
        out.push(haystack.slice(start, end).replace(/\s+/g, ' ').trim());
        if (match[0].length === 0) global.lastIndex += 1;
    }
    return out;
}

/** Innermost elements whose text matches `pattern` (no matching descendants). */
async function innermostMatching(page: Page, pattern: string): Promise<TextFinding[]> {
    return page.evaluate((source: string) => {
        const re = new RegExp(source, 'i');
        const matching = [...document.querySelectorAll('body *')].filter((el) =>
            re.test(el.textContent || ''),
        );
        return matching
            .filter((el) => !matching.some((other) => other !== el && el.contains(other)))
            .slice(0, 25)
            .map((el) => ({
                tag: el.tagName.toLowerCase(),
                text: ((el.textContent || '').replace(/\s+/g, ' ').trim()).slice(0, 200),
            }));
    }, pattern);
}

async function loneDashCells(page: Page): Promise<TextFinding[]> {
    return page.evaluate(() => {
        const out: { tag: string; text: string }[] = [];
        for (const el of document.querySelectorAll('body *')) {
            if (el.children.length > 0) continue;
            if ((el.textContent || '').trim() !== '-') continue;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            out.push({
                tag: el.tagName.toLowerCase(),
                text: (el.outerHTML || '').slice(0, 200),
            });
            if (out.length >= 25) break;
        }
        return out;
    });
}

test.describe('global content rules', () => {
    for (const route of routes.public) {
        test(`content ${route}`, async ({ page }, testInfo) => {
            await stabilize(page, route);
            const text = await visibleText(page);

            // No em/en dashes in visible copy.
            const dashHits = contexts(text, /[—–]/);
            await testInfo.attach('dash-contexts', {
                body: JSON.stringify(dashHits, null, 2),
                contentType: 'application/json',
            });
            expect.soft(dashHits, `${route}: visible text contains em/en dashes`).toEqual([]);

            // No lone '-' used as an empty value.
            const loneDashes = await loneDashCells(page);
            await testInfo.attach('lone-dashes', {
                body: JSON.stringify(loneDashes, null, 2),
                contentType: 'application/json',
            });
            expect.soft(loneDashes, `${route}: elements using lone '-' as a value`).toEqual([]);

            // Banned whole words (case-insensitive).
            const banned = contexts(text, BANNED_WORDS_ALL);
            await testInfo.attach('banned-words', {
                body: JSON.stringify(banned, null, 2),
                contentType: 'application/json',
            });
            expect
                .soft(BANNED_WORDS.test(text), `${route}: banned word found: ${banned[0] ?? ''}`)
                .toBe(false);

            // Any element mentioning EPCIS must also say Preview.
            const epcis = await innermostMatching(page, 'epcis');
            const epcisWithoutPreview = epcis.filter((el) => !el.text.includes('Preview'));
            await testInfo.attach('epcis-without-preview', {
                body: JSON.stringify(epcisWithoutPreview, null, 2),
                contentType: 'application/json',
            });
            expect.soft(
                epcisWithoutPreview,
                `${route}: EPCIS mention without Preview`,
            ).toEqual([]);
        });
    }
});

test.describe('page-specific content rules', () => {
    test('home: only CSV upload and JSON events API labeled Live', async ({ page }) => {
        await stabilize(page, '/');
        const live = await innermostMatching(page, '\\bLive\\b');
        const csvOrJson = /csv|json/i;
        for (const el of live) {
            expect.soft(
                csvOrJson.test(el.text),
                `home: non-CSV/JSON element labeled Live: <${el.tag}> ${el.text}`,
            ).toBe(true);
        }
    });

    test('integrations: EPCIS says Preview, EDI/SFTP absent', async ({ page }) => {
        await stabilize(page, '/integrations');
        const text = await visibleText(page);
        expect.soft(/\b(edi|sftp)\b/i.test(text), '/integrations mentions EDI/SFTP').toBe(false);
        const epcis = await innermostMatching(page, 'epcis');
        for (const el of epcis) {
            expect.soft(
                el.text.includes('Preview'),
                `/integrations: EPCIS without Preview: <${el.tag}> ${el.text}`,
            ).toBe(true);
        }
    });

    for (const route of routes.public.filter((r) => r.startsWith('/trust'))) {
        test(`trust: no Sample archives on ${route}`, async ({ page }) => {
            await stabilize(page, route);
            const text = await visibleText(page);
            expect.soft(/\bSample\b/.test(text), `${route} mentions Sample archives`).toBe(false);
        });
    }
});
