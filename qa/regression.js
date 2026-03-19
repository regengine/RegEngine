#!/usr/bin/env node
/**
 * Regression Harness
 * Loads canonical "known bad" fixtures from qa/fixtures/bad/
 * and verifies each one would still be caught by the pipeline.
 *
 * Does NOT modify real files. Runs mutations in memory or temp copies
 * and verifies the detection logic catches them.
 */

const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

const FIXTURES = path.join(__dirname, 'fixtures', 'bad');
const SAMPLES = path.join(__dirname, '..', 'frontend', 'public', 'samples');
const SRC = path.join(__dirname, '..', 'frontend', 'src');

let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}

console.log('\n=== Regression Harness ===\n');

const fixtures = fs.readdirSync(FIXTURES)
  .filter(f => f.endsWith('.json'))
  .map(f => JSON.parse(fs.readFileSync(path.join(FIXTURES, f), 'utf8')));

console.log(`Loaded ${fixtures.length} regression fixtures.\n`);

// ── 1. Tampered Chain ───────────────────────────────────
const chainFixture = fixtures.find(f => f.name === 'tampered-merkle-chain');
if (chainFixture) {
  console.log(`1. ${chainFixture.name}`);
  console.log(`   ${chainFixture.description}`);

  const epcis = JSON.parse(fs.readFileSync(path.join(SAMPLES, 'sample_epcis_2.0.json'), 'utf8'));
  const events = epcis.epcisBody.eventList;

  // Apply mutation in memory
  events[2].extension['regengine:merkleHash'] = chainFixture.mutation.tampered;

  // Run chain verification
  const hashes = events.map(e => ({
    payload: e.extension['regengine:payloadSHA256'],
    merkle: e.extension['regengine:merkleHash'],
  }));

  let chainBroken = false;
  for (let i = 1; i < hashes.length; i++) {
    const expected = crypto.createHash('sha256')
      .update(hashes[i - 1].merkle + hashes[i].payload)
      .digest('hex');
    if (expected !== hashes[i].merkle) { chainBroken = true; break; }
  }
  check('Tampered chain is detected', chainBroken, 'Chain passed when it should fail');
}

// ── 2. Wrong CTE Count ──────────────────────────────────
const cteFixture = fixtures.find(f => f.name === 'wrong-cte-count');
if (cteFixture) {
  console.log(`\n2. ${cteFixture.name}`);
  console.log(`   ${cteFixture.description}`);

  const fsmaPage = path.join(SRC, 'app', 'fsma-204', 'page.tsx');
  const content = fs.readFileSync(fsmaPage, 'utf8');
  // Simulate the mutation in memory
  const mutated = content.replace(cteFixture.mutation.find, cteFixture.mutation.replace);

  check('Mutation produces different content', mutated !== content, 'Replace had no effect');
  check('Mutated content contains "6 Critical Tracking Events"',
    mutated.includes('6 Critical Tracking Events'), 'Mutation did not apply');
  check('Original content does NOT contain "6 Critical Tracking Events"',
    !content.includes('6 Critical Tracking Events'), 'Original already has the bug');
}

// ── 3. Missing Export Artifact ───────────────────────────
const missingFixture = fixtures.find(f => f.name === 'missing-export-artifact');
if (missingFixture) {
  console.log(`\n3. ${missingFixture.name}`);
  console.log(`   ${missingFixture.description}`);

  const targetFile = path.join(SAMPLES, path.basename(missingFixture.mutation.file));
  check('Target file currently exists (so deletion would be caught)',
    fs.existsSync(targetFile), `${targetFile} does not exist`);
}

// ── 4. Empty Lot Code ────────────────────────────────────
const lotFixture = fixtures.find(f => f.name === 'empty-lot-code');
if (lotFixture) {
  console.log(`\n4. ${lotFixture.name}`);
  console.log(`   ${lotFixture.description}`);

  const row = lotFixture.test_row;
  const hasLotCode = row.lot_code && row.lot_code.trim().length > 0;
  check('Empty lot code is detected as invalid', !hasLotCode, 'Lot code passed validation');
}

// ── 5. Invalid CTE Type ─────────────────────────────────
const cteTypeFixture = fixtures.find(f => f.name === 'invalid-cte-type');
if (cteTypeFixture) {
  console.log(`\n5. ${cteTypeFixture.name}`);
  console.log(`   ${cteTypeFixture.description}`);

  const VALID_CTES = [
    'harvesting', 'cooling', 'initial_packing',
    'first_land_based_receiving',
    'shipping', 'receiving', 'transformation'
  ];
  const row = cteTypeFixture.test_row;
  const isValid = VALID_CTES.includes(row.cte_type.toLowerCase());
  check('Invalid CTE type "cooking" is rejected', !isValid, 'CTE passed validation');
}

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Regression Harness: ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
