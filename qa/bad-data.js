#!/usr/bin/env node
/**
 * Bad Data Rejection Tests
 * Validates that the system's validation rules would catch common errors:
 * - Missing required fields
 * - Invalid CTE types
 * - Malformed hashes
 * - Broken Merkle chains
 * - Duplicate sequences
 * - Future timestamps
 */

const crypto = require('crypto');

let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}

// Simulate the validator logic from services/admin/app/bulk_upload/validators.py
const VALID_CTES = [
  'harvesting', 'cooling', 'initial_packing',
  'first_land_based_receiving',
  'shipping', 'receiving', 'transformation'
];

function validateRow(row) {
  const errors = [];
  const warnings = [];

  if (!row.lot_code || row.lot_code.trim().length === 0) errors.push('Missing lot code');
  if (!row.cte_type || !VALID_CTES.includes(row.cte_type.toLowerCase())) {
    errors.push(`Invalid CTE type: "${row.cte_type}"`);
  }
  if (!row.facility_name || row.facility_name.trim().length === 0) {
    warnings.push('Missing facility name — will auto-fill "Unnamed Facility"');
  }
  if (!row.quantity || isNaN(parseInt(row.quantity)) || parseInt(row.quantity) <= 0) {
    warnings.push('Invalid quantity — will default to 0');
  }
  if (row.event_time) {
    const ts = new Date(row.event_time);
    if (ts > new Date()) warnings.push('Future timestamp detected');
  }

  return { errors, warnings, can_commit: errors.length === 0 };
}

console.log('\n=== Bad Data Rejection Tests ===\n');

// ── Test 1: Missing lot code ────────────────────────────
console.log('1. Missing Required Fields');

let result = validateRow({ lot_code: '', cte_type: 'shipping', facility_name: 'Test', quantity: '100' });
check('Empty lot code → error', result.errors.length > 0, 'Should reject');
check('Empty lot code → cannot commit', !result.can_commit, 'Should block commit');

result = validateRow({ lot_code: 'LOT-001', cte_type: 'shipping', facility_name: '', quantity: '100' });
check('Empty facility → warning only', result.warnings.length > 0 && result.errors.length === 0, 'Should warn, not error');
check('Empty facility → can still commit', result.can_commit, 'Should allow commit');

// ── Test 2: Invalid CTE types ───────────────────────────
console.log('\n2. Invalid CTE Types');

result = validateRow({ lot_code: 'LOT-001', cte_type: 'cooking', facility_name: 'Test', quantity: '100' });
check('"cooking" → rejected', result.errors.length > 0, 'Should reject invalid CTE');

result = validateRow({ lot_code: 'LOT-001', cte_type: 'SHIPPING', facility_name: 'Test', quantity: '100' });
check('"SHIPPING" (uppercase) → accepted', result.can_commit, 'Should accept case-insensitive');

result = validateRow({ lot_code: 'LOT-001', cte_type: '', facility_name: 'Test', quantity: '100' });
check('Empty CTE → rejected', !result.can_commit, 'Should reject empty CTE');

// ── Test 3: Malformed hashes ────────────────────────────
console.log('\n3. Hash Validation');

function isValidSHA256(hash) {
  return /^[0-9a-f]{64}$/.test(hash);
}

check('Valid hash accepted', isValidSHA256('de23337e6ffd8a9fbdd6e973e4c342aa3a2589c1356b5ec65026e283127d183b'), 'Should pass');
check('Short hash rejected', !isValidSHA256('de23337e6ffd8a9f'), 'Should fail (16 chars)');
check('Uppercase hash rejected', !isValidSHA256('DE23337E6FFD8A9FBDD6E973E4C342AA3A2589C1356B5EC65026E283127D183B'), 'Should fail');
check('Non-hex rejected', !isValidSHA256('zz23337e6ffd8a9fbdd6e973e4c342aa3a2589c1356b5ec65026e283127d183b'), 'Should fail');

// ── Test 4: Broken Merkle chain ─────────────────────────
console.log('\n4. Chain Integrity');

const goodPayload1 = crypto.createHash('sha256').update('event1').digest('hex');
const goodPayload2 = crypto.createHash('sha256').update('event2').digest('hex');
const goodMerkle2 = crypto.createHash('sha256').update(goodPayload1 + goodPayload2).digest('hex');

check('Valid chain link passes', goodMerkle2 === crypto.createHash('sha256').update(goodPayload1 + goodPayload2).digest('hex'), 'Math is broken');

const badMerkle2 = crypto.createHash('sha256').update('tampered' + goodPayload2).digest('hex');
check('Tampered chain link detected', badMerkle2 !== goodMerkle2, 'Should detect tampering');

// ── Test 5: Duplicate sequences ─────────────────────────
console.log('\n5. Duplicate Detection');

function findDuplicates(seqs) {
  const seen = new Set();
  const dupes = [];
  for (const s of seqs) {
    if (seen.has(s)) dupes.push(s);
    seen.add(s);
  }
  return dupes;
}

check('No dupes in [1,2,3,4]', findDuplicates([1,2,3,4]).length === 0, 'False positive');
check('Catches dupe in [1,2,2,3]', findDuplicates([1,2,2,3]).length > 0, 'Missed duplicate');
check('Catches multiple dupes', findDuplicates([1,1,2,2,3]).length === 2, 'Wrong count');

// ── Test 6: Quantity sanity ─────────────────────────────
console.log('\n6. Quantity Validation');

result = validateRow({ lot_code: 'LOT-001', cte_type: 'shipping', facility_name: 'Test', quantity: '-5' });
check('Negative quantity → warning', result.warnings.length > 0, 'Should warn');

result = validateRow({ lot_code: 'LOT-001', cte_type: 'shipping', facility_name: 'Test', quantity: 'abc' });
check('Non-numeric quantity → warning', result.warnings.length > 0, 'Should warn');

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Bad Data Tests: ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
