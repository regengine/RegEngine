import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.LIVE_PASSWORD_RESET_QA_FRONTEND_URL || 'http://localhost:3000';

export default defineConfig({
    testDir: './tests/e2e',
    testMatch: /password-reset\.live\.spec\.ts/,
    fullyParallel: false,
    forbidOnly: !!process.env.CI,
    retries: 0,
    workers: 1,
    reporter: 'html',
    use: {
        baseURL,
        trace: 'on',
    },
    projects: [
        {
            name: 'chromium',
            use: { ...devices['Desktop Chrome'] },
        },
    ],
});
