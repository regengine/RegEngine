#!/usr/bin/env node
/**
 * FSMA 204 Compliance Lite Check
 * Validates sample export data against FDA FSMA 204 requirements:
 * - 7 CTE types recognized
 * - Required KDEs present per event
 * - Lot codes follow TLC format
 * - Hash chain integrity
 * - Export format compliance (EPCIS 2.0)
 */

const fs = require('fs');
const crypto = require('crypto');
const path = require('path');

const SAMPLES = path.join(__dirname, '..', 'frontend', 'public', 'samples');

const VALID_CTES = [
  'harvesting', 'cooling', 'initial_packing',
  'first_land_based_receiving',
  'shipping', 'receiving', 'transformation'
];

const REQUIRED_EXTENSION_FIELDS = [
  'fsma:traceabilityLotCode',
  'fsma:productDescription',
  'fsma:quantity',
  'fsma:unitOfMeasure',
  'regengine:payloadSHA256',
  'regengine:merkleHash',
  'regengine:sequenceNumber'
];

let passed = 0;
let failed = 0;

function check(name, condition, detail) {
  if (condition) {
    console.log(`  \u2713 ${name}`);
    passed++;
  } else {
    console.error(`  \u2717 ${name}: ${detail}`);
    failed++;
  }
}

// ── 1. Load sample EPCIS ────────────────────────────────
console.log('\n=== FSMA 204 Compliance Checks ===\n');
console.log('1. EPCIS 2.0 Structure');

const epcisPath = path.join(SAMPLES, 'sample_epcis_2.0.json');
check('EPCIS file exists', fs.existsSync(epcisPath), 'Missing sample_epcis_2.0.json');

const epcis = JSON.parse(fs.readFileSync(epcisPath, 'utf8'));
check('Has @context', Array.isArray(epcis['@context']), 'Missing @context array');
check('Schema version is 2.0', epcis.schemaVersion === '2.0', `Got ${epcis.schemaVersion}`);
check('Type is EPCISDocument', epcis.type === 'EPCISDocument', `Got ${epcis.type}`);
check('Has eventList', Array.isArray(epcis.epcisBody?.eventList), 'Missing epcisBody.eventList');

const events = epcis.epcisBody.eventList;

// ── 2. CTE Validation ───────────────────────────────────
console.log('\n2. Critical Tracking Events');

const cteTypes = events.map(e => e.bizStep.replace('urn:epcglobal:cbv:bizstep:', ''));
const uniqueCtes = [...new Set(cteTypes)];

check('All events use valid CTE types',
  cteTypes.every(c => VALID_CTES.includes(c)),
  `Invalid CTEs: ${cteTypes.filter(c => !VALID_CTES.includes(c)).join(', ')}`
);

check('At least 3 distinct CTE types used',
  uniqueCtes.length >= 3,
  `Only ${uniqueCtes.length} types: ${uniqueCtes.join(', ')}`
);

// ── 3. KDE Completeness ─────────────────────────────────
console.log('\n3. Key Data Elements');

events.forEach((evt, i) => {
  const ext = evt.extension || {};
  const missing = REQUIRED_EXTENSION_FIELDS.filter(f => !(f in ext));
  check(`Event ${i + 1} has all required KDEs`,
    missing.length === 0,
    `Missing: ${missing.join(', ')}`
  );
});

// ── 4. Lot Code Format ──────────────────────────────────
console.log('\n4. Traceability Lot Codes');

const lotCodes = events.map(e => e.extension['fsma:traceabilityLotCode']);
check('All events have a TLC', lotCodes.every(Boolean), 'Some events missing TLC');
check('TLC is consistent across chain',
  new Set(lotCodes).size === 1,
  `Multiple TLCs: ${[...new Set(lotCodes)].join(', ')}`
);
check('TLC is non-empty string',
  lotCodes[0] && lotCodes[0].length > 3,
  `TLC too short: "${lotCodes[0]}"`
);

// ── 5. Hash Chain Integrity ─────────────────────────────
console.log('\n5. Merkle Hash Chain');

const hashes = events.map(e => ({
  payload: e.extension['regengine:payloadSHA256'],
  merkle: e.extension['regengine:merkleHash'],
  seq: e.extension['regengine:sequenceNumber']
}));

check('First event: merkle == payload (chain root)',
  hashes[0].merkle === hashes[0].payload,
  `Root mismatch: ${hashes[0].merkle.slice(0, 16)} != ${hashes[0].payload.slice(0, 16)}`
);

check('All hashes are 64-char hex strings',
  hashes.every(h => /^[0-9a-f]{64}$/.test(h.payload) && /^[0-9a-f]{64}$/.test(h.merkle)),
  'Some hashes are not valid SHA-256'
);

// Verify Merkle chain linkage
let chainValid = true;
for (let i = 1; i < hashes.length; i++) {
  const expected = crypto.createHash('sha256')
    .update(hashes[i - 1].merkle + hashes[i].payload)
    .digest('hex');
  if (expected !== hashes[i].merkle) {
    chainValid = false;
    console.error(`    Chain break at seq ${i + 1}: expected ${expected.slice(0, 16)}..., got ${hashes[i].merkle.slice(0, 16)}...`);
  }
}
check('Merkle chain is cryptographically valid', chainValid, 'Chain verification failed');

// Verify final hash matches integrity block
const finalHash = epcis['regengine:integrity']?.finalMerkleHash;
check('Final hash matches integrity block',
  finalHash === hashes[hashes.length - 1].merkle,
  `Integrity: ${finalHash?.slice(0, 16)} vs chain: ${hashes[hashes.length - 1].merkle.slice(0, 16)}`
);

check('Chain length matches event count',
  epcis['regengine:integrity']?.chainLength === events.length,
  `Integrity says ${epcis['regengine:integrity']?.chainLength}, events: ${events.length}`
);

// ── 6. Sequence Ordering ────────────────────────────────
console.log('\n6. Event Sequencing');

const seqs = events.map(e => e.extension['regengine:sequenceNumber']);
check('Sequences start at 1', seqs[0] === 1, `Starts at ${seqs[0]}`);
check('Sequences are contiguous',
  seqs.every((s, i) => s === i + 1),
  `Gap in sequence: ${seqs.join(',')}`
);

// ── 7. Site Copy Check ──────────────────────────────────
console.log('\n7. Regulatory Copy Consistency');

const fsmaPage = path.join(__dirname, '..', 'frontend', 'src', 'app', 'fsma-204', 'page.tsx');
if (fs.existsSync(fsmaPage)) {
  const content = fs.readFileSync(fsmaPage, 'utf8');
  check('FSMA guide does NOT say "6 Critical Tracking Events"',
    !content.includes('6 Critical Tracking Events'),
    'Found "6 Critical Tracking Events" — must be 7'
  );
  check('FSMA guide says "7 Critical Tracking Events"',
    content.includes('7 Critical Tracking Events'),
    'Missing "7 Critical Tracking Events"'
  );
} else {
  console.log('  (skipped — fsma-204/page.tsx not found)');
}

// ── Summary ─────────────────────────────────────────────
console.log(`\n${'='.repeat(50)}`);
console.log(`FSMA 204 Checks: ${passed} passed, ${failed} failed`);
console.log(`${'='.repeat(50)}\n`);

if (failed > 0) {
  process.exit(1);
}
