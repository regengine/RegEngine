/**
 * @regengine/nuclear-sdk
 * TypeScript Type Definitions v1.0.0
 * 
 * NRC-aligned compliance evidence API
 * 
 * CRITICAL: This SDK enforces server-side safety guarantees.
 * - Attribution is server-assigned (client cannot forge)
 * - Safety mode blocks mutations when integrity fails
 * - Classification is permissioned
 * - Retention is policy-enforced
 */

// ============================================================================
// Client Configuration
// ============================================================================

export interface NuclearClientOptions {
    /** API base URL (default: https://api.regengine.co/v1/nuclear) */
    baseUrl?: string;
    /** Request timeout in milliseconds (default: 30000) */
    timeout?: number;
    /** Custom headers to include in all requests */
    headers?: Record<string, string>;
    /** Enable debug logging */
    debug?: boolean;
}

// ============================================================================
// Records
// ============================================================================

export type RecordType =
    | 'CYBER_SECURITY_PLAN'
    | 'CONFIG_ATTESTATION'
    | 'SYSTEM_MODIFICATION'
    | 'QUALITY_ASSURANCE'
    | 'INCIDENT_REPORT'
    | 'DECOMMISSIONING';

export type Classification =
    | 'STANDARD'         // No classification
    | 'PROPRIETARY'      // Company proprietary
    | 'SAFEGUARDS';      // SGI/similar (requires explicit permission)

export interface RegulatoryRef {
    /** CFR citation (e.g., "10-CFR-73.54") */
    cfr: string;
    /** Optional note explaining applicability */
    note?: string;
}

export interface RecordCreateInput {
    /** Facility identifier (e.g., "NPP-UNIT-1") */
    facilityId: string;
    /** Reactor unit identifier */
    reactorId: string;
    /** NRC docket number (e.g., "50-12345") */
    docketNumber: string;
    /** Type of compliance record */
    recordType: RecordType;
    /** Classification level (server-validated) */
    classification: Classification;
    /** Record content (any JSON-serializable object) */
    content: Record<string, any>;
    /** CFR regulatory references */
    regulatoryRefs?: RegulatoryRef[];
    /** Retention policy ID (must exist on server) */
    retentionPolicyId: string;
    /** Optional idempotency key */
    clientRequestId?: string;
}

export interface Attribution {
    /** Principal type: SERVICE, HUMAN, SYSTEM */
    principalType: 'SERVICE' | 'HUMAN' | 'SYSTEM';
    /** Principal identifier (server-assigned) */
    principalId: string;
    /** Request ID for tracing */
    requestId: string;
    /** Source IP address */
    sourceIp: string;
    /** User email (if human principal) */
    userEmail?: string;
}

export interface RetentionInfo {
    /** Retention policy ID */
    policyId: string;
    /** Computed retention deadline (server-assigned) */
    retentionUntil: string; // ISO 8601 timestamp
    /** Whether record is under legal hold */
    legalHold: boolean;
    /** Legal hold IDs if any */
    legalHoldIds?: string[];
}

export type ChainStatus = 'valid' | 'broken' | 'unknown';

export interface IntegrityInfo {
    /** Canonical representation version */
    canonicalVersion: string;
    /** SHA-256 content hash */
    contentHash: string;
    /** SHA-256 signature hash (identity + content binding) */
    signatureHash: string;
    /** Whether record is cryptographically sealed */
    sealed: boolean;
    /** Chain integrity status */
    chainStatus: ChainStatus;
    /** Previous record ID in chain */
    previousRecordId?: string;
}

export interface ComplianceRecord {
    /** Record ID */
    id: string;
    /** Facility identifier */
    facilityId: string;
    /** Reactor identifier */
    reactorId: string;
    /** NRC docket number */
    docketNumber: string;
    /** Record type */
    recordType: RecordType;
    /** Classification level */
    classification: Classification;
    /** Record content */
    content: Record<string, any>;
    /** Creation timestamp (server-assigned) */
    createdAt: string; // ISO 8601
    /** Attribution (server-assigned) */
    createdBy: Attribution;
    /** Regulatory references */
    regulatoryRefs?: RegulatoryRef[];
    /** Retention information */
    retention: RetentionInfo;
    /** Cryptographic integrity */
    integrity: IntegrityInfo;
}

