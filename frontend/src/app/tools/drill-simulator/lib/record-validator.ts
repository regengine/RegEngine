/**
 * FSMA 204 Traceability Record Validator
 * Client-side validation of CSV/XLSX traceability records against FSMA requirements
 */

// ============================================================================
// TYPES & INTERFACES
// ============================================================================

/**
 * The KDE (Key Data Element) fields a ParsedRecord may carry. Mapping from
 * CSV/XLSX headers to these names lives in COLUMN_MAP below; validation code
 * iterates this list to check completeness.
 */
export const PARSED_RECORD_FIELDS = [
  'eventType',
  'product',
  'lotCode',
  'gtin',
  'locationGLN',
  'sourceGLN',
  'destGLN',
  'timestamp',
  'tlcSource',
  'quantity',
  'unitOfMeasure',
  'referenceDocument',
] as const;

export type ParsedRecordField = typeof PARSED_RECORD_FIELDS[number];

const PARSED_RECORD_FIELD_SET: ReadonlySet<string> = new Set(PARSED_RECORD_FIELDS);

export function isParsedRecordField(field: string): field is ParsedRecordField {
  return PARSED_RECORD_FIELD_SET.has(field);
}

/** A KDE field lookup that returns undefined for unknown field names — so
 *  callers iterating arbitrary field strings don't have to widen to `any`. */
export function getRecordField(record: ParsedRecord, field: string): string | undefined {
  return isParsedRecordField(field) ? record[field] : undefined;
}

export type ParsedRecord = Partial<Record<ParsedRecordField, string>> & {
  rowIndex: number;
  raw: Record<string, string>;
};

export interface ValidationFinding {
  severity: 'critical' | 'major' | 'minor';
  category: string;
  message: string;
  citation: string;
  affectedRows: number[];
  recommendation: string;
}

export interface TraceabilityGap {
  gapType: 'missing_cte' | 'missing_kde' | 'broken_chain' | 'time_gap' | 'missing_link';
  description: string;
  citation: string;
  severity: 'critical' | 'major' | 'minor';
  details: string;
}

export interface ValidationResult {
  totalRecords: number;
  parsedRecords: ParsedRecord[];
  cteBreakdown: {
    ship: number;
    receive: number;
    transform: number;
    create: number;
    other: number;
    total: number;
  };
  kdeCompleteness: {
    field: string;
    present: number;
    missing: number;
    percentage: number;
    required: boolean;
    citation: string;
  }[];
  findings: ValidationFinding[];
  gaps: TraceabilityGap[];
  scores: {
    cteCompleteness: number;
    kdeCompleteness: number;
    chainIntegrity: number;
    timelineCoverage: number;
    dataQuality: number;
    overallScore: number;
    grade: string;
  };
  timelineEvents: {
    timestamp: string;
    eventType: string;
    product: string;
    location: string;
    lotCode: string;
    hasGap: boolean;
    gapDescription?: string;
  }[];
  responseMetrics: {
    uploadedAt: Date;
    elapsedSeconds: number;
    withinSLA: boolean;
    slaRating: string;
  };
}

// ============================================================================
// COLUMN MAPPING
// ============================================================================

