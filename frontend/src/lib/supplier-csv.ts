/* ── FSMA 204 client-side validation (no auth required) ── */

const EVENT_TYPE_LABELS: Record<string, string> = {
  receiving: 'Receiving', shipping: 'Shipping', transforming: 'Transforming',
  cooling: 'Cooling', initial_packing: 'Initial Packing', harvesting: 'Harvesting', first_receiver: 'First Receiver',
};
// Keep aligned with admin bulk_upload.validators.normalize_cte_type.
const EVENT_ALIASES: Record<string, string> = {
  r: 'receiving', s: 'shipping', d: 'shipping', depletion: 'shipping', t: 'transforming', c: 'cooling', p: 'initial_packing', h: 'harvesting',
  transformation: 'transforming', first_land_based_receiving: 'first_receiver',
  harvest: 'harvesting', packing: 'initial_packing', pack: 'initial_packing', receive: 'receiving',
  ship: 'shipping', transform: 'transforming', cool: 'cooling', creation: 'initial_packing', holding: 'receiving',
  distribute: 'shipping', distribution: 'shipping', di: 'shipping', process: 'transforming', processing: 'transforming',
};
const eventType = (value: string) => {
  const normalized = value.trim().toLowerCase();
  return Object.hasOwn(EVENT_ALIASES, normalized) ? EVENT_ALIASES[normalized] : normalized;
};
const columnName = (value: string) => {
  const normalized = value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');
  const aliases: Record<string, string> = { cte_type: 'event_type', tlc_code: 'lot_number', traceability_lot_code: 'lot_number', lot_code: 'lot_number', tlc: 'lot_number', event_time: 'event_datetime', event_date: 'event_datetime', timestamp: 'event_datetime', cte_date: 'event_datetime' };
  return Object.hasOwn(aliases, normalized) ? aliases[normalized] : normalized;
};

/** Parse complete CSV records before interpreting columns. Reject ambiguous malformed input. */
export function parseCSVRecords(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = '', quoted = false, closed = false;
  const finishCell = () => { row.push(cell.trim()); cell = ''; closed = false; };
  const finishRow = () => { finishCell(); if (row.some(value => value !== '')) rows.push(row); row = []; };
  text = text.replace(/^\uFEFF/, '');
  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    if (quoted) {
      if (char === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; }
        else { quoted = false; closed = true; }
      } else { cell += char; }
    } else if (char === ',') { finishCell(); }
    else if (char === '\r' || char === '\n') {
      finishRow(); if (char === '\r' && text[i + 1] === '\n') i++;
    } else if (char === '"') {
      if (cell || closed) throw new Error('Invalid quote in CSV field.');
      quoted = true;
    } else {
      if (closed) throw new Error('Unexpected text after a quoted CSV field.');
      cell += char;
    }
  }
  if (quoted) throw new Error('Unclosed quoted CSV field.');
  if (cell || row.length || closed) finishRow();
  if (rows.length) {
    const headers = rows[0].map(columnName);
    if (headers.some(header => !header) || new Set(headers).size !== headers.length) throw new Error('CSV headers must be non-empty and unique, including column aliases.');
    for (let i = 1; i < rows.length; i++) {
      if (rows[i].length !== headers.length) throw new Error(`CSV record ${i + 1} has ${rows[i].length} fields; expected ${headers.length}.`);
    }
  }
  return rows;
}

const REQUIRED_COLUMNS = [
  'event_type', 'product_name', 'lot_number',
];
const RECOMMENDED_COLUMNS = [
  'event_datetime', 'product_code', 'quantity', 'unit',
  'origin_facility_code', 'origin_facility_name',
  'destination_facility_code', 'destination_facility_name',
];

interface ValidationIssue {
  severity: 'error' | 'warning';
  row?: number;
  column?: string;
  message: string;
}

export interface ClientValidationResult {
  totalRows: number;
  columnsFound: string[];
  requiredColumnsPresent: string[];
  requiredColumnsMissing: string[];
  recommendedColumnsPresent: string[];
  recommendedColumnsMissing: string[];
  eventTypeCounts: Record<string, number>;
  invalidEventTypes: { row: number; value: string }[];
  issues: ValidationIssue[];
  completenessScore: number; // 0-100
  canProceed: boolean; // true if no errors (warnings ok)
  productNames: string[];
  lotNumbers: string[];
  facilityNames: string[];
  dateRange: { earliest: string | null; latest: string | null };
}

