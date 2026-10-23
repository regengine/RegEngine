/**
 * Shared helpers for the report-only visual suite.
 *
 * stabilize() navigates and settles a page before screenshotting; 
 * screenshotMasks() returns tolerant mask locators for dynamic regions.
 */
import { test, type Locator, type Page } from '@playwright/test';
import routesData from './routes.json';

export interface RoutesFile {
    baseURLEnv: string;
    priority: string[];
    public: string[];
    skippedDynamic: string[];
    expectRedirectOr404: string[];
    authOnly: string[];
    excludedReason: Record<string, string>;
}

export const routes = routesData as unknown as RoutesFile;

/**
 * Fixed clock for every stabilized page, so relative dates ("3 days ago")
 * render identically on every run. Same value as the designer's
 * visual.spec.ts. Change it only with a baseline regeneration.
 */
export const FIXED_CLOCK_ISO = '2026-10-23T08:00:00Z';

/** Filesystem-safe screenshot stem for a route ('/' -> 'home'). No extension. */
export function screenshotName(route: string): string {
    if (route === '/') return 'home';
    return route
        .replace(/^\//, '')
        .replace(/\//g, '__')
        .replace(/[^a-zA-Z0-9_-]+/g, '-');
}

/**
 * Navigate to a route and settle it for a deterministic screenshot:
 * DOM load, best-effort network idle, webfonts ready, animations frozen,
 * dynamic text auto-tagged for masking.
 */
export async function stabilize(page: Page, route: string): Promise<void> {
    // Fixed clock BEFORE navigation so nothing renders with real time.
    await page.clock.setFixedTime(new Date(FIXED_CLOCK_ISO));
    await page.goto(route, { waitUntil: 'domcontentloaded' });
    try {
        await page.waitForLoadState('networkidle', { timeout: 30_000 });
    } catch {
        // Pages with polling/analytics never go idle; screenshot the settled
        // state anyway and note it so the report shows why.
        test.info().annotations.push({
            type: 'networkidle-timeout',
            description: route,
        });
        await page.waitForTimeout(1000);
    }
    await page.evaluate(() => document.fonts.ready.then(() => undefined));
    await page.addStyleTag({
        content: `
            *, *::before, *::after {
                animation: none !important;
                animation-duration: 0s !important;
                transition: none !important;
                transition-duration: 0s !important;
                scroll-behavior: auto !important;
                caret-color: transparent !important;
            }
        `,
    });
    await scrollToLoadLazyImages(page);
    await autoTagDynamicText(page);
}

/**
 * Scroll through the page in steps so lazy-loaded images fetch, then return
 * to the top for the screenshot. Mirrors the designer's visual.spec.ts.
 */
async function scrollToLoadLazyImages(page: Page): Promise<void> {
    await page.evaluate(async () => {
        for (let y = 0; y < document.body.scrollHeight; y += 800) {
            window.scrollTo(0, y);
            await new Promise((resolve) => setTimeout(resolve, 50));
        }
        window.scrollTo(0, 0);
    });
    // Best-effort settle for images triggered by the scroll. Polling pages
    // never go idle, so this is bounded and annotated like the first wait.
    try {
        await page.waitForLoadState('networkidle', { timeout: 10_000 });
    } catch {
        test.info().annotations.push({
            type: 'networkidle-timeout-after-scroll',
            description: page.url(),
        });
    }
}

/**
 * Tag small elements whose own text is time/version-like with
 * data-visual-mask so they join the standard mask set. Skips elements with
 * child elements so containers are never blanked.
 */
async function autoTagDynamicText(page: Page): Promise<void> {
    await page.evaluate(() => {
        const patterns = [
            /last[\s-]?updated/i,
            /\bupdated\s+\d/i,
            /\bversion\s+\d/i,
            /\bbuild\s+[0-9a-f]{5,}/i,
            /^v\d+\.\d+(\.\d+)?$/i,
            /^\d+\s+(seconds?|minutes?|hours?|days?|weeks?|months?)\s+ago$/i,
        ];
        const candidates = document.querySelectorAll(
            'time, span, small, p, li, td, dd, div, a, h1, h2, h3, h4, h5, h6',
        );
        for (const el of candidates) {
            if (!(el instanceof HTMLElement)) continue;
            if (el.hasAttribute('data-visual-mask')) continue;
            if (el.children.length > 0) continue;
            const text = (el.textContent || '').trim();
            if (text.length === 0 || text.length > 120) continue;
            if (patterns.some((re) => re.test(text))) {
                el.setAttribute('data-visual-mask', 'auto');
            }
        }
    });
}

/**
 * Tolerant mask locators for dynamic regions. Non-matching locators are
 * harmless to toHaveScreenshot, so prefer over-broad selectors here over
 * missing a flaky region. Deliberately does NOT mask whole heroes or page
 * landmarks — those are the visual content under test.
 */
export function screenshotMasks(page: Page): Locator[] {
    return [
        // Explicit opt-outs placed by component authors (follow-up work).
        // [data-vr-mask] is the designer's equivalent alias; either opts out.
        page.locator('[data-visual-mask], [data-vr-mask]'),
        page.locator('[data-testid="build-sha"], [data-testid="timestamp"]'),
        // Time / relative-time.
        page.locator('time, [datetime]'),
        // Charts and counters.
        page.locator('canvas, svg.recharts-surface, .recharts-wrapper'),
        page.locator(
            '[data-testid*="counter"], [class*="counter"], [class*="Counter"], ' +
                '[class*="stat-tile"], [class*="StatTile"], [class*="stat_tile"]',
        ),
        // Status pills / live regions.
        page.locator(
            '[role="status"], [role="progressbar"], [class*="status-pill"], ' +
                '[class*="status-badge"], [class*="StatusBadge"], [class*="status_badge"]',
        ),
        // Heartbeat / health widgets.
        page.locator(
            '[data-testid*="heartbeat"], [data-testid*="Heartbeat"], ' +
                '[class*="heartbeat"], [class*="Heartbeat"], ' +
                '[id*="heartbeat"], [id*="Heartbeat"]',
        ),
        // Animated decorations (frozen by stabilize CSS, masked for safety).
        page.locator(
            '[class*="animate-pulse"], [class*="animate-ping"], [class*="animate-spin"], ' +
                '[class*="marquee"], [class*="Marquee"], [data-marquee]',
        ),
        // Embedded media.
        page.locator('video, iframe'),
        // Cookie banners.
        page.locator(
            '[data-cookie-banner], [class*="cookie-banner"], [class*="CookieBanner"], ' +
                '[id*="cookie-banner"], [id*="CookieBanner"]',
        ),
        // Chat widgets.
        page.locator(
            '[class*="chat-widget"], [class*="ChatWidget"], [id*="chat-widget"], ' +
                '[id*="ChatWidget"], [class*="intercom"], [class*="drift-widget"]',
        ),
    ];
}

/** Tolerance (px) for header/nav bounding-box drift assertions. */
export const BOX_TOLERANCE_PX = 2;
