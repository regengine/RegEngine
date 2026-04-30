export type SandboxRuleResultForDiagnosis = {
  rule_title: string;
  severity: string;
  result: string;
  why_failed: string | null;
  remediation: string | null;
  category: string;
};

export type SandboxEventForDiagnosis = {
  event_index: number;
  cte_type: string;
  traceability_lot_code: string;
  product_description: string;
  kde_errors: string[];
  compliant: boolean;
  blocking_defects?: SandboxRuleResultForDiagnosis[];
  all_results?: SandboxRuleResultForDiagnosis[];
};

export type SandboxResultForDiagnosis = {
  total_events: number;
  compliant_events: number;
  non_compliant_events: number;
  total_kde_errors: number;
  total_rule_failures: number;
  submission_blocked: boolean;
  blocking_reasons: string[];
  duplicate_warnings?: string[];
  entity_warnings?: string[];
  normalizations?: { field: string; original: string; normalized: string; action_type: string }[];
  events: SandboxEventForDiagnosis[];
};

export type DiagnosisBucket = {
  id: string;
  label: string;
  count: number;
  description: string;
  tone: 'danger' | 'warning' | 'info' | 'success';
};

export type RemediationStep = {
  title: string;
  detail: string;
  action: string;
};

export type CorrectionActionType = 'edit_cell' | 'add_row' | 'mass_fill' | 'review_row';

export type CorrectionWorklistItem = {
  id: string;
  priority: 'blocker' | 'fix' | 'warning';
  actionType: CorrectionActionType;
  rowIndex: number | null;
  rowNumber: number | null;
  targetColumn: string | null;
  lotCode: string;
  cteType: string;
  title: string;
  detail: string;
  action: string;
};

const RELATIONAL_CATEGORIES = new Set(['temporal_ordering', 'quantity_consistency', 'lot_linkage']);
const KDE_ERROR_RE = /Missing required KDE '([^']+)'/;
const INVALID_CTE_RE = /Invalid CTE type/i;

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
  cte_type: ['cte_type', 'cte', 'event_type'],
  timestamp: ['timestamp', 'event_timestamp', 'event_time', 'date'],
};

function ruleIssues(result: SandboxResultForDiagnosis) {
  return result.events.flatMap((event) =>
    (event.all_results || []).filter((rule) => rule.result === 'fail' || rule.result === 'warn'),
  );
}

function normalizeHeader(value: string) {
  return value.toLowerCase().trim().replace(/\s+/g, '_');
}

function findCsvColumn(fieldName: string, csvHeaders: string[] = []) {
  const normalizedField = normalizeHeader(fieldName);
  const normalizedHeaders = csvHeaders.map(normalizeHeader);

  const directIndex = normalizedHeaders.indexOf(normalizedField);
  if (directIndex >= 0) return csvHeaders[directIndex];

  for (const alias of KDE_TO_CSV_COLUMNS[normalizedField] || []) {
    const aliasIndex = normalizedHeaders.indexOf(alias);
    if (aliasIndex >= 0) return csvHeaders[aliasIndex];
  }

  return fieldName;
}

function rowLabel(rowIndex: number) {
  return `Row ${rowIndex + 1}`;
}

function eventContext(event: SandboxEventForDiagnosis) {
  const lotCode = event.traceability_lot_code || 'missing lot code';
  const cteType = event.cte_type || 'unknown CTE';
  const product = event.product_description ? `, ${event.product_description}` : '';
  return `${cteType} for ${lotCode}${product}`;
}

function makeItem(
  event: SandboxEventForDiagnosis,
  indexSuffix: string,
  values: Omit<CorrectionWorklistItem, 'id' | 'rowIndex' | 'rowNumber' | 'lotCode' | 'cteType'>,
): CorrectionWorklistItem {
  return {
    id: `row-${event.event_index}-${indexSuffix}`,
    rowIndex: event.event_index,
    rowNumber: event.event_index + 1,
    lotCode: event.traceability_lot_code || 'Unassigned lot',
    cteType: event.cte_type || 'unknown',
    ...values,
  };
}