const COLUMN_MAP: Record<string, keyof ParsedRecord> = {
  'event type': 'eventType',
  'event_type': 'eventType',
  'eventtype': 'eventType',
  'cte': 'eventType',
  'cte_type': 'eventType',
  'activity': 'eventType',
  'activity type': 'eventType',

  'product': 'product',
  'product_name': 'product',
  'product name': 'product',
  'product description': 'product',
  'item': 'product',
  'commodity': 'product',

  'lot': 'lotCode',
  'lot_code': 'lotCode',
  'lot code': 'lotCode',
  'lot number': 'lotCode',
  'lot_number': 'lotCode',
  'batch': 'lotCode',
  'batch number': 'lotCode',
  'batch_number': 'lotCode',

  'gtin': 'gtin',
  'gtin_code': 'gtin',
  'upc': 'gtin',
  'upc_code': 'gtin',
  'barcode': 'gtin',

  'gln': 'locationGLN',
  'location gln': 'locationGLN',
  'location_gln': 'locationGLN',
  'facility gln': 'locationGLN',
  'facility_gln': 'locationGLN',
  'facility': 'locationGLN',

  'source gln': 'sourceGLN',
  'source_gln': 'sourceGLN',
  'ship from gln': 'sourceGLN',
  'ship_from_gln': 'sourceGLN',
  'origin gln': 'sourceGLN',
  'origin_gln': 'sourceGLN',
  'shipper': 'sourceGLN',

  'destination gln': 'destGLN',
  'destination_gln': 'destGLN',
  'dest gln': 'destGLN',
  'dest_gln': 'destGLN',
  'ship to gln': 'destGLN',
  'ship_to_gln': 'destGLN',
  'receiver': 'destGLN',

  'timestamp': 'timestamp',
  'date': 'timestamp',
  'event date': 'timestamp',
  'event_date': 'timestamp',
  'datetime': 'timestamp',
  'date time': 'timestamp',
  'time': 'timestamp',

  'tlc source': 'tlcSource',
  'tlc_source': 'tlcSource',
  'traceability lot code source': 'tlcSource',

  'quantity': 'quantity',
  'qty': 'quantity',
  'amount': 'quantity',
  'quantity received': 'quantity',
  'quantity_received': 'quantity',

  'unit': 'unitOfMeasure',
  'unit of measure': 'unitOfMeasure',
  'unit_of_measure': 'unitOfMeasure',
  'uom': 'unitOfMeasure',
  'units': 'unitOfMeasure',

  'reference': 'referenceDocument',
  'reference document': 'referenceDocument',
  'reference_document': 'referenceDocument',
  'po': 'referenceDocument',
  'po number': 'referenceDocument',
  'po_number': 'referenceDocument',
  'bol': 'referenceDocument',
  'bol number': 'referenceDocument',
  'bol_number': 'referenceDocument',
  'invoice': 'referenceDocument',
};

// Normalize header names for lookup
function normalizeHeader(header: string): string {
  return header.toLowerCase().trim();
}

// ============================================================================
// FSMA 204 REQUIRED KDEs
// ============================================================================

interface KDERequirement {
  field: keyof ParsedRecord;
  citation: string;
}

const REQUIRED_KDES: Record<string, KDERequirement[]> = {
  ship: [
    { field: 'lotCode', citation: '21 CFR 1.1350(a)(1)' },
    { field: 'product', citation: '21 CFR 1.1350(a)(2)' },
    { field: 'sourceGLN', citation: '21 CFR 1.1350(a)(3)' },
    { field: 'destGLN', citation: '21 CFR 1.1350(a)(4)' },
    { field: 'timestamp', citation: '21 CFR 1.1350(a)(5)' },
    { field: 'quantity', citation: '21 CFR 1.1350(a)(6)' },
    { field: 'unitOfMeasure', citation: '21 CFR 1.1350(a)(6)' },
    { field: 'referenceDocument', citation: '21 CFR 1.1350(a)(7)' },
  ],
  receive: [
    { field: 'lotCode', citation: '21 CFR 1.1345(a)(1)' },
    { field: 'product', citation: '21 CFR 1.1345(a)(2)' },
    { field: 'sourceGLN', citation: '21 CFR 1.1345(a)(3)' },
    { field: 'locationGLN', citation: '21 CFR 1.1345(a)(4)' },
    { field: 'timestamp', citation: '21 CFR 1.1345(a)(5)' },
    { field: 'quantity', citation: '21 CFR 1.1345(a)(6)' },
    { field: 'unitOfMeasure', citation: '21 CFR 1.1345(a)(6)' },
    { field: 'referenceDocument', citation: '21 CFR 1.1345(a)(7)' },
  ],
  transform: [
    { field: 'lotCode', citation: '21 CFR 1.1340(a)(1)' },
    { field: 'product', citation: '21 CFR 1.1340(a)(2)' },
    { field: 'locationGLN', citation: '21 CFR 1.1340(a)(3)' },
    { field: 'timestamp', citation: '21 CFR 1.1340(a)(4)' },
    { field: 'quantity', citation: '21 CFR 1.1340(a)(5)' },
    { field: 'unitOfMeasure', citation: '21 CFR 1.1340(a)(5)' },
  ],
  create: [
    { field: 'lotCode', citation: '21 CFR 1.1330(a)(1)' },
    { field: 'product', citation: '21 CFR 1.1330(a)(2)' },
    { field: 'locationGLN', citation: '21 CFR 1.1330(a)(3)' },
    { field: 'timestamp', citation: '21 CFR 1.1330(a)(4)' },
    { field: 'quantity', citation: '21 CFR 1.1330(a)(5)' },
    { field: 'unitOfMeasure', citation: '21 CFR 1.1330(a)(5)' },
  ],
};

