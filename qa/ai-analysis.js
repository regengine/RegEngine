#!/usr/bin/env node
/**
 * AI Content Analysis
 * Scans site source files for regulatory accuracy, copy consistency,
 * and common investor-facing credibility issues. No external API calls —
 * pure static analysis.
 */

const fs = require('fs');
const path = require('path');

const FRONTEND = path.join(__dirname, '..', 'frontend', 'src');
let passed = 0;
let failed = 0;
let warnings = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}
function warn(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.log(`  \u26a0 ${name}: ${detail}`); warnings++; }
}

function readAllFiles(dir, ext) {
  let files = [];
  try {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
        files = files.concat(readAllFiles(full, ext));
      } else if (entry.name.endsWith(ext)) {
        files.push(full);
      }
    }
  } catch (e) { /* skip inaccessible dirs */ }
  return files;
}

function searchFiles(pattern, files) {
  const results = [];
  const regex = typeof pattern === 'string' ? new RegExp(pattern, 'gi') : pattern;
  for (const f of files) {
    const content = fs.readFileSync(f, 'utf8');
    const matches = content.match(regex);
    if (matches) results.push({ file: path.relative(FRONTEND, f), matches: matches.length });
  }
  return results;
}

console.log('\n=== AI Content Analysis ===\n');

const tsxFiles = readAllFiles(FRONTEND, '.tsx');
const tsFiles = readAllFiles(FRONTEND, '.ts');
const allFiles = [...tsxFiles, ...tsFiles];
console.log(`Scanning ${allFiles.length} source files...\n`);

// ── 1. Regulatory Precision ─────────────────────────────
console.log('1. Regulatory Precision');

const bad6cte = searchFiles('6 Critical Tracking Event', allFiles);
check('No references to "6 CTEs" (must be 7)', bad6cte.length === 0,
  `Found in: ${bad6cte.map(r => r.file).join(', ')}`);

const badEnforcement = searchFiles('extended the (compliance|enforcement) (date|deadline)', allFiles);
warn('No "extended the deadline" language (FDA proposed, Congress directed)',
  badEnforcement.length === 0,
  `Found in: ${badEnforcement.map(r => r.file).join(', ')}`);

const badSoc2 = searchFiles('SOC.?2 (certified|compliant|certification)', allFiles);
warn('No SOC 2 certification claims (not yet certified)',
  badSoc2.length === 0,
  `Found in: ${badSoc2.map(r => r.file).join(', ')}`);

// ── 2. Pricing Consistency ──────────────────────────────
console.log('\n2. Pricing Consistency');

const oldTiers = searchFiles('Growth|Scale|Enterprise', allFiles.filter(f =>
  f.includes('pricing') || f.includes('retailer-readiness') || f.includes('customer-readiness')
));
warn('No old tier names (Growth/Scale/Enterprise) in pricing files',
  oldTiers.length === 0,
  `Found in: ${oldTiers.map(r => r.file).join(', ')}`);

const fiftyOff = searchFiles('50%.*(Off|off)', allFiles.filter(f => f.includes('pricing')));
warn('Pricing mentions 50% off', fiftyOff.length > 0, 'Missing 50% off messaging');

// ── 3. Dead Link Indicators ─────────────────────────────
console.log('\n3. Link Health Indicators');

const todoLinks = searchFiles('href="(TODO|FIXME|placeholder|example\\.com)"', allFiles);
warn('No placeholder links (excluding # anchors)', todoLinks.length === 0,
  `Found in: ${todoLinks.map(r => r.file).join(', ')}`);

const brokenImports = searchFiles("from ['\"]\\./[^'\"]+['\"]", tsxFiles.filter(f => f.includes('page.tsx')));
// This is informational — not a failure

// ── 4. Competitive Claims ───────────────────────────────
console.log('\n4. Competitive Claims');

const cheapestClaims = searchFiles('cheapest|lowest.price|most.affordable', allFiles);
warn('No "cheapest" claims (compete on transparency, not price)',
  cheapestClaims.length === 0,
  `Found in: ${cheapestClaims.map(r => r.file).join(', ')}`);

const networkClaims = searchFiles('largest.network|biggest.network|most.suppliers', allFiles);
warn('No "largest network" claims (incumbents own that lane)',
  networkClaims.length === 0,
  `Found in: ${networkClaims.map(r => r.file).join(', ')}`);

// ── 5. Loading State Audit ──────────────────────────────
console.log('\n5. Loading State Quality');

const bareLoading = searchFiles('fallback=\\{<div>Loading\\.\\.\\.', tsxFiles);
warn('No bare "Loading..." Suspense fallbacks',
  bareLoading.length === 0,
  `Found in: ${bareLoading.map(r => r.file).join(', ')}`);

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`AI Analysis: ${passed} passed, ${failed} failed, ${warnings} warnings`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
