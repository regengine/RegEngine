// QA-only safety envelope for the unchanged browser suite. Never loads dotenv.
require('./node-isolation.cjs');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { syncBuiltinESMExports } = require('node:module');
const root = path.resolve(__dirname, '../../../..');

for (const method of ['execFileSync', 'spawn', 'spawnSync', 'exec', 'execSync']) {
  const original = childProcess[method];
  childProcess[method] = function (...args) {
    if (args.slice(0, 2).flat().some(value => /seed_passwordless_e2e_user|start-e2e-backend|sqlite|alembic/.test(String(value)))) {
      throw new Error('QA environment restriction: database/bootstrap helper is outside browser-only scope');
    }
    return original.apply(this, args);
  };
}
const rmSync = fs.rmSync;
fs.rmSync = function (file, ...args) {
  if (String(file).includes('regengine-playwright-email-outbox')) {
    throw new Error('QA environment restriction: OTP database fixture cleanup is outside browser-only scope');
  }
  return rmSync.call(this, file, ...args);
};
syncBuiltinESMExports();

const playwright = require(path.join(root, 'frontend/node_modules/@playwright/test'));
playwright.test = playwright.test.extend({
  _qaSafety: [async ({ browser }, use) => {
    const newContext = browser.newContext.bind(browser);
    browser.newContext = async (...args) => {
      const context = await newContext(...args);
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== 'http://127.0.0.1:3115') {
          return route.abort('blockedbyclient');
        }
        // Playwright only routes the first URL in a redirect chain. The proxy
        // validates every upstream Location and sanitizes every final HTML.
        return route.continue();
      });
      return context;
    };
    await use();
    browser.newContext = newContext;
  }, { auto: true }],
});
