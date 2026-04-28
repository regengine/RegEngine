export type CustomerVisibleStatus =
    | 'ga'
    | 'pilot'
    | 'design_partner'
    | 'export_supported'
    | 'file_import_supported'
    | 'custom_scoped';

export type DeliveryMode =
    | 'native_api'
    | 'webhook'
    | 'csv_sftp_import'
    | 'export_only'
    | 'custom_scoped';

/**
 * Diligence-grade integration type classification.
 * Maps to the taxonomy used in customer procurement diligence:
 *   Native Bidirectional | API-Based Custom | File-Based Import | One-Way Export Adapter
 */
export type IntegrationType =
    | 'native_bidirectional'
    | 'api_based_custom'
    | 'file_based_import'
    | 'one_way_export';

export const INTEGRATION_TYPE_LABELS: Record<IntegrationType, string> = {
    native_bidirectional: 'Native Bidirectional',
    api_based_custom: 'API-Based Custom',
    file_based_import: 'File-Based Import',
    one_way_export: 'One-Way Export Adapter',
};

export const INTEGRATION_TYPE_DESCRIPTIONS: Record<IntegrationType, string> = {
    native_bidirectional: 'Real-time, two-way sync with source system. Write-back supported where applicable.',
    api_based_custom: 'Customer-managed integration via RegEngine REST API. SDK documented, customer builds and maintains.',
    file_based_import: 'Scheduled or manual CSV/XLSX ingestion with field mapping and exception handling.',
    one_way_export: 'RegEngine prepares outbound packages. No write-back to source system.',
};

export const INTEGRATION_TYPE_VERIFY: Record<IntegrationType, string> = {
    native_bidirectional: 'Is write-back supported? What is the sync frequency? What triggers reconciliation?',
    api_based_custom: 'Who builds and maintains this? Is the SDK documented? What is the versioning policy?',
    file_based_import: 'How often? Manual trigger or automated? What is the error handling and rejection flow?',
    one_way_export: 'What is the latency? Is this real-time or batch? What format is produced?',
};

export type CapabilityCategory =
    | 'food_safety_iot'
    | 'erp_warehouse'
    | 'retailer_network'
    | 'developer_api'
    | 'commercial';

export type EvidenceAccess = 'public' | 'request' | 'nda';

export interface CapabilityRegistryEntry {
    id: string;
    name: string;
    category: CapabilityCategory;
    status: CustomerVisibleStatus;
    delivery_mode: DeliveryMode;
    integration_type: IntegrationType;
    customer_copy: string;
    evidence_url: string | null;
    notes?: string;
}

export interface TrustArtifact {
    id: string;
    title: string;
    summary: string;
    access: EvidenceAccess;
    href: string;
}

export interface ArchiveExportJob {
    id: string;
    name: string;
    format: 'FDA Package' | 'GS1 EPCIS 2.0' | 'Audit Bundle';
    cadence: 'Daily' | 'Weekly' | 'Monthly';
    destination: 'Downloadable bundle' | 'Object storage archive';
    status: 'active' | 'paused';
    lastRun: string;
    nextRun: string;
    manifestHash: string;
    tenantId: string;
}

export interface MappingReviewItem {
    id: string;
    source: string;
    sourceField: string;
    mappedField: string | null;
    status: 'mapped' | 'needs_review' | 'missing_required_kde' | 'identity_conflict';
    detail: string;
}

export interface RecallDrillRun {
    id: string;
    scenario: string;
    lots: string[];
    dateRange: string;
    status: 'completed' | 'completed_with_warnings' | 'in_progress';
    elapsed: string;
    artifacts: string[];
    warnings: string[];
}

export interface SupportChannel {
    tier: 'Base' | 'Standard' | 'Premium';
    responseWindow: string;
    escalation: string;
    notes: string;
}

export const STATUS_LABELS: Record<CustomerVisibleStatus, string> = {
    ga: 'GA',
    pilot: 'Pilot',
    design_partner: 'Design Partner',
    export_supported: 'Export Supported',
    file_import_supported: 'File Import Supported',
    custom_scoped: 'Custom Scoped',
};

export const DELIVERY_MODE_LABELS: Record<DeliveryMode, string> = {
    native_api: 'Native API',
    webhook: 'Webhook',
    csv_sftp_import: 'CSV / SFTP Import',
    export_only: 'Export Only',
    custom_scoped: 'Custom Scoped',
};

