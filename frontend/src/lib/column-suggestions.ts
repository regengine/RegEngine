import type { HeaderMappingSuggestion } from '@/types/api';

/**
 * Display names for the canonical fields Jev can suggest for a CSV column
 * (CANONICAL_FIELDS in services/shared/jev/header_mapping.py). Each label is
 * also a header the CSV parser reads as that field: lowercased with spaces
 * turned into underscores it is the field name itself, so "rename the column
 * to <label>" is always an instruction that works.
 */
export const FIELD_LABELS: Readonly<Record<string, string>> = {
  traceability_lot_code: 'Traceability Lot Code',
  product_description: 'Product Description',
  quantity: 'Quantity',
  unit_of_measure: 'Unit Of Measure',
  location_name: 'Location Name',
  location_gln: 'Location GLN',
  event_date: 'Event Date',
  event_time: 'Event Time',
  harvest_date: 'Harvest Date',
  cooling_date: 'Cooling Date',
  packing_date: 'Packing Date',
  ship_date: 'Ship Date',
  receive_date: 'Receive Date',
  transformation_date: 'Transformation Date',
  landing_date: 'Landing Date',
  ship_from_location: 'Ship From Location',
  ship_to_location: 'Ship To Location',
  ship_from_gln: 'Ship From GLN',
  ship_to_gln: 'Ship To GLN',
  receiving_location: 'Receiving Location',
  receiving_gln: 'Receiving GLN',
  reference_document: 'Reference Document',
  tlc_source_reference: 'TLC Source Reference',
  immediate_previous_source: 'Immediate Previous Source',
  harvester_business_name: 'Harvester Business Name',
  harvester_business_phone: 'Harvester Business Phone',
  input_lot_codes: 'Input Lot Codes',
  input_quantities: 'Input Quantities',
  input_units_of_measure: 'Input Units Of Measure',
  cte_type: 'CTE Type',
  carrier: 'Carrier',
};

export interface ColumnSuggestion {
  header: string;
  field: string;
  label: string;
  /** 0..1, or null when the server sent none. */
  confidence: number | null;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

/**
 * Suggestions an uploader can act on by renaming a column: they name a known
 * field, were not already applied by the server, and are not in the reject
 * band. `no_match` answers and unknown fields are dropped.
 */
export function columnSuggestions(value: unknown): ColumnSuggestion[] {
  if (!Array.isArray(value)) return [];
  const seen = new Set<string>();
  const out: ColumnSuggestion[] = [];
  for (const item of value) {
    const suggestion = asRecord(item) as Partial<HeaderMappingSuggestion>;
    const { source_header: header, canonical_field: field } = suggestion;
    if (typeof header !== 'string' || !header.trim()) continue;
    if (typeof field !== 'string' || !Object.hasOwn(FIELD_LABELS, field)) continue;
    if (suggestion.applied === true || suggestion.band === 'reject') continue;
    if (seen.has(header)) continue;
    seen.add(header);
    const confidence = typeof suggestion.confidence === 'number'
      && Number.isFinite(suggestion.confidence)
      && suggestion.confidence >= 0
      && suggestion.confidence <= 1
      ? suggestion.confidence
      : null;
    out.push({ header, field, label: FIELD_LABELS[field], confidence });
  }
  return out;
}

/** Column suggestions carried by a CSV upload the server rejected (400 "No valid rows found"). */
export function columnSuggestionsFromUploadError(error: unknown): ColumnSuggestion[] {
  const detail = asRecord(asRecord(asRecord(error).response).data).detail;
  return columnSuggestions(asRecord(detail).header_mapping_suggestions);
}
