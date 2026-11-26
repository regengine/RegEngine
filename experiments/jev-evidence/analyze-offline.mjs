// Recompute this completed comparison from saved responses. No network or credentials.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { POLICY, MODEL, validateRequest } from './contract.ts';
import { classifyEvidence, VERDICTS } from './evidence.ts';

const url = path => new URL(path, import.meta.url);
const read = async path => JSON.parse(await readFile(url(path), 'utf8'));
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const usd = nano => (nano / 1e9).toFixed(9);
const variants = ['combined', 'omission-aware'];
const ledger = await read('./comparison-ledger.json');
const queue = (await read('./evaluation-queue.json')).requests;
const heldoutCases = await read('./heldout/cases.json');
const regressionCases = await read('./regression/cases.json');
const cases = [...heldoutCases, ...regressionCases];
const freeze = await read('./prompt-freeze.json');
assert.equal(ledger.status, 'completed');
assert.equal(ledger.attempts.length, 100);
assert.equal(queue.length, 100);
assert.equal(sha(await readFile(url('./evaluation-queue.json'))), ledger.queue_sha256);
assert.deepEqual(POLICY, freeze.thresholds);
assert.equal(MODEL, freeze.model);
assert.equal(sha(await readFile(url('./heldout/cases.json'))), (await read('./heldout/freeze.json')).cases_sha256);
assert.equal(sha(await readFile(url('./regression/cases.json'))), (await read('./regression/freeze.json')).cases_sha256);
for (const [path, hash] of Object.entries(freeze.frozen_source_hashes))
  assert.equal(sha(await readFile(url(path))), hash);
for (const spec of Object.values(freeze.variants))
  assert.equal(sha(await readFile(url(spec.path))), spec.sha256);

