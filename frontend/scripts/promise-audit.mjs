#!/usr/bin/env node

import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const ROOT = path.resolve(new URL('..', import.meta.url).pathname);
const APP_ROOT = path.join(ROOT, 'src', 'app');
const SRC_ROOT = path.join(ROOT, 'src');

const BANNED_SOURCE_PATTERNS = [
  { label: 'Dead status host', pattern: /status\.regengine\.co/g },
  { label: 'Dead Slack host', pattern: /slack\.regengine\.co/g },
  { label: 'Dead legacy API host', pattern: /api\.regengine\.co/g },
  { label: 'Dead Cal.com CTA', pattern: /cal\.com\/regengine/g },
  { label: 'Overclaim: Start Free Trial', pattern: /Start Free Trial/g },
  { label: 'Overclaim: 14-day free trial', pattern: /14-day free trial/g },
  { label: 'Overclaim: Get API Access', pattern: /Get API Access/g },
  { label: 'Overclaim: community Slack', pattern: /community Slack/g },
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

async function fetchWithTimeout(url, timeoutMs = 30000) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      redirect: 'follow',
      cache: 'no-store',
      signal: controller.signal,
      headers: { 'user-agent': 'regengine-promise-audit/1.0' },
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchWithRetry(url, attempts = 2) {
  // External hosts (e.g. calendly.com) intermittently take >10s to first
  // byte, which flaked this gate on unrelated PRs. One retry plus a more
  // generous timeout keeps the dead-link signal (dead hosts still error or
  // 4xx/5xx) without failing the build on a slow-but-alive endpoint.
  let lastError;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fetchWithTimeout(url);
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
        findings.push({
          type: 'bad-external-url',
          url,
          status: response.status,
        });
      }
    } catch (error) {
      findings.push({
        type: 'bad-external-url',
        url,
        error: error instanceof Error ? error.message : String(error),
      });
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