export const CAPABILITY_REGISTRY: CapabilityRegistryEntry[] = [
    {
        id: 'safetyculture',
        name: 'SafetyCulture',
        category: 'food_safety_iot',
        status: 'pilot',
        delivery_mode: 'custom_scoped',
        integration_type: 'file_based_import',
        customer_copy: 'Inspection and audit data can be mapped into RegEngine during guided onboarding.',
        evidence_url: '/trust',
    },
    {
        id: 'foodready',
        name: 'FoodReady',
        category: 'food_safety_iot',
        status: 'pilot',
        delivery_mode: 'custom_scoped',
        integration_type: 'file_based_import',
        customer_copy: 'HACCP and temperature-monitoring exports can be normalized into FSMA traceability records.',
        evidence_url: '/trust',
    },
    {
        id: 'fooddocs',
        name: 'FoodDocs',
        category: 'food_safety_iot',
        status: 'pilot',
        delivery_mode: 'custom_scoped',
        integration_type: 'file_based_import',
        customer_copy: 'Food safety tasks and records can be ingested through scoped integration work.',
        evidence_url: '/trust',
    },
    {
        id: 'tive',
        name: 'Tive Trackers',
        category: 'food_safety_iot',
        status: 'pilot',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'Cold-chain sensor exports can be imported and linked to traceability lots.',
        evidence_url: '/trust',
    },
    {
        id: 'sensitech',
        name: 'Sensitech TempTale',
        category: 'food_safety_iot',
        status: 'ga',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'Sensitech CSV exports are supported in the data-import flow for temperature-linked events.',
        evidence_url: '/tools/data-import',
    },
    {
        id: 'csv-sftp',
        name: 'CSV / SFTP Import',
        category: 'erp_warehouse',
        status: 'file_import_supported',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'Use CSV or scheduled file delivery for ERP and warehouse data that is not available over API.',
        evidence_url: '/tools/data-import',
    },
    {
        id: 'sap',
        name: 'SAP S/4HANA',
        category: 'erp_warehouse',
        status: 'custom_scoped',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'Implemented through exported traceability extracts and mapping review, not a turnkey native connector.',
        evidence_url: '/trust',
    },
    {
        id: 'netsuite',
        name: 'Oracle NetSuite',
        category: 'erp_warehouse',
        status: 'custom_scoped',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'NetSuite data can be onboarded via CSV or SFTP export with RegEngine mapping review.',
        evidence_url: '/trust',
    },
    {
        id: 'fishbowl',
        name: 'Fishbowl',
        category: 'erp_warehouse',
        status: 'custom_scoped',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'Fishbowl support relies on file exports and customer-specific data mapping.',
        evidence_url: '/trust',
    },
    {
        id: 'quickbooks',
        name: 'QuickBooks',
        category: 'erp_warehouse',
        status: 'custom_scoped',
        delivery_mode: 'csv_sftp_import',
        integration_type: 'file_based_import',
        customer_copy: 'QuickBooks is suitable for transaction export and reconciliation, not as a deep native traceability connector.',
        evidence_url: '/trust',
    },
    {
        id: 'walmart',
        name: 'Walmart',
        category: 'retailer_network',
        status: 'export_supported',
        delivery_mode: 'export_only',
        integration_type: 'one_way_export',
        customer_copy: 'RegEngine can prepare EPCIS-oriented export packages for retailer submission workflows.',
        evidence_url: '/trust',
    },
    {
        id: 'kroger',
        name: 'Kroger',
        category: 'retailer_network',
        status: 'export_supported',
        delivery_mode: 'export_only',
        integration_type: 'one_way_export',
        customer_copy: 'Retailer-specific exports are supported as outbound packages, not a managed portal integration.',
        evidence_url: '/trust',
    },
    {
        id: 'whole-foods',
        name: 'Whole Foods',
        category: 'retailer_network',
        status: 'export_supported',
        delivery_mode: 'export_only',
        integration_type: 'one_way_export',
        customer_copy: 'Use export bundles for retailer readiness and submission support.',
        evidence_url: '/trust',
    },
    {
        id: 'costco',
        name: 'Costco',
        category: 'retailer_network',
        status: 'export_supported',
        delivery_mode: 'export_only',
        integration_type: 'one_way_export',
        customer_copy: 'RegEngine prepares export-ready traceability packages; portal acceptance should be validated directly with the retailer.',
        evidence_url: '/trust',
    },
    {
        id: 'rest-api',
        name: 'REST API',
        category: 'developer_api',
        status: 'ga',
        delivery_mode: 'native_api',
        integration_type: 'api_based_custom',
        customer_copy: 'Core REST endpoints are available for paid tenants and internal integration work.',
        evidence_url: '/docs/api',
    },
    {
        id: 'webhooks',
        name: 'Webhooks',
        category: 'developer_api',
        status: 'ga',
        delivery_mode: 'webhook',
        integration_type: 'native_bidirectional',
        customer_copy: 'Webhook ingestion is available for customer event submission and downstream normalization.',
        evidence_url: '/docs/api',
    },
    {
        id: 'inflow-lab',
        name: 'Inflow Lab',
        category: 'developer_api',
        status: 'pilot',
        delivery_mode: 'webhook',
        integration_type: 'api_based_custom',
        customer_copy: 'RegEngine-owned FSMA 204 simulator for webhook demos, contract tests, and developer validation.',
        evidence_url: '/docs/connectors/inflow-lab',
    },
    {
        id: 'epcis',
        name: 'GS1 EPCIS 2.0',
        category: 'developer_api',
        status: 'ga',
        delivery_mode: 'native_api',
        integration_type: 'native_bidirectional',
        customer_copy: 'JSON-LD EPCIS ingest and export flows are part of the current FSMA-first product surface.',
        evidence_url: '/developers',
    },
    {
        id: 'edi-856',
        name: 'EDI 856',
        category: 'developer_api',
        status: 'pilot',
        delivery_mode: 'custom_scoped',
        integration_type: 'file_based_import',
        customer_copy: 'ASN inbound processing exists, but production rollout should be treated as guided integration work.',
        evidence_url: '/trust',
    },
    {
        id: 'design-partner',
        name: 'Design Partner Program',
        category: 'commercial',
        status: 'design_partner',
        delivery_mode: 'custom_scoped',
        integration_type: 'api_based_custom',
        customer_copy: 'Reserved for customers needing custom integrations, advanced onboarding, or commercial pilot support.',
        evidence_url: '/alpha',
    },
];

