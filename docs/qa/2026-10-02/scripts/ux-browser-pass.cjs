// QA-only local browser audit. No production calls; API requests are intercepted.
// Usage: QA_MIRROR=/private/tmp/... node this-file.cjs [smoke|audit]
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../../../..');
const { chromium, firefox, webkit } = require(path.join(root, 'frontend/node_modules/playwright'));
const mirror = process.env.QA_MIRROR;
if (!mirror || !mirror.startsWith('/private/tmp/regengine-qa-ux-')) throw new Error('Set QA_MIRROR to the isolated QA directory');
const out = path.join(root, 'docs/qa/2026-10-02/artifacts/ux');
const baseURL = 'http://127.0.0.1:3104';
const mode = process.argv[2] || 'smoke';
const results = { startedAt: new Date().toISOString(), mode, baseURL, syntheticApi: true, browsers: [] };
const safe = text => String(text).replace(/\b(?:sk-[\w-]{20,}|gh[pousr]_[\w]+|github_pat_[\w]+)\b/g, '[REDACTED]');
const pause = ms => new Promise(r => setTimeout(r, ms));

async function configure(context, evidence) {
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (!['localhost', '127.0.0.1', '::1'].includes(url.hostname)) {
      evidence.blockedHosts.add(url.hostname);
      return route.abort('blockedbyclient');
    }
    if (url.pathname.startsWith('/api/')) {
      evidence.stubbedApis.add(url.pathname);
      if (url.pathname.includes('/csrf')) return route.fulfill({ status: 200, json: { csrf_token: 'synthetic-qa-csrf' } });
      return route.fulfill({ status: 401, json: { detail: 'Synthetic QA unauthenticated response' } });
    }
    return route.continue();
  });
  await context.addInitScript(() => {
    window.__qaPerformance = { lcp: null, cls: 0, longTasks: [] };
    try { new PerformanceObserver(l => { window.__qaPerformance.lcp = l.getEntries().at(-1).startTime; }).observe({ type: 'largest-contentful-paint', buffered: true }); } catch {}
    try { new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) window.__qaPerformance.cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch {}
    try { new PerformanceObserver(l => { window.__qaPerformance.longTasks.push(...l.getEntries().map(e => e.duration)); }).observe({ type: 'longtask', buffered: true }); } catch {}
  });
}

async function snapshot(page, label, accessibility) {
  await page.screenshot({ path: path.join(out, label + '.png'), fullPage: true });
  const data = await page.evaluate(() => ({
    title: document.title,
    headings: [...document.querySelectorAll('h1,h2,h3')].map(el => ({ level: el.tagName, text: el.textContent.trim() })),
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    viewportWidth: innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    inputs: [...document.querySelectorAll('input,textarea,select')].map(el => ({ tag: el.tagName, type: el.type, id: el.id, name: el.name, labels: [...(el.labels || [])].map(x => x.textContent.trim()), required: el.required, disabled: el.disabled })),
    cameraAllowed: document.featurePolicy?.allowsFeature('camera') ?? null,
    performance: { ...window.__qaPerformance, navigation: performance.getEntriesByType('navigation').map(e => ({ duration: e.duration, domContentLoaded: e.domContentLoadedEventEnd, responseStart: e.responseStart })), paint: performance.getEntriesByType('paint').map(e => ({ name: e.name, startTime: e.startTime })) },
  }));
  data.url = page.url();
  data.screenshot = label + '.png';
  data.ariaSnapshot = await page.locator('body').ariaSnapshot();
  if (accessibility) {
    await page.evaluate(fs.readFileSync(path.join(mirror, 'qa-tools/node_modules/axe-core/axe.min.js'), 'utf8'));
    const axe = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'] } }));
    data.axe = { version: axe.testEngine.version, violations: axe.violations, incomplete: axe.incomplete, passes: axe.passes.map(x => x.id) };
  }
  fs.writeFileSync(path.join(out, label + '.json'), JSON.stringify(data, null, 2));
  return { url: data.url, screenshot: data.screenshot, title: data.title, h1: data.headings.filter(x => x.level === 'H1').map(x => x.text), overflow: data.horizontalOverflow, cameraAllowed: data.cameraAllowed, axe: data.axe?.violations.map(x => ({ id: x.id, impact: x.impact, nodes: x.nodes.length })), performance: data.performance };
}

(async () => {
  for (const [name, engine] of Object.entries(mode === 'smoke' ? { chromium, firefox, webkit } : { chromium })) {
    const result = { name, startedAt: new Date().toISOString(), pages: [], errors: [], consoleErrors: [], networkErrors: [], blockedHosts: new Set(), stubbedApis: new Set() };
    let browser;
    try {
      browser = await engine.launch({ headless: true,
        ...(name === 'chromium' ? { args: ['--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1', '--disable-background-networking'] } : {}),
        ...(name === 'firefox' ? { firefoxUserPrefs: { 'network.dns.disablePrefetch': true, 'network.prefetch-next': false, 'network.http.speculative-parallel-limit': 0 } } : {}),
      });
      result.version = browser.version();
      for (const width of mode === 'smoke' ? [1440] : [1440, 390, 320]) {
        const context = await browser.newContext({ viewport: { width, height: 900 }, serviceWorkers: 'block' });
        await configure(context, result);
        const page = await context.newPage();
        page.on('pageerror', e => result.errors.push(safe(e.message)));
        page.on('console', e => { if (e.type() === 'error') result.consoleErrors.push(safe(e.text())); });
        page.on('response', r => { if (r.status() >= 400) result.networkErrors.push({ status: r.status(), url: new URL(r.url()).pathname }); });
        const routes = mode === 'smoke' ? ['/', '/login', '/verify', '/tools/scan'] : ['/', '/login', '/verify', '/demo', '/contact', '/tools/ftl-checker'];
        for (const route of routes) {
          try {
            const response = await page.goto(baseURL + route, { waitUntil: 'networkidle', timeout: 90000 });
            await pause(300);
            const label = `${mode}-${name}-${width}-${route.replace(/\//g, '_') || 'home'}`;
            const data = await snapshot(page, label, mode === 'audit');
            data.status = response.status();
            data.permissionsPolicy = response.headers()['permissions-policy'];
            result.pages.push(data);
            console.log(JSON.stringify({ browser: name, width, route, status: data.status, title: data.title, h1: data.h1, overflow: data.overflow, axe: data.axe }));
          } catch (error) { result.errors.push(safe(`${width} ${route}: ${error.message}`)); }
        }
        await context.close();
      }
    } catch (error) { result.errors.push(safe(error.message)); }
    finally { if (browser) await browser.close(); }
    result.blockedHosts = [...result.blockedHosts];
    result.stubbedApis = [...result.stubbedApis];
    result.completedAt = new Date().toISOString();
    results.browsers.push(result);
    fs.writeFileSync(path.join(out, `${mode}-results.json`), JSON.stringify(results, null, 2));
    console.log(JSON.stringify({ browser: name, errors: result.errors, blockedHosts: result.blockedHosts }));
  }
  results.completedAt = new Date().toISOString();
  fs.writeFileSync(path.join(out, `${mode}-results.json`), JSON.stringify(results, null, 2));
})().catch(error => { console.error(safe(error.stack)); process.exitCode = 1; });
