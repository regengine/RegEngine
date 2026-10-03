// Browser witness for the existing tour test's WebKit geometry failure.
require('./node-isolation.cjs');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../../..');
const engines = require(path.join(root, 'frontend/node_modules/playwright'));
const artifacts = path.join(root, 'docs/qa/2026-10-02/artifacts/browser');
const base = 'http://127.0.0.1:3115';
const suffix = process.env.QA_E2E_RUN || 'proxy';

(async () => {
  const results = [];
  for (const engine of ['chromium', 'firefox', 'webkit']) {
    const browser = await engines[engine].connect(process.env.PW_TEST_CONNECT_WS_ENDPOINT);
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: 'block' });
    await context.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== base) return route.abort('blockedbyclient');
      // Every redirect hop and HTML response is enforced by the local proxy.
      return route.continue();
    });
    const page = await context.newPage();
    await page.goto(base + '/tools/inflow-lab-dashboard-preview');
    await page.getByTestId('inflow-tutorial-banner').getByRole('button', { name: /Learn to operate it step by step/i }).click();
    await page.getByText('Step 1 of 7').waitFor();
    const samples = [];
    for (const delayMs of [900, 2000, 5000]) {
      await page.waitForTimeout(delayMs);
      const box = await page.getByRole('dialog').boundingBox();
      const next = await page.getByRole('dialog').getByRole('button', { name: 'Next' }).boundingBox();
      samples.push({ elapsedMs: samples.reduce((sum, sample) => sum + sample.delayMs, 0) + delayMs,
        delayMs, box, bottom: box.y + box.height, next, nextBottom: next.y + next.height,
        viewport: await page.evaluate(() => ({ width: innerWidth, height: innerHeight })) });
    }
    const screenshot = `existing-e2e-tour-${suffix}-${engine}-settled.png`;
    await page.screenshot({ path: path.join(artifacts, screenshot) });
    results.push({ engine, route: '/tools/inflow-lab-dashboard-preview', step: 1, screenshot, samples });
    await context.close();
    await browser.close();
  }
  fs.writeFileSync(path.join(artifacts, `existing-e2e-tour-${suffix}-settling.json`), JSON.stringify(results, null, 2) + '\n');
  console.log(JSON.stringify(results, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