// ============================================================================
// PARSING FUNCTIONS
// ============================================================================

export function parseCSV(text: string): ParsedRecord[] {
  const lines = text.split('\n').filter((line) => line.trim());
  if (lines.length < 2) return [];

  const headerLine = lines[0];
  const headers = parseCSVLine(headerLine);
  const normalizedHeaders = headers.map(normalizeHeader);

  const records: ParsedRecord[] = [];

  for (let i = 1; i < lines.length; i++) {
    const values = parseCSVLine(lines[i]);
    const rowData: Record<string, string> = {};

    headers.forEach((header, idx) => {
      rowData[header] = values[idx] || '';
    });

    const record = mapRowToRecord(rowData, normalizedHeaders, headers, i);
    records.push(record);
  }

  return records;
}

function parseCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let i = 0; i < line.length; i++) {
    const char = line[i];
    const nextChar = line[i + 1];

    if (char === '"') {
      if (inQuotes && nextChar === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += char;
    }
  }

  result.push(current.trim());
  return result;
}

function mapRowToRecord(
  rowData: Record<string, string>,
  normalizedHeaders: string[],
  originalHeaders: string[],
  rowIndex: number
): ParsedRecord {
  const record: ParsedRecord = {
    rowIndex,
    raw: rowData,
  };

  const headerMap: Record<string, string> = {};
  normalizedHeaders.forEach((norm, idx) => {
    const mappedField = COLUMN_MAP[norm];
    if (mappedField) {
      headerMap[mappedField] = originalHeaders[idx];
    }
  });

  Object.entries(headerMap).forEach(([field, header]) => {
    const value = rowData[header]?.trim();
    // COLUMN_MAP values are typed as `keyof ParsedRecord`, but headerMap keys
    // lose that narrowing through Object.entries. Re-narrow via the field set.
    if (value && isParsedRecordField(field)) {
      record[field] = value;
    }
  });

  return record;
}

export function parseRecords(rows: Record<string, string>[]): ParsedRecord[] {
  return rows.map((row, idx) => {
    const headers = Object.keys(row);
    const normalizedHeaders = headers.map(normalizeHeader);
    return mapRowToRecord(row, normalizedHeaders, headers, idx + 1);
  });
}

// ============================================================================
// VALIDATION LOGIC
// ============================================================================

