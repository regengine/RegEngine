import { describe, expect, it } from 'vitest';
import { columnSuggestions, columnSuggestionsFromUploadError, FIELD_LABELS } from '@/lib/column-suggestions';

function suggestion(overrides: Record<string, unknown> = {}) {
  return {
    source_header: 'Lot #',
    source_key: 'lot_#',
    canonical_field: 'traceability_lot_code',
    confidence: 0.97,
    band: 'auto_apply',
    applied: false,
    blocked_reason: 'apply_disabled',
    ...overrides,
  };
}

describe('FIELD_LABELS', () => {
  it('uses labels that the CSV parser reads as the field itself', () => {
    // "Rename the column to <label>" must work: the parser lowercases headers
    // and turns spaces into underscores before it looks them up.
    for (const [field, label] of Object.entries(FIELD_LABELS)) {
      expect(label.trim().toLowerCase().replaceAll(' ', '_')).toBe(field);
    }
  });
});

describe('columnSuggestions', () => {
  it('offers an unapplied suggestion for a known field', () => {
    expect(columnSuggestions([suggestion()])).toEqual([
      { header: 'Lot #', field: 'traceability_lot_code', label: 'Traceability Lot Code', confidence: 0.97 },
    ]);
  });

  it('keeps review-band suggestions', () => {
    expect(columnSuggestions([suggestion({ band: 'review', confidence: 0.7 })])).toHaveLength(1);
  });

  it.each([
    ['no match', { canonical_field: null, blocked_reason: 'no_match' }],
    ['the reject band', { band: 'reject', confidence: 0.3 }],
    ['an applied mapping', { applied: true, blocked_reason: null }],
    ['an unknown field', { canonical_field: 'lot' }],
    ['an inherited property name', { canonical_field: 'toString' }],
    ['a blank header', { source_header: '  ' }],
  ])('drops %s', (_, overrides) => {
    expect(columnSuggestions([suggestion(overrides)])).toEqual([]);
  });

  it('keeps the first suggestion per header and tolerates junk', () => {
    const result = columnSuggestions([
      suggestion(),
      suggestion({ canonical_field: 'reference_document' }),
      null,
      'Lot #',
      suggestion({ source_header: 'Qty Shpd', canonical_field: 'quantity', confidence: 2 }),
    ]);
    expect(result).toEqual([
      { header: 'Lot #', field: 'traceability_lot_code', label: 'Traceability Lot Code', confidence: 0.97 },
      { header: 'Qty Shpd', field: 'quantity', label: 'Quantity', confidence: null },
    ]);
  });

  it.each([undefined, null, {}, 'x'])('returns nothing for a non-list %#', (value) => {
    expect(columnSuggestions(value)).toEqual([]);
  });
});

describe('columnSuggestionsFromUploadError', () => {
  it('reads the suggestions from the 400 detail kept on the error', () => {
    const error = Object.assign(new Error('No valid rows found'), {
      response: { status: 400, data: { detail: { message: 'No valid rows found', header_mapping_suggestions: [suggestion()] } } },
    });
    expect(columnSuggestionsFromUploadError(error)).toHaveLength(1);
  });

  it.each([new Error('Network Error'), 'boom', { response: { data: { detail: 'CSV contained no data rows' } } }])(
    'returns nothing without a detail list %#',
    (error) => {
      expect(columnSuggestionsFromUploadError(error)).toEqual([]);
    },
  );
});
