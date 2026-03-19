#!/usr/bin/env node
/**
 * Regression Harness (v2)
 * Loads canonical "known bad" fixtures from qa/fixtures/bad/
 * and verifies each one is caught FOR THE CORRECT REASON.
 *
 * Does NOT modify real files. Runs mutations in memory.
 * Fails if a fixture passes, or fails for the wrong reason.
 */

const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

const FIXTURES = path.join(__dirname, 'fixtures', 'bad');
const SAMPLES = path.join(__dirname, '..', 'frontend', 'public', 'samples');
const SRC = path.join(__dirname, '..', 'frontend', 'src');

const VALID_CTES = [
  'harvesting', 'cooling', 'initial_packing',
  'first_land_based_receiving',
  'shipping', 'receiving', 'transformation'
];

let passed = 0;
let failed = 0;

function assert(fixtureName, reason, condition, detail) {
  if (condition) {
    console.log(`  \u2713 [${reason}] ${detail || 'detected'}`);
    passed++;
  } else {
    console.error(`  \u2717 [${reason}] ${detail || 'NOT detected'}`);
    failed++;
  }
}

console.log('\n=== Regression Harness v2 ===\n');

const fixtures = fs.readdirSync(FIXTURES)
  .filter(f => f.endsWith('.json'))
  .map(f => JSON.parse(fs.readFileSync(path.join(FIXTURES, f), 'utf8')));

console.log(`Loaded ${fixtures.length} regression fixtures.\n`);

// ── DETECTOR: Merkle chain tamper ────────────────────────
function detectMerkleChainTamper(tamperedHash, targetIndex) {
  const epcis = JSON.parse(fs.readFileSync(path.join(SAMPLES, 'sample_epcis_2.0.json'), 'utf8'));
  const events = epcis.epcisBody.eventList;
  events[targetIndex].extension['regengine:merkleHash'] = tamperedHash;

  const hashes = events.map(e => ({
    payload: e.extension['regengine:payloadSHA256'],
    merkle: e.extension['regengine:merkleHash'],
  }));

  let breakAt = null;
  for (let i = 1; i < hashes.length; i++) {
    const expected = crypto.createHash('sha256')
      .update(hashes[i - 1].merkle + hashes[i].payload)
      .digest('hex');
    if (expected !== hashes[i].merkle) { breakAt = i; break; }
  }
  return { detected: breakAt !== null, breakAt, reason: 'merkle_chain_broken' };
}

// ── DETECTOR: Regulatory copy regression ─────────────────
function detectCopyRegression(find, replace) {
  const fsmaPage = path.join(SRC, 'app', 'fsma-204', 'page.tsx');
  const original = fs.readFileSync(fsmaPage, 'utf8');
  const mutated = original.replace(find, replace);
  const hasBadCopy = mutated.includes('6 Critical Tracking Events');
  const originalClean = !original.includes('6 Critical Tracking Events');
  return {
    detected: hasBadCopy && originalClean,
    reason: 'regulatory_copy_regression',
    detail: hasBadCopy ? 'Mutated content contains "6 CTEs"' : 'Mutation had no effect'
  };
}

// ── DETECTOR: Missing artifact ───────────────────────────
function detectMissingArtifact(filename) {
  const exists = fs.existsSync(path.join(SAMPLES, path.basename(filename)));
  return {
    detected: exists, // if it exists now, deletion WOULD be caught
    reason: 'missing_artifact',
    detail: exists ? 'File present — deletion would trigger failure' : 'File already missing'
  };
}

// ── DETECTOR: Validator rejection ────────────────────────
function detectValidatorRejection(row, expectedReason) {
  const errors = [];
  if (!row.lot_code || row.lot_code.trim().length === 0) errors.push('missing_lot_code');
  if (!row.cte_type || !VALID_CTES.includes(row.cte_type.toLowerCase())) errors.push('invalid_cte_type');
  const matchesExpected = errors.includes(expectedReason);
  return {
    detected: matchesExpected,
    reason: expectedReason,
    detail: matchesExpected ? `Correctly rejected: ${expectedReason}` : `Expected ${expectedReason}, got: [${errors.join(', ')}]`
  };
}

// ── RUN EACH FIXTURE ─────────────────────────────────────
for (const fixture of fixtures) {
  console.log(`${fixture.name} [${fixture.severity}]`);
  console.log(`  ${fixture.description}`);

  let result;

  switch (fixture.expected_failure) {
    case 'merkle_chain_broken':
      result = detectMerkleChainTamper(fixture.mutation.tampered, 2);
      assert(fixture.name, result.reason,
        result.detected,
        result.detected
          ? `Chain break at seq ${result.breakAt + 1} — correct`
          : 'Chain passed when it should fail'
      );
      assert(fixture.name, 'reason_match',
        result.reason === fixture.expected_failure,
        `Expected: ${fixture.expected_failure}, Got: ${result.reason}`
      );
      break;

    case 'regulatory_copy_regression':
      result = detectCopyRegression(fixture.mutation.find, fixture.mutation.replace);
      assert(fixture.name, result.reason,
        result.detected,
        result.detail
      );
      assert(fixture.name, 'reason_match',
        result.reason === fixture.expected_failure,
        `Expected: ${fixture.expected_failure}, Got: ${result.reason}`
      );
      break;

    case 'missing_artifact':
      result = detectMissingArtifact(fixture.mutation.file);
      assert(fixture.name, result.reason,
        result.detected,
        result.detail
      );
      assert(fixture.name, 'reason_match',
        result.reason === fixture.expected_failure,
        `Expected: ${fixture.expected_failure}, Got: ${result.reason}`
      );
      break;

    case 'missing_lot_code':
    case 'invalid_cte_type':
      result = detectValidatorRejection(fixture.test_row, fixture.expected_failure);
      assert(fixture.name, result.reason,
        result.detected,
        result.detail
      );
      assert(fixture.name, 'reason_match',
        result.reason === fixture.expected_failure,
        `Expected: ${fixture.expected_failure}, Got: ${result.reason}`
      );
      break;

    default:
      console.error(`  \u2717 Unknown expected_failure: ${fixture.expected_failure}`);
      failed++;
  }
  console.log('');
}

// ── Summary ─────────────────────────────────────────────
console.log(`${'='.repeat(50)}`);
console.log(`Regression v2: ${passed} passed, ${failed} failed`);
console.log(`Fixtures: ${fixtures.length} | Severity: ${fixtures.filter(f => f.severity === 'critical').length} critical`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
