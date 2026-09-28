import { describe, expect, it } from 'vitest';
import { actionableCteSuggestion, CTE_LABELS, cteSuggestionFromUploadError } from '@/lib/cte-suggestion';

function suggestion(overrides: Record<string, unknown> = {}) {
  return {
    provider: 'typesafe',
    status: 'ok',
    cte_type: 'receiving',
    confidence: 0.97,
    band: 'auto_apply',
    applied: false,
    blocked_reason: 'apply_disabled',
    model: 'jev-1.13.0',
    request_id: 'req_1',
    questions_version: 'csv-file-cte.v1',
    apply_enabled: false,
    artifacts_recorded: 0,
    ...overrides,
  };
}

function uploadError(detail: unknown) {
  return Object.assign(new Error('No valid rows found: Row 2: No CTE type'), {
    response: { status: 400, data: { detail } },
  });
}

describe('actionableCteSuggestion', () => {
  it('offers an advisory answer that names one of the seven CTEs', () => {
    expect(actionableCteSuggestion(suggestion())).toEqual({
      cteType: 'receiving',
      label: 'Receiving',
      confidence: 0.97,
    });
  });

  it('covers exactly the seven FDA CTEs', () => {
    expect(Object.keys(CTE_LABELS).sort()).toEqual([
      'cooling',
      'first_land_based_receiving',
      'harvesting',
      'initial_packing',
      'receiving',
      'shipping',
      'transformation',
    ]);
  });

  it('offers a review-band answer', () => {
    expect(actionableCteSuggestion(suggestion({ band: 'review', confidence: 0.7 }))?.cteType).toBe('receiving');
  });

  it.each([
    ['a mixed or unclear file', { cte_type: null, blocked_reason: 'mixed_or_unclear' }],
    ['a reject-band answer', { band: 'reject', confidence: 0.3 }],
    ['an answer the server already applied', { applied: true, blocked_reason: null }],
    ['a provider failure', { status: 'unavailable:timeout', cte_type: null, confidence: null, band: null }],
    ['a CTE outside the vocabulary', { cte_type: 'growing' }],
    ['an inherited property name', { cte_type: 'constructor' }],
  ])('offers nothing for %s', (_, overrides) => {
    expect(actionableCteSuggestion(suggestion(overrides))).toBeNull();
  });

  it.each([undefined, null, 'receiving', ['receiving'], 42])('offers nothing for a malformed value %#', (value) => {
    expect(actionableCteSuggestion(value)).toBeNull();
  });

  it.each([null, 'high', Number.NaN, -0.1, 1.5])('drops an unusable confidence %#', (confidence) => {
    expect(actionableCteSuggestion(suggestion({ confidence }))).toEqual({
      cteType: 'receiving',
      label: 'Receiving',
      confidence: null,
    });
  });
});

describe('cteSuggestionFromUploadError', () => {
  it('reads the suggestion from the 400 detail the API client keeps on the error', () => {
    const error = uploadError({
      message: 'No valid rows found',
      errors: ['Row 2: No CTE type'],
      cte_type_suggestion: suggestion({ cte_type: 'shipping', confidence: 0.91 }),
    });
    expect(cteSuggestionFromUploadError(error)).toEqual({ cteType: 'shipping', label: 'Shipping', confidence: 0.91 });
  });

  it.each([
    ['a detail without a suggestion', uploadError({ message: 'No valid rows found', errors: [] })],
    ['a string detail', uploadError('CSV contained no data rows')],
    ['a validation array', uploadError([{ msg: 'field required' }])],
    ['a network error', new Error('Network Error')],
    ['a non-error value', 'boom'],
  ])('returns null for %s', (_, error) => {
    expect(cteSuggestionFromUploadError(error)).toBeNull();
  });
});
