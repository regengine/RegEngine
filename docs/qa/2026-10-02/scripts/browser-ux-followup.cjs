// Browser-only QA; uses the orchestrator's external Playwright 1.63 browser server.
// Public APIs are synthetic and no off-origin request is allowed to leave a context.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../../..');
const engines = require(path.join(root, 'frontend/node_modules/playwright'));
const AxeBuilder = require('/private/tmp/regengine-browser-ux-tools/node_modules/@axe-core/playwright').default;
const baseURL = 'http://127.0.0.1:3114';
const endpoint = process.env.PW_TEST_CONNECT_WS_ENDPOINT;
if (!endpoint || new URL(endpoint).hostname !== '127.0.0.1') throw new Error('A loopback browser server endpoint is required');
const stamp = new Date().toISOString().replace(/[:.]/g, '-');
const out = path.join(root, 'docs/qa/2026-10-02/artifacts/browser', `browser-ux-${stamp}`);
fs.mkdirSync(out, { recursive: true });
const routes = ['/', '/login', '/verify', '/tools/scan', '/contact', '/demo', '/tools/ftl-checker'];
const mode = process.argv[2] || 'audit'; // keyboard/states are focused harness retries.
const viewports = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };
const report = { startedAt: new Date().toISOString(), baseURL, playwrightVersion: require(path.join(root, 'frontend/node_modules/playwright/package.json')).version,
  axePlaywrightVersion: require('/private/tmp/regengine-browser-ux-tools/node_modules/@axe-core/playwright/package.json').version,
  restrictions: ['All APIs intercepted with synthetic responses; no backend', 'Exact local origin only; external resources/websockets blocked', 'Service workers blocked', 'HTML preconnect/dns-prefetch links removed and same-origin resource/connect CSP added', 'Synthetic login/contact errors; no email sent', 'Desktop and mobile are top-level browser viewport emulation, not physical devices'], pages: [], keyboard: [], errors: [] };
const safe = value => String(value).replace(/\b(?:sk-[\w-]{20,}|gh[pousr]_[\w]+|github_pat_[\w]+)\b/g, '[REDACTED]');
const save = () => fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(report, null, 2));

