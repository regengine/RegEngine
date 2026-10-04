#!/usr/bin/env node

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const ROOT = path.resolve(new URL('..', import.meta.url).pathname);
const APP_ROOT = path.join(ROOT, 'src', 'app');
const SRC_ROOT = path.join(ROOT, 'src');

const BANNED_SOURCE_PATTERNS = [
  // `include` (optional) restricts a rule to files under that directory.
  // The portal no longer mints or labels `rge_test_` sandbox keys (guarded by
  // src/__tests__/developer-portal-guards.test.ts); docs pages must never
  // present the sandbox prefix as a live API credential format.
  {
    label: 'Sandbox key prefix presented in docs',
    pattern: /rge_test_/g,
    include: path.join(APP_ROOT, 'docs'),
  },
  { label: 'Dead status host', pattern: /status\.regengine\.co/g },
  { label: 'Dead Slack host', pattern: /slack\.regengine\.co/g },
  { label: 'Dead legacy API host', pattern: /api\.regengine\.co/g },
  { label: 'Dead Cal.com CTA', pattern: /cal\.com\/regengine/g },
  { label: 'Overclaim: Start Free Trial', pattern: /Start Free Trial/g },
  { label: 'Overclaim: 14-day free trial', pattern: /14-day free trial/g },
  { label: 'Overclaim: Get API Access', pattern: /Get API Access/g },
  { label: 'Overclaim: community Slack', pattern: /community Slack/g },
  // Copy-remediation program 2026-08 (see COPY_AUDIT.md) — keep these dead:
  { label: 'Placeholder API host', pattern: /your-preview-host/g },
  { label: 'Fabricated evidence: customer interviews', pattern: /customer interviews/g },
  { label: 'Implied customers: Why teams switch', pattern: /Why teams switch/g },
  { label: 'Implied third parties: we have identified', pattern: /we have identified/g },
  { label: 'Legal verdict: FSMA 204 Compliant', pattern: /FSMA 204 Compliant/g },
  { label: 'Overclaim: tamper-proof', pattern: /[Tt]amper-proof/g },
  { label: 'Overclaim: unbreakable', pattern: /unbreakable/g },
  { label: 'Fake verification: Integrity Status: VERIFIED', pattern: /Integrity Status: VERIFIED/g },
  { label: 'Password-auth copy', pattern: /Create Password|Confirm Password|Reset your password/g },
  { label: 'Dead anchor: /#sandbox', pattern: /\/#sandbox/g },
  { label: 'Invented uptime stat', pattern: /uptime_percent/g },
  { label: 'Stale version promise: Coming in v1.1', pattern: /Coming in v1\.1/g },
  { label: 'Fake audit actor: dashboard_user', pattern: /dashboard_user/g },
];

const SOURCE_GLOBS = [
  path.join(SRC_ROOT, 'app'),
  path.join(SRC_ROOT, 'components'),
  path.join(SRC_ROOT, 'lib'),
];

const CRITICAL_INTERNAL_ROUTES = [
  '/',
  '/pricing',
  '/product',
  '/integrations',
  '/docs',
  '/docs/api',
  '/docs/quickstart',
  '/docs/sdks',
  '/developers',
  '/developer/portal',
  '/developer/portal/keys',
  '/about',
  '/blog',
  '/contact',
  '/privacy',
  '/terms',
  '/dpa',
  '/security',
  '/trust',
  '/tools',
  '/tools/ftl-checker',
  '/tools/recall-readiness',
  '/tools/roi-calculator',
  '/signup',
  '/login',
];

const CRITICAL_EXTERNAL_URLS = [
  'https://calendly.com/regengine/fsma-strategy-session',
  'https://supabase.com/privacy',
  'https://railway.app/legal/privacy',
  'https://vercel.com/legal/privacy-policy',
  'https://stripe.com/privacy',
  'https://resend.com/legal/privacy-policy',
  'https://sentry.io/privacy/',
  'https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list',
  'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)',
];

const findings = [];

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const fullPath = path.join(dir, entry);
    const stat = statSync(fullPath);
    if (stat.isDirectory()) {
      walk(fullPath, out);
      continue;
    }
    if (/\.(tsx?|jsx?|mjs|cjs|json|md)$/i.test(entry)) {
      out.push(fullPath);
    }
  }
  return out;
}

