// API Types - Core types used across the application

// Health Check
export interface HealthCheckResponse {
    status: string;
    service?: string;
    version?: string;
    timestamp?: string;
}

// API Keys
export interface APIKeyResponse {
    id: string;
    key_id?: string;      // alternative ID field
    key?: string;         // the actual key value (on creation)
    api_key?: string;     // alternative key field name from some endpoints
    name: string;
    description?: string;
    tenant_id?: string;
    created_at: string;
    expires_at?: string;
    is_active?: boolean;
}

// Ingestion
export interface IngestURLRequest {
    url: string;
    source_system?: string;
}

export interface IngestURLResponse {
    event_id: string;
    document_id: string;
    doc_id?: string;      // alternative field name
    document_hash: string;
    tenant_id?: string;
    source_system: string;
    source_url: string;
    raw_s3_path: string;
    normalized_s3_path: string;
    timestamp: string;
    content_sha256: string;
    message?: string;     // status message
    job_id?: string;      // for async processing
}

// Compliance
export interface ComplianceChecklist {
    id: string;
    name: string;
    description?: string;
    industry: string;
    framework?: string;
    version?: string;
    requirements: ComplianceRequirement[];
    items?: ComplianceRequirement[];  // alternative name for requirements
    created_at?: string;
    updated_at?: string;
}

export interface ComplianceRequirement {
    id: string;
    title: string;
    description: string;
    category?: string;
    priority?: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    status?: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLIANT' | 'NON_COMPLIANT';
}

export interface Industry {
    id: string;
    name: string;
    description?: string;
    checklist_count?: number;
}

// Validation
export interface ValidationRequest {
    config: Record<string, unknown>;
    framework?: string;
    strict?: boolean;
}

export interface ValidationResult {
    valid: boolean;
    errors: ValidationError[];
    warnings: ValidationWarning[];
}

export interface ValidationError {
    path: string;
    message: string;
    code?: string;
}

export interface ValidationWarning {
    path: string;
    message: string;
    suggestion?: string;
}

// Opportunities
export interface OpportunityArbitrage {
    id: string;
    j1: string;
    j2: string;
    jurisdiction1?: string;  // alias for j1
    jurisdiction2?: string;  // alias for j2
    concept: string;
    delta: number;
    description?: string;
    detected_at: string;
    status?: 'OPEN' | 'REVIEWED' | 'DISMISSED';
}

export interface ComplianceGap {
    id: string;
    j1?: string;
    j2?: string;
    gap_type: string;
    description: string;
    severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
    recommendation?: string;
    detected_at: string;
    concept?: string;
    example_text?: string;
    citation?: string;
}

// Tenants
export interface TenantResponse {
    id: string;
    tenant_id?: string;   // alternative ID field
    name: string;
    created_at: string;
    status?: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';
    settings?: Record<string, unknown>;
}

// Compliance Alert (used in dashboard widgets)
export interface ComplianceAlert {
    id: string;
    tenant_id: string;
    title: string;
    message: string;
    severity: 'INFO' | 'WARNING' | 'CRITICAL';
    source_type: string;
    source_id: string;
    created_at: string;
    acknowledged?: boolean;
    acknowledged_at?: string;
    acknowledged_by?: string;
}

// Authentication

export interface Role {
    id: string;
    name: string;
    is_system: boolean;
}

export interface User {
    id: string;
    email: string;
    is_sysadmin: boolean;
    status: string;
    role_id?: string;
    role_name?: string;
    created_at?: string;
}

export interface Invite {
    id: string;
    email: string;
    role_id: string;
    status: string;
    created_at: string;
    expires_at: string;
    invite_link?: string;
}

export interface InviteCreate {
    email: string;
    role_id: string;
}

export interface AcceptInviteRequest {
    token: string;
    password: string;
    name: string;
}

export interface FTLCategory {
    id: string;
    name: string;
    ctes: string[];
}

export interface SupplierFacilityCreateRequest {
    name: string;
    street: string;
    city: string;
    state: string;
    postal_code: string;
    fda_registration_number?: string;
    roles: string[];
}

