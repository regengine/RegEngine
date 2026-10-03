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
  35 |         if (!['localhost', '127.0.0.1', '::1', '[::1]'].includes(url.hostname)) {
  36 |           return route.abort('blockedbyclient');
  37 |         }
  38 |         if (route.request().resourceType() === 'document') {
  39 |           const response = await route.fetch({ maxRedirects: 0 });
  40 |           if ((response.headers()['content-type'] || '').includes('text/html')) {
  41 |             const body = (await response.text()).replace(/<link\b[^>]*rel=["'](?:preconnect|dns-prefetch)["'][^>]*>/gi, '');
  42 |             return route.fulfill({ response, body, headers: {
  43 |               ...response.headers(),
  44 |               'content-security-policy': "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self' data:; frame-src 'self'; object-src 'none'; base-uri 'self'",
  45 |             } });
  46 |           }
  47 |           return route.fulfill({ response });
  48 |         }
  49 |         return route.continue();
  50 |       });
  51 |       return context;
  52 |     };
  53 |     await use();
  54 |     browser.newContext = newContext;
  55 |   }, { auto: true }],
  56 | });
  57 | 
```