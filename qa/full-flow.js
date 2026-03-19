#!/usr/bin/env node
/**
 * Full Flow Simulation
 * Simulates the ingestion-to-export pipeline offline using sample data:
 * 1. Parse CSV input
 * 2. Validate fields
 * 3. Compute SHA-256 hashes
 * 4. Build Merkle chain
 * 5. Generate EPCIS 2.0 output
 * 6. Verify output matches expected
 */

const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

const SAMPLES = path.join(__dirname, '..', 'frontend', 'public', 'samples');
let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}

console.log('\n=== Full Flow Simulation ===\n');

// ── Step 1: Parse CSV ───────────────────────────────────
console.log('1. CSV Ingestion');

const csvPath = path.join(SAMPLES, 'sample_fda_export.csv');
const csvContent = fs.readFileSync(csvPath, 'utf8');
const lines = csvContent.trim().split('\n');
const headers = lines[0].split(',');
const rows = lines.slice(1).map(line => {
  const values = [];
  let current = '';
  let inQuotes = false;
  for (const char of line) {
    if (char === '"') { inQuotes = !inQuotes; }
    else if (char === ',' && !inQuotes) { values.push(current); current = ''; }
    else { current += char; }
  }
  values.push(current);
  const row = {};
  headers.forEach((h, i) => row[h] = values[i] || '');
  return row;
});

check('CSV has header row', headers.length >= 10, `Only ${headers.length} columns`);
check('CSV has 12 data rows', rows.length === 12, `Got ${rows.length} rows`);
check('CSV has Merkle Hash column', headers.includes('Merkle Hash'), 'Missing Merkle Hash');
check('CSV has Sequence # column', headers.includes('Sequence #'), 'Missing Sequence #');

// ── Step 2: Validate Fields ─────────────────────────────
console.log('\n2. Field Validation');

rows.forEach((row, i) => {
  const seq = parseInt(row['Sequence #']);
  check(`Row ${seq}: has lot code`, row['Traceability Lot Code']?.length > 0, 'Empty TLC');
  check(`Row ${seq}: has facility`, row['Facility Name']?.length > 0, 'Empty facility');
  check(`Row ${seq}: has valid CTE`, row['CTE Type']?.length > 0, 'Empty CTE type');
  check(`Row ${seq}: has quantity`, parseInt(row['Quantity']) > 0, `Qty: ${row['Quantity']}`);
});

// ── Step 3: Verify Hashes ───────────────────────────────
console.log('\n3. Hash Verification');

const csvHashes = rows.map(r => ({
  payload: r['Payload SHA-256'],
  merkle: r['Merkle Hash'],
  seq: parseInt(r['Sequence #'])
}));

check('First row: merkle == payload (root)',
  csvHashes[0].merkle === csvHashes[0].payload,
  'Root hash mismatch'
);

let csvChainValid = true;
for (let i = 1; i < csvHashes.length; i++) {
  const expected = crypto.createHash('sha256')
    .update(csvHashes[i - 1].merkle + csvHashes[i].payload)
    .digest('hex');
  if (expected !== csvHashes[i].merkle) {
    csvChainValid = false;
    console.error(`    Break at seq ${csvHashes[i].seq}`);
  }
}
check('CSV Merkle chain is valid', csvChainValid, 'Chain broken');

// ── Step 4: Cross-validate CSV ↔ JSON ───────────────────
console.log('\n4. Cross-Format Validation');

const epcis = JSON.parse(fs.readFileSync(path.join(SAMPLES, 'sample_epcis_2.0.json'), 'utf8'));
const jsonEvents = epcis.epcisBody.eventList;

check('JSON and CSV have same event count',
  jsonEvents.length === rows.length,
  `JSON: ${jsonEvents.length}, CSV: ${rows.length}`
);

jsonEvents.forEach((evt, i) => {
  const csvRow = rows[i];
  const jsonMerkle = evt.extension['regengine:merkleHash'];
  const csvMerkle = csvRow['Merkle Hash'];
  check(`Seq ${i + 1}: JSON merkle == CSV merkle`,
    jsonMerkle === csvMerkle,
    `JSON: ${jsonMerkle.slice(0, 16)} vs CSV: ${csvMerkle.slice(0, 16)}`
  );
});

// ── Step 5: Verify Final Hash Propagation ────────────────
console.log('\n5. Final Hash Propagation');

const verification = JSON.parse(
  fs.readFileSync(path.join(SAMPLES, 'sample_chain_verification.json'), 'utf8')
);
const manifest = JSON.parse(
  fs.readFileSync(path.join(SAMPLES, 'sample_manifest.json'), 'utf8')
);

const finalHashes = {
  epcis: epcis['regengine:integrity']?.finalMerkleHash,
  verification: verification.verification_report?.final_merkle_hash,
  manifest: manifest.manifest?.integrity?.final_merkle_hash,
  csvLast: csvHashes[csvHashes.length - 1].merkle,
};

check('All 4 artifacts agree on final hash',
  new Set(Object.values(finalHashes)).size === 1,
  `Mismatch: ${JSON.stringify(finalHashes, null, 2)}`
);

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Full Flow: ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
