
import { defineConfig, devices } from '@playwright/test';

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
    testDir: './tests/e2e',
    globalSetup: './tests/e2e/global-setup.ts',
    /* Run tests in files in parallel */
    fullyParallel: true,
    /* Fail the build on CI if you accidentally left test.only in the source code. */
    forbidOnly: !!process.env.CI,
    /* Retry on CI only — retries=1 handles genuine flakiness; backend-down failures
     * are caught by the preflight health check before tests run, not by retrying. */
    retries: process.env.CI ? 1 : 0,
    /* 2 workers in CI — tests are independent, parallelism halves total run time. */
    workers: process.env.CI ? 1 : undefined,
    /* Reporter to use. See https://playwright.dev/docs/test-reporters */
    reporter: 'html',
    /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
    use: {
        /* Base URL — override with PLAYWRIGHT_BASE_URL for staging/prod runs */
        baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3001',

        /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
        trace: 'on-first-retry',
    },

    /* Start the Next.js dev server before running tests in CI.
     * env: explicitly forward secrets so the Next.js middleware can verify
     * JWTs signed by the Railway admin service. Without this, the child
     * process may not inherit CI env vars and every authenticated route
     * redirects to /login?error=session_expired. */
    webServer: {
        command: 'npm run dev -- -p 3001',
        url: 'http://localhost:3001',
        reuseExistingServer: !process.env.CI,
        timeout: 120_000,
        env: {
            ...process.env,
            // Ensure JWT keys reach the dev server for middleware verification
            JWT_SIGNING_KEY: process.env.JWT_SIGNING_KEY ?? '',
            JWT_PREVIOUS_KEY: process.env.JWT_PREVIOUS_KEY ?? '',
            // AUTH_SECRET_KEY is used by the CSRF module as a signing secret.
            // Fall back to JWT_SIGNING_KEY so CSRF token generation works in CI.
            AUTH_SECRET_KEY: process.env.AUTH_SECRET_KEY || process.env.JWT_SIGNING_KEY || '',
            CSRF_SECRET: process.env.CSRF_SECRET || process.env.JWT_SIGNING_KEY || '',
            // Service URLs for Next.js rewrites / API proxy
            ADMIN_SERVICE_URL: process.env.ADMIN_SERVICE_URL ?? '',
            INGESTION_SERVICE_URL: process.env.INGESTION_SERVICE_URL ?? '',
            COMPLIANCE_SERVICE_URL: process.env.COMPLIANCE_SERVICE_URL ?? '',
            // Supabase config: intentionally OMITTED for E2E.
            // The middleware cross-validates custom JWT + Supabase session (#538).
            // E2E login only uses the admin service JWT — no Supabase signIn occurs,
            // so no Supabase auth cookies are set. Without these env vars, the
            // middleware's hasSomeSupabaseCookie() returns true (bypass), allowing
            // JWT-only auth to work. Production still enforces both auth systems.
            NEXT_PUBLIC_SUPABASE_URL: '',
            NEXT_PUBLIC_SUPABASE_ANON_KEY: '',
        },
    },

    /* Configure projects for major browsers */
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
});
