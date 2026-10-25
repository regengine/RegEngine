#!/usr/bin/env node
/**
 * FSMA 204 CTE count copy check.
 *
 * Reads the real frontend FSMA 204 page source and fails if it says the rule
 * has 6 Critical Tracking Events, or if it does not state 7. Restores the
 * regulatory copy check from the former qa/fsma-lite-check.js, with no sample
 * files. Node built-ins only.
 */
const fs = require('fs');
const path = require('path');

const PAGE = path.join(__dirname, '..', 'frontend', 'src', 'app', 'fsma-204', 'page.tsx');

if (!fs.existsSync(PAGE)) {
  console.error(`✗ FSMA 204 page not found: ${path.relative(process.cwd(), PAGE)}`);
  process.exit(1);
}

const content = fs.readFileSync(PAGE, 'utf8');
const failures = [];

const sixPattern = /\b(?:6|six)\s+(?:Critical\s+Tracking\s+Events|CTEs)\b/i;
const sevenPattern = /\b7\s+Critical\s+Tracking\s+Events\b/;

const six = content.match(sixPattern);
if (six) failures.push(`Found "${six[0]}" — FSMA 204 has 7 CTEs, never 6`);
if (!sevenPattern.test(content)) failures.push('Missing "7 Critical Tracking Events"');

console.log('FSMA 204 CTE count copy check');
console.log(`  ${six ? '✗' : '✓'} Page does not say 6 CTEs`);
console.log(`  ${sevenPattern.test(content) ? '✓' : '✗'} Page says "7 Critical Tracking Events"`);

if (failures.length) {
  for (const f of failures) console.error(`  ${f}`);
  process.exit(1);
}
console.log('PASS');
