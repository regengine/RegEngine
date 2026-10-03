import { expect, type BrowserContext, type Route, type TestInfo } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

export const syntheticUser = (account: string) => ({
  id: `qa-user-${account}`, email: `qa-${account}@example.invalid`,
  is_sysadmin: false, status: 'active', role_name: 'member', permissions: [],
});

export async function isolateRegressionBrowser(
  context: BrowserContext,
  baseURL: string,
  api?: (route: Route, url: URL) => Promise<boolean>,
) {
  const origin = new URL(baseURL).origin;
  expect(['localhost', '127.0.0.1', '[::1]']).toContain(new URL(origin).hostname);
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) return route.abort('blockedbyclient');
    if (url.pathname.startsWith('/api/')) {
      if (api && await api(route, url)) return;
      return route.fulfill({ status: 200, json: url.pathname === '/api/session'
        ? { authenticated: false, has_api_key: false, has_credentials: false, tenant_id: null, user: null }
        : { hasAccess: false, products: [] } });
    }
    if (route.request().resourceType() === 'document') {
      // Prevent preconnect/DNS hints as well as ordinary browser requests.
      const response = await route.fetch({ maxRedirects: 0 });
      const location = response.headers().location;
      if (location) {
        expect(new URL(location, origin).origin).toBe(origin);
        return route.continue(); // WebKit cannot fulfill a redirect response.
      }
      const body = (await response.text()).replace(/<link\b[^>]*rel=["'](?:preconnect|dns-prefetch)["'][^>]*>/gi, '');
      return route.fulfill({ response, body, headers: {
        ...response.headers(),
        'content-security-policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'",
        'x-dns-prefetch-control': 'off',
      } });
    }
    return route.continue();
  });
}

export async function writeRegressionEvidence(testInfo: TestInfo, name: string, evidence: unknown) {
  const directory = path.resolve(__dirname, '../../../../docs/qa/2026-10-02/artifacts/browser');
  await mkdir(directory, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(directory, `${name}-${testInfo.project.name}-${stamp}.json`);
  await writeFile(file, JSON.stringify(evidence, null, 2) + '\n');
  await testInfo.attach(name, { path: file, contentType: 'application/json' });
  return file.replace(/\.json$/, '.png');
}