export function validateRecords(records: ParsedRecord[], startTime: Date): ValidationResult {
  const findings: ValidationFinding[] = [];
  const gaps: TraceabilityGap[] = [];

  // 1. CTE Breakdown
  const cteBreakdown = {
    ship: 0,
    receive: 0,
    transform: 0,
    create: 0,
    other: 0,
    total: records.length,
  };

  records.forEach((record) => {
    const type = normalizeEventType(record.eventType);
    if (type === 'ship') cteBreakdown.ship++;
    else if (type === 'receive') cteBreakdown.receive++;
    else if (type === 'transform') cteBreakdown.transform++;
    else if (type === 'create') cteBreakdown.create++;
    else cteBreakdown.other++;
  });

  // 2. Missing CTE Types
  const hasMissingCTE = cteBreakdown.ship === 0 || cteBreakdown.receive === 0;
  if (hasMissingCTE) {
    findings.push({
      severity: 'critical',
      category: 'CTE Coverage',
      message: `Missing critical CTE types: ${!cteBreakdown.ship ? 'Ship' : ''} ${!cteBreakdown.receive ? 'Receive' : ''}. Complete traceability requires both ship and receive events.`,
      citation: '21 CFR 1.1342 - CTEs required',
      affectedRows: records
        .filter((r) => !['ship', 'receive'].includes(normalizeEventType(r.eventType)))
        .map((r) => r.rowIndex),
      recommendation:
        'Add ship and receive events to establish complete chain of custody for all lot codes.',
    });
  }

  // 3. KDE Completeness Analysis
  const kdeCompleteness: ValidationResult['kdeCompleteness'] = [];
  const allRequiredFields = new Set<string>();

  Object.values(REQUIRED_KDES).forEach((reqs) => {
    reqs.forEach((req) => {
      allRequiredFields.add(req.field);
    });
  });

  allRequiredFields.forEach((field) => {
    const present = records.filter((r) => {
      const value = getRecordField(r, field);
      return value && value.trim().length > 0;
    }).length;

    const missing = records.length - present;
    const percentage = records.length > 0 ? Math.round((present / records.length) * 100) : 0;

    const citation = Array.from(
      new Set(
        Object.values(REQUIRED_KDES)
          .flat()
          .filter((req) => req.field === field)
          .map((req) => req.citation)
      )
    ).join('; ');

    kdeCompleteness.push({
      field,
      present,
      missing,
      percentage,
      required: true,
      citation,
    });
  });

  // Add KDE findings for low completeness
  kdeCompleteness.forEach((kde) => {
    if (kde.percentage < 100) {
      const affectedRows = records
        .filter((r) => {
          const value = getRecordField(r, kde.field);
          return !value || value.trim().length === 0;
        })
        .map((r) => r.rowIndex);

      findings.push({
        severity: kde.percentage < 50 ? 'critical' : kde.percentage < 80 ? 'major' : 'minor',
        category: 'KDE Completeness',
        message: `${kde.field} missing in ${kde.missing} record(s) (${100 - kde.percentage}% incomplete)`,
        citation: kde.citation,
        affectedRows,
        recommendation: `Ensure all records include the ${kde.field} field as required by FSMA 204.`,
      });
    }
  });

  // 4. Data Quality Checks
  const dataQualityIssues = validateDataQuality(records);
  findings.push(...dataQualityIssues.findings);
  gaps.push(...dataQualityIssues.gaps);

  // 5. Chain Integrity
  const chainIssues = validateChainIntegrity(records);
  findings.push(...chainIssues.findings);
  gaps.push(...chainIssues.gaps);

  // 6. Timeline Coverage
  const timelineIssues = validateTimeline(records);
  findings.push(...timelineIssues.findings);
  gaps.push(...timelineIssues.gaps);

  // 7. Build Timeline Events
  const timelineEvents = buildTimelineEvents(records, timelineIssues.gapsByLot);

  // 8. Calculate Scores
  const scores = calculateScores(
    records,
    cteBreakdown,
    kdeCompleteness,
    chainIssues.chainIntegrityRate,
    timelineIssues.gapRate,
    dataQualityIssues.qualityScore
  );

  // 9. Response Metrics
  const endTime = new Date();
  const elapsedSeconds = (endTime.getTime() - startTime.getTime()) / 1000;
  const slaTarget = 5; // 5 second SLA for client-side validation

  return {
    totalRecords: records.length,
    parsedRecords: records,
    cteBreakdown,
    kdeCompleteness,
    findings: findings.sort((a, b) => {
      const severityOrder = { critical: 0, major: 1, minor: 2 };
      return severityOrder[a.severity] - severityOrder[b.severity];
    }),
    gaps,
    scores,
    timelineEvents,
    responseMetrics: {
      uploadedAt: startTime,
      elapsedSeconds: Math.round(elapsedSeconds * 1000) / 1000,
      withinSLA: elapsedSeconds <= slaTarget,
      slaRating: elapsedSeconds <= slaTarget ? 'Excellent' : 'Standard',
    },
  };
}

// ============================================================================
// VALIDATION HELPERS
// ============================================================================

function normalizeEventType(eventType?: string): string {
  if (!eventType) return 'unknown';
  const normalized = eventType.toLowerCase().trim();

  if (['ship', 'shipped', 'shipment', 'send', 'sent'].includes(normalized)) return 'ship';
  if (['receive', 'received', 'receipt', 'recv', 'incoming'].includes(normalized))
    return 'receive';
  if (['transform', 'transformed', 'processing', 'process', 'manufacture'].includes(normalized))
    return 'transform';
  if (['create', 'created', 'harvest', 'production'].includes(normalized)) return 'create';

  return 'other';
}