export interface RecordCreateResponse {
    record: ComplianceRecord;
}

export interface RecordGetResponse {
    record: ComplianceRecord;
}

export interface RecordListQuery {
    /** Filter by facility */
    facilityId?: string;
    /** Filter by reactor */
    reactorId?: string;
    /** Filter by record type */
    recordType?: RecordType;
    /** Pagination cursor */
    before?: string;
    /** Page size (max 100) */
    limit?: number;
}

export interface RecordSummary {
    id: string;
    createdAt: string;
    recordType: RecordType;
    classification: Classification;
    integrity: {
        sealed: boolean;
        chainStatus: ChainStatus;
        contentHash: string;
    };
}

export interface RecordListResponse {
    items: RecordSummary[];
    page: {
        nextCursor?: string;
        limit: number;
    };
}

export type VerificationStatus = 'valid' | 'corrupted' | 'unknown';

export interface VerificationResults {
    /** Content hash matches recomputed hash */
    contentHashValid: boolean;
    /** Signature hash matches recomputed signature */
    signatureValid: boolean;
    /** Chain linkage is intact */
    chainIntact: boolean;
    /** Chain head is reachable */
    chainHeadValid: boolean;
}

export interface RecordVerifyResponse {
    recordId: string;
    checkedAt: string; // ISO 8601
    status: VerificationStatus;
    results: VerificationResults;
    /** Reason for failure (if status !== 'valid') */
    reason?: string;
    /** Detailed hash comparison */
    details: {
        expectedContentHash: string;
        computedContentHash: string;
        expectedSignatureHash: string;
        computedSignatureHash: string;
    };
}

export type ExportFormat = 'jsonl' | 'json' | 'csv';

export interface RecordExportRequest {
    facilityId: string;
    reactorId?: string;
    query?: {
        recordType?: RecordType;
        createdAfter?: string; // ISO 8601
        createdBefore?: string; // ISO 8601
    };
    /** Export format */
    format: ExportFormat;
    /** Include verification metadata */
    includeVerification: boolean;
}

export type ExportStatus = 'queued' | 'processing' | 'ready' | 'failed' | 'expired';

export interface RecordExportHandle {
    exportId: string;
    status: ExportStatus;
    format: ExportFormat;
    download: {
        url?: string;
        expiresAt?: string; // ISO 8601
    };
}

// ============================================================================
// Legal Holds
// ============================================================================

export interface HoldCreateInput {
    /** Hold name/description */
    name: string;
    /** Case number or identifier */
    caseNumber: string;
    /** Issuing authority */
    issuingAuthority: string;
    /** Scope of hold */
    scope: {
        facilityId: string;
        reactorId?: string;
    };
}

export interface LegalHold {
    id: string;
    name: string;
    caseNumber: string;
    issuingAuthority: string;
    issuedAt: string; // ISO 8601
    liftedAt?: string; // ISO 8601
    scope: {
        facilityId: string;
        reactorId?: string;
    };
    /** Number of records under this hold */
    recordCount: number;
}

export interface HoldResponse {
    hold: LegalHold;
}

export interface HoldListQuery {
    /** Filter by facility */
    facilityId?: string;
    /** Include lifted holds */
    includeLiftedHolds?: boolean;
}

export interface HoldListResponse {
    items: LegalHold[];
}

// ============================================================================
// Retention Policies
// ============================================================================

export interface RetentionPolicy {
    id: string;
    name: string;
    description: string;
    /** Record types this policy applies to */
    appliesTo: RecordType[];
    /** When deletion is allowed */
    deletionAllowedAfter: 'policy_expiry_only' | 'never';
    /** Whether legal hold overrides deletion */
    legalHoldOverridesDeletion: boolean;
}