function ruleTargetColumn(rule: SandboxRuleResultForDiagnosis, headers: string[]) {
  if (rule.category === 'temporal_ordering') return findCsvColumn('timestamp', headers);
  if (rule.category === 'quantity_consistency') return findCsvColumn('quantity', headers);
  if (rule.category === 'lot_linkage' && /identity/i.test(rule.rule_title)) return findCsvColumn('product_description', headers);
  if (rule.category === 'lot_linkage') return findCsvColumn('input_traceability_lot_codes', headers);
  if (rule.category === 'custom_business_rule' && /temperature/i.test(rule.rule_title)) return findCsvColumn('temperature', headers);
  return findCsvColumn('cte_type', headers);
}

function ruleActionType(rule: SandboxRuleResultForDiagnosis): CorrectionActionType {
  if (rule.category === 'lot_linkage' && /input|source|previous|upstream/i.test(`${rule.rule_title} ${rule.why_failed || ''}`)) {
    return 'add_row';
  }
  if (rule.category === 'lot_linkage' && /identity/i.test(rule.rule_title)) {
    return 'mass_fill';
  }
  return 'edit_cell';
}

function ruleActionLabel(actionType: CorrectionActionType, targetColumn: string | null) {
  if (actionType === 'add_row') return 'Add missing source event row';
  if (actionType === 'mass_fill') return `Standardize ${targetColumn || 'matching cells'}`;
  if (actionType === 'review_row') return 'Review row';
  return `Edit ${targetColumn || 'cell'}`;
}

export function buildSandboxCorrectionWorklist(
  result: SandboxResultForDiagnosis,
  csvHeaders: string[] = [],
): CorrectionWorklistItem[] {
  const items: CorrectionWorklistItem[] = [];

  for (const event of result.events) {
    event.kde_errors.forEach((error, errorIndex) => {
      const missingKde = error.match(KDE_ERROR_RE)?.[1];
      if (missingKde) {
        const targetColumn = findCsvColumn(missingKde, csvHeaders);
        items.push(makeItem(event, `kde-${errorIndex}`, {
          priority: 'fix',
          actionType: 'edit_cell',
          targetColumn,
          title: `${rowLabel(event.event_index)}: fill ${targetColumn}`,
          detail: `${eventContext(event)} is missing required data in the ${targetColumn} cell.`,
          action: `Edit ${targetColumn}`,
        }));
        return;
      }

      if (INVALID_CTE_RE.test(error)) {
        const targetColumn = findCsvColumn('cte_type', csvHeaders);
        items.push(makeItem(event, `cte-${errorIndex}`, {
          priority: 'blocker',
          actionType: 'edit_cell',
          targetColumn,
          title: `${rowLabel(event.event_index)}: choose a supported CTE`,
          detail: `${event.cte_type || 'This CTE'} is not recognized. Change the CTE cell to the closest operational event type.`,
          action: `Edit ${targetColumn}`,
        }));
      }
    });

    (event.all_results || [])
      .filter((rule) => rule.result === 'fail' || rule.result === 'warn')
      .forEach((rule, ruleIndex) => {
        const actionType = ruleActionType(rule);
        const targetColumn = actionType === 'add_row' ? null : ruleTargetColumn(rule, csvHeaders);
        const priority = rule.severity === 'critical' || rule.result === 'fail' ? 'blocker' : 'warning';
        items.push(makeItem(event, `rule-${ruleIndex}`, {
          priority,
          actionType,
          targetColumn,
          title: `${rowLabel(event.event_index)}: ${ruleActionLabel(actionType, targetColumn)}`,
          detail: rule.why_failed || rule.remediation || `${eventContext(event)} needs row-level correction.`,
          action: ruleActionLabel(actionType, targetColumn),
        }));
      });
  }

  return items.slice(0, 12);
}

