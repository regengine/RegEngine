/**
 * Demo data for the FSMA 204 Compliance Control Plane.
 *
 * Used when the backend isn't connected — keeps the UI populated
 * for FDA presentations and demos without requiring live services.
 */

const NOW = new Date();
const hours = (h: number) => new Date(NOW.getTime() - h * 3600_000).toISOString();
const days = (d: number) => new Date(NOW.getTime() - d * 86400_000).toISOString();

// ---------------------------------------------------------------------------
// Exception Cases
// ---------------------------------------------------------------------------

export const DEMO_EXCEPTIONS = {
  tenant_id: 'demo',
  total: 6,
  cases: [
    {
      case_id: 'exc-001',
      severity: 'critical',
      status: 'open',
      linked_event_ids: ['evt-009'],
      owner_user_id: null,
      due_date: hours(18),
      source_supplier: 'Sunshine Packing Co',
      source_facility_reference: '0061414100020',
      rule_category: 'kde_presence',
      recommended_remediation: 'Request the traceability lot code source reference from your immediate supplier',
      resolution_summary: null,
      created_at: hours(6),
      updated_at: hours(6),
    },
    {
      case_id: 'exc-002',
      severity: 'critical',
      status: 'in_review',
      linked_event_ids: ['evt-009'],
      owner_user_id: 'sarah.chen',
      due_date: hours(12),
      source_supplier: 'Sunshine Packing Co',
      source_facility_reference: '0061414100020',
      rule_category: 'kde_presence',
      recommended_remediation: 'Record the business name and location of the entity that shipped this food to you',
      resolution_summary: null,
      created_at: hours(6),
      updated_at: hours(3),
    },
    {
      case_id: 'exc-003',
      severity: 'warning',
      status: 'awaiting_supplier',
      linked_event_ids: ['evt-008'],
      owner_user_id: 'mike.johnson',
      due_date: days(5),
      source_supplier: 'Sunshine Packing Co',
      source_facility_reference: '0061414100020',
      rule_category: 'lot_linkage',
      recommended_remediation: 'Record the GLN or business name of the entity that assigned the traceability lot code',
      resolution_summary: null,
      created_at: days(1),
      updated_at: hours(12),
    },
    {
      case_id: 'exc-004',
      severity: 'warning',
      status: 'open',
      linked_event_ids: ['evt-007'],
      owner_user_id: null,
      due_date: days(10),
      source_supplier: 'Fresh Farms LLC',
      source_facility_reference: '0061414100010',
      rule_category: 'source_reference',
      recommended_remediation: 'Record at least one reference document: bill of lading, invoice, purchase order',
      resolution_summary: null,
      created_at: days(2),
      updated_at: days(2),
    },
    {
      case_id: 'exc-005',
      severity: 'critical',
      status: 'resolved',
      linked_event_ids: ['evt-003'],
      owner_user_id: 'sarah.chen',
      due_date: days(1),
      source_supplier: 'Fresh Farms LLC',
      source_facility_reference: '0061414100010',
      rule_category: 'kde_presence',
      recommended_remediation: 'Record the date of harvest',
      resolution_summary: 'Harvest date confirmed via supplier phone call — 2026-03-20',
      created_at: days(3),
      updated_at: days(1),
    },
    {
      case_id: 'exc-006',
      severity: 'warning',
      status: 'waived',
      linked_event_ids: ['evt-011'],
      owner_user_id: 'mike.johnson',
      due_date: days(7),
      source_supplier: 'Pacific Seafood Co',
      source_facility_reference: '0061414100050',
      rule_category: 'identifier_format',
      recommended_remediation: 'Verify the GLN is exactly 13 digits with a valid GS1 check digit',
      resolution_summary: null,
      created_at: days(4),
      updated_at: days(2),
    },
  ],
};

export const DEMO_BLOCKING_COUNT = { tenant_id: 'demo', blocking_count: 2 };

// ---------------------------------------------------------------------------
// Request Cases
// ---------------------------------------------------------------------------