function validateDataQuality(records: ParsedRecord[]): {
  findings: ValidationFinding[];
  gaps: TraceabilityGap[];
  qualityScore: number;
} {
  const findings: ValidationFinding[] = [];
  const gaps: TraceabilityGap[] = [];
  let issues = 0;

  // Check for duplicates
  const lotTimestampCombos = new Map<string, number[]>();
  records.forEach((record) => {
    if (record.lotCode && record.timestamp) {
      const key = `${record.lotCode}|${record.timestamp}`;
      if (!lotTimestampCombos.has(key)) {
        lotTimestampCombos.set(key, []);
      }
      lotTimestampCombos.get(key)!.push(record.rowIndex);
    }
  });

  const duplicateRows: number[] = [];
  lotTimestampCombos.forEach((rows) => {
    if (rows.length > 1) {
      duplicateRows.push(...rows);
      issues++;
    }
  });

  if (duplicateRows.length > 0) {
    findings.push({
      severity: 'major',
      category: 'Data Quality',
      message: `${duplicateRows.length} duplicate records detected (same lot code and timestamp)`,
      citation: '21 CFR 1.1300(b)(2)',
      affectedRows: duplicateRows,
      recommendation: 'Remove duplicate records to ensure accurate chain of custody.',
    });
  }

  // Check for invalid timestamps
  const invalidTimestampRows: number[] = [];
  records.forEach((record) => {
    if (record.timestamp && !isValidTimestamp(record.timestamp)) {
      invalidTimestampRows.push(record.rowIndex);
      issues++;
    }
  });

  if (invalidTimestampRows.length > 0) {
    findings.push({
      severity: 'major',
      category: 'Data Quality',
      message: `${invalidTimestampRows.length} records with invalid timestamp format`,
      citation: '21 CFR 1.1301(a)',
      affectedRows: invalidTimestampRows,
      recommendation: 'Use ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ) or MM/DD/YYYY HH:MM:SS',
    });
  }

  // Check for missing lot codes (critical for traceability)
  const missingLotRows = records
    .filter((r) => !r.lotCode || !r.lotCode.trim())
    .map((r) => r.rowIndex);

  if (missingLotRows.length > 0) {
    findings.push({
      severity: 'critical',
      category: 'Data Quality',
      message: `${missingLotRows.length} records missing lot code (cannot establish traceability)`,
      citation: '21 CFR 1.1300(b)(1)',
      affectedRows: missingLotRows,
      recommendation: 'Lot codes are required to establish traceability. All records must include a lot identifier.',
    });
    issues += missingLotRows.length;
  }

  // Check for invalid GLN format (13 digits)
  const invalidGLNRows: number[] = [];
  const GLN_FIELDS = ['locationGLN', 'sourceGLN', 'destGLN'] as const satisfies readonly ParsedRecordField[];
  records.forEach((record) => {
    GLN_FIELDS.forEach((field) => {
      const gln = record[field];
      if (gln && !isValidGLN(gln)) {
        invalidGLNRows.push(record.rowIndex);
      }
    });
  });

  if (invalidGLNRows.length > 0) {
    findings.push({
      severity: 'major',
      category: 'Data Quality',
      message: `${invalidGLNRows.length} records with invalid GLN format (must be 13 digits)`,
      citation: '21 CFR 1.1301(b)',
      affectedRows: [...new Set(invalidGLNRows)],
      recommendation: 'GLNs must be 13-digit Global Location Numbers. Verify against facility registry.',
    });
    issues += invalidGLNRows.length;
  }

  const qualityScore = Math.max(0, 100 - (issues / records.length) * 100);

  return { findings, gaps, qualityScore };
}

function isValidTimestamp(timestamp: string): boolean {
  // Try ISO 8601
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(timestamp)) {
    return !isNaN(Date.parse(timestamp));
  }
  // Try MM/DD/YYYY HH:MM:SS
  if (/^\d{1,2}\/\d{1,2}\/\d{4}\s+\d{1,2}:\d{2}:\d{2}/.test(timestamp)) {
    return !isNaN(Date.parse(timestamp));
  }
  // Try YYYY-MM-DD HH:MM:SS
  if (/^\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2}/.test(timestamp)) {
    return !isNaN(Date.parse(timestamp));
  }
  return false;
}

function isValidGLN(gln: string): boolean {
  const normalized = gln.replace(/\D/g, '');
  return normalized.length === 13 && /^\d+$/.test(normalized);
}

