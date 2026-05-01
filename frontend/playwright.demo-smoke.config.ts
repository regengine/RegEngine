import { defineConfig, devices } from '@playwright/test';

const externalBaseURL = process.env.DEMO_SMOKE_BASE_URL || process.env.PLAYWRIGHT_BASE_URL;

export default defineConfig({
    testDir: './tests/e2e',
    testMatch: /demo-smoke\.spec\.ts/,
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,
    workers: 1,
    reporter: [
        ['list'],
        ['html', { outputFolder: 'playwright-report/demo-smoke', open: 'never' }],
    ],
    use: {
        baseURL: externalBaseURL || 'http://localhost:3001',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'retain-on-failure',
    },
    webServer: externalBaseURL
        ? undefined
        : {
            command: 'npm run dev -- -p 3001',
            url: 'http://localhost:3001',
            reuseExistingServer: !process.env.CI,
            timeout: 120_000,
            env: {
                ...process.env,
                JWT_SIGNING_KEY: process.env.JWT_SIGNING_KEY ?? '',
                JWT_PREVIOUS_KEY: process.env.JWT_PREVIOUS_KEY ?? '',
                AUTH_SECRET_KEY: process.env.AUTH_SECRET_KEY || process.env.JWT_SIGNING_KEY || '',
                CSRF_SECRET: process.env.CSRF_SECRET || process.env.JWT_SIGNING_KEY || '',
                ADMIN_SERVICE_URL: process.env.ADMIN_SERVICE_URL ?? '',
                INGESTION_SERVICE_URL: process.env.INGESTION_SERVICE_URL ?? '',
                COMPLIANCE_SERVICE_URL: process.env.COMPLIANCE_SERVICE_URL ?? '',
                NEXT_PUBLIC_SUPABASE_URL: '',
                NEXT_PUBLIC_SUPABASE_ANON_KEY: '',
            },
        },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
});