export const DEMO_REQUEST_CASES = {
  tenant_id: 'demo',
  total: 3,
  cases: [
    {
      request_case_id: 'req-001',
      request_received_at: hours(8),
      response_due_at: hours(-16), // 16 hours remaining
      requesting_party: 'FDA',
      scope_type: 'tlc_trace',
      scope_description: 'Recall drill — Romaine Lettuce from Fresh Farms, lots 2026Q1-001 and 2026Q1-005',
      package_status: 'gap_analysis',
      affected_lots: ['00614141000012ROM2026Q1-001', '00614141000012ROM2026Q1-005'],
      affected_products: ['Romaine Lettuce, Whole Head'],
      affected_facilities: ['Fresh Farms LLC', 'Sunshine Packing Co', 'Metro Distribution Center'],
      total_records: 10,
      gap_count: 2,
      active_exception_count: 2,
      hours_remaining: 16.0,
      is_overdue: false,
      countdown_display: '16h 0m remaining',
    },
    {
      request_case_id: 'req-002',
      request_received_at: days(5),
      response_due_at: days(4),
      requesting_party: 'Internal Drill',
      scope_type: 'product_recall',
      scope_description: 'Quarterly recall readiness drill — Baby Spinach',
      package_status: 'submitted',
      affected_lots: ['00614141000029SPN2026Q1-002'],
      affected_products: ['Baby Spinach, 5oz Clamshell'],
      affected_facilities: ['Fresh Farms LLC', 'Sunshine Packing Co'],
      total_records: 4,
      gap_count: 0,
      active_exception_count: 0,
      hours_remaining: 0,
      is_overdue: false,
      countdown_display: 'Submitted',
    },
    {
      request_case_id: 'req-003',
      request_received_at: days(14),
      response_due_at: days(13),
      requesting_party: 'Customer Audit',
      scope_type: 'facility_audit',
      scope_description: 'Annual audit — Metro Distribution Center traceability records',
      package_status: 'submitted',
      affected_lots: [],
      affected_products: [],
      affected_facilities: ['Metro Distribution Center'],
      total_records: 15,
      gap_count: 0,
      active_exception_count: 0,
      hours_remaining: 0,
      is_overdue: false,
      countdown_display: 'Submitted',
    },
  ],
};

// ---------------------------------------------------------------------------
// Canonical Records
// ---------------------------------------------------------------------------