function validateChainIntegrity(records: ParsedRecord[]): {
  findings: ValidationFinding[];
  gaps: TraceabilityGap[];
  chainIntegrityRate: number;
} {
  const findings: ValidationFinding[] = [];
  const gaps: TraceabilityGap[] = [];

  // Map lot codes to their events
  const lotCodeEvents = new Map<string, ParsedRecord[]>();
  records.forEach((record) => {
    if (record.lotCode) {
      if (!lotCodeEvents.has(record.lotCode)) {
        lotCodeEvents.set(record.lotCode, []);
      }
      lotCodeEvents.get(record.lotCode)!.push(record);
    }
  });

  let brokenChains = 0;
  const brokenChainRows: number[] = [];

  lotCodeEvents.forEach((events, lotCode) => {
    const eventTypes = events.map((e) => normalizeEventType(e.eventType));

    // Check for unmatched ship/receive pairs
    const hasShip = eventTypes.includes('ship');
    const hasReceive = eventTypes.includes('receive');

    if (hasShip && !hasReceive) {
      brokenChainRows.push(...events.map((e) => e.rowIndex));
      brokenChains++;

      gaps.push({
        gapType: 'broken_chain',
        description: `Lot ${lotCode} was shipped but not received (missing receive event)`,
        citation: '21 CFR 1.1342(a)',
        severity: 'critical',
        details: `Ship event(s) at ${events.filter((e) => normalizeEventType(e.eventType) === 'ship').map((e) => e.timestamp).join(', ')} have no corresponding receive event.`,
      });
    }

    if (hasReceive && !hasShip) {
      brokenChainRows.push(...events.map((e) => e.rowIndex));
      brokenChains++;

      gaps.push({
        gapType: 'broken_chain',
        description: `Lot ${lotCode} was received without documented shipment (missing ship event)`,
        citation: '21 CFR 1.1342(a)',
        severity: 'major',
        details: `Receive event(s) at ${events.filter((e) => normalizeEventType(e.eventType) === 'receive').map((e) => e.timestamp).join(', ')} have no corresponding ship event.`,
      });
    }
  });

  if (brokenChainRows.length > 0) {
    findings.push({
      severity: 'critical',
      category: 'Chain Integrity',
      message: `${brokenChains} lot code(s) with broken chain of custody (unmatched ship/receive events)`,
      citation: '21 CFR 1.1342(a)',
      affectedRows: brokenChainRows,
      recommendation: 'Ensure every shipped lot has a corresponding receive event and vice versa.',
    });
  }

  const totalLots = lotCodeEvents.size;
  const intactChains = totalLots - brokenChains;
  const chainIntegrityRate = totalLots > 0 ? (intactChains / totalLots) * 100 : 0;

  return { findings, gaps, chainIntegrityRate };
}

function validateTimeline(records: ParsedRecord[]): {
  findings: ValidationFinding[];
  gaps: TraceabilityGap[];
  gapRate: number;
  gapsByLot: Map<string, TraceabilityGap[]>;
} {
  const findings: ValidationFinding[] = [];
  const gaps: TraceabilityGap[] = [];
  const gapsByLot = new Map<string, TraceabilityGap[]>();

  // Group by lot code
  const lotCodeEvents = new Map<string, ParsedRecord[]>();
  records.forEach((record) => {
    if (record.lotCode) {
      if (!lotCodeEvents.has(record.lotCode)) {
        lotCodeEvents.set(record.lotCode, []);
      }
      lotCodeEvents.get(record.lotCode)!.push(record);
    }
  });

  let lotsWithGaps = 0;
  const timeGapRows: number[] = [];
  const GAP_THRESHOLD_HOURS = 24;

  lotCodeEvents.forEach((events, lotCode) => {
    // Sort by timestamp
    const sortedEvents = events
      .filter((e) => e.timestamp && isValidTimestamp(e.timestamp))
      .sort((a, b) => new Date(a.timestamp!).getTime() - new Date(b.timestamp!).getTime());

    if (sortedEvents.length < 2) return;

    let lotHasGap = false;
    const lotGaps: TraceabilityGap[] = [];

    for (let i = 1; i < sortedEvents.length; i++) {
      const prevTime = new Date(sortedEvents[i - 1].timestamp!);
      const currTime = new Date(sortedEvents[i].timestamp!);
      const gapHours = (currTime.getTime() - prevTime.getTime()) / (1000 * 60 * 60);

      if (gapHours > GAP_THRESHOLD_HOURS) {
        lotHasGap = true;
        timeGapRows.push(sortedEvents[i].rowIndex);

        const gap: TraceabilityGap = {
          gapType: 'time_gap',
          description: `Lot ${lotCode}: ${gapHours.toFixed(1)} hour gap between events`,
          citation: '21 CFR 1.1342(b)',
          severity: 'major',
          details: `Gap between ${sortedEvents[i - 1].timestamp} and ${sortedEvents[i].timestamp}`,
        };
        lotGaps.push(gap);
        gaps.push(gap);
      }
    }

    if (lotHasGap) {
      lotsWithGaps++;
      gapsByLot.set(lotCode, lotGaps);
    }
  });

  if (timeGapRows.length > 0) {
    findings.push({
      severity: 'major',
      category: 'Timeline Coverage',
      message: `${lotsWithGaps} lot(s) with time gaps >24 hours between events`,
      citation: '21 CFR 1.1342(b)',
      affectedRows: timeGapRows,
      recommendation:
        'Investigate and document reason for gaps. Consider whether intermediate events should be recorded.',
    });
  }

  const totalLots = lotCodeEvents.size;
  const gapRate = totalLots > 0 ? (lotsWithGaps / totalLots) * 100 : 0;

  return { findings, gaps, gapRate, gapsByLot };
}

