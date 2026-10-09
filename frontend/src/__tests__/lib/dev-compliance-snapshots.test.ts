/**
 * Audit finding: test-mode compliance snapshots returned hardcoded COMPLIANT
 * verdicts, and verifyDevComplianceSnapshot always reported valid without
 * comparing anything. These tests pin the fixed behavior:
 *
 *   1. A fresh fallback snapshot never claims COMPLIANT (no evaluation ran).
 *   2. verify recomputes the content hash and fails closed on tampering.
 *   3. Human-readable artifacts (FDA response, audit pack) are labeled as
 *      dev/test fallback material, never as regulatory evidence.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import {
    _resetDevComplianceSnapshotsForTesting,
    buildDevComplianceSnapshotAuditPack,
    buildDevComplianceSnapshotFdaResponse,
    createDevComplianceSnapshot,
    verifyDevComplianceSnapshot,
} from '@/lib/dev-compliance-snapshots';

const TENANT_ID = '6ba7b810-9dad-41d1-a0b4-00c04fd430c8';

type StoredSnapshot = { id: string; snapshot_name: string };

function liveStore(): Map<string, StoredSnapshot[]> {
    return (globalThis as unknown as Record<string, Map<string, StoredSnapshot[]>>)
        .__regengineDevComplianceSnapshots;
}

function createFallbackSnapshot() {
    return createDevComplianceSnapshot({
        tenantId: TENANT_ID,
        snapshotName: 'Manual Freeze',
        snapshotReason: 'Local dev fallback',
        createdBy: 'tester@regengine.local',
    });
}

beforeEach(() => {
    _resetDevComplianceSnapshotsForTesting();
});

describe('dev compliance snapshots do not fabricate verdicts', () => {
    it('never marks a fresh fallback snapshot COMPLIANT', () => {
        const snapshot = createFallbackSnapshot();
        expect(snapshot.compliance_status).not.toBe('COMPLIANT');
        expect(snapshot.compliance_status).toBe('UNKNOWN');
        expect(snapshot.compliance_status_emoji).not.toBe('✅');
    });

    it('verify passes an untampered snapshot', () => {
        const snapshot = createFallbackSnapshot();
        const result = verifyDevComplianceSnapshot({
            tenantId: TENANT_ID,
            snapshotId: snapshot.id,
            verifiedBy: 'tester@regengine.local',
        });
        expect(result).toMatchObject({ is_valid: true, hash_match: true });
        expect(result?.computed_hash).toBe(result?.stored_hash);
    });

    it('verify fails closed when stored fields are tampered', () => {
        const snapshot = createFallbackSnapshot();
        const stored = liveStore().get(TENANT_ID)?.find((item) => item.id === snapshot.id);
        expect(stored).toBeDefined();
        stored!.snapshot_name = 'Tampered Name';
        const result = verifyDevComplianceSnapshot({
            tenantId: TENANT_ID,
            snapshotId: snapshot.id,
            verifiedBy: 'tester@regengine.local',
        });
        expect(result).toMatchObject({ is_valid: false, hash_match: false });
        expect(result?.computed_hash).not.toBe(result?.stored_hash);
    });

    it('labels the FDA response as dev/test fallback material', () => {
        const snapshot = createFallbackSnapshot();
        const response = buildDevComplianceSnapshotFdaResponse({
            tenantId: TENANT_ID,
            snapshotId: snapshot.id,
        });
        expect(response?.text).toContain('Dev/test fallback');
        expect(response?.text).toContain('Not for regulatory submission');
        expect(response?.text).not.toContain('✅ COMPLIANT');
    });

    it('labels the audit pack as dev/test fallback material', () => {
        const snapshot = createFallbackSnapshot();
        const pack = buildDevComplianceSnapshotAuditPack({
            tenantId: TENANT_ID,
            snapshotId: snapshot.id,
        });
        expect(pack).toContain('Dev/test fallback');
        expect(pack).toContain('Not for regulatory submission');
        expect(pack).not.toContain('✅ COMPLIANT');
    });
});
