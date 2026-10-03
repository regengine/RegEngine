# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: security-release-gate.spec.ts >> Security release gate >> session tenant cannot be replaced by a path assertion
- Location: tests/e2e/security-release-gate.spec.ts:23:9

# Error details

```
Error: QA environment restriction: database/bootstrap helper is outside browser-only scope
```

# Test source

```ts
  1  | // QA-only safety envelope for the unchanged browser suite. Never loads dotenv.
  2  | require('./node-isolation.cjs');
  3  | const childProcess = require('node:child_process');
  4  | const fs = require('node:fs');
  5  | const path = require('node:path');
  6  | const { syncBuiltinESMExports } = require('node:module');
  7  | const root = path.resolve(__dirname, '../../../..');
  8  | 
  9  | for (const method of ['execFileSync', 'spawn', 'spawnSync', 'exec', 'execSync']) {
  10 |   const original = childProcess[method];
  11 |   childProcess[method] = function (...args) {
  12 |     if (args.slice(0, 2).flat().some(value => /seed_passwordless_e2e_user|start-e2e-backend|sqlite|alembic/.test(String(value)))) {
> 13 |       throw new Error('QA environment restriction: database/bootstrap helper is outside browser-only scope');
     |             ^ Error: QA environment restriction: database/bootstrap helper is outside browser-only scope
  14 |     }
  15 |     return original.apply(this, args);
  16 |   };
  17 | }
  18 | const rmSync = fs.rmSync;
  19 | fs.rmSync = function (file, ...args) {
  20 |   if (String(file).includes('regengine-playwright-email-outbox')) {
  21 |     throw new Error('QA environment restriction: OTP database fixture cleanup is outside browser-only scope');
  22 |   }
  23 |   return rmSync.call(this, file, ...args);
  24 | };
  25 | syncBuiltinESMExports();
  26 | 
  27 | const playwright = require(path.join(root, 'frontend/node_modules/@playwright/test'));
  28 | playwright.test = playwright.test.extend({
  29 |   _qaSafety: [async ({ browser }, use) => {
  30 |     const newContext = browser.newContext.bind(browser);
  31 |     browser.newContext = async (...args) => {
  32 |       const context = await newContext(...args);
  33 |       await context.route('**/*', async route => {
  34 |         const url = new URL(route.request().url());
  35 |         if (url.origin !== 'http://127.0.0.1:3115') {
  36 |           return route.abort('blockedbyclient');
  37 |         }
  38 |         // Playwright only routes the first URL in a redirect chain. The proxy
  39 |         // validates every upstream Location and sanitizes every final HTML.
  40 |         return route.continue();
  41 |       });
  42 |       return context;
  43 |     };
  44 |     await use();
  45 |     browser.newContext = newContext;
  46 |   }, { auto: true }],
  47 | });
  48 | 
```