/**
 * PCOS Type Definitions
 * 
 * TypeScript types for API responses and component props.
 */

// Compliance Snapshot Types
export interface ComplianceSnapshot {
    id: string;
    project_id: string;
    snapshot_type: 'manual' | 'pre_greenlight' | 'scheduled' | 'post_wrap';
    snapshot_name: string;
    compliance_status: 'compliant' | 'partial' | 'non_compliant' | 'unknown';
    overall_score: number;
    total_rules_evaluated: number;
    rules_passed: number;
    rules_failed: number;
    rules_warning: number;
    category_scores: Record<string, CategoryScore>;
    delta_summary?: DeltaSummary;
    is_attested: boolean;
    attested_at?: string;
    created_at: string;
}

export interface CategoryScore {
    evaluated: number;
    passed: number;
    failed: number;
    warning: number;
    score: number;
}

export interface DeltaSummary {
    new_failures: number;
    resolved_failures: number;
    score_change: number;
}

// Fringe Analysis Types
export interface FringeAnalysis {
    budget_id: string;
    budget_total: number;
    total_labor_cost: number;
    total_union_fringes: number;
    total_statutory_taxes: number;
    total_workers_comp: number;
    total_employer_burden: number;
    budgeted_fringes: number;
    budgeted_fringes_detected: number;
    shortfall: number;
    shortfall_pct: number;
    is_underfunded: boolean;
    warnings: string[];
    breakdown_by_item: FringeBreakdownItem[];
}

export interface FringeBreakdownItem {
    line_item_id: string;
    description: string;
    labor_cost: number;
    union_code: string;
    union_fringe: number;
    statutory: number;
    workers_comp: number;
    total_burden: number;
    burden_pct: number;
}

// Paperwork Status Types
export interface PaperworkStatus {
    project_id: string;
    engagements: EngagementPaperwork[];
    overall_completion_pct: number;
    total_docs: number;
    total_received: number;
    total_pending: number;
}

export interface EngagementPaperwork {
    engagement_id: string;
    person_name: string;
    role_title: string;
    classification: string;
    documents: DocumentStatus[];
    received_count: number;
    pending_count: number;
    completion_pct: number;
}

export interface DocumentStatus {
    requirement_code: string;
    requirement_name: string;
    document_type: string;
    is_required: boolean;
    status: 'pending' | 'requested' | 'received' | 'verified' | 'expired' | 'waived';
    received_at: string | null;
}

// Audit Pack Types
export interface AuditPack {
    generated_at: string;
    pack_version: string;
    project: ProjectSummary;
    compliance_summary?: ComplianceSummary;
    rule_evaluations: RuleEvaluationGroup[];
    findings_by_category: FindingsSummary;
    budget_summary?: BudgetSummary;
    evidence_inventory?: EvidenceItem[];
    attestation?: AttestationInfo;
}

export interface ProjectSummary {
    project_id: string;
    project_name: string;
    project_code: string;
    project_type: string;
    gate_state: string;
    risk_score: number;
    start_date?: string;
    end_date?: string;
}

export interface ComplianceSummary {
    snapshot_id: string;
    snapshot_date: string;
    snapshot_type: string;
    overall_status: string;
    overall_score: number;
    metrics: {
        total_rules_evaluated: number;
        passed: number;
        failed: number;
        warnings: number;
        pass_rate_pct: number;
    };
}

export interface RuleEvaluationGroup {
    category: string;
    evaluations: RuleEvaluation[];
}

export interface RuleEvaluation {
    rule_code: string;
    rule_name: string;
    result: 'pass' | 'fail' | 'warning' | 'skip';
    severity: 'low' | 'medium' | 'high' | 'critical';
    message?: string;
    source_authorities: SourceAuthority[];
}

export interface SourceAuthority {
    type: 'statute' | 'regulation' | 'cba' | 'municipal' | 'internal_policy';
    code?: string;
    section?: string;
    name?: string;
    authority?: string;
}

export interface FindingsSummary {
    total_findings: number;
    by_status: Record<string, number>;
    by_category: Record<string, number>;
    open_critical_count: number;
}

export interface BudgetSummary {
    budget_id: string;
    source_file: string;
    grand_total: number;
    line_item_count: number;
    department_breakdown: Record<string, number>;
}

export interface EvidenceItem {
    evidence_id: string;
    title: string;
    document_type: string;
    file_name: string;
    file_size_bytes: number;
    uploaded_at: string;
    verification_status: string;
}

export interface AttestationInfo {
    is_attested: boolean;
    attested_at?: string;
    attestation_signature_id?: string;
    attestation_notes?: string;
}

// Classification Types
export interface ClassificationResult {
    analysis_id: string;
    engagement_id: string;
    overall_result: 'employee' | 'contractor' | 'uncertain';
    overall_score: number;
    confidence: 'high' | 'medium' | 'low';
    risk_level: 'low' | 'medium' | 'high' | 'critical';
    prong_a: ProngResult;
    prong_b: ProngResult;
    prong_c: ProngResult;
    exemption?: ExemptionResult;
    recommended_action: string;
}

export interface ProngResult {
    passed: boolean;
    score: number;
    factors: Record<string, unknown>;
    reasoning: string;
}

export interface ExemptionResult {
    is_applicable: boolean;
    type?: string;
    reason?: string;
}

// Visa Timeline Types
export interface VisaTimeline {
    person_id: string;
    person_name: string;
    has_visa_record: boolean;
    visa_code?: string;
    visa_name?: string;
    status?: string;
    is_work_authorized?: boolean;
    expiration_date?: string;
    warnings: VisaWarning[];
    warning_count: number;
    has_critical_warning: boolean;
}

export interface VisaWarning {
    type: 'critical' | 'high' | 'medium' | 'info';
    message: string;
    action: string;
}
