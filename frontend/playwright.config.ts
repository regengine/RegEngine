
import { defineConfig, devices } from '@playwright/test';

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
    testDir: './tests/e2e',
    /* Run tests in files in parallel */
    fullyParallel: true,
    /* Fail the build on CI if you accidentally left test.only in the source code. */
    forbidOnly: !!process.env.CI,
    /* Retry on CI only — retries=1 handles genuine flakiness; backend-down failures
     * are caught by the preflight health check before tests run, not by retrying. */
    retries: process.env.CI ? 1 : 0,
    /* 2 workers in CI — tests are independent, parallelism halves total run time. */
    workers: process.env.CI ? 2 : undefined,
    /* Reporter to use. See https://playwright.dev/docs/test-reporters */
    reporter: 'html',
    /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
    use: {
        /* Base URL — override with PLAYWRIGHT_BASE_URL for staging/prod runs */
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001',

        /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
        trace: 'on-first-retry',
    },

    /* Start the Next.js dev server before running tests in CI */
    webServer: {
        command: 'npm run dev -- -p 3001',
        url: 'http://localhost:3001',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
    },

    /* Configure projects for major browsers */
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
});
