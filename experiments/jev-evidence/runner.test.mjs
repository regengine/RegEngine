import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

// Only selected synthetic files enter scratch. No real credential is inherited.
const source = fileURLToPath(new URL('.', import.meta.url));
const json = path => JSON.parse(readFileSync(path, 'utf8'));
const mock = `
import assert from 'node:assert/strict';
import { appendFileSync } from 'node:fs';
globalThis.fetch = async (endpoint, options) => {
  assert.equal(endpoint, 'https://api.typesafe.ai/v1/systemone');
  assert.equal(options.redirect, 'error');
  assert.equal(options.method, 'POST');
  const body = JSON.parse(options.body);
  assert.deepEqual(Object.keys(body), ['model', 'state', 'questions']);
  assert.equal(body.model, 'jev-1.13.0');
  assert.equal(body.state.synthetic, true);
  assert.equal(Object.hasOwn(body.state, 'expected_verdict'), false);
  assert.equal(Object.hasOwn(body.state, 'rationale'), false);
  appendFileSync(process.env.RUNNER_TEST_CALLS, 'mock-call\\n');
  if (process.env.RUNNER_TEST_MODE === 'http429') return new Response('', { status: 429 });
  if (process.env.RUNNER_TEST_MODE === 'transport') throw new Error('mock transport failure');
  return new Response(JSON.stringify({ model: body.model,
    answers: {
      evidence_addresses_claim: { type: 'noul', noul: 0.95 },
      sources_conflict_on_claim: { type: 'noul', noul: 0.05 },
      claim_polarity: { type: 'choice', choice: 'affirms_hypothesis', confidence: 1,
        probabilities: { affirms_hypothesis: 1, refutes_hypothesis: 0,
          partial_scope_only: 0, unaddressed_cannot_judge: 0 } }
    }, usage: { input_tokens: 1000, output_tokens: 10 } }));
};
`;

function sandbox() {
  const dir = mkdtempSync(join(tmpdir(), 'jev-polarity-runner-'));
  for (const name of ['run-compare.mjs', 'contract.ts', 'evidence.ts', 'package.json',
    'prompt-freeze.json', 'evaluation-queue.json', 'authorization.json',
    'prompts', 'payloads', 'heldout', 'regression'])
    cpSync(join(source, name), join(dir, name), { recursive: true });
  writeFileSync(join(dir, 'mock-fetch.mjs'), mock);
  return dir;
}
function run(dir, mode = 'success', args = ['--live']) {
  return spawnSync(process.execPath, ['--import', join(dir, 'mock-fetch.mjs'),
    join(dir, 'run-compare.mjs'), ...args], {
    cwd: dir, encoding: 'utf8', timeout: 30000,
    env: { TYPESAFE_API_KEY: 'synthetic-only', RUNNER_TEST_MODE: mode, // pragma: allowlist secret -- synthetic test marker, never used by live transport
      RUNNER_TEST_CALLS: join(dir, 'mock-calls.txt') },
  });
}
function calls(dir) {
  const path = join(dir, 'mock-calls.txt');
  return existsSync(path) ? readFileSync(path, 'utf8').trim().split('\n').length : 0;
}

test('preflight checks every frozen payload without dispatch or ledger creation', () => {
  const dir = sandbox(), result = run(dir, 'success', ['--preflight']);
  assert.equal(result.status, 0, result.stderr);
  assert.deepEqual(JSON.parse(result.stdout), { requests: 100, prior_cost_usd: '0.006837516',
    maximum_cumulative_reservation_usd: '0.906837516', live_calls: 0 });
  assert.equal(calls(dir), 0);
  assert.equal(existsSync(join(dir, 'comparison-ledger.json')), false);
});

test('100 mocked requests reconcile costs and a duplicate run makes no further call', () => {
  const dir = sandbox(), result = run(dir);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(calls(dir), 100);
  const ledger = json(join(dir, 'comparison-ledger.json'));
  assert.equal(ledger.status, 'completed');
  assert.equal(ledger.attempts.length, 100);
  assert.equal(new Set(ledger.attempts.map(r => `${r.dataset}/${r.case_id}/${r.variant}`)).size, 100);
  assert.equal(ledger.cost_usd, '0.004200000');
  assert.equal(ledger.cumulative_cost_usd, '0.011037516');
  assert.equal(ledger.remaining_budget_usd, '0.988962484');
  assert.equal(ledger.unmetered_attempts, 0);
  assert.equal(ledger.input_tokens, 100000);
  assert.equal(ledger.output_tokens, 1000);
  for (const item of ledger.attempts) {
    const prefix = join(dir, 'records', `${item.case_id}.${item.variant}`);
    assert.equal(json(`${prefix}.response.json`).usage.input_tokens, 1000);
    assert.equal(json(`${prefix}.result.json`).actual.verdict, item.actual);
  }
  assert.equal(run(dir).status, 1);
  assert.equal(calls(dir), 100, 'Existing ledger must prevent duplicate dispatch');
  assert.deepEqual(json(join(dir, 'comparison-ledger.json')), ledger);
});

for (const [mode, error] of [['http429', 'HTTP_429'], ['transport', 'TRANSPORT_OR_RESPONSE_ERROR']]) {
  test(`${mode} stops after one attempt without retry and reserves its unknown cost`, () => {
    const dir = sandbox(), result = run(dir, mode);
    assert.equal(result.status, 1);
    assert.equal(calls(dir), 1);
    const ledger = json(join(dir, 'comparison-ledger.json'));
    assert.equal(ledger.status, 'stopped_after_error');
    assert.equal(ledger.attempts.length, 1);
    assert.equal(ledger.attempts[0].error, error);
    assert.equal(ledger.unmetered_attempts, 1);
    assert.equal(ledger.cost_usd, '0.000000000');
    assert.equal(ledger.conservative_cumulative_cost_bound_usd, '0.015837516');
    assert.equal(run(dir).status, 1);
    assert.equal(calls(dir), 1);
  });
}

test('a modified frozen request is rejected before dispatch or ledger creation', () => {
  const dir = sandbox();
  const first = json(join(dir, 'evaluation-queue.json')).requests[0];
  const path = join(dir, first.path), request = json(path);
  request.state.hypothesis_to_verify += ' Changed after freeze.';
  writeFileSync(path, JSON.stringify(request));
  assert.equal(run(dir).status, 1);
  assert.equal(calls(dir), 0);
  assert.equal(existsSync(join(dir, 'comparison-ledger.json')), false);
});

test('a duplicate case/variant hidden behind a different path is rejected before dispatch', () => {
  const dir = sandbox(), path = join(dir, 'evaluation-queue.json'), queue = json(path);
  Object.assign(queue.requests[1], { dataset: queue.requests[0].dataset,
    case_id: queue.requests[0].case_id, variant: queue.requests[0].variant });
  writeFileSync(path, JSON.stringify(queue));
  assert.equal(run(dir).status, 1);
  assert.equal(calls(dir), 0);
  assert.equal(existsSync(join(dir, 'comparison-ledger.json')), false);
});
