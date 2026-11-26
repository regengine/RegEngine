import { assert, choice, noul, object, POLICY, string, validateResponse } from './contract.ts';
import type { Request } from './contract.ts';

export type EvidenceVerdict = 'supported' | 'contradicted' | 'conflicting' | 'insufficient';
export const VERDICTS: EvidenceVerdict[] = ['supported', 'contradicted', 'conflicting', 'insufficient'];

export function classifyEvidence(request: Request, rawResponse: unknown) {
  const response = validateResponse(request, rawResponse);
  const state = request.state;
  string(state.claim_id);
  string(state.hypothesis_to_verify);
  const sources = state.curated_evidence_sources;
  assert(Array.isArray(sources), 'Evidence sources must be an array');
  const ids = sources.map(source => {
    const item = object(source);
    string(item.excerpt);
    string(item.scope);
    return string(item.source_id);
  });
  assert(new Set(ids).size === ids.length, 'Duplicate evidence source IDs');
  const addressed = noul(response, 'evidence_addresses_claim');
  const conflict = noul(response, 'sources_conflict_on_claim');
  const polarity = choice(response, 'claim_polarity');
  const result = (verdict: EvidenceVerdict, reason: string) => ({
    claim_id: state.claim_id, verdict, reason, policy_status: 'uncalibrated' as const,
    review_required: verdict === 'conflicting' || verdict === 'insufficient',
    model: response.model,
  });
  if (sources.length === 0) return result('insufficient', 'no_supplied_evidence');
  if (addressed < POLICY.yes) return result('insufficient', 'claim_coverage_not_established');
  // A polarity question can be undecidable precisely because sources conflict.
  if (conflict >= POLICY.yes) return result('conflicting', 'incompatible_same_scope_evidence');
  if (conflict > POLICY.no) return result('insufficient', 'conflict_uncertain');
  if (polarity.probabilities[polarity.choice] < POLICY.choice) return result('insufficient', 'polarity_uncertain');
  if (polarity.choice === 'affirms_hypothesis') return result('supported', 'direct_support');
  if (polarity.choice === 'refutes_hypothesis') return result('contradicted', 'explicit_incompatible_fact');
  return result('insufficient', polarity.choice === 'partial_scope_only' ? 'only_partial_support' : 'claim_not_resolved');
}

/** Evaluate saved, labeled controls. Does not call Jev or claim synthetic cases are real controls. */
export function evaluateControls(cases: Array<{ id: string; expected: EvidenceVerdict; request: Request; response: unknown }>) {
  assert(cases.length > 0, 'No labeled controls supplied');
  assert(new Set(cases.map(c => c.id)).size === cases.length, 'Duplicate control IDs');
  const confusion = Object.fromEntries(VERDICTS.map(expected => [expected,
    Object.fromEntries(VERDICTS.map(predicted => [predicted, 0]))]));
  const rows = cases.map(item => {
    string(item.id);
    assert(VERDICTS.includes(item.expected), 'Unknown expected verdict');
    const actual = classifyEvidence(item.request, item.response).verdict;
    confusion[item.expected][actual]++;
    return { id: item.id, expected: item.expected, actual, matches: actual === item.expected };
  });
  const correct = rows.filter(row => row.matches).length;
  return { total: rows.length, correct, accuracy: correct / rows.length, confusion, rows,
    calibration_status: 'not_established_by_replay' };
}
