import { describe, expect, it } from 'vitest';
import {
  buildSandboxCorrectionWorklist,
  buildSandboxRemediationPlan,
  summarizeSandboxDiagnosis,
} from '@/components/marketing/sandbox-grid/diagnosis';

describe('sandbox diagnosis', () => {
  it('separates blockers, KDE gaps, mapping fixes, lineage issues, and data-quality warnings', () => {
    const diagnosis = summarizeSandboxDiagnosis({
      total_events: 3,
      compliant_events: 1,
      non_compliant_events: 2,
      total_kde_errors: 2,
      total_rule_failures: 2,
      submission_blocked: true,
      blocking_reasons: ['Event 2: missing input lot'],
      duplicate_warnings: ['Duplicate lot code'],
      entity_warnings: ['Possible entity mismatch'],
      normalizations: [{ field: 'cte_type', original: 'ship', normalized: 'shipping', action_type: 'cte_type_normalize' }],
      events: [
        {
          event_index: 0,
          cte_type: 'shipping',
          traceability_lot_code: 'LOT-1',
          product_description: 'Romaine',
          kde_errors: [],
          compliant: true,
          all_results: [],
        },
        {
          event_index: 1,
          cte_type: 'transformation',
          traceability_lot_code: 'LOT-2',
          product_description: 'Salad',
          kde_errors: ["Missing required KDE 'reference_document' for transformation CTE"],
          compliant: false,
          all_results: [
            {
              rule_title: 'Transformation: Input TLCs Required',
              severity: 'critical',
              result: 'fail',
              why_failed: 'Input lots are missing',
              remediation: 'List all input traceability lot codes',
              category: 'lot_linkage',
            },
            {
              rule_title: 'Cold Chain: Temperature Must Be Recorded',
              severity: 'warning',
              result: 'warn',
              why_failed: 'No temperature',
              remediation: 'Record temperature',
              category: 'custom_business_rule',
            },
          ],
        },
        {
          event_index: 2,
          cte_type: 'bad_cte',
          traceability_lot_code: 'LOT-3',
          product_description: 'Spinach',
          kde_errors: ["Invalid CTE type 'bad_cte'. Valid types: harvesting, shipping"],
          compliant: false,
          all_results: [],
        },
      ],
    });

    expect(diagnosis.status).toBe('blocked');
    expect(diagnosis.headline).toMatch(/1 blocker/);
    expect(diagnosis.buckets.find((bucket) => bucket.id === 'blocking')?.count).toBe(1);
    expect(diagnosis.buckets.find((bucket) => bucket.id === 'missing-kdes')?.count).toBe(2);
    expect(diagnosis.buckets.find((bucket) => bucket.id === 'mapping')?.count).toBe(2);
    expect(diagnosis.buckets.find((bucket) => bucket.id === 'lineage')?.count).toBe(1);
    expect(diagnosis.buckets.find((bucket) => bucket.id === 'data-quality')?.count).toBe(3);
  });

  it('gives operational correction steps instead of generic validation advice', () => {
    const plan = buildSandboxRemediationPlan({
      total_events: 1,
      compliant_events: 0,
      non_compliant_events: 1,
      total_kde_errors: 1,
      total_rule_failures: 1,
      submission_blocked: true,
      blocking_reasons: ['Missing BOL'],
      normalizations: [{ field: 'unit_of_measure', original: 'lbs', normalized: 'pounds', action_type: 'uom_normalize' }],
      events: [
        {
          event_index: 0,
          cte_type: 'shipping',
          traceability_lot_code: 'LOT-1',
          product_description: 'Romaine',
          kde_errors: ["Missing required KDE 'reference_document' for shipping CTE"],
          compliant: false,
          all_results: [
            {
              rule_title: 'Temporal order',
              severity: 'critical',
              result: 'fail',
              why_failed: 'Shipping happened before packing',
              remediation: 'Correct timestamps',
              category: 'temporal_ordering',
            },
          ],
        },
      ],
    });

    expect(plan.map((step) => step.title)).toEqual([
      'Normalize the file shape',
      'Fill required KDEs',
      'Repair lot logic',
    ]);
    expect(plan[1].action).toBe('Row 1: fill reference_document');
  });

  it('builds row and cell correction actions with operational targets', () => {
    const worklist = buildSandboxCorrectionWorklist({
      total_events: 2,
      compliant_events: 0,
      non_compliant_events: 2,
      total_kde_errors: 2,
      total_rule_failures: 2,
      submission_blocked: true,
      blocking_reasons: ['Event 1: missing BOL', 'Event 2: missing source lot'],
      events: [
        {
          event_index: 0,
          cte_type: 'shipping',
          traceability_lot_code: 'LOT-1',
          product_description: 'Romaine',
          kde_errors: [
            "Missing required KDE 'reference_document' for shipping CTE",
            "Invalid CTE type 'ship'. Valid types: harvesting, shipping",
          ],
          compliant: false,
          all_results: [
            {
              rule_title: 'Temporal order',
              severity: 'critical',
              result: 'fail',
              why_failed: 'Shipping happened before packing',
              remediation: 'Correct timestamps',
              category: 'temporal_ordering',
            },
          ],
        },
        {
          event_index: 1,
          cte_type: 'transformation',
          traceability_lot_code: 'LOT-2',
          product_description: 'Salad',
          kde_errors: [],
          compliant: false,
          all_results: [
            {
              rule_title: 'Transformation: Input TLCs Required',
              severity: 'critical',
              result: 'fail',
              why_failed: 'Input lots are missing',
              remediation: 'List all input traceability lot codes',
              category: 'lot_linkage',
            },
          ],
        },
      ],
    }, ['cte_type', 'traceability_lot_code', 'bol_number', 'event_timestamp', 'input_tlcs']);

    expect(worklist).toEqual(expect.arrayContaining([
      expect.objectContaining({
        rowNumber: 1,
        actionType: 'edit_cell',
        targetColumn: 'bol_number',
        title: 'Row 1: fill bol_number',
        action: 'Edit bol_number',
      }),
      expect.objectContaining({
        rowNumber: 1,
        actionType: 'edit_cell',
        targetColumn: 'cte_type',
        title: 'Row 1: choose a supported CTE',
      }),
      expect.objectContaining({
        rowNumber: 1,
        actionType: 'edit_cell',
        targetColumn: 'event_timestamp',
        action: 'Edit event_timestamp',
      }),
      expect.objectContaining({
        rowNumber: 2,
        actionType: 'add_row',
        targetColumn: null,
        action: 'Add missing source event row',
      }),
    ]));
  });

  it('includes the correction worklist in the diagnosis summary', () => {
    const diagnosis = summarizeSandboxDiagnosis({
      total_events: 1,
      compliant_events: 0,
      non_compliant_events: 1,
      total_kde_errors: 1,
      total_rule_failures: 0,
      submission_blocked: false,
      blocking_reasons: [],
      events: [
        {
          event_index: 4,
          cte_type: 'receiving',
          traceability_lot_code: 'LOT-99',
          product_description: 'Spinach',
          kde_errors: ["Missing required KDE 'receiving_location' for receiving CTE"],
          compliant: false,
          all_results: [],
        },
      ],
    }, ['received_at']);

    expect(diagnosis.correctionWorklist).toEqual([
      expect.objectContaining({
        rowNumber: 5,
        lotCode: 'LOT-99',
        targetColumn: 'received_at',
        detail: expect.stringContaining('received_at cell'),
      }),
    ]);
  });

  it('keeps clear files in a test-run handoff lane instead of calling them production evidence', () => {
    const diagnosis = summarizeSandboxDiagnosis({
      total_events: 2,
      compliant_events: 2,
      non_compliant_events: 0,
      total_kde_errors: 0,
      total_rule_failures: 0,
      submission_blocked: false,
      blocking_reasons: [],
      events: [
        {
          event_index: 0,
          cte_type: 'harvesting',
          traceability_lot_code: 'LOT-1',
          product_description: 'Romaine',
          kde_errors: [],
          compliant: true,
          all_results: [],
        },
        {
          event_index: 1,
          cte_type: 'shipping',
          traceability_lot_code: 'LOT-1',
          product_description: 'Romaine',
          kde_errors: [],
          compliant: true,
          all_results: [],
        },
      ],
    });
    const plan = buildSandboxRemediationPlan({
      total_events: 2,
      compliant_events: 2,
      non_compliant_events: 0,
      total_kde_errors: 0,
      total_rule_failures: 0,
      submission_blocked: false,
      blocking_reasons: [],
      events: [],
    });

    expect(diagnosis.status).toBe('clear');
    expect(diagnosis.impact).toContain('saved test run');
    expect(diagnosis.impact).toContain('authenticated import mapping');
    expect(`${diagnosis.headline} ${diagnosis.impact}`).not.toMatch(/FDA-ready|submission-ready|production evidence-ready/i);
    expect(plan).toEqual([
      {
        title: 'Save the clean run',
        detail: 'Use this result as the test-run baseline, then convert the detected columns into a production import mapping.',
        action: 'Save as test run',
      },
    ]);
  });
});