export function summarizeSandboxDiagnosis(result: SandboxResultForDiagnosis, csvHeaders: string[] = []) {
  const issues = ruleIssues(result);
  const mappingHints = result.normalizations?.length || 0;
  const invalidCteErrors = result.events.reduce(
    (sum, event) => sum + event.kde_errors.filter((error) => error.toLowerCase().includes('invalid cte type')).length,
    0,
  );
  const relationalIssues = issues.filter((rule) => RELATIONAL_CATEGORIES.has(rule.category)).length;
  const duplicateWarnings = result.duplicate_warnings?.length || 0;
  const entityWarnings = result.entity_warnings?.length || 0;
  const customWarnings = issues.filter((rule) => rule.category === 'custom_business_rule').length;
  const blockingCount = result.blocking_reasons.length;

  const buckets: DiagnosisBucket[] = [
    {
      id: 'blocking',
      label: 'Import blockers',
      count: blockingCount,
      description: 'Rows that need a concrete edit or added source event before handoff.',
      tone: 'danger',
    },
    {
      id: 'missing-kdes',
      label: 'Missing KDEs',
      count: result.total_kde_errors,
      description: 'Blank row cells that need the required CTE data filled in.',
      tone: result.total_kde_errors > 0 ? 'warning' : 'success',
    },
    {
      id: 'mapping',
      label: 'Mapping fixes',
      count: mappingHints + invalidCteErrors,
      description: 'Headers, CTE names, or coded values that should be normalized in the file.',
      tone: 'info',
    },
    {
      id: 'lineage',
      label: 'Lineage integrity',
      count: relationalIssues,
      description: 'Rows where lot links, quantities, product identity, or timing do not reconcile.',
      tone: relationalIssues > 0 ? 'danger' : 'success',
    },
    {
      id: 'data-quality',
      label: 'Data quality warnings',
      count: duplicateWarnings + entityWarnings + customWarnings,
      description: 'Duplicate rows, name drift, or operational checks that should be cleaned up.',
      tone: 'warning',
    },
  ];

  const totalIssues = result.total_kde_errors + result.total_rule_failures + duplicateWarnings + entityWarnings;
  const correctionWorklist = buildSandboxCorrectionWorklist(result, csvHeaders);
  const status = result.submission_blocked
    ? 'blocked'
    : result.non_compliant_events > 0
      ? 'needs_work'
      : 'clear';

  const headline = status === 'blocked'
    ? `${blockingCount} blocker${blockingCount === 1 ? '' : 's'} before this can become an import mapping`
    : status === 'needs_work'
      ? `${result.non_compliant_events} event${result.non_compliant_events === 1 ? '' : 's'} need correction before handoff`
      : 'Sandbox checks clear for this file';

  const impact = status === 'clear'
    ? 'The file can move into a saved test run, then into an authenticated import mapping.'
    : 'RegEngine can diagnose the file now, but only corrected and authenticated records should feed production evidence.';

  return {
    status,
    headline,
    impact,
    totalIssues,
    buckets,
    correctionWorklist,
  };
}

export function buildSandboxRemediationPlan(result: SandboxResultForDiagnosis, csvHeaders: string[] = []): RemediationStep[] {
  const diagnosis = summarizeSandboxDiagnosis(result, csvHeaders);
  const steps: RemediationStep[] = [];
  const firstCellFix = diagnosis.correctionWorklist.find((item) => item.actionType === 'edit_cell');
  const firstRowFix = diagnosis.correctionWorklist.find((item) => item.actionType === 'add_row');

  const mappingBucket = diagnosis.buckets.find((bucket) => bucket.id === 'mapping');
  if ((mappingBucket?.count || 0) > 0) {
    steps.push({
      title: 'Normalize the file shape',
      detail: 'Accept detected header, CTE type, and unit mappings or rename the source CSV columns to canonical fields.',
      action: firstCellFix?.targetColumn ? `Start with ${firstCellFix.targetColumn}` : 'Review normalization suggestions',
    });
  }

  if (result.total_kde_errors > 0) {
    steps.push({
      title: 'Fill required KDEs',
      detail: 'Open the spreadsheet fixer and complete the highlighted cells for the affected CTE rows.',
      action: firstCellFix ? `${firstCellFix.title}` : 'Fix highlighted KDE cells',
    });
  }

  const lineageBucket = diagnosis.buckets.find((bucket) => bucket.id === 'lineage');
  if ((lineageBucket?.count || 0) > 0) {
    steps.push({
      title: 'Repair lot logic',
      detail: 'Correct event timestamps, quantities, product identity, or add missing event rows so each lot reconciles end to end.',
      action: firstRowFix ? firstRowFix.action : 'Trace and repair lots',
    });
  }

  const dataQualityBucket = diagnosis.buckets.find((bucket) => bucket.id === 'data-quality');
  if ((dataQualityBucket?.count || 0) > 0) {
    steps.push({
      title: 'Standardize audit context',
      detail: 'Resolve duplicate rows, supplier/location name drift, and optional business-rule warnings before onboarding the feed.',
      action: 'Clean repeated values',
    });
  }

  if (steps.length === 0) {
    steps.push({
      title: 'Save the clean run',
      detail: 'Use this result as the test-run baseline, then convert the detected columns into a production import mapping.',
      action: 'Save as test run',
    });
  }

  return steps.slice(0, 4);
}
