/**
 * Sitemap crawler (report-only, read-only GET visits, public pages only).
 *
 * Fetches <baseURL>/sitemap.xml at runtime (live data, no fixtures),
 * rewrites each entry to the base URL's origin so preview deploys work,
 * and visits every entry that is not auth-gated or excluded in
 * routes.json. Flags broken same-origin links, dead ends, page errors,
 * and same-origin console errors. Writes a summary JSON per project to
 * test-results-visual/crawl-report-<project>.json.
 */
import { expect, test, type Page } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { routes } from './helpers';

/** Full crawl visits every sitemap page sequentially; budget 20 minutes. */
const CRAWL_TIMEOUT_MS = 1_200_000;

const NAV_TIMEOUT_MS = 30_000;
const LINK_TIMEOUT_MS = 15_000;
/** Max concurrent link-check GETs; page visits are sequential. */
const LINK_CONCURRENCY = 6;
const SKIP_EXACT = new Set(['/auth/sso/mock']);

interface BrokenLink {
    source: string;
    target: string;
    status: number;
    error?: string;
}

interface PageFinding {
    path: string;
    finalUrl: string;
    status: number;
    sameOriginLinks: number;
    deadEnd: boolean;
    deadEndReason: string | null;
    pageErrors: string[];
    consoleErrors: string[];
}

function baseOriginOf(page: Page): string {
    const raw =
        test.info().project.use.baseURL ??
        process.env.VISUAL_BASE_URL ??
        page.url();
    let origin: string;
    try {
        origin = new URL(raw).origin;
    } catch {
        throw new Error(`Cannot determine crawl base origin from "${raw}": invalid URL`);
    }
    if (origin === 'null' || origin === '') {
        const fallback = process.env.VISUAL_BASE_URL ?? 'https://regengine.co';
        try {
            const fallbackOrigin = new URL(fallback).origin;
            if (fallbackOrigin !== 'null' && fallbackOrigin !== '') {
                return fallbackOrigin;
            }
        } catch {
            // Fall through to the clear error below.
        }
        throw new Error(
            `Cannot determine crawl base origin from "${raw}": got opaque origin 'null'. ` +
                'Set VISUAL_BASE_URL to a valid http(s) URL.',
        );
    }
    return origin;
}

/** Rewrite a sitemap URL to the base origin so preview runs crawl the preview. */
function rewriteToBaseOrigin(loc: string, baseOrigin: string): string {
    try {
        const url = new URL(loc, baseOrigin);
        const base = new URL(baseOrigin);
        url.protocol = base.protocol;
        url.host = base.host;
        return url.toString();
    } catch {
        return loc;
    }
}

/** Extract <loc> values from a sitemap or sitemap-index document. */
function parseLocs(xml: string): string[] {
    const locs: string[] = [];
    const re = /<loc>\s*([^<]+?)\s*<\/loc>/gi;
    let match: RegExpExecArray | null;
    while ((match = re.exec(xml)) !== null) locs.push(match[1].trim());
    return locs;
}

