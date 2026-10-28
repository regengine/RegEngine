import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { check, compareBaseline, countsByFileRule, gateCompare, parseCapabilities, scanSource, summarize } from './check-copy.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const cfg = JSON.parse(fs.readFileSync(path.join(here, 'copy-rules.json'), 'utf8'));
const registryText = fs.readFileSync(path.resolve(here, '../../frontend/src/lib/capabilities.ts'), 'utf8');
const capabilities = parseCapabilities(registryText);
const rules = (src, rel = 'frontend/src/app/page.tsx') => scanSource(src, rel, cfg, capabilities).map(x => x.rule);
const liveName = capabilities.live[0];
const previewTerm = capabilities.preview[0].split(' ')[0];
const [sampleTerm, demoTerm] = 'sample-demo'.split('-');
const sandboxTerm = 'sandbox';
const registrySource = groups => Object.entries(groups).map(([status, names]) =>
  `${status}: [${names.map(name => `'${name}'`).join(', ')}]`).join(',\n');

test('rule sources and capability registry are complete', () => {
  assert.deepEqual(Object.keys(capabilities), ['live', 'preview', 'planned', 'off']);
  assert.equal(capabilities.live.length > 0 && capabilities.preview.length > 0 && capabilities.off.length > 0, true);
  assert.deepEqual(parseCapabilities(registrySource(capabilities)), capabilities);
  assert.equal(Object.values(cfg.rules).every(rule => ['visual-designer', 'product-designer', 'both'].includes(rule.source)), true);
});

test('a feature cannot have two capability statuses', () => {
  const duplicate = { ...capabilities, planned: [capabilities.live[0]] };
  assert.throws(() => parseCapabilities(registrySource(duplicate)), /Duplicate capability status/);
});

test('a double-quoted planned capability is rejected', () => {
  const invalid = registrySource({ ...capabilities, planned: ['X'] }).replace("planned: ['X']", 'planned: ["X"]');
  assert.throws(() => parseCapabilities(invalid), /Unparseable planned capability registry/);
});

test('an empty off registry is rejected', () => {
  const invalid = registrySource({ ...capabilities, off: [] });
  assert.throws(() => parseCapabilities(invalid), /Empty off capability registry/);
});

test('VD dash and preview rules remain, with stricter empty values', () => {
  assert.deepEqual(rules(`<p>${liveName} — ${liveName}</p>`), ['em-dash']);
  assert.deepEqual(rules(`<p>${liveName} – ${liveName}</p>`), ['en-dash']);
  assert.deepEqual(rules(`<p>${liveName} - ${liveName}</p>`), ['hyphen-dash']);
  assert.deepEqual(rules('<p>—</p>'), ['dash-placeholder']);
  assert.deepEqual(rules("<p>{value ?? '--'}</p>"), ['dash-placeholder']);
  assert.deepEqual(rules("<p>{value ?? '-'}</p>"), ['dash-placeholder']);
  assert.deepEqual(rules(`<p>${previewTerm}</p>`), ['epcis-unlabeled']);
  assert.deepEqual(rules(`<p>${previewTerm} Preview</p>`), []);
});

test('capability claims and forbidden names use the registry', () => {
  assert.deepEqual(rules(`<p>${capabilities.preview[1]} is Live</p>`), ['epcis-unlabeled', 'live-claim']);
  assert.deepEqual(rules(`<p>${capabilities.live[0]} is Live</p>`), []);
  assert.deepEqual(rules(`const items = [{ name: '${capabilities.preview[1]}', status: 'available' }];`), ['epcis-unlabeled', 'live-claim']);
  assert.deepEqual(rules(`<p>${capabilities.off[0]}</p>`), ['edi-sftp']);
  assert.deepEqual(rules(`<p>${capabilities.off[1]}</p>`), ['edi-sftp']);
  assert.deepEqual(rules(`<span className="badge">${cfg.rules['pilot-status'].message.split(' ')[0]}</span>`), ['pilot-status']);
});

test('live claim covers off and planned registry features', () => {
  const planned = { ...capabilities, live: capabilities.live.slice(1), planned: [capabilities.live[0]] };
  const parsed = parseCapabilities(registrySource(planned));
  for (const feature of [parsed.off[0], parsed.planned[0]]) {
    const hits = check({ text: `${feature} Live`, kind: 'jsx' }, '', cfg, parsed);
    assert.equal(hits.some(hit => hit.rule === 'live-claim'), true);
  }
});

