import { createHash, randomUUID } from 'crypto';

export interface DevComplianceSnapshot {
    id: string;
    tenant_id: string;
    snapshot_name: string;
    snapshot_reason?: string;
    created_by: string;
    trigger_alert_id?: string;
    is_auto_created: boolean;
    deadline?: string;
    countdown_seconds?: number;
    countdown_display?: string;
    regulatory_citation?: string;
    is_attested: boolean;
    attested_by?: string;
    attested_at?: string;
    attestation_title?: string;
    compliance_status: string;
    compliance_status_emoji: string;
    active_alert_count: number;
    critical_alert_count: number;
    content_hash: string;
    integrity_verified: boolean;
    snapshot_state: string;
    state_emoji: string;
    age_hours: number;
    degradation_reason?: string;
    captured_at: string;
}

interface SnapshotComparisonChange {
    label: string;
    before: string;
    after: string;
    severity: 'critical' | 'high' | 'positive' | 'info';
}

const DEV_ENVS = new Set(['development', 'dev', 'test', 'local']);

const globalForSnapshots = globalThis as typeof globalThis & {
    __regengineDevComplianceSnapshots?: Map<string, DevComplianceSnapshot[]>;
};

const snapshotStore =
    globalForSnapshots.__regengineDevComplianceSnapshots ??
    (globalForSnapshots.__regengineDevComplianceSnapshots = new Map());

export function _resetDevComplianceSnapshotsForTesting(): void {
    snapshotStore.clear();
}

function deepClone<T>(value: T): T {
    return JSON.parse(JSON.stringify(value)) as T;
}

function tenantSnapshots(tenantId: string): DevComplianceSnapshot[] {
    const existing = snapshotStore.get(tenantId);
    if (existing) return existing;
    const created: DevComplianceSnapshot[] = [];
    snapshotStore.set(tenantId, created);
    return created;
}

function findSnapshot(tenantId: string, snapshotId: string): DevComplianceSnapshot | null {
    return tenantSnapshots(tenantId).find((item) => item.id === snapshotId) ?? null;
}

function computeSnapshotHash(snapshot: {
    tenant_id: string;
    snapshot_name: string;
    snapshot_reason?: string;
    created_by: string;
    captured_at: string;
}): string {
    return createHash('sha256')
        .update(JSON.stringify(snapshot))
        .digest('hex');
}

export function allowDevComplianceSnapshotFallback(): boolean {
    const runtimeEnv = (
        process.env.REGENGINE_ENV ||
        process.env.NODE_ENV ||
        ''
    ).trim().toLowerCase();
    return DEV_ENVS.has(runtimeEnv);
}

export function listDevComplianceSnapshots(tenantId: string): DevComplianceSnapshot[] {
    return tenantSnapshots(tenantId)
        .slice()
        .sort((left, right) => right.captured_at.localeCompare(left.captured_at))
        .map(deepClone);
}

export function createDevComplianceSnapshot(params: {
    tenantId: string;
    snapshotName: string;
    snapshotReason?: string;
    createdBy: string;
}): DevComplianceSnapshot {
    const capturedAt = new Date().toISOString();
    const snapshot: DevComplianceSnapshot = {
        id: randomUUID(),
        tenant_id: params.tenantId,
        snapshot_name: params.snapshotName,
        snapshot_reason: params.snapshotReason,
        created_by: params.createdBy,
        is_auto_created: false,
        is_attested: false,
        compliance_status: 'COMPLIANT',
        compliance_status_emoji: '✅',
        active_alert_count: 0,
        critical_alert_count: 0,
        content_hash: computeSnapshotHash({
            tenant_id: params.tenantId,
            snapshot_name: params.snapshotName,
            snapshot_reason: params.snapshotReason,
            created_by: params.createdBy,
            captured_at: capturedAt,
        }),
        integrity_verified: true,
        snapshot_state: 'VALID',
        state_emoji: '🟢',
        age_hours: 0,
        captured_at: capturedAt,
    };

    tenantSnapshots(params.tenantId).unshift(snapshot);
    return deepClone(snapshot);
}

export function verifyDevComplianceSnapshot(params: {
    tenantId: string;
    snapshotId: string;
    verifiedBy: string;
}) {
    const snapshot = findSnapshot(params.tenantId, params.snapshotId);
    if (!snapshot) return null;

    return {
        is_valid: true,
        stored_hash: snapshot.content_hash,
        computed_hash: snapshot.content_hash,
        hash_match: true,
        verified_by: params.verifiedBy,
        verified_at: new Date().toISOString(),
    };
}

export function attestDevComplianceSnapshot(params: {
    tenantId: string;
    snapshotId: string;
    attestedBy: string;
    attestationTitle: string;
}) {
    const snapshot = findSnapshot(params.tenantId, params.snapshotId);
    if (!snapshot) return null;

    snapshot.is_attested = true;
    snapshot.attested_by = params.attestedBy;
    snapshot.attestation_title = params.attestationTitle;
    snapshot.attested_at = new Date().toISOString();
    return deepClone(snapshot);
}

