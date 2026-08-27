#!/usr/bin/env node
/**
 * Frontend Security Scan
 *
 * A STATIC TEXT SCAN of frontend TypeScript sources. It checks credential
 * hygiene (no hardcoded keys, no passwords in localStorage) and a few auth
 * wiring conventions.
 *
 * WHAT THIS DOES NOT DO (#2824): it does not verify tenant isolation. It
 * opens no database, starts no app, issues no request, and never attempts a
 * cross-tenant read. Tenant isolation in this platform is enforced by
 * PostgreSQL RLS policies, which are invisible to a .tsx text scan -- a
 * policy could be dropped, inverted, or written fail-open and every check
 * below would still pass.
 *
 * This file used to be named `tenant-test.js` and ran under a CI step called
 * "Tenant isolation checks", which is why it was mistaken for that. Real
 * isolation coverage lives in:
 *   - services/shared/tests/test_rls_enforcement_live.py
 *   - tests/migrations/test_rls_coverage.py
 *   - services/admin/tests/test_isolation_testcontainers.py
 */

const fs = require('fs');
const path = require('path');

let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}

const SRC = path.join(__dirname, '..', 'frontend', 'src');

function readAllTsx(dir) {
  let files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
      files = files.concat(readAllTsx(full));
    } else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts')) {
      files.push(full);
    }
  }
  return files;
}

function resolveLocalImport(fromFile, specifier) {
  let basePath = null;

  if (specifier.startsWith('@/')) {
    basePath = path.join(SRC, specifier.slice(2));
  } else if (specifier.startsWith('./') || specifier.startsWith('../')) {
    basePath = path.resolve(path.dirname(fromFile), specifier);
  } else {
    return null;
  }

  const candidates = [
    basePath,
    `${basePath}.ts`,
    `${basePath}.tsx`,
    path.join(basePath, 'index.ts'),
    path.join(basePath, 'index.tsx'),
  ];

  for (const candidate of candidates) {
    if (candidate.startsWith(SRC) && fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
      return candidate;
    }
  }

  return null;
}

function fileReferencesTenant(file, seen = new Set()) {
  if (seen.has(file) || !fs.existsSync(file)) {
    return false;
  }

  seen.add(file);
  const content = fs.readFileSync(file, 'utf8');
  if (content.includes('tenantId') || content.includes('tenant_id')) {
    return true;
  }

  const importPattern = /from\s+['"]([^'"]+)['"]/g;
  let match;
  while ((match = importPattern.exec(content)) !== null) {
    const importedFile = resolveLocalImport(file, match[1]);
    if (importedFile && fileReferencesTenant(importedFile, seen)) {
      return true;
    }
  }

  return false;
}

console.log('\n=== Frontend Security Scan (static text scan; NOT tenant-isolation verification) ===\n');

const allFiles = readAllTsx(SRC);
console.log(`Scanning ${allFiles.length} TypeScript files...\n`);

// ── 1. No hardcoded API keys ────────────────────────────
console.log('1. Credential Safety');

const keyPatterns = [
  { pattern: /sk[-_]live[-_][a-zA-Z0-9]{20,}/g, name: 'Stripe live key' },
  { pattern: /sk[-_]test[-_][a-zA-Z0-9]{20,}/g, name: 'Stripe test key' },
  { pattern: /eyJ[a-zA-Z0-9_-]{50,}\.[a-zA-Z0-9_-]{50,}\.[a-zA-Z0-9_-]{50,}/g, name: 'JWT token' },
  { pattern: /AKIA[0-9A-Z]{16}/g, name: 'AWS access key' },
];

let foundKeys = 0;
for (const file of allFiles) {
  const content = fs.readFileSync(file, 'utf8');
  for (const { pattern, name } of keyPatterns) {
    const matches = content.match(pattern);
    if (matches) {
      const rel = path.relative(SRC, file);
      // Skip test files and env examples
      if (!rel.includes('test') && !rel.includes('.example')) {
        console.error(`  \u2717 Found ${name} in ${rel}`);
        foundKeys++;
      }
    }
  }
}
check('No hardcoded API keys in source', foundKeys === 0, `Found ${foundKeys} keys`);

// ── 2. Auth context usage ───────────────────────────────
console.log('\n2. Auth Context');

const authContext = path.join(SRC, 'lib', 'auth-context.tsx');
check('auth-context.tsx exists', fs.existsSync(authContext), 'Missing auth context file');

if (fs.existsSync(authContext)) {
  const authContent = fs.readFileSync(authContext, 'utf8');
  // Auth context must source session state from somewhere live —
  // either Supabase's onAuthStateChange listener (legacy) or the
  // HTTP-only-cookie session source via /api/session + getSessionInfo
  // (post-#2353 hardening). Either is acceptable; both being absent
  // is the regression we want to catch.
  const hasSupabaseListener = authContent.includes('onAuthStateChange');
  const hasCookieSession =
    authContent.includes('/api/session') &&
    authContent.includes('getSessionInfo');
  check('Auth context wires a live session source',
    hasSupabaseListener || hasCookieSession,
    'Missing both Supabase auth state listener AND /api/session getSessionInfo flow'
  );
  check('Auth context does NOT clear on INITIAL_SESSION null',
    !authContent.includes("case 'INITIAL_SESSION'") ||
    authContent.includes('SIGNED_OUT'),
    'May clear credentials on initial null session'
  );
}

// ── 3. Dashboard pages use tenantId ─────────────────────
console.log('\n3. Dashboard Tenant-Reference Convention (lint-level; proves nothing about isolation)');

const dashboardDir = path.join(SRC, 'app', 'dashboard');
if (fs.existsSync(dashboardDir)) {
  const dashPages = readAllTsx(dashboardDir).filter(f => f.endsWith('page.tsx'));
  let tenantMissing = [];
  for (const page of dashPages) {
    const rel = path.relative(SRC, page);
    const hasTenant = fileReferencesTenant(page);
    if (hasTenant) { console.log(`  \u2713 ${rel} mentions a tenant identifier`); passed++; }
    else { tenantMissing.push(rel); }
  }
  if (tenantMissing.length > 0) {
    console.log(`  \u26a0 ${tenantMissing.length} dashboard pages do not mention a tenant identifier (non-blocking convention check):`);
    tenantMissing.forEach(f => console.log(`    - ${f}`));
  }
}

// ── 4. No localStorage passwords ────────────────────────
console.log('\n4. Credential Storage');

let storedPasswords = 0;
for (const file of allFiles) {
  const content = fs.readFileSync(file, 'utf8');
  if (content.includes("localStorage.setItem") && content.includes('password')) {
    const rel = path.relative(SRC, file);
    console.error(`  \u2717 Password stored in localStorage: ${rel}`);
    storedPasswords++;
  }
}
check('No passwords in localStorage', storedPasswords === 0, `Found ${storedPasswords}`);

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Frontend Security Scan: ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
