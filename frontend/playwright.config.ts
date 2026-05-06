
import { defineConfig, devices } from '@playwright/test';

if (process.env.FORCE_COLOR) {
    delete process.env.NO_COLOR;
}

const externalBaseURL = process.env.PLAYWRIGHT_BASE_URL;
const localBaseURL = 'http://localhost:3001';
const localJwtSigningKey =
    process.env.JWT_SIGNING_KEY ||
    process.env.AUTH_SECRET_KEY ||
    'playwright-local-jwt-signing-key-2026';
const localTestUserEmail = process.env.TEST_USER_EMAIL || 'playwright-e2e@example.com';
const localTestPassword = process.env.TEST_PASSWORD || 'Trace204!Playwright1';
const localTestAdminEmail =
    process.env.TEST_ADMIN_EMAIL || 'playwright-sysadmin@example.com';
const localTestAdminPassword =
    process.env.TEST_ADMIN_PASSWORD || 'Trace204!Playwright1';
const localAdminServiceUrl = process.env.ADMIN_SERVICE_URL || 'http://localhost:8000';
const localAdminMasterKey =
    process.env.ADMIN_MASTER_KEY || 'playwright-local-admin-master-key-2026';
const localAdminHealthUrl = new URL(
    '/health',
    localAdminServiceUrl.endsWith('/') ? localAdminServiceUrl : `${localAdminServiceUrl}/`
).toString();

if (!externalBaseURL) {
    process.env.JWT_SIGNING_KEY = localJwtSigningKey;
    process.env.AUTH_SECRET_KEY = process.env.AUTH_SECRET_KEY || localJwtSigningKey;
    process.env.CSRF_SECRET = process.env.CSRF_SECRET || localJwtSigningKey;
    process.env.TEST_USER_EMAIL = localTestUserEmail;
    process.env.TEST_PASSWORD = localTestPassword;
    process.env.TEST_ADMIN_EMAIL = localTestAdminEmail;
    process.env.TEST_ADMIN_PASSWORD = localTestAdminPassword;
    process.env.ADMIN_SERVICE_URL = localAdminServiceUrl;
    process.env.INGESTION_SERVICE_URL =
        process.env.INGESTION_SERVICE_URL || localAdminServiceUrl;
    process.env.COMPLIANCE_SERVICE_URL =
        process.env.COMPLIANCE_SERVICE_URL || localAdminServiceUrl;
    process.env.ADMIN_MASTER_KEY = localAdminMasterKey;
}

const forwardedEnv = { ...process.env };
delete forwardedEnv.NO_COLOR;

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
    workers: process.env.CI ? 1 : externalBaseURL ? undefined : 1,
    /* Reporter to use. See https://playwright.dev/docs/test-reporters */
    reporter: 'html',
    /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
    use: {
        /* Base URL — override with PLAYWRIGHT_BASE_URL for staging/prod runs */
        baseURL: externalBaseURL || localBaseURL,

        /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
        trace: 'on-first-retry',
    },

    /* Start the Next.js dev server before running tests in CI.
     * env: explicitly forward secrets so the Next.js middleware can verify
     * JWTs signed by the Railway admin service. Without this, the child
     * process may not inherit CI env vars and every authenticated route
     * redirects to /login?error=session_expired. */
    webServer: externalBaseURL
        ? undefined
        : [
            {
                command: 'env -u NO_COLOR bash ../scripts/start-e2e-backend.sh',
                url: localAdminHealthUrl,
                reuseExistingServer: !process.env.CI,
                timeout: 120_000,
                env: {
                    ...forwardedEnv,
                    PORT: '8000',
                    AUTH_SECRET_KEY: process.env.AUTH_SECRET_KEY || localJwtSigningKey,
                    JWT_SIGNING_KEY: process.env.JWT_SIGNING_KEY || localJwtSigningKey,
                    ADMIN_MASTER_KEY: process.env.ADMIN_MASTER_KEY || localAdminMasterKey,
                    DATABASE_URL:
                        process.env.DATABASE_URL || 'sqlite:////tmp/regengine-playwright-shared.db',
                    ADMIN_FALLBACK_SQLITE:
                        process.env.ADMIN_FALLBACK_SQLITE ||
                        'sqlite:////tmp/regengine-playwright-admin.db',
                    DISABLE_TASK_WORKER: process.env.DISABLE_TASK_WORKER || 'true',
                    ALLOW_INMEMORY_SESSION_STORE:
                        process.env.ALLOW_INMEMORY_SESSION_STORE || 'true',
                    INVITE_BASE_URL: process.env.INVITE_BASE_URL || localBaseURL,
                },
            },
            {
                command: 'env -u NO_COLOR npm run dev -- -p 3001',
                url: localBaseURL,
                reuseExistingServer: !process.env.CI,
                timeout: 120_000,
                env: {
                    ...forwardedEnv,
                    // Ensure JWT keys reach the dev server for middleware verification.
                    JWT_SIGNING_KEY: process.env.JWT_SIGNING_KEY || localJwtSigningKey,
                    JWT_PREVIOUS_KEY: process.env.JWT_PREVIOUS_KEY ?? '',
                    AUTH_SECRET_KEY: process.env.AUTH_SECRET_KEY || localJwtSigningKey,
                    CSRF_SECRET: process.env.CSRF_SECRET || localJwtSigningKey,
                    TEST_USER_EMAIL: process.env.TEST_USER_EMAIL || localTestUserEmail,
                    TEST_PASSWORD: process.env.TEST_PASSWORD || localTestPassword,
                    TEST_ADMIN_EMAIL: process.env.TEST_ADMIN_EMAIL || localTestAdminEmail,
                    TEST_ADMIN_PASSWORD:
                        process.env.TEST_ADMIN_PASSWORD || localTestAdminPassword,
                    ADMIN_MASTER_KEY: process.env.ADMIN_MASTER_KEY || localAdminMasterKey,
                    ADMIN_SERVICE_URL: process.env.ADMIN_SERVICE_URL || localAdminServiceUrl,
                    INGESTION_SERVICE_URL:
                        process.env.INGESTION_SERVICE_URL || localAdminServiceUrl,
                    COMPLIANCE_SERVICE_URL:
                        process.env.COMPLIANCE_SERVICE_URL || localAdminServiceUrl,
                    // Supabase config: intentionally omitted for JWT-only E2E mode.
                    NEXT_PUBLIC_SUPABASE_URL: '',
                    NEXT_PUBLIC_SUPABASE_ANON_KEY: '',
                },
            },
        ],

    /* Configure projects for major browsers */
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
});