export function refreezeDevComplianceSnapshot(params: {
    tenantId: string;
    snapshotId: string;
    createdBy?: string;
}) {
    const snapshot = findSnapshot(params.tenantId, params.snapshotId);
    if (!snapshot) return null;

    const capturedAt = new Date().toISOString();
    snapshot.created_by = params.createdBy || snapshot.created_by;
    snapshot.snapshot_state = 'VALID';
    snapshot.state_emoji = '🟢';
    snapshot.degradation_reason = undefined;
    snapshot.age_hours = 0;
    snapshot.captured_at = capturedAt;
    snapshot.integrity_verified = true;
    snapshot.content_hash = computeSnapshotHash({
        tenant_id: snapshot.tenant_id,
        snapshot_name: snapshot.snapshot_name,
        snapshot_reason: snapshot.snapshot_reason,
        created_by: snapshot.created_by,
        captured_at: capturedAt,
    });

    return deepClone(snapshot);
}

export function compareDevComplianceSnapshots(params: {
    tenantId: string;
    snapshotA: string;
    snapshotB: string;
}) {
    const left = findSnapshot(params.tenantId, params.snapshotA);
    const right = findSnapshot(params.tenantId, params.snapshotB);
    if (!left || !right) return null;

    const changes: SnapshotComparisonChange[] = [];
    if (left.snapshot_name !== right.snapshot_name) {
        changes.push({
            label: 'Snapshot Name',
            before: left.snapshot_name,
            after: right.snapshot_name,
            severity: 'info',
        });
    }
    if ((left.snapshot_reason || '') !== (right.snapshot_reason || '')) {
        changes.push({
            label: 'Snapshot Reason',
            before: left.snapshot_reason || '-',
            after: right.snapshot_reason || '-',
            severity: 'info',
        });
    }
    if (left.content_hash !== right.content_hash) {
        changes.push({
            label: 'Content Hash',
            before: left.content_hash.slice(0, 12),
            after: right.content_hash.slice(0, 12),
            severity: 'positive',
        });
    }

    return {
        snapshot_a: { name: left.snapshot_name },
        snapshot_b: { name: right.snapshot_name },
        changes,
    };
}

export function exportDevComplianceSnapshot(params: {
    tenantId: string;
    snapshotId: string;
}) {
    const snapshot = findSnapshot(params.tenantId, params.snapshotId);
    if (!snapshot) return null;

    return {
        snapshot_id: snapshot.id,
        tenant_id: snapshot.tenant_id,
        snapshot_name: snapshot.snapshot_name,
        snapshot_reason: snapshot.snapshot_reason,
        created_by: snapshot.created_by,
        captured_at: snapshot.captured_at,
        export_date: new Date().toISOString(),
        content_hash: snapshot.content_hash,
        integrity_verified: snapshot.integrity_verified,
        compliance_status: snapshot.compliance_status,
        compliance_status_emoji: snapshot.compliance_status_emoji,
        active_alert_count: snapshot.active_alert_count,
        critical_alert_count: snapshot.critical_alert_count,
        snapshot_state: snapshot.snapshot_state,
        state_emoji: snapshot.state_emoji,
        is_attested: snapshot.is_attested,
        attested_by: snapshot.attested_by,
        attested_at: snapshot.attested_at,
        attestation_title: snapshot.attestation_title,
    };
}

export function buildDevComplianceSnapshotFdaResponse(params: {
    tenantId: string;
    snapshotId: string;
}) {
    const snapshot = findSnapshot(params.tenantId, params.snapshotId);
    if (!snapshot) return null;

    return {
        text: [
            'FDA Response Template',
            '',
            `Snapshot Name: ${snapshot.snapshot_name}`,
            `Snapshot ID: ${snapshot.id}`,
            `Captured At: ${snapshot.captured_at}`,
            `Prepared By: ${snapshot.created_by}`,
            `Compliance Status: ${snapshot.compliance_status_emoji} ${snapshot.compliance_status}`,
            `Integrity Verified: ${snapshot.integrity_verified ? 'Yes' : 'No'}`,
            `Attested: ${snapshot.is_attested ? 'Yes' : 'No'}`,
            `Reason: ${snapshot.snapshot_reason || 'Not provided'}`,
            '',
            'Summary:',
            'This compliance snapshot captures the point-in-time control state supplied for regulatory review.',
            'No unresolved critical findings were recorded in the local dev/test fallback snapshot payload.',
        ].join('\n'),
    };
}

export function buildDevComplianceSnapshotAuditPack(params: {
    tenantId: string;
    snapshotId: string;
}) {
    const snapshot = findSnapshot(params.tenantId, params.snapshotId);
    if (!snapshot) return null;

    return [
        'RegEngine Zero-Trust Audit Pack',
        '',
        `Snapshot Name: ${snapshot.snapshot_name}`,
        `Snapshot ID: ${snapshot.id}`,
        `Tenant ID: ${snapshot.tenant_id}`,
        `Captured At: ${snapshot.captured_at}`,
        `Created By: ${snapshot.created_by}`,
        `Content Hash: ${snapshot.content_hash}`,
        `Integrity Verified: ${snapshot.integrity_verified ? 'Yes' : 'No'}`,
        `Compliance Status: ${snapshot.compliance_status_emoji} ${snapshot.compliance_status}`,
        `Active Alerts: ${snapshot.active_alert_count}`,
        `Critical Alerts: ${snapshot.critical_alert_count}`,
        `Reason: ${snapshot.snapshot_reason || 'Not provided'}`,
    ].join('\n');
}