export const TRUST_ARTIFACTS: TrustArtifact[] = [
    {
        id: 'security-overview',
        title: 'Security overview',
        summary: 'Tenant isolation, audit integrity, disclosure path, and infrastructure controls.',
        access: 'public',
        href: '/security',
    },
    {
        id: 'architecture-summary',
        title: 'Architecture summary',
        summary: 'FSMA-first topology, service boundaries, and where RegEngine sits in the stack.',
        access: 'public',
        href: '/trust/architecture',
    },
    {
        id: 'retention-export',
        title: 'Retention and export guidance',
        summary: 'Subscription retention, external archive expectations, and recurring export posture.',
        access: 'public',
        href: '/trust/retention',
    },
    {
        id: 'support-model',
        title: 'Support and escalation model',
        summary: 'Response windows, emergency recall escalation path, and enterprise escalation handling.',
        access: 'public',
        href: '/trust/support',
    },
    {
        id: 'subprocessors',
        title: 'Subprocessors and data residency',
        summary: 'US-hosted default posture, vendor categories, and subprocessor details available on request.',
        access: 'request',
        href: '/contact',
    },
    {
        id: 'security-artifacts',
        title: 'Security artifacts package',
        summary: 'Additional materials such as pen-test summaries or diligence documents are available under request or NDA when applicable.',
        access: 'nda',
        href: '/contact',
    },
];

export const SUPPORT_CHANNELS: SupportChannel[] = [
    {
        tier: 'Base',
        responseWindow: 'Within 1 business day',
        escalation: 'Email support with documented emergency recall instructions',
        notes: 'Customers should maintain recurring exports and off-platform archives rather than depend on live support during a regulatory event.',
    },
    {
        tier: 'Standard',
        responseWindow: 'Priority queue with same-business-day target for urgent issues',
        escalation: 'Priority support plus recall escalation guidance in product',
        notes: 'Recommended tier for teams actively rehearsing recall drills and supplier onboarding at scale.',
    },
    {
        tier: 'Premium',
        responseWindow: 'Custom SLA by contract',
        escalation: 'Named contacts, negotiated escalation tree, and security review support',
        notes: 'Exact commitments are contractual, not implied by the public site.',
    },
];

