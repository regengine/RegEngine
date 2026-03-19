#!/usr/bin/env node
/**
 * QA Summary Artifact Generator
 * Runs all QA scripts and produces a single JSON summary.
 * Output goes to stdout as JSON and optionally to a file.
 */

const { execSync } = require('child_process');
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

  // Parse counts from output
  const passMatch = output.match(/(\d+) passed/);
  const failMatch = output.match(/(\d+) failed/);
  const warnMatch = output.match(/(\d+) warning/);

  const passed = passMatch ? parseInt(passMatch[1]) : 0;
  const failed = failMatch ? parseInt(failMatch[1]) : 0;
  const warnings = warnMatch ? parseInt(warnMatch[1]) : 0;

  results[s.name] = {
    status: exitCode === 0 ? 'PASS' : 'FAIL',
    passed,
    failed,
    warnings,
    exitCode,
  };

  totalChecks += passed + failed;
  totalFailures += failed;
  totalWarnings += warnings;

  if (!categories[s.category]) categories[s.category] = 'PASS';
  if (exitCode !== 0) categories[s.category] = 'FAIL';
  else if (warnings > 0 && categories[s.category] === 'PASS') categories[s.category] = 'WARN';
}

const summary = {
  verdict: totalFailures === 0 ? 'PASS' : 'FAIL',
  timestamp: new Date().toISOString(),
  checks: totalChecks,
  failures: totalFailures,
  warnings: totalWarnings,
  categories,
  scripts: results,
};

console.log(JSON.stringify(summary, null, 2));

// Write to file if QA_SUMMARY_PATH is set
if (process.env.QA_SUMMARY_PATH) {
  require('fs').writeFileSync(process.env.QA_SUMMARY_PATH, JSON.stringify(summary, null, 2));
  console.error(`Summary written to ${process.env.QA_SUMMARY_PATH}`);
}

if (totalFailures > 0) process.exit(1);
