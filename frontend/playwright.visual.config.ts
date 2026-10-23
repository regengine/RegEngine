/**
 * Report-only visual regression + page monitoring config.
 *
 * Read-only by design: every project in this file visits pages with GET only,
 * except the two conditional projects below, which do not exist unless their
 * env flag is set (so nothing ever shows as "skipped"):
 *
 * - preview-forms: blank-submit validation screenshots on /login + /signup.
 *   Only on preview deploys, via VISUAL_ALLOW_FORM_SUBMIT=1. Never fills
 *   credentials, never creates an account.
 * - signed-in: read-only signed-in page loads. Manual runs only, via
 *   VISUAL_AUTH=1 plus a provisioned session (see signed-in.spec.ts).
 *   No workflow sets VISUAL_AUTH.
 *
 * Run: npx playwright test --config=playwright.visual.config.ts
 * Run one project: ... --project=desktop
 * Refresh baselines (CI only, designer approval required): see
 * .github/workflows/visual-update-baselines.yml
 */
import { defineConfig } from '@playwright/test';

const allowFormSubmit = process.env.VISUAL_ALLOW_FORM_SUBMIT === '1';
const allowSignedIn = process.env.VISUAL_AUTH === '1';

export default defineConfig({
    testDir: './tests/visual',
    /* No webServer: this suite only ever points at a deployed URL. */
    timeout: 60_000,
    expect: {
        timeout: 15_000,
        toHaveScreenshot: {
            maxDiffPixelRatio: 0.001,
            threshold: 0.2,
            animations: 'disabled',
            caret: 'hide',
            // CSS-pixel scaling so deviceScaleFactor never changes the image.
            scale: 'css',
        },
    },
    fullyParallel: true,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    reporter: [
        ['html', { outputFolder: 'playwright-visual-report', open: 'never' }],
        ['list'],
    ],
    outputDir: 'test-results-visual',
    // Designer-matching names: <route-stem>-<project>.png, so regenerated
    // baselines map 1:1 to the designer's reference PNGs for review.
    snapshotPathTemplate: '{testDir}/__screenshots__/{arg}-{projectName}{ext}',
    use: {
        baseURL: process.env.VISUAL_BASE_URL || 'https://regengine.co',
        // Optional Vercel Deployment Protection bypass (preview deploys).
        // Sent ONLY when VERCEL_AUTOMATION_BYPASS_SECRET is set at runtime
        // (env var name only — no workflow sets it, no secret referenced).
        extraHTTPHeaders: process.env.VERCEL_AUTOMATION_BYPASS_SECRET
            ? { 'x-vercel-protection-bypass': process.env.VERCEL_AUTOMATION_BYPASS_SECRET }
            : {},
        locale: 'en-US',
        timezoneId: 'America/Los_Angeles',
        reducedMotion: 'reduce',
        colorScheme: 'light',
        trace: 'retain-on-failure',
    },
    projects: [
        {
            name: 'desktop',
            testMatch: ['pages.visual.spec.ts'],
            use: { viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
        },
        {
            name: 'mobile',
            testMatch: ['pages.visual.spec.ts'],
            use: {
                viewport: { width: 390, height: 844 },
                isMobile: true,
                hasTouch: true,
                deviceScaleFactor: 1,
            },
        },
        {
            name: 'priority-extras',
            testMatch: ['priority-extras.visual.spec.ts'],
        },
        {
            name: 'content',
            testMatch: ['content.spec.ts'],
        },
        {
            name: 'smoke',
            testMatch: ['smoke.spec.ts'],
        },
        /* Conditional projects: absent unless the env flag is set. */
        ...(allowFormSubmit
            ? [
                  {
                      name: 'preview-forms',
                      testMatch: ['preview-forms.spec.ts'],
                  },
              ]
            : []),
        ...(allowSignedIn
            ? [
                  {
                      name: 'signed-in',
                      testMatch: ['signed-in.spec.ts'],
                  },
              ]
            : []),
    ],
});
