import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { MODEL, POLICY } from './contract.ts';
import { classifyEvidence } from './evidence.ts';

globalThis.fetch = () => { throw new Error('Network disabled in offline regression tests'); };
const read = path => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8'));
const regression = read('./regression/cases.json');
const fresh = read('./heldout/cases.json');
const variants = ['combined', 'omission-aware'];

for (const item of regression) {
  test(`${item.id}: preserve the original combined response and verdict`, () => {
    const request = read(`./regression/original/${item.id}.request.json`);
    const response = read(`./regression/original/${item.id}.response.json`);
    const saved = read(`./regression/original/${item.id}.result.json`);
    const before = structuredClone(response);
    assert.deepEqual(classifyEvidence(request, response), saved.actual);
    assert.deepEqual(response, before);
    assert.equal(saved.matches, item.id !== 'HS04');
    if (item.id === 'HS04') {
      assert.equal(item.expected_verdict, 'insufficient');
      assert.equal(saved.actual.verdict, 'contradicted');
    }
  });
  test(`${item.id}: revised prompt live response matches the frozen regression label`, () => {
    const request = read(`./payloads/regression/omission-aware/${item.id}.request.json`);
    const response = read(`./records/${item.id}.omission-aware.response.json`);
    assert.equal(classifyEvidence(request, response).verdict, item.expected_verdict);
  });
}

test('frozen model, policy, and both question variants match their hashes', () => {
  const freeze = read('./prompt-freeze.json');
  assert.equal(MODEL, freeze.model);
  assert.deepEqual(POLICY, freeze.thresholds);
  for (const [path, hash] of Object.entries(freeze.frozen_source_hashes))
    assert.equal(createHash('sha256').update(readFileSync(new URL(path, import.meta.url))).digest('hex'), hash);
  for (const spec of Object.values(freeze.variants))
    assert.equal(createHash('sha256').update(readFileSync(new URL(spec.path, import.meta.url))).digest('hex'), spec.sha256);
});

test('all 100 saved responses reproduce the published results without model calls', () => {
  const summary = read('./results-summary.json');
  assert.equal(summary.rows.length, 100);
  assert.equal(new Set(summary.rows.map(r => `${r.case_id}/${r.variant}`)).size, 100);
  for (const row of summary.rows) {
    const request = read(`./payloads/${row.dataset}/${row.variant}/${row.case_id}.request.json`);
    const response = read(`./records/${row.case_id}.${row.variant}.response.json`);
    const actual = classifyEvidence(request, response);
    const gold = [...regression, ...fresh].find(c => c.id === row.case_id);
    assert.equal(actual.verdict, row.actual);
    assert.equal(row.expected, gold.expected_verdict);
    assert.equal(row.matches, actual.verdict === gold.expected_verdict);
  }
});

test('fresh evaluation preserves accuracy without new false decisive results or lost contradictions/conflicts', () => {
  const results = Object.fromEntries(variants.map(variant => [variant, fresh.map(item => {
    const request = read(`./payloads/heldout/${variant}/${item.id}.request.json`);
    const response = read(`./records/${item.id}.${variant}.response.json`);
    return { id: item.id, expected: item.expected_verdict, actual: classifyEvidence(request, response).verdict };
  })]));
  const correct = rows => rows.filter(r => r.expected === r.actual).length;
  assert(correct(results['omission-aware']) >= correct(results.combined));
  for (const row of results['omission-aware']) {
    if (['supported', 'contradicted'].includes(row.actual)) assert.equal(row.actual, row.expected, row.id);
    const baseline = results.combined.find(r => r.id === row.id);
    if (baseline.actual === baseline.expected && ['contradicted', 'conflicting'].includes(row.expected))
      assert.equal(row.actual, row.expected, row.id);
  }
});

test('malformed response probabilities cannot become a verdict', () => {
  const request = read('./regression/original/HS04.request.json');
  const response = read('./regression/original/HS04.response.json');
  response.answers.claim_polarity.probabilities.refutes_hypothesis = -0.1;
  assert.throws(() => classifyEvidence(request, response), /probability/);
});

test('response model mismatch cannot become a verdict', () => {
  const request = read('./regression/original/HS04.request.json');
  const response = read('./regression/original/HS04.response.json');
  response.model = 'different-model';
  assert.throws(() => classifyEvidence(request, response), /pinned model/);
});

test('original same-scope conflict keeps precedence over a decisive polarity', () => {
  const request = read('./regression/original/HC02.request.json');
  const response = read('./regression/original/HC02.response.json');
  assert.equal(classifyEvidence(request, response).verdict, 'conflicting');
});
