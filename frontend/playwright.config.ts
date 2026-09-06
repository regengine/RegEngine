
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
const localOtpHmacSecret =
    process.env.AUTH_OTP_HMAC_SECRET ||
    'playwright-local-otp-hmac-secret-2026-minimum-32-bytes';
const localTestUserEmail = process.env.TEST_USER_EMAIL || 'playwright-e2e@example.com';
const localTestPassword = process.env.TEST_PASSWORD || 'Trace204!Playwright1';
const localTestAdminEmail =
    process.env.TEST_ADMIN_EMAIL || 'playwright-sysadmin@example.com';
const localTestAdminPassword =
    process.env.TEST_ADMIN_PASSWORD || 'Trace204!Playwright1';
const localBackendBaseURL = 'http://localhost:8000';
const localEmailOutboxPath =
    process.env.REGENGINE_E2E_EMAIL_OUTBOX ||
    '/tmp/regengine-playwright-email-outbox.jsonl';
const localSharedDatabaseUrl =
    process.env.DATABASE_URL || 'postgresql://postgres:postgres@127.0.0.1:5432/playwright_shared'; // pragma: allowlist secret — local test service
const localAdminDatabaseUrl =
    process.env.ADMIN_FALLBACK_SQLITE || 'sqlite:////tmp/regengine-playwright-admin.db';
const localAdminHealthUrl = new URL('/health', `${localBackendBaseURL}/`).toString();

if (!externalBaseURL) {
    process.env.REGENGINE_ENV = process.env.REGENGINE_ENV || 'development';
    process.env.JWT_SIGNING_KEY = localJwtSigningKey;
    process.env.AUTH_SECRET_KEY = process.env.AUTH_SECRET_KEY || localJwtSigningKey;
    process.env.AUTH_OTP_HMAC_SECRET = localOtpHmacSecret;
    process.env.CSRF_SECRET = process.env.CSRF_SECRET || localJwtSigningKey;
    process.env.TEST_USER_EMAIL = localTestUserEmail;
    process.env.TEST_PASSWORD = localTestPassword;
    process.env.TEST_ADMIN_EMAIL = localTestAdminEmail;
    process.env.TEST_ADMIN_PASSWORD = localTestAdminPassword;
    // Playwright local mode owns the backend webServer. Ignore externally
    // provided service URLs so CI cannot accidentally mutate production.
    process.env.ADMIN_SERVICE_URL = localBackendBaseURL;
    process.env.INGESTION_SERVICE_URL = localBackendBaseURL;
    process.env.COMPLIANCE_SERVICE_URL = localBackendBaseURL;
    process.env.ENABLE_DB_API_KEYS = 'true';
    process.env.REDIS_URL = process.env.REDIS_URL || 'redis://127.0.0.1:6379/0';
    process.env.REGENGINE_E2E_MODE = process.env.REGENGINE_E2E_MODE || 'true';
    process.env.REGENGINE_E2E_EMAIL_OUTBOX = localEmailOutboxPath;
    process.env.DATABASE_URL = localSharedDatabaseUrl;
    process.env.ADMIN_FALLBACK_SQLITE = localAdminDatabaseUrl;
    process.env.WEBAUTHN_EXPECTED_ORIGIN =
        process.env.WEBAUTHN_EXPECTED_ORIGIN || localBaseURL;
    process.env.WEBAUTHN_RP_ID = process.env.WEBAUTHN_RP_ID || 'localhost';
    process.env.DISABLE_TASK_WORKER = process.env.DISABLE_TASK_WORKER || 'true';
    process.env.ALLOW_INMEMORY_SESSION_STORE =
        process.env.ALLOW_INMEMORY_SESSION_STORE || 'true';
    // Every seeded passwordless user shares one org/tenant (one organization
    // per email domain), so the suites' combined traffic exceeds the 100/min
    // per-tenant production default.
    process.env.TENANT_RATE_LIMIT_RPM = process.env.TENANT_RATE_LIMIT_RPM || '100000';
    process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES =
        process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES || 'true';
}

const forwardedEnv = { ...process.env };
delete forwardedEnv.NO_COLOR;

/**
 * See https://playwright.dev/docs/test-configuration.
 */
export default defineConfig({
    testDir: './tests/e2e',
    globalSetup: './tests/e2e/global-setup.ts',
    /* The local webServer runs `next dev`, which compiles each route on
     * first hit. A cold compile of a heavy page (dashboard, settings) can
     * exceed Playwright's default 30s test / 5s expect timeouts on a slow
     * runner, flaking auth-flow on unrelated PRs. Assertions still have to
     * genuinely pass — this only stops first-render latency from failing
     * the gate. */
    timeout: 120_000,
    expect: { timeout: 15_000 },
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
        /* Base URL — localhost is a secure context in Chromium, so Secure
         * __Host-regengine_session cookies are accepted without local HTTPS.
         * Override with PLAYWRIGHT_BASE_URL for staging/prod runs. */
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
                    AUTH_OTP_HMAC_SECRET:
                        process.env.AUTH_OTP_HMAC_SECRET || localOtpHmacSecret,
                    REGENGINE_E2E_MODE: process.env.REGENGINE_E2E_MODE || 'true',
                    REGENGINE_E2E_EMAIL_OUTBOX:
                        process.env.REGENGINE_E2E_EMAIL_OUTBOX || localEmailOutboxPath,
                    DATABASE_URL: process.env.DATABASE_URL || localSharedDatabaseUrl,
                    ADMIN_FALLBACK_SQLITE:
                        process.env.ADMIN_FALLBACK_SQLITE || localAdminDatabaseUrl,
                    WEBAUTHN_EXPECTED_ORIGIN:
                        process.env.WEBAUTHN_EXPECTED_ORIGIN || localBaseURL,
                    WEBAUTHN_RP_ID: process.env.WEBAUTHN_RP_ID || 'localhost',
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
                    AUTH_OTP_HMAC_SECRET:
                        process.env.AUTH_OTP_HMAC_SECRET || localOtpHmacSecret,
                    CSRF_SECRET: process.env.CSRF_SECRET || localJwtSigningKey,
                    TEST_USER_EMAIL: process.env.TEST_USER_EMAIL || localTestUserEmail,
                    TEST_PASSWORD: process.env.TEST_PASSWORD || localTestPassword,
                    TEST_ADMIN_EMAIL: process.env.TEST_ADMIN_EMAIL || localTestAdminEmail,
                    TEST_ADMIN_PASSWORD:
                        process.env.TEST_ADMIN_PASSWORD || localTestAdminPassword,
                    ADMIN_SERVICE_URL: localBackendBaseURL,
                    INGESTION_SERVICE_URL: localBackendBaseURL,
                    COMPLIANCE_SERVICE_URL: localBackendBaseURL,
                    // Supabase config: intentionally omitted for JWT-only E2E mode.
                    NEXT_PUBLIC_SUPABASE_URL: '',
                    NEXT_PUBLIC_SUPABASE_ANON_KEY: '',
                    NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES:
                        process.env.NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES || 'true',
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