async function contextFor(browser, viewport, evidence) {
  const context = await browser.newContext({ viewport, serviceWorkers: 'block', colorScheme: 'light', reducedMotion: 'reduce' });
  await context.routeWebSocket('**/*', socket => { evidence.blockedWebSockets.push(socket.url()); socket.close(); });
  await context.route('**/*', async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== baseURL) {
      evidence.blockedRequests.push({ url: `${url.origin}${url.pathname}`, kind: request.resourceType() });
      return route.abort('blockedbyclient');
    }
    if (url.pathname.startsWith('/api/')) {
      let status = 401;
      let json = { detail: 'Synthetic QA unauthenticated response' };
      if (url.pathname.includes('csrf')) { status = 200; json = { csrf_token: 'synthetic-qa-csrf' }; }
      else if (url.pathname === '/api/tools/check-access') { status = 200; json = { hasAccess: false }; }
      else if (request.method() !== 'GET') { status = 503; json = { error: 'Synthetic QA service unavailable', detail: 'Synthetic QA service unavailable' }; }
      evidence.stubbedRequests.push({ path: url.pathname, method: request.method(), status });
      return route.fulfill({ status, json });
    }
    if (request.isNavigationRequest()) {
      const response = await route.fetch({ maxRedirects: 0 });
      const headers = { ...response.headers() };
      const redirect = headers.location;
      if (redirect && new URL(redirect, request.url()).origin !== baseURL) {
        evidence.blockedRequests.push({ url: new URL(redirect, request.url()).origin, kind: 'document redirect' });
        return route.fulfill({ status: 502, body: 'QA blocked off-origin redirect' });
      }
      if ((headers['content-type'] || '').includes('text/html')) {
        const body = (await response.text()).replace(/<link\b[^>]*rel=["'](?:preconnect|dns-prefetch)["'][^>]*>/gi, '');
        headers['content-security-policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'self'";
        delete headers['content-length'];
        return route.fulfill({ response, headers, body });
      }
      return route.fulfill({ response });
    }
    return route.continue();
  });
  return context;
}

function freshEvidence(browser, viewport, route) {
  return { browser, viewport, route, startedAt: new Date().toISOString(), consoleErrors: [], pageErrors: [], failedRequests: [], httpErrors: [], blockedRequests: [], blockedWebSockets: [], stubbedRequests: [] };
}
function listen(page, evidence) {
  page.on('console', message => { if (message.type() === 'error') evidence.consoleErrors.push({ text: safe(message.text()), location: message.location() }); });
  page.on('pageerror', error => evidence.pageErrors.push(safe(error.message)));
  page.on('requestfailed', request => evidence.failedRequests.push({ url: request.url(), error: request.failure()?.errorText, classification: new URL(request.url()).origin === baseURL ? 'local-request-failure' : 'intentional-external-block' }));
  page.on('response', response => { if (response.status() >= 400) evidence.httpErrors.push({ url: response.url(), status: response.status(), classification: new URL(response.url()).pathname.startsWith('/api/') ? 'synthetic-api-response' : 'local-response' }); });
}
async function ready(page, route) {
  const response = await page.goto(baseURL + route, { waitUntil: 'networkidle', timeout: 45000 });
  await page.waitForTimeout(250);
  return response;
}
async function snapshot(page, name) {
  const viewport = page.viewportSize();
  const metrics = await page.evaluate(() => ({ innerWidth, innerHeight, devicePixelRatio, documentWidth: document.documentElement.scrollWidth, documentHeight: document.documentElement.scrollHeight, horizontalOverflow: document.documentElement.scrollWidth > innerWidth, topLevel: self === top, title: document.title, h1: [...document.querySelectorAll('h1')].map(x => x.textContent.trim()), cameraAllowed: document.featurePolicy?.allowsFeature('camera') ?? null }));
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: false });
  await page.screenshot({ path: path.join(out, `${name}-full.png`), fullPage: true });
  return { viewport, ...metrics, screenshot: `${name}.png`, fullScreenshot: `${name}-full.png` };
}
async function focusState(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const label = el.id ? document.querySelector(`label[for="${el.id}"]`) : null;
    const labelStyle = label && getComputedStyle(label);
    return { tag: el.tagName, id: el.id, role: el.getAttribute('role'), name: el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 110) || el.getAttribute('placeholder'), href: el.getAttribute('href'), insideMenu: !!el.closest('[aria-label="Navigation menu"]'), focusVisible: el.matches(':focus-visible'), rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height }, outline: style.outline, boxShadow: style.boxShadow, clip: style.clip, labelOutline: labelStyle?.outline, labelBoxShadow: labelStyle?.boxShadow };
  });
}
async function tabUntil(page, predicate, evidence, limit = 70, tabKey = 'Tab') {
  for (let i = 0; i < limit; i++) {
    await page.keyboard.press(tabKey);
    await page.waitForTimeout(100);
    const state = await focusState(page);
    evidence.push(state);
    if (predicate(state)) return state;
  }
  throw new Error('Target was not reachable within keyboard tab budget');
}