export const DEMO_RECORDS = {
  tenant_id: 'demo',
  total: 12,
  events: [
    { event_id: 'evt-001', event_type: 'harvesting', traceability_lot_code: '00614141000012ROM2026Q1-001', product_reference: 'Romaine Lettuce, Whole Head', quantity: 2000, unit_of_measure: 'lbs', from_facility_reference: '0061414100010', to_facility_reference: null, event_timestamp: hours(72), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(72) },
    { event_id: 'evt-002', event_type: 'cooling', traceability_lot_code: '00614141000012ROM2026Q1-001', product_reference: 'Romaine Lettuce, Whole Head', quantity: 2000, unit_of_measure: 'lbs', from_facility_reference: '0061414100010', to_facility_reference: null, event_timestamp: hours(70), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(70) },
    { event_id: 'evt-003', event_type: 'initial_packing', traceability_lot_code: '00614141000012ROM2026Q1-001', product_reference: 'Romaine Lettuce, Whole Head, 24ct', quantity: 500, unit_of_measure: 'cases', from_facility_reference: '0061414100020', to_facility_reference: null, event_timestamp: hours(66), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(66) },
    { event_id: 'evt-004', event_type: 'shipping', traceability_lot_code: '00614141000012ROM2026Q1-001', product_reference: 'Romaine Lettuce, Whole Head, 24ct', quantity: 500, unit_of_measure: 'cases', from_facility_reference: '0061414100020', to_facility_reference: '0061414100030', event_timestamp: hours(48), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(48) },
    { event_id: 'evt-005', event_type: 'receiving', traceability_lot_code: '00614141000012ROM2026Q1-001', product_reference: 'Romaine Lettuce, Whole Head, 24ct', quantity: 500, unit_of_measure: 'cases', from_facility_reference: '0061414100030', to_facility_reference: null, event_timestamp: hours(24), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(24) },
    { event_id: 'evt-006', event_type: 'harvesting', traceability_lot_code: '00614141000029SPN2026Q1-002', product_reference: 'Baby Spinach, 5oz Clamshell', quantity: 1500, unit_of_measure: 'lbs', from_facility_reference: '0061414100010', to_facility_reference: null, event_timestamp: hours(60), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(60) },
    { event_id: 'evt-007', event_type: 'initial_packing', traceability_lot_code: '00614141000029SPN2026Q1-002', product_reference: 'Baby Spinach, 5oz Clamshell', quantity: 300, unit_of_measure: 'cases', from_facility_reference: '0061414100020', to_facility_reference: null, event_timestamp: hours(54), source_system: 'webhook_api', status: 'active', confidence_score: 0.9, schema_version: '1.0.0', created_at: hours(54) },
    { event_id: 'evt-008', event_type: 'shipping', traceability_lot_code: '00614141000029SPN2026Q1-002', product_reference: 'Baby Spinach, 5oz Clamshell', quantity: 300, unit_of_measure: 'cases', from_facility_reference: '0061414100020', to_facility_reference: '0061414100030', event_timestamp: hours(36), source_system: 'webhook_api', status: 'active', confidence_score: 0.85, schema_version: '1.0.0', created_at: hours(36) },
    { event_id: 'evt-009', event_type: 'receiving', traceability_lot_code: '00614141000029SPN2026Q1-002', product_reference: 'Baby Spinach, 5oz Clamshell', quantity: 300, unit_of_measure: 'cases', from_facility_reference: '0061414100030', to_facility_reference: null, event_timestamp: hours(12), source_system: 'epcis_api', status: 'active', confidence_score: 0.85, schema_version: '1.0.0', created_at: hours(12) },
    { event_id: 'evt-010', event_type: 'first_land_based_receiving', traceability_lot_code: '00614141000043SAL2026Q1-004', product_reference: 'Atlantic Salmon Fillet, 8oz', quantity: 400, unit_of_measure: 'lbs', from_facility_reference: '0061414100050', to_facility_reference: null, event_timestamp: hours(48), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(48) },
    { event_id: 'evt-011', event_type: 'shipping', traceability_lot_code: '00614141000043SAL2026Q1-004', product_reference: 'Atlantic Salmon Fillet, 8oz', quantity: 400, unit_of_measure: 'lbs', from_facility_reference: '0061414100050', to_facility_reference: '0061414100030', event_timestamp: hours(30), source_system: 'csv_upload', status: 'active', confidence_score: 0.95, schema_version: '1.0.0', created_at: hours(30) },
    { event_id: 'evt-012', event_type: 'transformation', traceability_lot_code: '00614141000012ROM2026Q1-MIX', product_reference: 'Romaine Lettuce, Whole Head', quantity: 250, unit_of_measure: 'cases', from_facility_reference: '0061414100030', to_facility_reference: null, event_timestamp: hours(4), source_system: 'webhook_api', status: 'active', confidence_score: 1.0, schema_version: '1.0.0', created_at: hours(4) },
  ],
};

// ---------------------------------------------------------------------------
// Rules
// ---------------------------------------------------------------------------