export const ARCHIVE_EXPORT_JOBS: ArchiveExportJob[] = [
    {
        id: 'job_fda_daily',
        name: 'Daily FDA package archive',
        format: 'FDA Package',
        cadence: 'Daily',
        destination: 'Object storage archive',
        status: 'active',
        lastRun: '2026-03-11 06:00 UTC',
        nextRun: '2026-03-12 06:00 UTC',
        manifestHash: 'sha256:2d6f3d0ab2d5c2e1a31ab9814d392a1f',
        tenantId: 'tenant_demo_001',
    },
    {
        id: 'job_epcis_weekly',
        name: 'Weekly EPCIS outbound bundle',
        format: 'GS1 EPCIS 2.0',
        cadence: 'Weekly',
        destination: 'Downloadable bundle',
        status: 'active',
        lastRun: '2026-03-08 08:30 UTC',
        nextRun: '2026-03-15 08:30 UTC',
        manifestHash: 'sha256:e8f6fd0cb8f4ff73c9d79b4123f0e2aa',
        tenantId: 'tenant_demo_001',
    },
    {
        id: 'job_audit_monthly',
        name: 'Monthly audit evidence bundle',
        format: 'Audit Bundle',
        cadence: 'Monthly',
        destination: 'Object storage archive',
        status: 'active',
        lastRun: '2026-03-01 02:00 UTC',
        nextRun: '2026-04-01 02:00 UTC',
        manifestHash: 'sha256:8f4a2b1c7e9d3f50a6b8c2e1d4f7a0b3',
        tenantId: 'tenant_demo_001',
    },
];

export const MAPPING_REVIEW_ITEMS: MappingReviewItem[] = [
    {
        id: 'map_po_001',
        source: 'SAP shipping extract',
        sourceField: 'Outbound Lot',
        mappedField: 'traceability_lot_code',
        status: 'mapped',
        detail: 'Validated against current TLC format policy.',
    },
    {
        id: 'map_vendor_002',
        source: 'NetSuite receipt export',
        sourceField: 'Vendor Location',
        mappedField: null,
        status: 'missing_required_kde',
        detail: 'Missing GLN or facility identifier blocks automated receiving lineage.',
    },
    {
        id: 'map_temp_003',
        source: 'Sensitech CSV',
        sourceField: 'Logger Serial',
        mappedField: 'sensor_reference',
        status: 'mapped',
        detail: 'Mapped for cold-chain evidence linking.',
    },
    {
        id: 'map_shipto_004',
        source: 'CSV supplier upload',
        sourceField: 'Ship To',
        mappedField: 'ship_to_location',
        status: 'identity_conflict',
        detail: 'One supplier string matches two facility records and needs review.',
    },
    {
        id: 'map_case_005',
        source: 'EDI 856 ASN',
        sourceField: 'Case Count',
        mappedField: null,
        status: 'needs_review',
        detail: 'Units are inconsistent across suppliers and need normalization before publish.',
    },
];

export const RECALL_DRILL_RUNS: RecallDrillRun[] = [
    {
        id: 'drill_2026_q1',
        scenario: 'Quarterly retailer trace-back drill',
        lots: ['TOM-0226-F3-001'],
        dateRange: '2026-02-01 to 2026-02-28',
        status: 'completed',
        elapsed: '18m 24s',
        artifacts: ['FDA package', 'EPCIS export', 'drill report'],
        warnings: [],
    },
    {
        id: 'drill_2026_import',
        scenario: 'Imported seafood contamination scenario',
        lots: ['IMP-SHR-0311-07', 'IMP-SHR-0311-08'],
        dateRange: '2026-03-01 to 2026-03-11',
        status: 'completed_with_warnings',
        elapsed: '31m 09s',
        artifacts: ['FDA package', 'supplier contact list', 'warning summary'],
        warnings: ['2 supplier facilities missing GLNs', '1 receiving event required manual identity resolution'],
    },
    {
        id: 'drill_live_24hr',
        scenario: 'Weekend 24-hour response exercise',
        lots: ['LET-0310-WH-21'],
        dateRange: '2026-03-10 to 2026-03-12',
        status: 'in_progress',
        elapsed: '12m 11s',
        artifacts: ['live workspace'],
        warnings: ['Awaiting external archive bundle for final sign-off'],
    },
];

export function getCapabilitiesByCategory(category: CapabilityCategory): CapabilityRegistryEntry[] {
    return CAPABILITY_REGISTRY.filter((capability) => capability.category === category);
}