async function keyboardChecks(browser, engineName) {
  const evidence = freshEvidence(engineName, 'mobile', '/');
  const tabKey = engineName === 'webkit' ? 'Alt+Tab' : 'Tab';
  evidence.keyboardMode = engineName === 'webkit' ? 'Option/Alt+Tab to include links and buttons under this macOS WebKit preference' : 'Tab';
  evidence.checks = {};
  const context = await contextFor(browser, viewports.mobile, evidence);
  const page = await context.newPage();
  listen(page, evidence);
  try {
    await ready(page, '/');
    await page.keyboard.press(tabKey);
    await page.waitForTimeout(250);
    evidence.checks.skipLink = { focus: await focusState(page), ...(await snapshot(page, `${engineName}-mobile-skip-link-focus`)) };
    await page.keyboard.press('Enter');
    await page.waitForTimeout(150);
    evidence.checks.skipLink.afterActivate = { url: page.url(), focus: await focusState(page), scrollY: await page.evaluate(() => scrollY) };
    await page.keyboard.press(tabKey);
    evidence.checks.skipLink.nextTab = await focusState(page);
    await ready(page, '/');
    const tabs = [];
    await tabUntil(page, state => state.name === 'Open navigation menu', tabs, 70, tabKey);
    await page.keyboard.press('Enter');
    await page.getByRole('dialog', { name: 'Navigation menu' }).waitFor();
    await page.waitForTimeout(350);
    const afterOpen = await focusState(page);
    await page.keyboard.press(tabKey);
    await page.waitForTimeout(100);
    const afterTab = await focusState(page);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(100);
    const openAfterEscape = await page.getByRole('dialog', { name: 'Navigation menu' }).isVisible();
    await page.keyboard.press(engineName === 'webkit' ? 'Alt+Shift+Tab' : 'Shift+Tab');
    await page.waitForTimeout(100);
    const afterShiftTab = await focusState(page);
    const screenshots = await snapshot(page, `${engineName}-mobile-menu-keyboard`);
    evidence.checks.mobileMenu = { tabs, afterOpen, afterTab, openAfterEscape, afterShiftTab, ...screenshots };

    await ready(page, '/tools/scan');
    const scannerTabs = [];
    await tabUntil(page, state => state.id === 'scan-manual-input', scannerTabs, 70, tabKey);
    await page.keyboard.type('010950600013435210BATCH-ABC');
    const inputFocus = await snapshot(page, `${engineName}-mobile-scanner-input-focus`);
    await page.keyboard.press('Enter');
    await page.getByText('BATCH-ABC', { exact: true }).first().waitFor();
    const afterParse = await focusState(page);
    const nextTabs = [];
    for (let i = 0; i < 10; i++) { await page.keyboard.press(tabKey); nextTabs.push(await focusState(page)); }
    evidence.checks.scanner = { steps: 'Tab from initial page until manual barcode input, type valid barcode, Enter, continue ten Tabs', scannerTabs, inputFocus, afterParse, nextTabs, result: 'BATCH-ABC visible; keyboard can leave parser', ...(await snapshot(page, `${engineName}-mobile-scanner-result`)) };
    const essentialButton = page.getByRole('button', { name: /^Essential/ });
    if (await essentialButton.isVisible()) await essentialButton.click();
    await page.getByText('BATCH-ABC', { exact: true }).first().scrollIntoViewIfNeeded();
    evidence.checks.scanner.resultFocused = { note: 'After recorded keyboard traversal; dismissed cookie banner with Essential, then scrolled lot result into view', ...(await snapshot(page, `${engineName}-mobile-scanner-result-focused`)) };
    evidence.checks.scanner.headings = await page.locator('h1,h2,h3').evaluateAll(nodes => nodes.map(node => ({ tag: node.tagName, text: node.textContent.trim() })));
    const parsedAxe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
    evidence.checks.scanner.axe = { version: parsedAxe.testEngine.version, violations: parsedAxe.violations, incomplete: parsedAxe.incomplete };

    await page.setViewportSize(viewports.desktop);
    await ready(page, '/verify');
    const verifyTabs = [];
    await tabUntil(page, state => state.id === 'verify-bundle-file', verifyTabs, 70, tabKey);
    const focusedInput = await focusState(page);
    evidence.checks.verifier = { verifyTabs, focusedInput, ...(await snapshot(page, `${engineName}-desktop-verifier-file-focus`)) };
    await page.keyboard.press(tabKey);
    evidence.checks.verifier.nextTab = await focusState(page);
  } catch (error) { evidence.error = safe(error.stack); }
  finally { await context.close(); }
  report.keyboard.push(evidence);
  save();
}