export function validateCSVLocally(text: string): ClientValidationResult {
  const lines = parseCSVRecords(text);
  const result: ClientValidationResult = {
    totalRows: 0, columnsFound: [], requiredColumnsPresent: [], requiredColumnsMissing: [],
    recommendedColumnsPresent: [], recommendedColumnsMissing: [], eventTypeCounts: {},
    invalidEventTypes: [], issues: [], completenessScore: 0, canProceed: true,
    productNames: [], lotNumbers: [], facilityNames: [], dateRange: { earliest: null, latest: null },
  };

  if (lines.length < 2) {
    result.issues.push({ severity: 'error', message: 'File contains no data rows.' });
    result.canProceed = false;
    return result;
  }

  const columns = lines[0].map(columnName);
  result.columnsFound = lines[0];
  const dataLines = lines.slice(1);
  result.totalRows = dataLines.length;

  // Column presence checks
  for (const req of REQUIRED_COLUMNS) {
    if (columns.includes(req)) { result.requiredColumnsPresent.push(req); }
    else { result.requiredColumnsMissing.push(req); result.issues.push({ severity: 'error', column: req, message: `Required FSMA 204 column "${req}" is missing.` }); }
  }
  for (const rec of RECOMMENDED_COLUMNS) {
    if (columns.includes(rec)) { result.recommendedColumnsPresent.push(rec); }
    else { result.recommendedColumnsMissing.push(rec); result.issues.push({ severity: 'warning', column: rec, message: `Recommended column "${rec}" not found. Data may be incomplete for full FSMA 204 compliance.` }); }
  }

  // Index lookups
  const idx = (name: string) => columns.indexOf(name);
  const eventTypeIdx = idx('event_type');
  const productNameIdx = idx('product_name');
  const lotIdx = idx('lot_number');
  const datetimeIdx = idx('event_datetime');
  const origFacIdx = idx('origin_facility_name');
  const destFacIdx = idx('destination_facility_name');
  const qtyIdx = idx('quantity');

  const productSet = new Set<string>();
  const lotSet = new Set<string>();
  const facSet = new Set<string>();
  const dates: string[] = [];
  let emptyRequiredCells = 0;
  let totalRequiredCells = 0;

  for (let i = 0; i < dataLines.length; i++) {
    const cells = dataLines[i];
    const rowNum = i + 2; // 1-indexed, header is row 1

    // Event type validation
    if (eventTypeIdx >= 0) {
      const et = cells[eventTypeIdx]?.trim();
      totalRequiredCells++;
      if (!et) {
        emptyRequiredCells++;
        if (i < 20) result.issues.push({ severity: 'error', row: rowNum, column: 'event_type', message: 'Empty event_type.' });
      } else if (!Object.hasOwn(EVENT_TYPE_LABELS, eventType(et))) {
        result.invalidEventTypes.push({ row: rowNum, value: et });
        if (result.invalidEventTypes.length <= 10) {
          result.issues.push({ severity: 'error', row: rowNum, column: 'event_type', message: `Invalid event type "${et}". Expected a supported event name or code: R, S, T, C, D (shipping), P, H, first_receiver.` });
        }
      } else {
        const label = EVENT_TYPE_LABELS[eventType(et)] || et;
        result.eventTypeCounts[label] = (result.eventTypeCounts[label] || 0) + 1;
      }
    }

    // Product name
    if (productNameIdx >= 0) {
      totalRequiredCells++;
      const val = cells[productNameIdx]?.trim();
      if (!val) { emptyRequiredCells++; }
      else { productSet.add(val); }
    }

    // Lot number
    if (lotIdx >= 0) {
      totalRequiredCells++;
      const val = cells[lotIdx]?.trim();
      if (!val) { emptyRequiredCells++; }
      else { lotSet.add(val); }
    }

    // Datetime
    if (datetimeIdx >= 0) {
      const val = cells[datetimeIdx]?.trim();
      if (val) dates.push(val);
    }

    // Facilities
    if (origFacIdx >= 0) { const v = cells[origFacIdx]?.trim(); if (v) facSet.add(v); }
    if (destFacIdx >= 0) { const v = cells[destFacIdx]?.trim(); if (v) facSet.add(v); }

    // Quantity should be numeric
    if (qtyIdx >= 0) {
      const val = cells[qtyIdx]?.trim();
      if (val && isNaN(Number(val))) {
        if (i < 10) result.issues.push({ severity: 'warning', row: rowNum, column: 'quantity', message: `Non-numeric quantity "${val}".` });
      }
    }
  }

  if (emptyRequiredCells > 0) result.issues.push({ severity: 'error', message: `${emptyRequiredCells} required cells are empty.` });

  // Summary stats
  result.productNames = Array.from(productSet).slice(0, 15);
  result.lotNumbers = Array.from(lotSet).slice(0, 15);
  result.facilityNames = Array.from(facSet).slice(0, 15);

  if (dates.length > 0) {
    dates.sort();
    result.dateRange = { earliest: dates[0], latest: dates[dates.length - 1] };
  }

  // Truncation notices
  if (result.invalidEventTypes.length > 10) {
    result.issues.push({ severity: 'error', message: `${result.invalidEventTypes.length - 10} additional invalid event_type rows not shown.` });
  }

  // Completeness score
  const colScore = (result.requiredColumnsPresent.length / Math.max(REQUIRED_COLUMNS.length, 1)) * 40;
  const recColScore = (result.recommendedColumnsPresent.length / Math.max(RECOMMENDED_COLUMNS.length, 1)) * 20;
  const cellScore = totalRequiredCells > 0 ? ((totalRequiredCells - emptyRequiredCells) / totalRequiredCells) * 30 : 30;
  const eventScore = result.invalidEventTypes.length === 0 ? 10 : Math.max(0, 10 - result.invalidEventTypes.length);
  result.completenessScore = Math.round(colScore + recColScore + cellScore + eventScore);

  // Can proceed if no errors
  result.canProceed = !result.issues.some(i => i.severity === 'error');

  return result;
}

