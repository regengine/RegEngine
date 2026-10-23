import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { check, parseCapabilities, scanSource, summarize } from './check-copy.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(path.join(here, 'copy-rules.json'), 'utf8'));
const registryText = fs.readFileSync(path.resolve(here, '../../frontend/src/lib/capabilities.ts'), 'utf8');
const capabilities = parseCapabilities(registryText);
const rules = (src, rel = 'frontend/src/app/page.tsx') => scanSource(src, rel, cfg, capabilities).map(x => x.rule);

test('rule sources and capability registry are complete', () => {
  assert.deepEqual(Object.keys(capabilities), ['live', 'preview', 'neverShown']);
  assert.equal(capabilities.preview.includes('EPCIS export'), true);
  assert.equal(capabilities.live.includes('CSV upload'), true);
  assert.equal(capabilities.neverShown.includes('SFTP'), true);
  assert.equal(Object.values(cfg.rules).every(rule => ['visual-designer', 'product-designer', 'both'].includes(rule.source)), true);
});

test('VD dash and preview rules remain, with stricter empty values', () => {
  assert.deepEqual(rules('<p>word — word</p>'), ['em-dash']);
  assert.deepEqual(rules('<p>word – word</p>'), ['en-dash']);
  assert.deepEqual(rules('<p>word - word</p>'), ['hyphen-dash']);
  assert.deepEqual(rules('<p>—</p>'), ['dash-placeholder']);
  assert.deepEqual(rules("<p>{value ?? '--'}</p>"), ['dash-placeholder']);
  assert.deepEqual(rules("<p>{value ?? '-'}</p>"), ['dash-placeholder']);
  assert.deepEqual(rules('<p>EPCIS</p>'), ['epcis-unlabeled']);
  assert.deepEqual(rules('<p>EPCIS Preview</p>'), []);
});

test('capability claims and forbidden names use the registry', () => {
  assert.deepEqual(rules('<p>EPCIS export is Live</p>'), ['epcis-unlabeled', 'live-claim']);
  assert.deepEqual(rules('<p>CSV upload is Live</p>'), []);
  assert.deepEqual(rules("const items = [{ name: 'EPCIS export', status: 'available' }];"), ['epcis-unlabeled', 'live-claim']);
  assert.deepEqual(rules('<p>EDI 856</p>'), ['edi-sftp']);
  assert.deepEqual(rules('<p>SFTP Import</p>'), ['edi-sftp']);
  assert.deepEqual(rules('<span className="badge">Pilot</span>'), ['pilot-status']);
});

test('copy word rules skip comments, imports, identifiers, classes and paths', () => {
  assert.deepEqual(rules('<p>sample demo simulated synthetic sandbox</p>'), ['sample-demo', 'sandbox']);
  assert.deepEqual(rules('<p>test data</p>'), ['invented-entity']);
  assert.deepEqual(rules("import demo from '/demo'\nconst route = '/demo'\nconst id = 'sample_id'\nconst SANDBOX_SLUG = 'sandbox'\nconst item = { lastRun: 'sample' }\n// sandbox\n<div className='demo'>Ready</div>"), []);
  assert.deepEqual(rules('<a href="/demo">Ready</a>'), []);
  assert.deepEqual(rules('<p>/demo</p>'), []);
  assert.deepEqual(rules('<p>See (/demo) for details</p>'), []);
  assert.deepEqual(rules("const route = 'demo-route'"), []);
  assert.deepEqual(rules('<p>demo</p>', 'frontend/src/app/page.test.tsx'), []);
});

test('blank rendered fallbacks are caught only in JSX expressions', () => {
  assert.deepEqual(rules("<p>{value ?? ''}</p>"), ['empty-render']);
  assert.deepEqual(rules('<p>{value || ""}</p>'), ['empty-render']);
  assert.deepEqual(rules("const fallback = value ?? '';"), []);
  assert.deepEqual(rules("<button onClick={() => { setValue(value ?? ''); }}>Ready</button>"), []);
  assert.deepEqual(rules("// <p>{value ?? ''}</p>"), []);
});

test('allowlist and summary counts', () => {
  const findings = scanSource('<p>demo</p>', 'frontend/src/app/page.tsx', cfg, capabilities, [
    { file: 'frontend/src/app/page.tsx', rule: 'sample-demo', match: 'demo' },
  ]);
  assert.deepEqual(findings, []);
  assert.equal(summarize(findings, 1, cfg).byRule['sample-demo'], 0);
  assert.deepEqual(check({ text: 'NaN value', kind: 'str' }, '', cfg, capabilities).map(x => x.rule), ['nan-undefined']);
});
