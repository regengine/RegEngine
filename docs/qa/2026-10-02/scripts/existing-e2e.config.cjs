// Runs original specs unchanged against an isolated local frontend.
require('./existing-e2e-safety.cjs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../../..');
const { defineConfig, devices } = require(path.join(root, 'frontend/node_modules/@playwright/test'));
const suffix = process.env.QA_E2E_RUN || 'fallback';
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:3115';
if (baseURL !== 'http://127.0.0.1:3115') throw new Error('QA E2E requires the per-hop loopback proxy on port 3115');
const projects = [
  { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  { name: 'webkit', use: { ...devices['Desktop Safari'] } },
];

module.exports = defineConfig({
  testDir: path.join(root, 'frontend/tests/e2e'),
  testIgnore: '**/qa-2026-10-02/**',
  globalSetup: path.join(root, 'frontend/tests/e2e/global-setup.ts'),
  timeout: 45000,
  expect: { timeout: 15000 },
  workers: 3,
  retries: 0,
  fullyParallel: true,
  outputDir: path.join(root, `docs/qa/2026-10-02/artifacts/browser/existing-e2e-${suffix}-details`),
  reporter: [['list'], ['json', { outputFile: path.join(root, `docs/qa/2026-10-02/artifacts/browser/existing-e2e-${suffix}.json`) }]],
  use: {
    baseURL,
    serviceWorkers: 'block',
    screenshot: 'only-on-failure',
    trace: 'off',
  },
  projects,
});