const rows = [];
for (let index = 0; index < queue.length; index++) {
  const entry = queue[index], attempt = ledger.attempts[index];
  assert.equal(attempt.case_id, entry.case_id);
  assert.equal(attempt.variant, entry.variant);
  assert.equal(attempt.dataset, entry.dataset);
  assert.equal(attempt.status, 'completed');
  assert.equal(attempt.http_status, 200);
  const body = await readFile(url(entry.path));
  assert.equal(sha(body), entry.sha256);
  assert.equal(attempt.request_sha256, entry.sha256);
  const request = validateRequest(JSON.parse(body));
  assert.equal(request.state.synthetic, true);
  assert.deepEqual(Object.keys(request), ['model', 'state', 'questions']);
  assert.deepEqual(request.questions, await read(freeze.variants[entry.variant].path));
  const gold = cases.find(item => item.id === entry.case_id);
  const expected = gold.expected_verdict;
  assert.deepEqual(request.state, gold.state);
  const prefix = `./records/${entry.case_id}.${entry.variant}`;
  const response = await read(`${prefix}.response.json`);
  const saved = await read(`${prefix}.result.json`);
  const actual = classifyEvidence(request, response);
  assert.deepEqual(saved, { expected, actual, matches: actual.verdict === expected });
  assert.equal(attempt.expected, expected);
  assert.equal(attempt.actual, actual.verdict);
  assert.equal(attempt.reason, actual.reason);
  assert.equal(attempt.matches, saved.matches);
  assert.deepEqual(attempt.usage, response.usage);
  const costNano = response.usage.input_tokens * 42;
  assert.equal(attempt.cost_nano_usd, costNano);
  assert.equal(attempt.cost_usd, usd(costNano));
  const answers = response.answers, polarity = answers.claim_polarity;
  rows.push({ dataset: entry.dataset, case_id: entry.case_id, variant: entry.variant,
    family: gold?.family ?? 'regression', expected, actual: actual.verdict,
    matches: saved.matches, reason: actual.reason,
    coverage: answers.evidence_addresses_claim.noul, conflict: answers.sources_conflict_on_claim.noul,
    polarity: polarity.choice, chosen_probability: polarity.probabilities[polarity.choice],
    confidence: polarity.confidence, probabilities: polarity.probabilities,
    input_tokens: response.usage.input_tokens, output_tokens: response.usage.output_tokens,
    cost_nano_usd: costNano, cost_usd: usd(costNano) });
}
assert.equal(new Set(rows.map(r => `${r.dataset}/${r.case_id}/${r.variant}`)).size, 100);
for (const variant of variants) {
  assert.equal(rows.filter(r => r.variant === variant && r.dataset === 'heldout').length, 16);
  assert.equal(rows.filter(r => r.variant === variant && r.dataset === 'regression').length, 34);
}
function metrics(items) {
  const confusion = Object.fromEntries(VERDICTS.map(expected => [expected,
    Object.fromEntries(VERDICTS.map(actual => [actual, 0]))]));
  for (const row of items) confusion[row.expected][row.actual]++;
  const correct = items.filter(r => r.matches).length;
  const ids = predicate => items.filter(predicate).map(r => r.case_id);
  return { total: items.length, correct, accuracy: correct / items.length,
    mismatches: ids(r => !r.matches), harness_errors: 0, confusion,
    unnecessary_insufficient: ids(r => r.actual === 'insufficient' && r.expected !== 'insufficient'),
    false_decisive: ids(r => ['supported', 'contradicted'].includes(r.actual) && !r.matches),
    missed_conflicts: ids(r => r.expected === 'conflicting' && r.actual !== 'conflicting'),
    false_conflicts: ids(r => r.expected !== 'conflicting' && r.actual === 'conflicting') };
}
const datasets = {};
for (const dataset of ['heldout', 'regression']) {
  const items = rows.filter(r => r.dataset === dataset);
  const baseline = new Map(items.filter(r => r.variant === 'combined').map(r => [r.case_id, r]));
  datasets[dataset] = Object.fromEntries(variants.map(variant => {
    const subset = items.filter(r => r.variant === variant);
    return [variant, { ...metrics(subset),
      families: Object.fromEntries([...new Set(subset.map(r => r.family))].map(family =>
        [family, metrics(subset.filter(r => r.family === family))])),
      improvements_vs_baseline: subset.filter(r => r.matches && !baseline.get(r.case_id).matches).map(r => r.case_id),
      regressions_vs_baseline: subset.filter(r => !r.matches && baseline.get(r.case_id).matches).map(r => r.case_id) }];
  }));
}
const inputTokens = rows.reduce((sum, r) => sum + r.input_tokens, 0);
const outputTokens = rows.reduce((sum, r) => sum + r.output_tokens, 0);
const costNano = rows.reduce((sum, r) => sum + r.cost_nano_usd, 0);
assert.equal(inputTokens, ledger.input_tokens);
assert.equal(outputTokens, ledger.output_tokens);
assert.equal(ledger.unmetered_attempts, 0);
assert.equal(usd(costNano), ledger.cost_usd);
assert.equal(usd(6837516 + costNano), ledger.cumulative_cost_usd);
assert.equal(usd(1e9 - 6837516 - costNano), ledger.remaining_budget_usd);
assert(6837516 + costNano <= 1e9);
const summary = { model: MODEL, thresholds: POLICY, policy_status: 'uncalibrated', synthetic_only: true,
  requests: rows.length, unique_cases: cases.length, retries: 0,
  live_started_at_utc: ledger.started_at_utc, live_finished_at_utc: ledger.finished_at_utc,
  offline_replay_matches: rows.length, datasets,
  cost: { input_tokens: inputTokens, output_tokens: outputTokens,
    input_usd_per_million: '0.042', output_usd_per_million: '0',
    batch_usd: usd(costNano), prior_usd: '0.006837516', cumulative_usd: usd(6837516 + costNano),
    original_cap_usd: '1.00', remaining_usd: usd(1e9 - 6837516 - costNano),
    unmetered_attempts: 0, invoice_debit_verified: false, pricing_source: ledger.pricing_source },
  promotion_performed: false,
  limitations: ['One response per case and variant; repeated-run stability is unmeasured.',
    'Sixteen synthetic held-out cases include related pairs and are not independent production samples.',
    'All 34 exposed cases, including HS04, are regression evidence and excluded from primary accuracy.',
    'The 16 fresh cases become development evidence for any subsequent prompt revision.'],
  rows };
summary.acceptance = {
  hs04_fixed: rows.find(r => r.case_id === 'HS04' && r.variant === 'omission-aware').matches,
  all_regressions_correct: datasets.regression['omission-aware'].correct === 34,
  heldout_accuracy_not_lower: datasets.heldout['omission-aware'].correct >= datasets.heldout.combined.correct,
  no_heldout_false_decisive: datasets.heldout['omission-aware'].false_decisive.length === 0,
  no_lost_true_contradictions_or_conflicts: datasets.heldout['omission-aware'].regressions_vs_baseline.every(id =>
    !['contradicted', 'conflicting'].includes(cases.find(c => c.id === id).expected_verdict)),
};
summary.acceptance_passed = Object.values(summary.acceptance).every(Boolean);
await writeFile(url('./results-summary.json'), JSON.stringify(summary, null, 2) + '\n');
const columns = Object.keys(rows[0]).filter(key => key !== 'probabilities');
const cell = value => `"${String(value).replaceAll('"', '""')}"`;
await writeFile(url('./results.csv'), [columns.join(','), ...rows.map(row => columns.map(key => cell(row[key])).join(','))].join('\n') + '\n');
process.stdout.write(JSON.stringify({ replay_matches: rows.length, heldout_correct:
  Object.fromEntries(variants.map(v => [v, datasets.heldout[v].correct])), cost: summary.cost, acceptance: summary.acceptance, acceptance_passed: summary.acceptance_passed }, null, 2) + '\n');