/* ── Client-side CSV preview (no auth required) ── */
export interface CsvPreview {
  totalRows: number;
  columns: string[];
  sampleRows: string[][];
  eventTypeCounts: Record<string, number>;
  productNames: string[];
  lotNumbers: string[];
}

export function parseCSVLocally(text: string): CsvPreview {
  const lines = parseCSVRecords(text);
  if (lines.length < 2) return { totalRows: 0, columns: [], sampleRows: [], eventTypeCounts: {}, productNames: [], lotNumbers: [] };

  const columns = lines[0];
  const dataLines = lines.slice(1);

  const eventTypeIdx = columns.findIndex(c => columnName(c) === 'event_type');
  const productIdx = columns.findIndex(c => columnName(c) === 'product_name');
  const lotIdx = columns.findIndex(c => columnName(c) === 'lot_number');

  const eventTypeCounts: Record<string, number> = Object.create(null);
  const productSet = new Set<string>();
  const lotSet = new Set<string>();

  const sampleRows: string[][] = [];

  for (let i = 0; i < dataLines.length; i++) {
    const cells = dataLines[i];
    if (i < 5) sampleRows.push(cells);

    if (eventTypeIdx >= 0 && cells[eventTypeIdx]) {
      const et = eventType(cells[eventTypeIdx]);
      eventTypeCounts[et] = (eventTypeCounts[et] || 0) + 1;
    }
    if (productIdx >= 0 && cells[productIdx]) productSet.add(cells[productIdx]);
    if (lotIdx >= 0 && cells[lotIdx]) lotSet.add(cells[lotIdx]);
  }

  const mappedCounts: Record<string, number> = Object.create(null);
  for (const [k, v] of Object.entries(eventTypeCounts)) {
    mappedCounts[Object.hasOwn(EVENT_TYPE_LABELS, k) ? EVENT_TYPE_LABELS[k] : k] = v;
  }

  return {
    totalRows: dataLines.length,
    columns,
    sampleRows,
    eventTypeCounts: mappedCounts,
    productNames: Array.from(productSet).slice(0, 10),
    lotNumbers: Array.from(lotSet).slice(0, 10),
  };
}
