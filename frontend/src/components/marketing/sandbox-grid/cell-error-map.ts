/**
 * Maps evaluation results to specific grid cells.
 *
 * Two strategies:
 * 1. KDE errors: parse "Missing required KDE 'field_name' for X CTE" strings
 * 2. Rule failures: map rule categories/titles to known field names
 */

import type { CellError, CellErrorMap } from './types';
import { cellKey } from './types';

interface EventEvaluation {
  event_index: number;
  kde_errors: string[];
  all_results: {
    rule_title: string;
    severity: string;
    result: string;
    why_failed: string | null;
    citation: string | null;
    remediation: string | null;
    category: string;
  }[];
}

/** Regex to extract field name from KDE error strings */
const KDE_ERROR_RE = /Missing required KDE '([^']+)'/;

/**
 * Map from rule category + title keywords → CSV column names that the rule inspects.
 * This lets us highlight the correct cell even though the API response doesn't include
 * structured field references.
 */
const RULE_TO_COLUMNS: Record<string, string[]> = {
  // Relational rules
  'temporal_ordering': ['timestamp', 'event_date', 'harvest_date', 'ship_date', 'receive_date', 'cooling_date'],
  'quantity_consistency': ['quantity', 'unit_of_measure'],
  // Identity rules tagged under lot_linkage
  'lot_linkage:Identity': ['product_description', 'product', 'commodity'],

  // Structural rules (kde_presence) — these we handle via KDE error parsing instead
  // but some rules check specific fields:
  'source_reference': ['tlc_source_reference', 'immediate_previous_source'],
  'identifier_format': ['location_gln', 'gln'],
};

/**
 * KDE field name → possible CSV column names (the field might appear under various aliases)
 */
const KDE_TO_CSV_COLUMNS: Record<string, string[]> = {
  harvest_date: ['harvest_date', 'harvested', 'date_harvested'],
  cooling_date: ['cooling_date', 'cooled_date', 'cool_date'],
  ship_date: ['ship_date', 'shipped_date', 'shipping_date'],
  receive_date: ['receive_date', 'received_date', 'receipt_date'],
  reference_document: ['reference_document', 'ref_doc', 'bol', 'bol_number', 'invoice'],
  ship_from_location: ['ship_from_location', 'ship_from', 'from_location', 'origin'],
  ship_to_location: ['ship_to_location', 'ship_to', 'destination', 'to_location'],
  tlc_source_reference: ['tlc_source_reference', 'tlc_source', 'source_reference'],
  immediate_previous_source: ['immediate_previous_source', 'previous_source', 'source'],
  receiving_location: ['receiving_location', 'received_at'],
  carrier: ['carrier', 'carrier_name', 'transport'],
  harvester_business_name: ['harvester_business_name', 'harvester', 'grower', 'farm'],
  transformation_date: ['transformation_date', 'transform_date'],
  input_traceability_lot_codes: ['input_traceability_lot_codes', 'input_tlcs', 'input_lots'],
  traceability_lot_code: ['traceability_lot_code', 'tlc', 'lot_code', 'lot'],
  product_description: ['product_description', 'product', 'product_name', 'commodity'],
  quantity: ['quantity', 'qty', 'amount', 'weight'],
  unit_of_measure: ['unit_of_measure', 'uom', 'unit'],
  location_name: ['location_name', 'location', 'facility', 'site'],
  location_gln: ['location_gln', 'gln'],
};

/**
 * Find which CSV column header matches a KDE field name.
 * Returns the matching header from the actual CSV, or the KDE name itself as fallback.
 */
function findCsvColumn(kdeName: string, csvHeaders: string[]): string {
  const lowerHeaders = csvHeaders.map((h) => h.toLowerCase().replace(/\s+/g, '_'));

  // Direct match
  const directIdx = lowerHeaders.indexOf(kdeName.toLowerCase());
  if (directIdx >= 0) return csvHeaders[directIdx];

  // Check aliases
  const aliases = KDE_TO_CSV_COLUMNS[kdeName] || [];
  for (const alias of aliases) {
    const idx = lowerHeaders.indexOf(alias.toLowerCase());
    if (idx >= 0) return csvHeaders[idx];
  }

  return kdeName; // fallback — won't highlight but won't crash
}

/**
 * Build a cell error map from evaluation results.
 */
export function buildCellErrorMap(
  events: EventEvaluation[],
  csvHeaders: string[],
): CellErrorMap {
  const map: CellErrorMap = new Map();

  for (const ev of events) {
    const row = ev.event_index;

    // 1. KDE errors → map to specific columns
    for (const errStr of ev.kde_errors) {
      const match = errStr.match(KDE_ERROR_RE);
      if (match) {
        const kdeName = match[1];
        const col = findCsvColumn(kdeName, csvHeaders);
        const key = cellKey(row, col);
        const existing = map.get(key) || [];
        existing.push({
          ruleTitle: `Missing KDE: ${kdeName}`,
          severity: 'warning',
          whyFailed: errStr,
          citation: null,
          remediation: `Add a value for '${kdeName}' in this cell.`,
          category: 'kde_presence',
          isKdeError: true,
        });
        map.set(key, existing);
      }
    }

    // 2. Rule failures → map by category to columns
    for (const r of ev.all_results) {
      if (r.result !== 'fail' && r.result !== 'warn') continue;

      // Determine which columns this rule affects
      let columns: string[] = [];

      // Check category-specific mapping
      const categoryKey = r.category;
      if (RULE_TO_COLUMNS[categoryKey]) {
        columns = RULE_TO_COLUMNS[categoryKey];
      }

      // Special handling for identity rules under lot_linkage
      if (r.category === 'lot_linkage' && r.rule_title.includes('Identity')) {
        columns = RULE_TO_COLUMNS['lot_linkage:Identity'] || ['product_description'];
      }

      // For kde_presence rules, try to extract field from why_failed
      if (r.category === 'kde_presence' && r.why_failed) {
        const fieldMatch = r.why_failed.match(/field '([^']+)'/);
        if (fieldMatch) {
          columns = [findCsvColumn(fieldMatch[1], csvHeaders)];
        }
      }

      // Map to actual CSV headers
      const resolvedColumns = columns
        .map((c) => findCsvColumn(c, csvHeaders))
        .filter((c) => csvHeaders.includes(c));

      // If we couldn't resolve any columns, highlight the row's cte_type column as fallback
      if (resolvedColumns.length === 0) {
        const cteCol = findCsvColumn('cte_type', csvHeaders);
        resolvedColumns.push(cteCol);
      }

      for (const col of resolvedColumns) {
        const key = cellKey(row, col);
        const existing = map.get(key) || [];
        existing.push({
          ruleTitle: r.rule_title,
          severity: r.severity,
          whyFailed: r.why_failed || '',
          citation: r.citation,
          remediation: r.remediation,
          category: r.category,
          isKdeError: false,
        });
        map.set(key, existing);
      }
    }
  }

  return map;
}