async function states(browser) {
  for (const [viewportName, viewport] of Object.entries(viewports)) {
    for (const route of ['/login', '/contact', '/verify', '/tools/ftl-checker']) {
      const evidence = freshEvidence('chromium', viewportName, route);
      evidence.state = 'synthetic-interaction';
      const context = await contextFor(browser, viewport, evidence);
      const page = await context.newPage();
      listen(page, evidence);
      try {
        await ready(page, route);
        if (route === '/login') {
          await page.getByLabel('Email address', { exact: true }).fill('qa-browser@example.invalid');
          await page.getByRole('button', { name: 'Continue', exact: true }).click();
          await page.locator('#login-error').waitFor();
          evidence.result = await page.locator('#login-error').innerText();
        } else if (route === '/contact') {
          await page.locator('input[name="name"]').fill('Synthetic browser QA');
          await page.locator('input[name="email"]').fill('qa-browser@example.invalid');
          await page.locator('textarea[name="message"]').fill('Synthetic local-only QA message.');
          await page.getByRole('button', { name: 'Send message' }).click();
          const alert = page.getByRole('alert').filter({ hasText: 'Something went wrong.' });
          await alert.waitFor();
          evidence.result = { alert: await alert.innerText(), retainedName: await page.locator('input[name="name"]').inputValue() };
        } else if (route === '/verify') {
          await page.locator('#verify-bundle-file').setInputFiles({ name: 'synthetic-qa-bundle.json', mimeType: 'application/json', buffer: Buffer.from('{"synthetic":true}') });
          await page.getByRole('button', { name: 'Verify bundle' }).click();
          await page.getByText('Verification failed (HTTP 503). Try again shortly, or run verify_chain.py locally.').waitFor();
          evidence.result = 'Synthetic local HTTP503 retained selected bundle and exposed recovery';
        } else {
          await page.getByLabel('Search products (e.g. shrimp)').fill('unlikely-nonexistent-product-qa');
          evidence.result = { noMatchesText: await page.getByText(/no (matches|results)/i).count(), checkDisabled: await page.getByRole('button', { name: /Check Listed Groupings/ }).isDisabled() };
        }
        Object.assign(evidence, await snapshot(page, `chromium-${viewportName}-${route.replaceAll('/', '_')}-state`));
        const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
        evidence.axe = { version: axe.testEngine.version, violations: axe.violations, incomplete: axe.incomplete, passes: axe.passes.map(x => x.id) };
      } catch (error) { evidence.error = safe(error.stack); }
      finally { await context.close(); }
      report.pages.push(evidence);
      save();
      console.log(JSON.stringify({ browser: 'chromium', viewport: viewportName, route, state: evidence.state, error: evidence.error, result: evidence.result }));
    }
  }
}

(async () => {
  for (const engineName of mode === 'states' ? ['chromium'] : ['chromium', 'firefox', 'webkit']) {
    let browser;
    try {
      browser = await engines[engineName].connect(endpoint);
      const actualBrowserType = browser.browserType().name();
      if (actualBrowserType !== engineName) throw new Error(`Connected ${actualBrowserType} when ${engineName} requested`);
      for (const [viewportName, viewport] of mode === 'audit' ? Object.entries(viewports) : []) {
        for (const route of routes) {
          const evidence = freshEvidence(engineName, viewportName, route);
          evidence.browserVersion = browser.version();
          evidence.actualBrowserType = actualBrowserType;
          const context = await contextFor(browser, viewport, evidence);
          const page = await context.newPage();
          listen(page, evidence);
          try {
            const response = await ready(page, route);
            evidence.status = response.status();
            evidence.permissionsPolicy = response.headers()['permissions-policy'];
            const name = `${engineName}-${viewportName}-${route.replaceAll('/', '_') || 'home'}`;
            Object.assign(evidence, await snapshot(page, name));
            const axe = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze();
            evidence.axe = { version: axe.testEngine.version, violations: axe.violations, incomplete: axe.incomplete, passes: axe.passes.map(x => x.id) };
          } catch (error) { evidence.error = safe(error.stack); }
          finally { await context.close(); }
          report.pages.push(evidence);
          save();
          console.log(JSON.stringify({ browser: engineName, viewport: viewportName, route, status: evidence.status, overflow: evidence.horizontalOverflow, axe: evidence.axe?.violations.map(x => ({ id: x.id, nodes: x.nodes.length })), pageErrors: evidence.pageErrors, error: evidence.error }));
        }
      }
      if (mode !== 'states') await keyboardChecks(browser, engineName);
      if (engineName === 'chromium' && mode !== 'keyboard') await states(browser);
    } catch (error) { report.errors.push({ engineName, error: safe(error.stack) }); save(); }
    finally { if (browser) await browser.close(); }
  }
  report.completedAt = new Date().toISOString();
  report.harnessErrorCount = report.errors.length + report.pages.filter(page => page.error).length + report.keyboard.filter(check => check.error).length;
  save();
  console.log(JSON.stringify({ output: out, pages: report.pages.length, keyboard: report.keyboard.length, errors: report.errors }));
  if (report.harnessErrorCount) process.exitCode = 1;
})().catch(error => { console.error(safe(error.stack)); process.exitCode = 1; });