export const DEMO_RULES = {
  total: 8,
  rules: [
    { rule_id: 'r-001', title: 'Receiving: TLC Source Reference Required', severity: 'critical', category: 'kde_presence', citation_reference: '21 CFR §1.1345(b)(7)', remediation_suggestion: 'Request the traceability lot code source reference from your immediate supplier' },
    { rule_id: 'r-002', title: 'Receiving: Immediate Previous Source Required', severity: 'critical', category: 'kde_presence', citation_reference: '21 CFR §1.1345(b)(5)', remediation_suggestion: 'Record the business name and location of the entity that shipped this food to you' },
    { rule_id: 'r-003', title: 'Shipping: Ship-From Location Required', severity: 'critical', category: 'kde_presence', citation_reference: '21 CFR §1.1340(b)(3)', remediation_suggestion: 'Record the ship-from location (GLN preferred)' },
    { rule_id: 'r-004', title: 'TLC Must Be Present', severity: 'critical', category: 'kde_presence', citation_reference: '21 CFR §1.1310', remediation_suggestion: 'Assign a traceability lot code to this event' },
    { rule_id: 'r-005', title: 'Product Description Required', severity: 'critical', category: 'kde_presence', citation_reference: '21 CFR §1.1310(b)(1)', remediation_suggestion: 'Record the commodity and variety of the food' },
    { rule_id: 'r-006', title: 'Reference Document Required for All CTEs', severity: 'warning', category: 'source_reference', citation_reference: '21 CFR §1.1310(c)', remediation_suggestion: 'Record at least one reference document' },
    { rule_id: 'r-007', title: 'Shipping: TLC Source Reference Required', severity: 'warning', category: 'lot_linkage', citation_reference: '21 CFR §1.1340(b)(7)', remediation_suggestion: 'Record the GLN or business name of the entity that assigned the TLC' },
    { rule_id: 'r-008', title: 'GLN Format Validation', severity: 'warning', category: 'identifier_format', citation_reference: 'GS1 General Specifications §3.4.2', remediation_suggestion: 'Verify the GLN is exactly 13 digits with a valid GS1 check digit' },
  ],
};

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export const DEMO_ENTITIES = {
  tenant_id: 'demo',
  total: 7,
  entities: [
    { entity_id: 'ent-001', entity_type: 'facility', canonical_name: 'Fresh Farms LLC', gln: '0061414100010', gtin: null, verification_status: 'verified', confidence_score: 1.0 },
    { entity_id: 'ent-002', entity_type: 'facility', canonical_name: 'Sunshine Packing Co', gln: '0061414100020', gtin: null, verification_status: 'verified', confidence_score: 1.0 },
    { entity_id: 'ent-003', entity_type: 'facility', canonical_name: 'Metro Distribution Center', gln: '0061414100030', gtin: null, verification_status: 'verified', confidence_score: 1.0 },
    { entity_id: 'ent-004', entity_type: 'facility', canonical_name: 'Pacific Seafood Co', gln: '0061414100050', gtin: null, verification_status: 'unverified', confidence_score: 0.85 },
    { entity_id: 'ent-005', entity_type: 'product', canonical_name: 'Romaine Lettuce, Whole Head', gln: null, gtin: '00614141000012', verification_status: 'verified', confidence_score: 1.0 },
    { entity_id: 'ent-006', entity_type: 'product', canonical_name: 'Baby Spinach, 5oz Clamshell', gln: null, gtin: '00614141000029', verification_status: 'verified', confidence_score: 1.0 },
    { entity_id: 'ent-007', entity_type: 'firm', canonical_name: 'FedEx Freight', gln: null, gtin: null, verification_status: 'unverified', confidence_score: 0.7 },
  ],
};

export const DEMO_REVIEWS = {
  tenant_id: 'demo',
  total: 2,
  reviews: [
    {
      review_id: 'rev-001',
      entity_a_id: 'ent-004',
      entity_a_name: 'Pacific Seafood Co',
      entity_b_id: 'ent-new',
      entity_b_name: 'Pacific Seafood Company',
      match_type: 'likely',
      match_confidence: 0.92,
      status: 'pending',
      matching_fields: [{ field: 'name', a_value: 'Pacific Seafood Co', b_value: 'Pacific Seafood Company', similarity: 0.92 }],
    },
    {
      review_id: 'rev-002',
      entity_a_id: 'ent-007',
      entity_a_name: 'FedEx Freight',
      entity_b_id: 'ent-new2',
      entity_b_name: 'FedEx Ground',
      match_type: 'ambiguous',
      match_confidence: 0.68,
      status: 'pending',
      matching_fields: [{ field: 'name', a_value: 'FedEx Freight', b_value: 'FedEx Ground', similarity: 0.68 }],
    },
  ],
};