test('copy word rules skip comments, imports, identifiers, classes and paths', () => {
  assert.deepEqual(rules(`<p>${sampleTerm} ${sandboxTerm}</p>`), ['sample-demo', 'sandbox']);
  assert.deepEqual(rules(`<p>${cfg.denylist[0]}</p>`), ['invented-entity']);
  assert.deepEqual(rules(`import ${demoTerm} from '/${demoTerm}'\nconst route = '/${demoTerm}'\nconst id = '${sampleTerm}_id'\nconst SANDBOX_SLUG = '${sandboxTerm}'\nconst item = { lastRun: '${sampleTerm}' }\n// ${sandboxTerm}\n<div className='${demoTerm}'>${liveName}</div>`), []);
  assert.deepEqual(rules(`<a href="/${demoTerm}">${liveName}</a>`), []);
  assert.deepEqual(rules(`<p>/${demoTerm}</p>`), []);
  assert.deepEqual(rules(`<p>${liveName} (/${demoTerm}) ${liveName}</p>`), []);
  assert.deepEqual(rules(`const route = '${demoTerm}-route'`), []);
  assert.deepEqual(rules(`<p>${demoTerm}</p>`, 'frontend/src/app/page.test.tsx'), []);
});

test('blank rendered fallbacks are caught only in JSX expressions', () => {
  assert.deepEqual(rules("<p>{value ?? ''}</p>"), ['empty-render']);
  assert.deepEqual(rules('<p>{value || ""}</p>'), ['empty-render']);
  assert.deepEqual(rules("const fallback = value ?? '';"), []);
  assert.deepEqual(rules(`<button onClick={() => { setValue(value ?? ''); }}>${liveName}</button>`), []);
  assert.deepEqual(rules("// <p>{value ?? ''}</p>"), []);
});

test('allowlist and summary counts', () => {
  const findings = scanSource(`<p>${demoTerm}</p>`, 'frontend/src/app/page.tsx', cfg, capabilities, [
    { file: 'frontend/src/app/page.tsx', rule: 'sample-demo', match: demoTerm },
  ]);
  assert.deepEqual(findings, []);
  assert.equal(summarize(findings, 1, cfg).byRule['sample-demo'], 0);
  assert.deepEqual(check({ text: 'NaN value', kind: 'str' }, '', cfg, capabilities).map(x => x.rule), ['nan-undefined']);
});

test('copy gate detects regressions, accepts equal counts and reductions', () => {
  const file = path.relative(path.resolve(here, '../..'), path.resolve(here, '../../frontend/src/lib/capabilities.ts'));
  const rule = Object.keys(cfg.rules)[0];
  const findings = [{ file, rule }];
  const baseline = countsByFileRule(findings);
  assert.deepEqual(compareBaseline(baseline, baseline), { regressions: [], reductions: [] });
  assert.deepEqual(compareBaseline(countsByFileRule([...findings, ...findings]), baseline).regressions,
    [{ file, rule, baseline: 1, current: 2 }]);
  assert.deepEqual(compareBaseline({}, baseline).reductions,
    [{ file, rule, baseline: 1, current: 0 }]);
  assert.deepEqual(compareBaseline(baseline, {}).regressions,
    [{ file, rule, baseline: 0, current: 1 }]);
});

const gateFile = path.relative(path.resolve(here, '../..'), path.resolve(here, '../../frontend/src/lib/capabilities.ts'));
const gateRule = Object.keys(cfg.rules)[0];
const gateFinding = { file: gateFile, rule: gateRule };
const gateCounts = findings => Object.fromEntries(Object.entries(countsByFileRule(findings)).flatMap(([file, rules]) =>
  Object.entries(rules).map(([rule, count]) => [`${file}|${rule}`, count])));
const noFindings = gateCounts([]);
const oneFinding = gateCounts([gateFinding]);
const twoFindings = gateCounts([gateFinding, gateFinding]);

test('gateCompare fails when actual count rises', () => {
  const result = gateCompare(oneFinding, oneFinding, twoFindings);
  const key = `${gateFile}|${gateRule}`;
  const counts = `main=${oneFinding[key]}, PR baseline=${oneFinding[key]}, actual=${twoFindings[key]}`;
  assert.equal(result.ok, false);
  assert.equal(result.errors.some(error => error.includes('count went up vs main')), true);
  assert.equal(result.errors.every(error => error.includes(gateFile) && error.includes(gateRule)
    && error.includes(counts)), true);
});

test('gateCompare fails for a new key absent from main', () => {
  const result = gateCompare(noFindings, oneFinding, oneFinding);
  assert.equal(result.ok, false);
  assert.equal(result.errors.some(error => error.includes('count went up vs main')), true);
});

test('gateCompare rejects a PR baseline loosened above main', () => {
  const result = gateCompare(noFindings, oneFinding, noFindings);
  assert.equal(result.ok, false);
  assert.equal(result.errors.some(error => error.includes('PR baseline loosened vs main')), true);
});

test('gateCompare requires a baseline update after a drop', () => {
  const result = gateCompare(oneFinding, oneFinding, noFindings);
  assert.equal(result.ok, false);
  assert.equal(result.errors.some(error => error.includes('baseline.json is stale, run --update-baseline')), true);
});

test('gateCompare accepts equal counts', () => {
  assert.deepEqual(gateCompare(oneFinding, oneFinding, oneFinding), { ok: true, errors: [] });
});

test('gateCompare accepts a drop with a matching baseline update', () => {
  assert.deepEqual(gateCompare(oneFinding, noFindings, noFindings), { ok: true, errors: [] });
});
