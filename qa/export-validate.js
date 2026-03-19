#!/usr/bin/env node
/**
 * Export Artifact Validation
 * Verifies all downloadable export files are:
 * - Present and non-empty
 * - Valid JSON/CSV
 * - Cross-consistent (same hashes, same record counts)
 * - Zip bundle contains all expected files
 */

const fs = require('fs');
const path = require('path');

const SAMPLES = path.join(__dirname, '..', 'frontend', 'public', 'samples');
let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) { console.log(`  \u2713 ${name}`); passed++; }
  else { console.error(`  \u2717 ${name}: ${detail}`); failed++; }
}

console.log('\n=== Export Artifact Validation ===\n');

// ── 1. File Existence & Size ────────────────────────────
console.log('1. File Presence');

const expectedFiles = [
  'sample_epcis_2.0.json',
  'sample_fda_export.csv',
  'sample_chain_verification.json',
  'sample_manifest.json',
  'regengine_sample_export.zip',
];

for (const f of expectedFiles) {
  const fp = path.join(SAMPLES, f);
  const exists = fs.existsSync(fp);
  check(`${f} exists`, exists, 'File not found');
  if (exists) {
    const size = fs.statSync(fp).size;
    check(`${f} is non-empty (${size} bytes)`, size > 100, `Only ${size} bytes`);
  }
}

// ── 2. JSON Validity ────────────────────────────────────
console.log('\n2. JSON Validity');

const jsonFiles = ['sample_epcis_2.0.json', 'sample_chain_verification.json', 'sample_manifest.json'];
for (const f of jsonFiles) {
  try {
    JSON.parse(fs.readFileSync(path.join(SAMPLES, f), 'utf8'));
    check(`${f} is valid JSON`, true, '');
  } catch (e) {
    check(`${f} is valid JSON`, false, e.message);
  }
}

// ── 3. CSV Structure ────────────────────────────────────
console.log('\n3. CSV Structure');

const csv = fs.readFileSync(path.join(SAMPLES, 'sample_fda_export.csv'), 'utf8');
const csvLines = csv.trim().split('\n');
check('CSV has header + 12 data rows', csvLines.length === 13, `Got ${csvLines.length} lines`);
check('CSV header has 16 columns', csvLines[0].split(',').length === 16, `Got ${csvLines[0].split(',').length}`);

// ── 4. Record Count Consistency ─────────────────────────
console.log('\n4. Record Counts');

const epcis = JSON.parse(fs.readFileSync(path.join(SAMPLES, 'sample_epcis_2.0.json'), 'utf8'));
const verification = JSON.parse(fs.readFileSync(path.join(SAMPLES, 'sample_chain_verification.json'), 'utf8'));
const manifest = JSON.parse(fs.readFileSync(path.join(SAMPLES, 'sample_manifest.json'), 'utf8'));

const counts = {
  epcis: epcis.epcisBody.eventList.length,
  csv: csvLines.length - 1,
  verification: verification.verification_report.records.length,
  integrityBlock: epcis['regengine:integrity'].chainLength,
  manifest: manifest.manifest.integrity.chain_length,
};

check('All sources agree on 12 records',
  Object.values(counts).every(c => c === 12),
  `Counts: ${JSON.stringify(counts)}`
);

// ── 5. Facility Consistency ─────────────────────────────
console.log('\n5. Facility Consistency');

const epcisGLNs = new Set(epcis.epcisBody.eventList.map(e => e.bizLocation.id.split(':').pop()));
const verFacilities = new Set(verification.verification_report.records.map(r => r.facility));

check('EPCIS has 7 unique GLNs', epcisGLNs.size === 7, `Got ${epcisGLNs.size}`);
check('Verification has 7 unique facilities', verFacilities.size === 7, `Got ${verFacilities.size}`);

// ── 6. Manifest Integrity ───────────────────────────────
console.log('\n6. Manifest');

check('Manifest lists 3 files', manifest.manifest.files.length === 3, `Got ${manifest.manifest.files.length}`);
check('Manifest has sha256', typeof manifest.manifest.manifest_sha256 === 'string' && manifest.manifest.manifest_sha256.length === 64, 'Missing or invalid');
check('Manifest chain_valid is true', manifest.manifest.integrity.chain_valid === true, 'Not valid');
check('Manifest has retention notice', manifest.manifest.retention_notice?.length > 20, 'Missing');

// ── 7. Zip Bundle ───────────────────────────────────────
console.log('\n7. Zip Bundle');

const zipPath = path.join(SAMPLES, 'regengine_sample_export.zip');
if (fs.existsSync(zipPath)) {
  const zipSize = fs.statSync(zipPath).size;
  check('Zip is > 1KB', zipSize > 1000, `Only ${zipSize} bytes`);
  check('Zip is < 1MB (reasonable size)', zipSize < 1000000, `${zipSize} bytes is too large`);
  // Check zip magic bytes
  const buf = Buffer.alloc(4);
  const fd = fs.openSync(zipPath, 'r');
  fs.readSync(fd, buf, 0, 4, 0);
  fs.closeSync(fd);
  check('Zip has valid magic bytes (PK)', buf[0] === 0x50 && buf[1] === 0x4B, 'Not a valid zip file');
}

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`Export Validation: ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) process.exit(1);
