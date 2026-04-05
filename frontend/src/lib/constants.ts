/**
 * Shared reference data used across signup, onboarding, and compliance flows.
 *
 * Centralised here (#560) so a single edit propagates everywhere — previously
 * these were duplicated in signup/page.tsx, facility/page.tsx, and
 * compliance/profile/page.tsx.
 */

// ── Billing plan labels ──────────────────────────────────────────────────────

export const PLAN_LABELS: Record<string, string> = {
  base: 'Base',
  standard: 'Standard',
  premium: 'Premium',
  growth: 'Growth',
  scale: 'Scale',
};

// ── US states and territories (ISO 3166-2:US) ────────────────────────────────

export const US_STATES: string[] = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
  'DC', 'PR', 'GU', 'VI',
];

// ── Food supply chain roles (FSMA 204 relevant) ──────────────────────────────

export const SUPPLY_CHAIN_ROLES: string[] = [
  'Grower',
  'Packer',
  'Processor',
  'Distributor',
  'Importer',
];

// ── Compliance status labels (used in snapshots and dashboard widgets) ────────

export const COMPLIANCE_STATUSES = {
  COMPLIANT: 'Compliant',
  PARTIAL: 'Partial',
  NON_COMPLIANT: 'Non-Compliant',
  PENDING: 'Pending',
  UNKNOWN: 'Unknown',
} as const;

export type ComplianceStatus = (typeof COMPLIANCE_STATUSES)[keyof typeof COMPLIANCE_STATUSES];

// ── FSMA 204 regulatory constants ─────────────────────────────────────────────

/**
 * FSMA 204 enforcement deadline.
 *
 * Confirmed per FY 2025 Consolidated Appropriations Act, Division A, §775
 * (Pub. L. 118-158, signed March 2025). Congress directed FDA not to enforce
 * the Food Traceability Rule before this date. Last verified: 2026-04-04.
 */
export const FSMA_204_ENFORCEMENT_DATE = '2028-07-20';
export const FSMA_204_ENFORCEMENT_LABEL = 'July 20, 2028';
