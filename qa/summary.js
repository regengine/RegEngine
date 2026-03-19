#!/usr/bin/env node
/**
 * QA Summary Artifact Generator (v2)
 * Runs all QA scripts and produces a structured JSON summary
 * with per-category breakdown and per-script detail.
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const SCRIPTS = [
  { name: 'compliance', script: 'fsma-lite-check.js', category: 'compliance' },
  { name: 'tenant', script: 'tenant-test.js', category: 'security' },
  { name: 'full-flow', script: 'full-flow.js', category: 'pipeline' },
  { name: 'bad-data', script: 'bad-data.js', category: 'pipeline' },
  { name: 'export', script: 'export-validate.js', category: 'pipeline' },
  { name: 'ai-analysis', script: 'ai-analysis.js', category: 'trust' },
  { name: 'regression', script: 'regression.js', category: 'regression' },
];

const results = {};
const categories = {};
let totalChecks = 0;
let totalFailures = 0;
let totalWarnings = 0;

for (const s of SCRIPTS) {
  const scriptPath = path.join(__dirname, s.script);
  let output = '';
  let exitCode = 0;

  try {
    output = execSync(`node ${scriptPath} 2>&1`, { encoding: 'utf8', timeout: 30000 });
  } catch (e) {
    output = e.stdout || e.message;
    exitCode = e.status || 1;
  }

  const passMatch = output.match(/(\d+) passed/);
  const failMatch = output.match(/(\d+) failed/);
  const warnMatch = output.match(/(\d+) warning/);

  const p = passMatch ? parseInt(passMatch[1]) : 0;
  const f = failMatch ? parseInt(failMatch[1]) : 0;
  const w = warnMatch ? parseInt(warnMatch[1]) : 0;

  results[s.name] = { status: exitCode === 0 ? 'PASS' : 'FAIL', passed: p, failed: f, warnings: w, exitCode };

  // Category aggregation
  if (!categories[s.category]) categories[s.category] = { total: 0, passed: 0, failed: 0, warnings: 0, status: 'PASS' };
  categories[s.category].total += p + f;
  categories[s.category].passed += p;
  categories[s.category].failed += f;
  categories[s.category].warnings += w;
  if (exitCode !== 0) categories[s.category].status = 'FAIL';
  else if (w > 0 && categories[s.category].status === 'PASS') categories[s.category].status = 'WARN';

  totalChecks += p + f;
  totalFailures += f;
  totalWarnings += w;
}

const summary = {
  verdict: totalFailures === 0 ? (totalWarnings > 0 ? 'WARN' : 'PASS') : 'FAIL',
  timestamp: new Date().toISOString(),
  checks: totalChecks,
  failures: totalFailures,
  warnings: totalWarnings,
  categories,
  scripts: results,
};

// Output to stdout
console.log(JSON.stringify(summary, null, 2));

// Write to file
const outPath = process.env.QA_SUMMARY_PATH || path.join(__dirname, 'qa-summary.json');
fs.writeFileSync(outPath, JSON.stringify(summary, null, 2));
console.error(`\nSummary written to ${outPath}`);

if (totalFailures > 0) process.exit(1);
