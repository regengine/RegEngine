import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

const stamp = new Date().toISOString().replace(/[:.]/g, '-');

export default defineConfig({
  testDir: __dirname,
  testMatch: /fe-00[14].*\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: process.env.QA_FE_RESULTS
    ? path.resolve(process.env.QA_FE_RESULTS)
    : path.resolve(__dirname, `../../../../docs/qa/2026-10-02/artifacts/browser/fe-regression-results-${stamp}.json`) }]],
  outputDir: `/private/tmp/regengine-qa-fe-regression-test-results-${stamp}`,
  use: { baseURL: process.env.QA_BROWSER_BASE_URL || 'http://127.0.0.1:3114', serviceWorkers: 'block', viewport: { width: 1440, height: 900 } },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
});
