import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { MODEL, ENDPOINT, POLICY, assert, validateRequest } from './contract.ts';
import { classifyEvidence } from './evidence.ts';

const url = path => new URL(path, import.meta.url);
const read = async path => JSON.parse(await readFile(url(path), 'utf8'));
const save = (path, value, options = {}) => writeFile(url(path), JSON.stringify(value, null, 2) + '\n', options);
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const MAX_ATTEMPTS = 100;
const CAP_NANO_USD = 1_000_000_000;
const PRIOR_NANO_USD = 6_837_516;
const RESERVE_NANO_USD = 9_000_000;
const INPUT_TOKEN_NANO_USD = 42;
const usd = nano => (nano / 1_000_000_000).toFixed(9);

async function main() {
  const freeze = await read('./prompt-freeze.json');
  const queue = (await read('./evaluation-queue.json')).requests;
  const cases = {};
  for (const [dataset, count] of [['heldout', 16], ['regression', 34]]) {
    const bytes = await readFile(url(`./${dataset}/cases.json`));
    assert(sha(bytes) === (await read(`./${dataset}/freeze.json`)).cases_sha256, 'Frozen cases changed');
    cases[dataset] = JSON.parse(bytes);
    assert(cases[dataset].length === count && new Set(cases[dataset].map(c => c.id)).size === count, 'Invalid case count');
    assert(cases[dataset].every(c => ['supported', 'contradicted', 'conflicting', 'insufficient'].includes(c.expected_verdict)), 'Invalid expected verdict');
  }
  assert(new Set(Object.values(cases).flat().map(c => c.id)).size === 50, 'Overlapping dataset IDs');
  assert(same(freeze.thresholds, POLICY) && freeze.model === MODEL, 'Decision policy changed');
  for (const [path, expected] of Object.entries(freeze.frozen_source_hashes))
    assert(sha(await readFile(url(path))) === expected, 'Frozen source changed');
  const variants = {};
  assert(same(Object.keys(freeze.variants).sort(), ['combined', 'omission-aware']), 'Unexpected variants');
  for (const [name, spec] of Object.entries(freeze.variants)) {
    const bytes = await readFile(url(spec.path));
    assert(sha(bytes) === spec.sha256, 'Frozen prompt changed');
    variants[name] = JSON.parse(bytes);
  }
  assert(queue.length === MAX_ATTEMPTS && new Set(queue.map(r => r.path)).size === MAX_ATTEMPTS, 'Invalid request count');
  assert(new Set(queue.map(r => `${r.dataset}/${r.case_id}/${r.variant}`)).size === MAX_ATTEMPTS, 'Duplicate case variant');
  assert(queue.filter(r => r.dataset === 'heldout').length === 32 && queue.filter(r => r.dataset === 'regression').length === 68, 'Invalid dataset counts');
  assert(PRIOR_NANO_USD + MAX_ATTEMPTS * RESERVE_NANO_USD <= CAP_NANO_USD, 'Batch exceeds remaining budget');
  const prepared = [];
  for (const entry of queue) {
    assert(/^payloads\/(heldout|regression)\/(combined|omission-aware)\/[A-Z0-9]+\.request\.json$/.test(entry.path), 'Invalid request path');
    assert(entry.path === `payloads/${entry.dataset}/${entry.variant}/${entry.case_id}.request.json`, 'Request identity differs from path');
    const body = await readFile(url(entry.path), 'utf8');
    assert(sha(body) === entry.sha256, 'Prepared request changed');
    assert(Buffer.byteLength(body) < 16000, 'Request exceeds bounded size');
    const request = validateRequest(JSON.parse(body));
    assert(request.state.synthetic === true && same(request.questions, variants[entry.variant]), 'Unexpected payload');
    assert(same(Object.keys(request), ['model', 'state', 'questions']), 'Unexpected top-level request fields');
    const gold = cases[entry.dataset].find(item => item.id === entry.case_id);
    assert(gold && same(request.state, gold.state), 'Frozen state changed');
    const expected = gold.expected_verdict;
    prepared.push({ entry, body, request, expected });
  }
  if (process.argv.includes('--preflight')) {
    process.stdout.write(JSON.stringify({ requests: prepared.length, prior_cost_usd: usd(PRIOR_NANO_USD),
      maximum_cumulative_reservation_usd: usd(PRIOR_NANO_USD + MAX_ATTEMPTS * RESERVE_NANO_USD), live_calls: 0 }) + '\n');
    return;
  }
  assert(process.argv.includes('--live'), 'Explicit --live flag required');
  const authorization = await read('./authorization.json');
  assert(authorization.authorized === true && authorization.requests === MAX_ATTEMPTS
    && authorization.original_budget_cap_usd === '1.00' && authorization.prior_spend_usd === usd(PRIOR_NANO_USD), 'Authorization record does not match batch');
  const ledger = { status: 'prepared', model: MODEL, endpoint: ENDPOINT, synthetic_only: true,
    started_at_utc: new Date().toISOString(), budget_cap_usd: '1.00', prior_spend_usd: usd(PRIOR_NANO_USD),
    max_attempts: MAX_ATTEMPTS, reserved_per_attempt_usd: usd(RESERVE_NANO_USD),
    maximum_cumulative_reservation_usd: usd(PRIOR_NANO_USD + MAX_ATTEMPTS * RESERVE_NANO_USD),
    input_price_usd_per_million: '0.042', output_price_usd_per_million: '0',
    pricing_source: 'https://docs.typesafe.ai/models', pricing_checked_date: '2026-10-29',
    queue_sha256: sha(await readFile(url('./evaluation-queue.json'))), attempts: [] };
  // Persist before credential lookup; exclusive creation blocks duplicate dispatch.
  await save('./comparison-ledger.json', ledger, { flag: 'wx' });
  let key = process.env.TYPESAFE_API_KEY;
  if (!key) {
    try { key = execFileSync('/usr/bin/security', ['find-generic-password', '-s', 'cw-vault', '-a', 'TYPESAFE_API_KEY', '-w'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 10000 }).trim(); }
    catch { throw new Error('Existing credential unavailable'); }
  }
  assert(key?.trim(), 'Existing credential unavailable');
  await mkdir(url('./records/'), { recursive: true });
  for (const { entry, body, request, expected } of prepared) {
    assert(PRIOR_NANO_USD + (ledger.attempts.length + 1) * RESERVE_NANO_USD <= CAP_NANO_USD, 'Budget exhausted');
    const record = { case_id: entry.case_id, dataset: entry.dataset, variant: entry.variant,
      request_sha256: entry.sha256, expected, status: 'reserved', started_at_utc: new Date().toISOString() };
    ledger.attempts.push(record);
    ledger.status = 'running';
    await save('./comparison-ledger.json', ledger);
    const prefix = `./records/${entry.case_id}.${entry.variant}`;
    const start = performance.now();
    try {
      const result = await fetch(ENDPOINT, { method: 'POST', redirect: 'error', signal: AbortSignal.timeout(30000),
        headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, body });
      record.http_status = result.status;
      record.elapsed_ms = Math.round(performance.now() - start);
      if (!result.ok) throw new Error(`HTTP_${result.status}`);
      const response = await result.json();
      await save(`${prefix}.response.json`, response);
      const usage = response.usage;
      assert(Number.isSafeInteger(usage?.input_tokens) && usage.input_tokens >= 0
        && Number.isSafeInteger(usage?.output_tokens) && usage.output_tokens >= 0, 'INVALID_USAGE');
      record.usage = usage;
      record.cost_nano_usd = usage.input_tokens * INPUT_TOKEN_NANO_USD;
      record.cost_usd = usd(record.cost_nano_usd);
      assert(record.cost_nano_usd <= RESERVE_NANO_USD, 'USAGE_EXCEEDS_RESERVATION');
      try {
        const actual = classifyEvidence(request, response);
        record.actual = actual.verdict;
        record.reason = actual.reason;
        record.matches = actual.verdict === expected;
        record.status = 'completed';
        await save(`${prefix}.result.json`, { expected, actual, matches: record.matches });
      } catch (failure) {
        record.status = 'harness_error';
        record.error = failure.message;
        await save(`${prefix}.result.json`, { expected, harness_error: failure.message });
      }
      await save('./comparison-ledger.json', ledger);
      process.stdout.write(`${ledger.attempts.length}/${MAX_ATTEMPTS} ${entry.case_id} ${entry.variant}: ${record.actual ?? record.status}${record.status === 'completed' ? record.matches ? ' MATCH' : ' MISMATCH' : ''}\n`);
    } catch (failure) {
      record.status = 'failed';
      record.error = /^HTTP_\d+$|^INVALID_USAGE$|^USAGE_EXCEEDS_RESERVATION$/.test(failure.message) ? failure.message : 'TRANSPORT_OR_RESPONSE_ERROR';
      ledger.status = 'stopped_after_error';
      await save('./comparison-ledger.json', ledger);
      process.stdout.write(`Stopped at ${entry.case_id}/${entry.variant}: ${record.error}; no retry\n`);
      process.exitCode = 1;
      break;
    }
  }
  key = undefined;
  ledger.input_tokens = ledger.attempts.reduce((sum, r) => sum + (r.usage?.input_tokens ?? 0), 0);
  ledger.output_tokens = ledger.attempts.reduce((sum, r) => sum + (r.usage?.output_tokens ?? 0), 0);
  ledger.unmetered_attempts = ledger.attempts.filter(r => !r.usage).length;
  const cost = ledger.attempts.reduce((sum, r) => sum + (r.cost_nano_usd ?? 0), 0);
  ledger.cost_usd = usd(cost);
  ledger.cumulative_cost_usd = usd(PRIOR_NANO_USD + cost);
  ledger.remaining_budget_usd = usd(CAP_NANO_USD - PRIOR_NANO_USD - cost);
  ledger.conservative_cumulative_cost_bound_usd = usd(PRIOR_NANO_USD + cost + ledger.unmetered_attempts * RESERVE_NANO_USD);
  ledger.invoice_debit_verified = false;
  if (ledger.status === 'running') ledger.status = ledger.attempts.some(r => r.status !== 'completed') ? 'completed_with_harness_errors' : 'completed';
  ledger.finished_at_utc = new Date().toISOString();
  await save('./comparison-ledger.json', ledger);
}
main().catch(() => { process.stderr.write('Comparison stopped before completion. Inspect its ledger if present; no automatic retries.\n'); process.exitCode = 1; });