function isSitemapUrl(url: string): boolean {
    return /\.xml$/i.test(url.split(/[?#]/)[0]);
}

/**
 * Fetch the live sitemap (following a sitemap index one level) and return
 * unique pathnames rewritten to the base URL's origin.
 */
async function fetchSitemapPaths(page: Page, baseOrigin: string): Promise<string[]> {
    const first = await page.request.get(`${baseOrigin}/sitemap.xml`, {
        timeout: LINK_TIMEOUT_MS,
        maxRedirects: 5,
    });
    if (!first.ok()) throw new Error(`sitemap.xml GET failed: ${first.status()}`);
    let locs = parseLocs(await first.text());
    if (locs.length > 0 && locs.every((loc) => isSitemapUrl(loc))) {
        const childPaths: string[] = [];
        for (const loc of locs) {
            const response = await page.request.get(rewriteToBaseOrigin(loc, baseOrigin), {
                timeout: LINK_TIMEOUT_MS,
                maxRedirects: 5,
            });
            if (!response.ok()) continue;
            childPaths.push(...parseLocs(await response.text()));
        }
        locs = childPaths;
    }
    const paths = new Set<string>();
    for (const loc of locs) {
        let url: URL;
        try {
            url = new URL(loc);
        } catch {
            continue;
        }
        if (url.protocol !== 'http:' && url.protocol !== 'https:') continue;
        // Rewrite to the base URL's origin so preview runs crawl the preview.
        paths.add(url.pathname + (url.search || ''));
    }
    return [...paths].sort();
}

function isSkipped(pathname: string): boolean {
    const bare = pathname.split('?')[0];
    return (
        SKIP_EXACT.has(bare) ||
        routes.authOnly.includes(bare) ||
        bare in routes.excludedReason
    );
}

/** Normalize an href to a same-origin absolute URL, or null to skip it. */
function normalizeLink(href: string, pageUrl: string, baseOrigin: string): string | null {
    const trimmed = href.trim();
    if (trimmed === '' || trimmed.startsWith('#')) return null;
    const lower = trimmed.toLowerCase();
    if (lower.startsWith('mailto:') || lower.startsWith('tel:')) return null;
    if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed) && !lower.startsWith('http')) return null;
    let url: URL;
    try {
        url = new URL(trimmed, pageUrl);
    } catch {
        return null;
    }
    if (url.origin !== baseOrigin) return null;
    if (SKIP_EXACT.has(url.pathname)) return null;
    url.hash = '';
    return url.toString();
}

async function checkLinks(
    page: Page,
    targets: Map<string, string>,
): Promise<BrokenLink[]> {
    const broken: BrokenLink[] = [];
    const entries = [...targets.entries()];
    for (let i = 0; i < entries.length; i += LINK_CONCURRENCY) {
        const batch = entries.slice(i, i + LINK_CONCURRENCY);
        const results = await Promise.all(
            batch.map(async ([target, source]): Promise<BrokenLink | null> => {
                try {
                    const response = await page.request.get(target, {
                        timeout: LINK_TIMEOUT_MS,
                        maxRedirects: 5,
                    });
                    const status = response.status();
                    return status >= 400
                        ? { source, target, status }
                        : null;
                } catch (error) {
                    return {
                        source,
                        target,
                        status: 0,
                        error: String(error).slice(0, 200),
                    };
                }
            }),
        );
        for (const result of results) if (result) broken.push(result);
    }
    return broken.sort((a, b) =>
        a.source.localeCompare(b.source) || a.target.localeCompare(b.target),
    );
}

test('crawl sitemap pages for broken links, dead ends, and errors', async ({
    page,
}, testInfo) => {
    test.setTimeout(CRAWL_TIMEOUT_MS);
    const baseOrigin = baseOriginOf(page);
    const sitemapPaths = await fetchSitemapPaths(page, baseOrigin);
    const visitPaths = sitemapPaths.filter((p) => !isSkipped(p));
    const skippedPaths = sitemapPaths.filter((p) => isSkipped(p));

    const linkSources = new Map<string, string>();
    const findings: PageFinding[] = [];

    for (const crawlPath of visitPaths) {
        const pageErrors: string[] = [];
        const consoleErrors: string[] = [];
        const onPageError = (error: Error): void => {
            pageErrors.push(String(error).slice(0, 500));
        };
        const onConsole = (message: {
            type(): string;
            text(): string;
            location(): { url: string };
        }): void => {
            if (message.type() !== 'error') return;
            const locationUrl = message.location().url;
            if (!locationUrl) return;
            try {
                if (new URL(locationUrl).origin === baseOrigin) {
                    consoleErrors.push(message.text().slice(0, 500));
                }
            } catch {
                // Ignore unparseable location URLs.
            }
        };
        page.on('pageerror', onPageError);
        page.on('console', onConsole);
        let status = 0;
        let navigationFailed = false;
        try {
            const response = await page.goto(crawlPath, {
                waitUntil: 'domcontentloaded',
                timeout: NAV_TIMEOUT_MS,
            });
            status = response?.status() ?? 0;
            await page
                .waitForLoadState('networkidle', { timeout: 15_000 })
                .catch(() => undefined);
        } catch (error) {
            navigationFailed = true;
            pageErrors.push(`navigation failed: ${String(error).slice(0, 300)}`);
        } finally {
            page.off('pageerror', onPageError);
            page.off('console', onConsole);
        }

        const pageUrl = page.url();
        // Scope links per page: a failed load keeps the previous page's DOM,
        // so it must record no links rather than crediting them to this path.
        let scopedSameOrigin = 0;
        if (!navigationFailed) {
            const hrefs = await page.locator('a[href]').evaluateAll((anchors) =>
                anchors.map((a) => (a as HTMLAnchorElement).getAttribute('href') ?? ''),
            );
            const scopedHrefs = await page
                .locator('main a[href], nav a[href], footer a[href]')
                .evaluateAll((anchors) =>
                    anchors.map((a) => (a as HTMLAnchorElement).getAttribute('href') ?? ''),
                );
            for (const href of scopedHrefs) {
                if (normalizeLink(href, pageUrl, baseOrigin)) scopedSameOrigin += 1;
            }
            for (const href of hrefs) {
                const target = normalizeLink(href, pageUrl, baseOrigin);
                if (target && !linkSources.has(target)) linkSources.set(target, crawlPath);
            }
        }

        let deadEndReason: string | null = null;
        // A failed navigation leaves stale DOM behind and is already recorded
        // in pageErrors, so skip dead-end classification entirely.
        if (!navigationFailed && status >= 400) {
            deadEndReason = `HTTP ${status}`;
        } else if (!navigationFailed) {
            let finalPath = '';
            try {
                finalPath = new URL(pageUrl).pathname;
            } catch {
                finalPath = '';
            }
            const h1 = (
                (await page
                    .locator('h1')
                    .first()
                    .textContent({ timeout: 5_000 })
                    .catch(() => '')) ?? ''
            ).trim();
            if (finalPath === '/404' || finalPath === '/not-found' || h1 === '404') {
                deadEndReason = `ends on 404 page (${finalPath || pageUrl})`;
            } else if (scopedSameOrigin === 0) {
                deadEndReason = 'zero same-origin outbound links in main/nav/footer';
            }
        }

        findings.push({
            path: crawlPath,
            finalUrl: pageUrl,
            status,
            sameOriginLinks: scopedSameOrigin,
            deadEnd: deadEndReason !== null,
            deadEndReason,
            pageErrors,
            consoleErrors,
        });
    }

    const brokenLinks = await checkLinks(page, linkSources);
    const deadEnds = findings.filter((f) => f.deadEnd);
    const pagesWithPageErrors = findings.filter((f) => f.pageErrors.length > 0);
    const pagesWithConsoleErrors = findings.filter((f) => f.consoleErrors.length > 0);

    const report = {
        project: testInfo.project.name,
        baseOrigin,
        fetchedAt: new Date().toISOString(),
        sitemapCount: sitemapPaths.length,
        visitedCount: visitPaths.length,
        skippedCount: skippedPaths.length,
        skippedPaths,
        uniqueLinksChecked: linkSources.size,
        brokenLinks,
        deadEnds: deadEnds.map((f) => ({
            path: f.path,
            finalUrl: f.finalUrl,
            status: f.status,
            reason: f.deadEndReason,
        })),
        pagesWithPageErrors: pagesWithPageErrors.map((f) => ({
            path: f.path,
            errors: f.pageErrors,
        })),
        pagesWithConsoleErrors: pagesWithConsoleErrors.map((f) => ({
            path: f.path,
            errors: f.consoleErrors,
        })),
        pages: findings.map((f) => ({
            path: f.path,
            status: f.status,
            sameOriginLinks: f.sameOriginLinks,
            deadEnd: f.deadEnd,
        })),
    };

    const outDir = path.resolve(process.cwd(), 'test-results-visual');
    mkdirSync(outDir, { recursive: true });
    writeFileSync(
        path.join(outDir, `crawl-report-${testInfo.project.name}.json`),
        JSON.stringify(report, null, 2),
    );

    await testInfo.attach('broken-links', {
        body: JSON.stringify(brokenLinks, null, 2),
        contentType: 'application/json',
    });
    await testInfo.attach('dead-ends', {
        body: JSON.stringify(report.deadEnds, null, 2),
        contentType: 'application/json',
    });
    await testInfo.attach('crawl-page-errors', {
        body: JSON.stringify(
            { pagesWithPageErrors: report.pagesWithPageErrors, pagesWithConsoleErrors: report.pagesWithConsoleErrors },
            null,
            2,
        ),
        contentType: 'application/json',
    });

    expect.soft(brokenLinks, 'broken same-origin links (see broken-links attachment)').toEqual([]);
    expect.soft(
        report.deadEnds,
        'dead-end pages (see dead-ends attachment)',
    ).toEqual([]);
    expect.soft(
        report.pagesWithPageErrors,
        'pages with page errors (see crawl-page-errors attachment)',
    ).toEqual([]);
    expect.soft(
        report.pagesWithConsoleErrors,
        'pages with same-origin console errors (see crawl-page-errors attachment)',
    ).toEqual([]);
});

test('sitemap paths are covered by routes.json', async ({ page }, testInfo) => {
    const baseOrigin = baseOriginOf(page);
    const sitemapPaths = await fetchSitemapPaths(page, baseOrigin);
    const covered = new Set<string>([
        ...routes.public,
        ...routes.priority,
        ...routes.skippedDynamic,
        ...routes.expectRedirectOr404,
        ...routes.authOnly,
        ...Object.keys(routes.excludedReason),
    ]);
    const uncovered = sitemapPaths.filter((p) => !covered.has(p.split('?')[0]));

    await testInfo.attach('uncovered-sitemap-paths', {
        body: JSON.stringify(uncovered, null, 2),
        contentType: 'application/json',
    });
    expect.soft(
        uncovered,
        'sitemap paths missing from routes.json (see uncovered-sitemap-paths attachment)',
    ).toEqual([]);
});