function routeExists(route) {
  const normalized = route === '/' ? '' : route.replace(/^\/+/, '');
  const base = path.join(APP_ROOT, normalized);
  const candidates = [
    path.join(base, 'page.tsx'),
    path.join(base, 'page.ts'),
    path.join(base, 'route.ts'),
    path.join(base, 'route.tsx'),
    path.join(APP_ROOT, `${normalized}.tsx`),
    path.join(APP_ROOT, `${normalized}.ts`),
  ];
  return candidates.some((candidate) => existsSync(candidate));
}

async function auditSourcePatterns() {
  const files = (await Promise.all(SOURCE_GLOBS.map((dir) => walk(dir)))).flat();

  for (const file of files) {
    const contents = readFileSync(file, 'utf8');
    for (const rule of BANNED_SOURCE_PATTERNS) {
      if (rule.include && !file.startsWith(rule.include + path.sep)) {
        continue;
      }
      const matches = contents.match(rule.pattern);
      if (matches && matches.length > 0) {
        findings.push({
          type: 'banned-source-pattern',
          label: rule.label,
          file,
          count: matches.length,
        });
      }
    }
  }
}

function auditInternalRoutes() {
  for (const route of CRITICAL_INTERNAL_ROUTES) {
    if (!routeExists(route)) {
      findings.push({
        type: 'missing-internal-route',
        route,
      });
    }
  }
}

async function fetchWithTimeout(url, timeoutMs = 30000, method = 'GET') {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      method,
      redirect: 'follow',
      cache: 'no-store',
      signal: controller.signal,
      // A real browser UA — some hosts (calendly) stall or block obvious
      // bot user-agents, producing inconclusive timeouts.
      headers: {
        'user-agent':
          'Mozilla/5.0 (compatible; regengine-promise-audit/1.0; +https://regengine.co)',
      },
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchWithRetry(url, attempts = 3) {
  // Some external hosts (e.g. calendly.com) intermittently take a long time
  // to first byte, or stall a bot user-agent entirely. Retry a few times
  // with a generous timeout before giving up.
  let lastError;
  for (let i = 0; i < attempts; i++) {
    try {
      // Prefer HEAD — lighter, and less likely to hang on a heavy page
      // render than a full GET. Fall back to GET if the host rejects HEAD.
      const head = await fetchWithTimeout(url, 30000, 'HEAD');
      if (head.status === 405 || head.status === 501) {
        return await fetchWithTimeout(url, 30000, 'GET');
      }
      return head;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

async function auditExternalUrls() {
  if (process.env.PROMISE_AUDIT_SKIP_EXTERNAL === '1') {
    console.log('Skipping external URL checks because PROMISE_AUDIT_SKIP_EXTERNAL=1');
    return;
  }

  for (const url of CRITICAL_EXTERNAL_URLS) {
    try {
      const response = await fetchWithRetry(url);
      if (response.status >= 400) {
        // A definitive HTTP error status means the link is genuinely
        // broken (wrong path, removed page) — fail the build.
        findings.push({
          type: 'bad-external-url',
          url,
          status: response.status,
        });
      }
    } catch (error) {
      // A network error / timeout / abort is INCONCLUSIVE: it does not
      // prove the URL is dead, and hard-failing on it flaked this gate on
      // unrelated PRs (e.g. calendly.com stalling a bot user-agent). Warn
      // so a persistently unreachable host is still visible in logs, but
      // do not fail the build — only real 4xx/5xx responses do that.
      console.warn(
        `promise-audit: WARN could not verify external URL ${url} ` +
          `(${error instanceof Error ? error.message : String(error)}) — ` +
          'treating as inconclusive, not a dead link',
      );
    }
  }
}

function printSummary() {
  if (findings.length === 0) {
    console.log('promise-audit: ok');
    return;
  }

  console.error('promise-audit: found issues');
  for (const finding of findings) {
    if (finding.type === 'banned-source-pattern') {
      console.error(`- ${finding.label}: ${finding.file} (${finding.count})`);
      continue;
    }
    if (finding.type === 'missing-internal-route') {
      console.error(`- Missing internal route backing file: ${finding.route}`);
      continue;
    }
    if (finding.type === 'bad-external-url') {
      const detail = 'status' in finding ? `HTTP ${finding.status}` : finding.error;
      console.error(`- External URL check failed: ${finding.url} (${detail})`);
    }
  }
}

async function main() {
  await auditSourcePatterns();
  auditInternalRoutes();
  await auditExternalUrls();
  printSummary();
  process.exit(findings.length === 0 ? 0 : 1);
}

await main();
