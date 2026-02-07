/**
 * Energy Vertical Type Definitions
 * 
 * TypeScript interfaces matching backend API contracts.
 * Source: services/energy/app/models.py
 */

// Enums

export enum SystemStatus {
    NOMINAL = 'NOMINAL',
    DEGRADED = 'DEGRADED',
    NON_COMPLIANT = 'NON_COMPLIANT'
}

export enum MismatchSeverity {
    CRITICAL = 'CRITICAL',
    HIGH = 'HIGH',
    MEDIUM = 'MEDIUM',
    LOW = 'LOW'
}

export enum MismatchStatus {
    OPEN = 'OPEN',
    RESOLVED = 'RESOLVED',
    RISK_ACCEPTED = 'RISK_ACCEPTED'
}

export enum SnapshotGenerator {
    SYSTEM_AUTO = 'SYSTEM_AUTO',
    USER_MANUAL = 'USER_MANUAL',
    SCHEDULED = 'SCHEDULED'
}

export enum SnapshotTriggerEvent {
    ASSET_VERIFICATION_CHANGE = 'ASSET_VERIFICATION_CHANGE',
    MISMATCH_CREATED = 'MISMATCH_CREATED',
    MISMATCH_RESOLVED = 'MISMATCH_RESOLVED',
    ESP_TOPOLOGY_CHANGE = 'ESP_TOPOLOGY_CHANGE',
    PATCH_VELOCITY_BREACH = 'PATCH_VELOCITY_BREACH',
    SCHEDULED_DAILY = 'SCHEDULED_DAILY',
    USER_MANUAL_REQUEST = 'USER_MANUAL_REQUEST',
    INITIAL_BASELINE = 'INITIAL_BASELINE'
}

// Core Entities

export interface ComplianceSnapshot {
    id: string;
    created_at: string;
    snapshot_time: string;
    substation_id: string;
    facility_name: string;
    system_status: SystemStatus;
    content_hash: string;
    signature_hash: string;
    previous_snapshot_id: string | null;
    generated_by: SnapshotGenerator;
    trigger_event: SnapshotTriggerEvent | null;
    regulatory_version: string;
    // Optional heavy fields (loaded conditionally)
    asset_states?: Record<string, any>;
    esp_config?: Record<string, any>;
    patch_metrics?: Record<string, any>;
}

export interface Mismatch {
    id: string;
    created_at: string;
    substation_id: string;
    severity: MismatchSeverity;
    description: string;
    detected_snapshot_id: string;
    status: MismatchStatus;
    resolved_at: string | null;
    resolved_snapshot_id: string | null;
    resolution_type: string | null;
    resolution_justification: string | null;
    attester_name: string | null;
    attester_role: string | null;
}

// Verification

export interface VerificationCheck {
    name: string;
    valid: boolean;
    stored?: string;
    previous_snapshot_id?: string;
}

export interface VerificationReport {
    snapshot_id: string;
    snapshot_time: string;
    status: 'valid' | 'corrupted' | 'no_snapshots';
    checks: VerificationCheck[];
}

// API Response Types

export interface SnapshotListResponse {
    snapshots: ComplianceSnapshot[];
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
}

export interface MismatchListResponse {
    mismatches: Mismatch[];
    total: number;
}

// Request Types

export interface ResolveMismatchRequest {
    resolution_type: 'RESOLVED' | 'RISK_ACCEPTED';
    justification: string;
    attestation: {
        attester_name: string;
        attester_role: string;
        signature: string;
    };
}

// Filter Types

export interface SnapshotFilters {
    substation_id: string;
    from_time?: string;
    to_time?: string;
    status?: SystemStatus;
    limit?: number;
    offset?: number;
}

export interface MismatchFilters {
    substation_id: string;
    status?: MismatchStatus;
    severity?: MismatchSeverity;
}