export interface RetentionPolicyResponse {
    policy: RetentionPolicy;
}

export interface RetentionPolicyListResponse {
    items: RetentionPolicy[];
}

// ============================================================================
// Errors
// ============================================================================

export type ErrorCode =
    | 'AUTH_REQUIRED'               // 401
    | 'FORBIDDEN_SCOPE'             // 403
    | 'CLASSIFICATION_FORBIDDEN'    // 403
    | 'VALIDATION_ERROR'            // 422
    | 'SAFETY_MODE_ACTIVE'          // 503
    | 'INTEGRITY_VIOLATION'         // 409 or 503
    | 'LEGAL_HOLD_ACTIVE'           // 423
    | 'RETENTION_LOCKED'            // 423
    | 'RATE_LIMITED';               // 429

export interface ApiError {
    error: {
        code: ErrorCode;
        message: string;
        requestId: string;
        status: number;
        details?: Record<string, any>;
    };
}

// ============================================================================
// SDK Client
// ============================================================================

export class NuclearCompliance {
    constructor(apiKeyOrToken: string, options?: NuclearClientOptions);

    records: {
        /**
         * Create a new immutable compliance record.
         * 
         * @throws {ApiError} SAFETY_MODE_ACTIVE if integrity verification failed
         * @throws {ApiError} CLASSIFICATION_FORBIDDEN if classification not permitted
         * @throws {ApiError} VALIDATION_ERROR if input is invalid
         */
        create(input: RecordCreateInput): Promise<RecordCreateResponse>;

        /**
         * Retrieve a compliance record by ID.
         * 
         * @throws {ApiError} FORBIDDEN_SCOPE if record not accessible
         */
        get(recordId: string): Promise<RecordGetResponse>;

        /**
         * List compliance records (paginated).
         */
        list(query?: RecordListQuery): Promise<RecordListResponse>;

        /**
         * Verify cryptographic integrity of a record.
         * 
         * Independent hash recomputation and chain verification.
         * Safe to call anytime - read-only operation.
         */
        verify(recordId: string): Promise<RecordVerifyResponse>;

        /**
         * Request export of compliance records.
         * 
         * Returns export handle. Poll with same exportId to get download URL.
         * 
         * @throws {ApiError} FORBIDDEN_SCOPE if export not permitted
         */
        export(request: RecordExportRequest): Promise<RecordExportHandle>;

        /**
         * Get export status and download URL.
         */
        getExport(exportId: string): Promise<RecordExportHandle>;
    };

    holds: {
        /**
         * Create a legal hold.
         * 
         * Records under hold cannot be deleted even after retention expires.
         */
        create(input: HoldCreateInput): Promise<HoldResponse>;

        /**
         * Add a record to an existing hold.
         * 
         * @throws {ApiError} LEGAL_HOLD_ACTIVE if attempting to mutate held record
         */
        addRecord(holdId: string, recordId: string): Promise<HoldResponse>;

        /**
         * Remove a record from a hold.
         */
        removeRecord(holdId: string, recordId: string): Promise<HoldResponse>;

        /**
         * Get hold details.
         */
        get(holdId: string): Promise<HoldResponse>;

        /**
         * List legal holds.
         */
        list(query?: HoldListQuery): Promise<HoldListResponse>;

        /**
         * Lift a legal hold.
         */
        lift(holdId: string): Promise<HoldResponse>;
    };

    policies: {
        /**
         * List available retention policies.
         */
        listRetentionPolicies(): Promise<RetentionPolicyListResponse>;

        /**
         * Get retention policy details.
         */
        getRetentionPolicy(policyId: string): Promise<RetentionPolicyResponse>;
    };
}

// ============================================================================
// Convenience Types
// ============================================================================

export type { NuclearCompliance as default };
