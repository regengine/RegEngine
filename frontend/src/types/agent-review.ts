export type AgentArtifactType =
    | 'field_mapping_suggestion'
    | 'identity_match_suggestion'
    | 'validation_explanation'
    | 'review_routing_suggestion'
    | 'export_readiness_summary';

export type AgentReviewStatus = 'pending' | 'accepted' | 'rejected' | 'needs_more_evidence';
export type AgentReviewDecisionStatus = Exclude<AgentReviewStatus, 'pending'>;

export interface AgentRiskBreakdown {
    score: number;
    uncapped_score: number;
    confidence_risk: number;
    review_risk: number;
    artifact_type_risk: number;
    evidence_gap_risk: number;
    rule_gap_risk: number;
}

export interface AgentComplianceGap {
    code: string;
    message: string;
}

export interface AgentReviewItem {
    artifact_id: string;
    tenant_id: string;
    artifact_type: AgentArtifactType;
    created_at: string;
    agent_name: string;
    suggestion: string;
    confidence: number;
    requires_human_review: boolean;
    review_id: string | null;
    review_status: AgentReviewStatus;
    reviewed_by: string | null;
    reviewed_at: string | null;
    risk_score: number;
    risk_breakdown: AgentRiskBreakdown;
    compliance_gap_count: number;
    compliance_gaps: AgentComplianceGap[];
    ingestion_run_id: string | null;
    ingestion_run_status: string | null;
    source_system: string | null;
    source_file_name: string | null;
    advisory_receipt_id: string | null;
    advisory_receipt_state: string | null;
    receipt_hash: string | null;
    chain_valid: boolean | null;
    evidence_ids: string[];
    canonical_event_ids: string[];
    source_hashes: string[];
    rule_id: string | null;
    rule_version: number | null;
}

export interface AgentReviewListResponse {
    items: AgentReviewItem[];
    total: number;
    limit: number;
    offset: number;
}

export interface AgentReviewDecisionRequest {
    status: AgentReviewDecisionStatus;
    review_reason?: string;
    operator_notes?: string;
    decision_metadata?: Record<string, unknown>;
}

export interface AgentReviewDecisionInput extends AgentReviewDecisionRequest {
    artifactId: string;
}

export interface AgentReviewDecisionResponse {
    artifact_id: string;
    review_id: string | null;
    review_status: AgentReviewDecisionStatus;
    reviewed_by: string | null;
    reviewed_at: string | null;
}

export interface AgentReviewItemsQuery {
    tenantId?: string;
    ingestionRunId?: string;
    reviewStatus?: AgentReviewStatus | 'all';
    artifactType?: AgentArtifactType | 'all';
    createdAfter?: string;
    createdBefore?: string;
    limit?: number;
    offset?: number;
}