function buildTimelineEvents(
  records: ParsedRecord[],
  gapsByLot: Map<string, TraceabilityGap[]>
): ValidationResult['timelineEvents'] {
  const events = records
    .filter((r) => r.timestamp && isValidTimestamp(r.timestamp))
    .map((r) => {
      const gaps = gapsByLot.get(r.lotCode || '') || [];
      const hasGap = gaps.length > 0;

      return {
        timestamp: r.timestamp || '',
        eventType: normalizeEventType(r.eventType),
        product: r.product || 'Unknown',
        location: r.locationGLN || r.sourceGLN || r.destGLN || 'Unknown',
        lotCode: r.lotCode || 'Unknown',
        hasGap,
        gapDescription: gaps.map((g) => g.description).join('; ') || undefined,
      };
    })
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

  return events;
}

function calculateScores(
  records: ParsedRecord[],
  cteBreakdown: ValidationResult['cteBreakdown'],
  kdeCompleteness: ValidationResult['kdeCompleteness'],
  chainIntegrityRate: number,
  gapRate: number,
  qualityScore: number
): ValidationResult['scores'] {
  if (records.length === 0) {
    return {
      cteCompleteness: 0,
      kdeCompleteness: 0,
      chainIntegrity: 0,
      timelineCoverage: 0,
      dataQuality: 0,
      overallScore: 0,
      grade: 'F',
    };
  }

  // CTE Completeness: Do they have required event types?
  // Full credit if they have ship, receive, and transform. Otherwise partial credit.
  let cteScore = 0;
  if (cteBreakdown.ship > 0 && cteBreakdown.receive > 0) cteScore = 100;
  else if (cteBreakdown.ship > 0 || cteBreakdown.receive > 0) cteScore = 50;
  else cteScore = 0;

  // KDE Completeness: Average percentage across all required fields
  const kdeScore =
    kdeCompleteness.length > 0
      ? kdeCompleteness.reduce((sum, k) => sum + k.percentage, 0) / kdeCompleteness.length
      : 0;

  // Chain Integrity: percentage of lots with complete chains
  const chainScore = chainIntegrityRate;

  // Timeline Coverage: inverse of gap rate
  const timelineScore = 100 - gapRate;

  // Data Quality: calculated during validation
  const dataScore = qualityScore;

  // Weighted overall score
  const overallScore =
    cteScore * 0.25 + kdeScore * 0.3 + chainScore * 0.2 + timelineScore * 0.1 + dataScore * 0.15;

  // Grade assignment
  let grade = 'F';
  if (overallScore >= 90) grade = 'A';
  else if (overallScore >= 80) grade = 'B';
  else if (overallScore >= 70) grade = 'C';
  else if (overallScore >= 60) grade = 'D';

  return {
    cteCompleteness: Math.round(cteScore),
    kdeCompleteness: Math.round(kdeScore),
    chainIntegrity: Math.round(chainScore),
    timelineCoverage: Math.round(timelineScore),
    dataQuality: Math.round(dataScore),
    overallScore: Math.round(overallScore),
    grade,
  };
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

export function generateSampleCSV(): string {
  const lines = [
    'Event Type,Product,Lot Code,GTIN,Facility GLN,Source GLN,Destination GLN,Timestamp,Quantity,Unit of Measure,Reference Document',
  ];

  // Harvest/Create
  lines.push(
    'Create,Romaine Lettuce - Head,LOT-2024-001,0123456789012,1234567890128,1234567890128,3456789012345,2024-01-15T08:30:00Z,500,cases,FARM-001-DOC'
  );

  // First transformation
  lines.push(
    'Transform,Romaine Lettuce - Packaged,LOT-2024-001,0123456789029,3456789012345,,3456789012345,2024-01-15T12:00:00Z,480,cases,PKG-2024-001'
  );

  // Ship from packer
  lines.push(
    'Ship,Romaine Lettuce - Packaged,LOT-2024-001,0123456789029,3456789012345,3456789012345,5678901234567,2024-01-16T14:00:00Z,480,cases,BOL-2024-001'
  );

  // Receive at distributor
  lines.push(
    'Receive,Romaine Lettuce - Packaged,LOT-2024-001,0123456789029,5678901234567,3456789012345,5678901234567,2024-01-17T08:30:00Z,475,cases,RCV-2024-001'
  );

  // Ship from distributor
  lines.push(
    'Ship,Romaine Lettuce - Packaged,LOT-2024-001,0123456789029,5678901234567,5678901234567,7890123456789,2024-01-18T10:00:00Z,450,cases,BOL-2024-002'
  );

  // Receive at retailer
  lines.push(
    'Receive,Romaine Lettuce - Packaged,LOT-2024-001,0123456789029,7890123456789,5678901234567,7890123456789,2024-01-18T15:30:00Z,450,cases,RCV-2024-002'
  );

  // Different lot - intentionally missing some KDEs
  lines.push('Create,Spinach - Bulk,LOT-2024-002,,1234567890135,1234567890135,3456789012352,2024-01-15T07:00:00Z,800,cases,');

  lines.push('Ship,Spinach - Bulk,LOT-2024-002,,3456789012352,3456789012352,5678901234574,2024-01-16T16:00:00Z,800,,BOL-2024-003');

  lines.push('Receive,Spinach - Bulk,LOT-2024-002,,5678901234574,3456789012352,5678901234574,2024-01-17T09:00:00Z,800,cases,');

  // Third lot with time gap
  lines.push(
    'Create,Tomatoes - Vine Ripe,LOT-2024-003,0123456789036,1234567890142,1234567890142,3456789012359,2024-01-10T06:00:00Z,1200,cases,FARM-003'
  );

  lines.push(
    'Ship,Tomatoes - Vine Ripe,LOT-2024-003,0123456789036,3456789012359,3456789012359,5678901234581,2024-01-10T14:00:00Z,1200,cases,BOL-2024-004'
  );

  // Large gap here - 3 days
  lines.push(
    'Receive,Tomatoes - Vine Ripe,LOT-2024-003,0123456789036,5678901234581,3456789012359,5678901234581,2024-01-13T10:30:00Z,1150,cases,RCV-2024-003'
  );

  // Fourth lot with unmatched ship (no receive)
  lines.push(
    'Create,Cucumbers,LOT-2024-004,0123456789043,1234567890159,1234567890159,3456789012366,2024-01-14T08:00:00Z,600,cases,FARM-004'
  );

  lines.push(
    'Ship,Cucumbers,LOT-2024-004,0123456789043,3456789012366,3456789012366,5678901234598,2024-01-15T12:00:00Z,600,cases,BOL-2024-005'
  );

  return lines.join('\n');
}

export function getScoreColor(score: number): string {
  if (score >= 90) return 'from-green-500 to-green-600';
  if (score >= 80) return 'from-blue-500 to-blue-600';
  if (score >= 70) return 'from-yellow-500 to-yellow-600';
  if (score >= 60) return 'from-orange-500 to-orange-600';
  return 'from-red-500 to-red-600';
}

export function getSeverityColor(severity: 'critical' | 'major' | 'minor'): string {
  if (severity === 'critical') return 'border-red-500 bg-red-50';
  if (severity === 'major') return 'border-yellow-500 bg-yellow-50';
  return 'border-blue-500 bg-blue-50';
}

export function getSeverityBadgeColor(severity: 'critical' | 'major' | 'minor'): string {
  if (severity === 'critical') return 'bg-red-100 text-red-800';
  if (severity === 'major') return 'bg-yellow-100 text-yellow-800';
  return 'bg-blue-100 text-blue-800';
}
