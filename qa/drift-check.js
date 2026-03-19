#!/usr/bin/env node
/**
 * Drift Detection
 * Compares current QA summary against the locked baseline.
 * Fails if:
 *   - Coverage decreased (fewer checks)
 *   - Warnings increased without acknowledgment
 *   - Any category degraded from PASS to WARN or FAIL
 */

const fs = require('fs');
const path = require('path');

const BASELINE_PATH = path.join(__dirname, 'baseline-summary.json');
const CURRENT_PATH = path.join(__dirname, 'qa-summary.json');

let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}

console.log('\n=== Drift Detection ===\n');

if (!fs.existsSync(BASELINE_PATH)) {
  console.log('  No baseline found. Skipping drift check.');
  console.log('  Run: node qa/summary.js && cp qa/qa-summary.json qa/baseline-summary.json');
  console.log('  to establish a baseline.\n');
  process.exit(0);
}

if (!fs.existsSync(CURRENT_PATH)) {
  console.error('  No current summary found. Run node qa/summary.js first.');
  process.exit(1);
}

const baseline = JSON.parse(fs.readFileSync(BASELINE_PATH, 'utf8'));
const current = JSON.parse(fs.readFileSync(CURRENT_PATH, 'utf8'));

// ── 1. Coverage must not decrease ───────────────────────
console.log('1. Coverage');
check('Check count did not decrease',
  current.checks >= baseline.checks,
  `Was ${baseline.checks}, now ${current.checks} (-${baseline.checks - current.checks})`
);

// ── 2. Warnings must not increase ───────────────────────
console.log('\n2. Warning Drift');
check('Warnings did not increase',
  current.warnings <= baseline.warnings,
  `Was ${baseline.warnings}, now ${current.warnings} (+${current.warnings - baseline.warnings})`
);

// ── 3. No category degraded ─────────────────────────────
console.log('\n3. Category Health');
const STATUS_RANK = { 'PASS': 0, 'WARN': 1, 'FAIL': 2 };

for (const [cat, curr] of Object.entries(current.categories)) {
  const base = baseline.categories[cat];
  if (!base) {
    console.log(`  \u2713 ${cat}: new category (no baseline)`);
    passed++;
    continue;
  }
  const currRank = STATUS_RANK[curr.status] || 0;
  const baseRank = STATUS_RANK[base.status] || 0;
  check(`${cat} did not degrade`,
    currRank <= baseRank,
    `Was ${base.status}, now ${curr.status}`
  );
}

// ── 4. No script regressed ──────────────────────────────
console.log('\n4. Script Health');
for (const [name, curr] of Object.entries(current.scripts)) {
  const base = baseline.scripts[name];
  if (!base) {
    console.log(`  \u2713 ${name}: new script`);
    passed++;
    continue;
  }
  check(`${name} did not regress`,
    curr.failed <= base.failed,
    `Was ${base.failed} failures, now ${curr.failed}`
  );
}

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Drift Check: ${passed} passed, ${failed} failed`);
console.log(`Baseline: ${baseline.timestamp}`);
console.log(`Current:  ${current.timestamp}`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