export interface SupplierFacility {
    id: string;
    name: string;
    street: string;
    city: string;
    state: string;
    postal_code: string;
    fda_registration_number?: string | null;
    roles: string[];
}

export interface FacilityFTLScopingRequest {
    category_ids: string[];
}

export interface FacilityFTLScopingResponse {
    facility_id: string;
    categories: FTLCategory[];
    required_ctes: string[];
    source: string;
}

export interface SupplierCTEEventCreateRequest {
    cte_type: string;
    tlc_code: string;
    event_time?: string;
    kde_data: Record<string, unknown>;
    obligation_ids?: string[];
}

export interface SupplierCTEEventResponse {
    event_id: string;
    facility_id: string;
    tlc_code: string;
    cte_type: string;
    payload_sha256: string;
    merkle_hash: string;
    merkle_prev_hash?: string | null;
    merkle_sequence: number;
}

export interface SupplierTLCUpsertRequest {
    facility_id: string;
    tlc_code: string;
    product_description?: string;
    status?: string;
}

export interface SupplierTLC {
    id: string;
    facility_id: string;
    tlc_code: string;
    product_description?: string | null;
    status: string;
    event_count: number;
    created_at: string;
}

export interface SupplierComplianceScore {
    score: number;
    coverage_ratio: number;
    freshness_ratio: number;
    integrity_ratio: number;
    required_ctes: number;
    covered_ctes: number;
    stale_ctes: number;
    missing_ctes: number;
    total_events: number;
    evaluated_at: string;
}

export interface SupplierComplianceGap {
    facility_id: string;
    facility_name: string;
    cte_type?: string | null;
    severity: string;
    issue: string;
    reason: string;
    last_seen?: string | null;
}

export interface SupplierComplianceGapsResponse {
    gaps: SupplierComplianceGap[];
    total: number;
    high: number;
    medium: number;
    low: number;
    evaluated_at: string;
}

export interface SupplierFDAExportRow {
    event_id: string;
    tlc_code: string;
    product_description?: string | null;
    cte_type: string;
    facility_name: string;
    event_time: string;
    quantity: string;
    unit_of_measure: string;
    reference_document: string;
    payload_sha256: string;
    merkle_hash: string;
    merkle_sequence: number;
}

export interface SupplierFDAExportPreviewResponse {
    rows: SupplierFDAExportRow[];
    total_count: number;
}

export interface SupplierDemoResetResponse {
    focus_facility_id: string;
    focus_required_ctes: string[];
    seeded_facilities: number;
    seeded_tlcs: number;
    seeded_events: number;
    dashboard_score: number;
    open_gap_count: number;
}

export interface SupplierFunnelEventRequest {
    event_name: string;
    step?: string;
    status?: string;
    facility_id?: string;
    metadata?: Record<string, unknown>;
}

export interface SupplierFunnelEventResponse {
    event_id: string;
    event_name: string;
    created_at: string;
}

export interface SupplierSocialProofResponse {
    suppliers_onboarded: number;
    facilities_registered: number;
    tlcs_tracked: number;
    cte_events_verified: number;
    fda_exports_generated: number;
    updated_at: string;
}

export interface LoginResponse {
    access_token: string;
    token_type: string;
    refresh_token: string;
    tenant_id?: string;
    user: User;
    available_tenants: Array<{ id: string; name: string; slug: string }>;
}


// Analysis Summary
export interface AnalysisRisk {
    id: string;
    description: string;
    severity: string;
}

export interface AnalysisSummary {
    document_id: string;
    status: string;
    risk_score: number;
    obligations_count: number;
    missing_dates_count: number;
    critical_risks: AnalysisRisk[];
}

// Traceability
export interface TraceabilityEventRequest {
    event_type: string;
    event_date: string;
    tlc: string;
    location_identifier: string;
    quantity?: number;
    uom?: string;
    product_description?: string;
    gtin?: string;
    image_data?: string; // Base64 encoded image
}

export interface TraceabilityEventResponse {
    status: string;
    event_id: string;
    tlc: string;
    message: string;
}
