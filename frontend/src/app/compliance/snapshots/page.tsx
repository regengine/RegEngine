'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState, useEffect } from 'react';
import { useTenant } from '@/lib/tenant-context';
import { useAuth } from '@/lib/auth-context';
import { generateBrandedPDF, type PDFSection } from '@/lib/pdf-report';
import {
    Camera,
    Shield,
    ShieldCheck,
    CheckCircle2,
    XCircle,
    Download,
    Check,
    Circle,
    ClipboardList,
    GitCompare,
    FileCheck,
    Plus,
    Hash,
    User,
    Calendar,
    AlertTriangle,
    BookOpen,
    PenLine,
    Timer
} from 'lucide-react';

import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { Field } from '@/components/ui/field';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';

interface Snapshot {
    id: string;
    tenant_id: string;
    snapshot_name: string;
    snapshot_reason?: string;
    created_by: string;
    // Trigger + deadline
    trigger_alert_id?: string;
    is_auto_created: boolean;
    deadline?: string;
    countdown_seconds?: number;
    countdown_display?: string;
    regulatory_citation?: string;
    // Attestation
    is_attested: boolean;
    attested_by?: string;
    attested_at?: string;
    attestation_title?: string;
    // Status
    compliance_status: string;
    compliance_status_emoji: string;
    active_alert_count: number;
    critical_alert_count: number;
    content_hash: string;
    integrity_verified: boolean;
    // Degradation
    snapshot_state: string;  // VALID, STALE, INVALID
    state_emoji: string;     // 🟢, 🟠, 🔴
    age_hours: number;
    degradation_reason?: string;
    captured_at: string;
}


interface VerifyResult {
    is_valid: boolean;
    stored_hash: string;
    computed_hash: string;
    hash_match: boolean;
    verified_by: string;
    verified_at: string;
}

interface DiffChange {
    label: string;
    before: string;
    after: string;
    diff?: string;
    severity: 'critical' | 'high' | 'positive' | 'info';
}

interface DiffResult {
    snapshot_a?: { name: string };
    snapshot_b?: { name: string };
    changes?: DiffChange[];
}

async function loadSnapshotsForTenant(tenantId: string): Promise<{
    items: Snapshot[];
    error: string | null;
}> {
    try {
        const response = await fetchWithCsrf(`/api/v1/compliance/snapshots/${tenantId}`);
        if (response.ok) {
            const data = await response.json();
            if (Array.isArray(data)) {
                return { items: data, error: null };
            }
            if (data && Array.isArray(data.items)) {
                return { items: data.items, error: null };
            }
            return { items: [], error: null };
        }

        return {
            items: [],
            error: `Snapshot API returned ${response.status}`,
        };
    } catch {
        return {
            items: [],
            error: 'Unable to reach snapshot service. Check your connection.',
        };
    }
}

export default function SnapshotsPage() {
    const { tenantId } = useTenant();
    const { user } = useAuth();
    const userEmail = user?.email || `admin@tenant-${tenantId.slice(0, 8)}.regengine.co`;
    const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
    const [loading, setLoading] = useState(true);
    const [fetchError, setFetchError] = useState<string | null>(null);
    const [creating, setCreating] = useState(false);
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
    const [showVerifyModal, setShowVerifyModal] = useState(false);
    const [showAttestModal, setShowAttestModal] = useState(false);
    const [attestingSnapshotId, setAttestingSnapshotId] = useState<string | null>(null);

    // FDA Response modal
    const [showFdaModal, setShowFdaModal] = useState(false);
    const [fdaResponse, setFdaResponse] = useState<string>('');

    // Diff modal
    const [showDiffModal, setShowDiffModal] = useState(false);
    const [selectedForDiff, setSelectedForDiff] = useState<string[]>([]);
    const [diffResult, setDiffResult] = useState<DiffResult | null>(null);

    // Form state
    const [snapshotName, setSnapshotName] = useState('');
    const [snapshotReason, setSnapshotReason] = useState('');
    const [attestName, setAttestName] = useState('');
    const [attestTitle, setAttestTitle] = useState('');

    useEffect(() => {
        let disposed = false;

        const syncSnapshots = async () => {
            const result = await loadSnapshotsForTenant(tenantId);
            if (disposed) return;

            setFetchError(result.error);
            setSnapshots(result.items);
            setLoading(false);
        };

        void syncSnapshots();
        // Refresh countdown every 30 seconds
        const interval = setInterval(() => {
            void syncSnapshots();
        }, 30000);

        return () => {
            disposed = true;
            clearInterval(interval);
        };
    }, [tenantId]);

    const refreshSnapshots = async () => {
        const result = await loadSnapshotsForTenant(tenantId);
        setFetchError(result.error);
        setSnapshots(result.items);
        setLoading(false);
    };

    const createSnapshot = async () => {
        if (!snapshotName.trim()) return;

        setCreating(true);
        try {
            const response = await fetchWithCsrf(`/api/v1/compliance/snapshots/${tenantId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    snapshot_name: snapshotName,
                    snapshot_reason: snapshotReason || undefined,
                    created_by: userEmail,
                }),
            });

            if (response.ok) {
                await refreshSnapshots();
                setShowCreateModal(false);
                setSnapshotName('');
                setSnapshotReason('');
            }
        } catch (error) {
            console.error('Failed to create snapshot:', error);
        } finally {
            setCreating(false);
        }
    };

    const attestSnapshot = async () => {
        if (!attestingSnapshotId || !attestName.trim() || !attestTitle.trim()) return;

        try {
            const response = await fetchWithCsrf(`/api/v1/compliance/snapshots/${tenantId}/${attestingSnapshotId}/attest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    attested_by: attestName,
                    attestation_title: attestTitle,
                }),
            });

            if (response.ok) {
                await refreshSnapshots();
                setShowAttestModal(false);
                setAttestingSnapshotId(null);
                setAttestName('');
                setAttestTitle('');
            }
        } catch (error) {
            console.error('Failed to attest snapshot:', error);
        }
    };

    const verifySnapshot = async (snapshotId: string) => {
        try {
            const response = await fetchWithCsrf(
                `/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/verify?verified_by=${encodeURIComponent(userEmail)}`
            );

            if (response.ok) {
                const result = await response.json();
                setVerifyResult(result);
                setShowVerifyModal(true);
                await refreshSnapshots();
            }
        } catch (error) {
            console.error('Failed to verify snapshot:', error);
        }
    };

    const downloadAuditPack = async (snapshotId: string, snapshotName: string) => {
        try {
            const response = await fetchWithCsrf(
                `/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/audit-pack`
            );

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `ZeroTrust-AuditPack-${snapshotName.replace(/\s+/g, '-')}.zip`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
            } else {
                console.error('Failed to download audit pack');
            }
        } catch (error) {
            console.error('Failed to download audit pack:', error);
        }
    };

    const exportSnapshot = async (snapshotId: string, snapshotName: string) => {
        try {
            const response = await fetchWithCsrf(
                `/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/export`
            );

            if (response.ok) {
                const data = await response.json();

                const isRecord = (value: unknown): value is Record<string, unknown> =>
                    typeof value === 'object' && value !== null && !Array.isArray(value);

                const toText = (value: unknown): string => {
                    if (value === null || value === undefined) return '-';
                    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
                    if (typeof value === 'number') return Number.isFinite(value) ? String(value) : '-';
                    if (typeof value === 'string') return value;
                    if (Array.isArray(value)) return `${value.length} items`;
                    if (isRecord(value)) return 'Object';
                    return String(value);
                };

                const sections: PDFSection[] = [
                    { type: 'heading', text: 'Snapshot Metadata', level: 2 },
                    {
                        type: 'keyValue',
                        pairs: [
                            { key: 'Snapshot Name', value: snapshotName },
                            { key: 'Snapshot ID', value: snapshotId },
                            { key: 'Tenant ID', value: tenantId },
                            {
                                key: 'Export Timestamp',
                                value: data?.export_date ? String(data.export_date) : new Date().toISOString(),
                            },
                            {
                                key: 'Content Hash',
                                value: data?.content_hash ? String(data.content_hash) : 'N/A',
                            },
                            {
                                key: 'Integrity Verified',
                                value: data?.integrity_verified ? 'Yes' : 'No',
                                status: data?.integrity_verified ? 'success' : 'danger',
                            },
                        ],
                    },
                ];

                if (isRecord(data)) {
                    const primitivePairs = Object.entries(data)
                        .filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value))
                        .slice(0, 12)
                        .map(([key, value]) => ({
                            key: key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
                            value: toText(value),
                        }));

                    if (primitivePairs.length > 0) {
                        sections.push({ type: 'divider' });
                        sections.push({ type: 'heading', text: 'Export Fields', level: 2 });
                        sections.push({ type: 'keyValue', pairs: primitivePairs });
                    }

                    const arrayEntries = Object.entries(data).filter(([, value]) => Array.isArray(value));
                    arrayEntries.slice(0, 2).forEach(([key, value]) => {
                        const rows = (value as unknown[]).filter(isRecord);
                        if (rows.length === 0) return;

                        const columnSet = new Set<string>();
                        rows.slice(0, 40).forEach((row) => {
                            Object.keys(row).forEach((column) => columnSet.add(column));
                        });
                        const headers = Array.from(columnSet).slice(0, 6);
                        if (headers.length === 0) return;

                        sections.push({ type: 'divider' });
                        sections.push({
                            type: 'heading',
                            text: key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
                            level: 2,
                        });
                        sections.push({
                            type: 'table',
                            headers: headers.map((header) =>
                                header.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
                            ),
                            rows: rows.slice(0, 40).map((row) => headers.map((header) => toText(row[header]))),
                        });
                    });
                }

                await generateBrandedPDF({
                    title: 'Compliance Snapshot Artifact',
                    subtitle: snapshotName,
                    reportType: 'RegEngine Compliance Snapshots',
                    sections,
                    footer: {
                        left: 'Confidential',
                        right: 'regengine.co',
                        legalLine: 'Compliance Snapshot Artifact',
                    },
                    filename: `compliance-snapshot-${snapshotName.replace(/\s+/g, '-')}`,
                });
            }
        } catch (error) {
            console.error('Failed to export snapshot:', error);
        }
    };

    const refreezeSnapshot = async (snapshotId: string) => {
        try {
            const response = await fetchWithCsrf(
                `/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/refreeze`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ created_by: userEmail }),
                }
            );

            if (response.ok) {
                await refreshSnapshots();
            }
        } catch (error) {
            console.error('Failed to refreeze snapshot:', error);
        }
    };

    const getFdaResponse = async (snapshotId: string) => {
        try {
            const response = await fetchWithCsrf(
                `/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/fda-response`
            );

            if (response.ok) {
                const data = await response.json();
                setFdaResponse(data.text);
                setShowFdaModal(true);
            }
        } catch (error) {
            console.error('Failed to get FDA response:', error);
        }
    };

    const toggleDiffSelection = (snapshotId: string) => {
        if (selectedForDiff.includes(snapshotId)) {
            setSelectedForDiff(selectedForDiff.filter(id => id !== snapshotId));
        } else if (selectedForDiff.length < 2) {
            setSelectedForDiff([...selectedForDiff, snapshotId]);
        }
    };

    const compareSnapshots = async () => {
        if (selectedForDiff.length !== 2) return;

        try {
            const response = await fetchWithCsrf(
                `/api/v1/compliance/snapshots/${tenantId}/diff?snapshot_a=${selectedForDiff[0]}&snapshot_b=${selectedForDiff[1]}`
            );

            if (response.ok) {
                const data = await response.json();
                setDiffResult(data);
                setShowDiffModal(true);
            }
        } catch (error) {
            console.error('Failed to compare snapshots:', error);
        }
    };

    const copyToClipboard = async (text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            alert('Copied to clipboard!');
        } catch (error) {
            console.error('Failed to copy:', error);
        }
    };

    const formatDate = (dateStr: string) => {

        return new Date(dateStr).toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    };

    // Compliance status and degradation state both travel as a StatusBadge:
    // icon + label, never colour alone. The API-supplied emoji stays inside the
    // label so the recorded string is unchanged.
    const getComplianceState = (status: string): ComplianceState => {
        switch (status) {
            case 'COMPLIANT': return 'compliant';
            case 'AT_RISK': return 'at-risk';
            case 'NON_COMPLIANT': return 'non-compliant';
            default: return 'unknown';
        }
    };

    const getSnapshotState = (state: string): ComplianceState => {
        switch (state) {
            case 'VALID': return 'compliant';
            case 'STALE': return 'at-risk';
            default: return 'non-compliant';
        }
    };

    const getCountdownColor = (seconds?: number) => {
        if (!seconds) return 'text-re-text-tertiary';
        if (seconds <= 0) return 'text-re-danger animate-pulse motion-reduce:animate-none';
        if (seconds < 3600) return 'text-re-danger';  // < 1 hour
        if (seconds < 14400) return 'text-re-warning';  // < 4 hours
        return 'text-re-warning';
    };


    return (
        <PageContainer>
            <PageHeader
                title="Compliance Snapshots"
                description="Point-in-time compliance state capture for audit defense"
                meta={
                    selectedForDiff.length > 0 && selectedForDiff.length < 2 ? (
                        <span>Select 1 more to compare</span>
                    ) : undefined
                }
                secondaryActions={
                    selectedForDiff.length === 2 ? (
                        <Button variant="secondary" onClick={compareSnapshots}>
                            <GitCompare className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            Compare Selected
                        </Button>
                    ) : undefined
                }
                primaryAction={
                    <Button onClick={() => setShowCreateModal(true)}>
                        <Plus className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        Manual Freeze
                    </Button>
                }
            />

            <div className="space-y-6">
                {/* Info Banner */}
                <Callout tone="info" icon={Shield} title="Living Compliance Artifacts">
                    Snapshots are automatically created when CRITICAL or HIGH alerts trigger.
                    Each requires <strong className="font-medium text-re-text-primary">owner attestation</strong> before the alert can be resolved.
                </Callout>

                {/* Error State */}
                {fetchError && (
                    <Callout tone="danger" role="alert" icon={AlertTriangle}>
                        {fetchError}
                    </Callout>
                )}

                {/* Snapshots List */}
                {loading ? (
                    <div className="space-y-4" aria-busy="true">
                        <span className="sr-only">Loading snapshots...</span>
                        {Array.from({ length: 3 }).map((_, i) => (
                            <Skeleton key={i} className="h-40 w-full rounded-lg" />
                        ))}
                    </div>
                ) : snapshots.length === 0 && !fetchError ? (
                    <div data-testid="snapshot-empty-state">
                        <EmptyState
                            icon={Camera}
                            title="No Snapshots Yet"
                            description="Snapshots auto-create when CRITICAL/HIGH alerts trigger."
                            action={
                                <p className="text-small text-re-text-tertiary">
                                    Or create a manual snapshot for proactive audit prep.
                                </p>
                            }
                        />
                    </div>
                ) : (
                    <div className="space-y-4">
                        {snapshots.map((snapshot) => {
                            const needsAttestation = snapshot.is_auto_created && !snapshot.is_attested;
                            const isSelectedForDiff = selectedForDiff.includes(snapshot.id);

                            return (
                                <Card
                                    key={snapshot.id}
                                    data-testid={`snapshot-card-${snapshot.id}`}
                                    padding="spacious"
                                    className={cn(needsAttestation && 'border-re-border-strong')}
                                >
                                    <div className="flex flex-col justify-between gap-6 lg:flex-row">
                                        <div className="min-w-0 flex-1">
                                            {/* Header Row */}
                                            <div className="mb-2 flex flex-wrap items-center gap-2">
                                                <h3 className="text-heading text-re-text-primary">{snapshot.snapshot_name}</h3>
                                                {/* Degradation State Badge */}
                                                <span title={snapshot.degradation_reason || `${snapshot.age_hours}h old`}>
                                                    <StatusBadge
                                                        state={getSnapshotState(snapshot.snapshot_state)}
                                                        label={`${snapshot.state_emoji} ${snapshot.snapshot_state}`}
                                                    />
                                                </span>
                                                <StatusBadge
                                                    state={getComplianceState(snapshot.compliance_status)}
                                                    label={`${snapshot.compliance_status_emoji} ${snapshot.compliance_status}`}
                                                />
                                                {snapshot.is_auto_created && (
                                                    <Badge tone="neutral" size="sm" mono>
                                                        AUTO-TRIGGERED
                                                    </Badge>
                                                )}
                                                {snapshot.integrity_verified && (
                                                    <Badge tone="success" size="sm" mono>
                                                        <ShieldCheck className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                        INTEGRITY VERIFIED
                                                    </Badge>
                                                )}
                                                {snapshot.is_attested ? (
                                                    <span className="flex items-center gap-1.5 text-small text-re-text-secondary">
                                                        <CheckCircle2 className="h-4 w-4 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                                        Attested by {snapshot.attested_by}
                                                    </span>
                                                ) : snapshot.is_auto_created && (
                                                    <span className="flex items-center gap-1.5 text-small text-re-text-secondary">
                                                        <AlertTriangle className="h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                                                        Awaiting Attestation
                                                    </span>
                                                )}
                                            </div>


                                            {/* Deadline + Citation Row */}
                                            {snapshot.deadline && (
                                                <div className="mb-3 flex w-fit flex-wrap items-center gap-4 rounded-md bg-re-surface-inset px-4 py-2">
                                                    <span className={cn('flex items-center gap-2 font-mono text-subheading tabular-nums', getCountdownColor(snapshot.countdown_seconds))}>
                                                        <Timer className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                        {snapshot.countdown_display || 'EXPIRED'}
                                                    </span>
                                                    {snapshot.regulatory_citation && (
                                                        <span className="flex items-center gap-1.5 text-small text-re-text-secondary">
                                                            <BookOpen className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                            {snapshot.regulatory_citation}
                                                        </span>
                                                    )}
                                                </div>
                                            )}

                                            {/* Metadata Row */}
                                            <div className="mt-3 flex flex-wrap items-center gap-4 text-small text-re-text-tertiary">
                                                <span className="flex items-center gap-1.5">
                                                    <Calendar className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                    {formatDate(snapshot.captured_at)}
                                                </span>
                                                <span className="flex items-center gap-1.5">
                                                    <User className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                    {snapshot.created_by}
                                                </span>
                                                <span className="flex min-w-0 items-center gap-1.5 font-mono text-[0.8125rem]">
                                                    <Hash className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                    <span className="truncate">{snapshot.content_hash}</span>
                                                </span>
                                            </div>

                                            <div className="mt-4 flex items-center gap-4 text-ui">
                                                <span className="text-re-text-tertiary">
                                                    {snapshot.active_alert_count} active alerts
                                                </span>
                                                {snapshot.critical_alert_count > 0 && (
                                                    <span className="flex items-center gap-1.5 text-re-text-secondary">
                                                        <AlertTriangle className="h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                                                        {snapshot.critical_alert_count} critical
                                                    </span>
                                                )}
                                            </div>

                                            {snapshot.snapshot_reason && (
                                                <p className="mt-4 text-ui text-re-text-secondary">
                                                    {snapshot.snapshot_reason}
                                                </p>
                                            )}
                                        </div>

                                        <div className="flex shrink-0 flex-col items-stretch gap-2 lg:items-end">
                                            {/* Primary Action: Attest if not attested */}
                                            {needsAttestation && (
                                                <Button
                                                    onClick={() => {
                                                        setAttestingSnapshotId(snapshot.id);
                                                        setShowAttestModal(true);
                                                    }}
                                                >
                                                    <PenLine className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    Attest Now
                                                </Button>
                                            )}

                                            {/* Re-freeze button for degraded snapshots */}
                                            {(snapshot.snapshot_state === 'STALE' || snapshot.snapshot_state === 'INVALID') && (
                                                <Button variant="secondary" onClick={() => refreezeSnapshot(snapshot.id)}>
                                                    <Camera className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    Re-freeze
                                                </Button>
                                            )}

                                            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                                                {/* Compare checkbox */}
                                                <Button
                                                    variant="secondary"
                                                    size="icon"
                                                    className={isSelectedForDiff ? 'bg-re-brand-muted text-re-brand' : undefined}
                                                    aria-pressed={isSelectedForDiff}
                                                    onClick={() => toggleDiffSelection(snapshot.id)}
                                                    aria-label={`Select snapshot ${snapshot.snapshot_name} for comparison`}
                                                    title={`Select snapshot ${snapshot.snapshot_name} for comparison`}
                                                >
                                                    {isSelectedForDiff ? (
                                                        <Check className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    ) : (
                                                        <Circle className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    )}
                                                </Button>
                                                <Button
                                                    variant="secondary"
                                                    onClick={() => getFdaResponse(snapshot.id)}
                                                    title="Generate FDA Response"
                                                >
                                                    <ClipboardList className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    FDA
                                                </Button>
                                                <Button
                                                    variant="secondary"
                                                    onClick={() => verifySnapshot(snapshot.id)}
                                                    aria-label={`Verify snapshot ${snapshot.snapshot_name}`}
                                                >
                                                    <FileCheck className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    Verify
                                                </Button>
                                                <Button
                                                    variant={needsAttestation ? 'secondary' : 'primary'}
                                                    onClick={() => downloadAuditPack(snapshot.id, snapshot.snapshot_name)}
                                                    title="Generate Zero-Trust Audit Pack"
                                                >
                                                    <ShieldCheck className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    Audit Pack
                                                </Button>
                                                <Button
                                                    variant="secondary"
                                                    onClick={() => exportSnapshot(snapshot.id, snapshot.snapshot_name)}
                                                >
                                                    <Download className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                                    PDF
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                </Card>
                            );
                        })}
                    </div>
                )}
            </div>

            {/* Create Modal */}
            {showCreateModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-re-surface-overlay p-4">
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="snapshot-create-title"
                        className="w-full max-w-lg rounded-xl border border-re-border bg-re-surface-elevated p-6"
                    >
                        <h2 id="snapshot-create-title" className="mb-2 flex items-center gap-3 text-heading text-re-text-primary">
                            <Camera className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            Manual Compliance Freeze
                        </h2>
                        <p className="mb-6 text-ui text-re-text-secondary">
                            Create a manual snapshot for proactive audit preparation.
                            Note: CRITICAL/HIGH alerts auto-create bound snapshots.
                        </p>

                        <div className="space-y-4">
                            <Field label="Snapshot Name" htmlFor="snapshot-name" required>
                                <Input
                                    id="snapshot-name"
                                    type="text"
                                    aria-label="Snapshot Name"
                                    value={snapshotName}
                                    onChange={(e) => setSnapshotName(e.target.value)}
                                    placeholder="e.g., Pre-Audit Q1 2026"
                                />
                            </Field>

                            <Field label="Reason (optional)" htmlFor="snapshot-reason">
                                <textarea
                                    id="snapshot-reason"
                                    aria-label="Snapshot Reason"
                                    value={snapshotReason}
                                    onChange={(e) => setSnapshotReason(e.target.value)}
                                    placeholder="e.g., FDA audit scheduled for next week"
                                    rows={3}
                                    className={cn(fieldControlClasses, 'h-auto resize-none py-2')}
                                />
                            </Field>
                        </div>

                        <div className="mt-8 flex items-center justify-end gap-2">
                            <Button variant="ghost" onClick={() => setShowCreateModal(false)}>
                                Cancel
                            </Button>
                            <Button
                                onClick={createSnapshot}
                                disabled={!snapshotName.trim()}
                                loading={creating}
                                leadingIcon={<Camera strokeWidth={1.75} aria-hidden="true" />}
                            >
                                {creating ? 'Creating...' : 'Create Snapshot'}
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Attest Modal */}
            {showAttestModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-re-surface-overlay p-4">
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="snapshot-attest-title"
                        className="w-full max-w-lg rounded-xl border border-re-border bg-re-surface-elevated p-6"
                    >
                        <h2 id="snapshot-attest-title" className="mb-2 flex items-center gap-3 text-heading text-re-text-primary">
                            <PenLine className="h-5 w-5 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                            Owner Attestation Required
                        </h2>
                        <p className="mb-2 text-ui text-re-text-secondary">
                            By attesting, you take <strong className="font-medium text-re-text-primary">personal accountability</strong> for this compliance state.
                        </p>
                        <p className="mb-6 text-small text-re-text-tertiary">
                            Your name will be permanently attached to this snapshot for regulatory review.
                        </p>

                        <div className="space-y-4">
                            <Field label="Your Full Name" htmlFor="attest-name" required>
                                <Input
                                    id="attest-name"
                                    type="text"
                                    value={attestName}
                                    onChange={(e) => setAttestName(e.target.value)}
                                    placeholder="e.g., Jane Smith"
                                />
                            </Field>

                            <Field label="Your Title/Role" htmlFor="attest-title" required>
                                <Input
                                    id="attest-title"
                                    type="text"
                                    value={attestTitle}
                                    onChange={(e) => setAttestTitle(e.target.value)}
                                    placeholder="e.g., VP Operations"
                                />
                            </Field>
                        </div>

                        <div className="mt-6">
                            <Callout tone="danger" role="alert" icon={AlertTriangle}>
                                This action cannot be undone. Once attested, your name is permanently on record.
                            </Callout>
                        </div>

                        <div className="mt-8 flex items-center justify-end gap-2">
                            <Button
                                variant="ghost"
                                onClick={() => {
                                    setShowAttestModal(false);
                                    setAttestingSnapshotId(null);
                                    setAttestName('');
                                    setAttestTitle('');
                                }}
                            >
                                Cancel
                            </Button>
                            <Button
                                onClick={attestSnapshot}
                                disabled={!attestName.trim() || !attestTitle.trim()}
                                leadingIcon={<PenLine strokeWidth={1.75} aria-hidden="true" />}
                            >
                                I Attest to This State
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Verify Result Modal */}
            {showVerifyModal && verifyResult && (
                <div
                    data-testid="snapshot-verify-modal"
                    className="fixed inset-0 z-50 flex items-center justify-center bg-re-surface-overlay p-4"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="snapshot-verify-title"
                        className="w-full max-w-lg rounded-xl border border-re-border bg-re-surface-elevated p-6"
                    >
                        <div className="text-center">
                            {verifyResult.is_valid ? (
                                <>
                                    <CheckCircle2 className="mx-auto mb-4 h-8 w-8 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                                    <h2 id="snapshot-verify-title" className="mb-2 text-heading text-re-text-primary">
                                        Integrity Verified
                                    </h2>
                                    <p className="mb-6 text-ui text-re-text-secondary">
                                        The snapshot data has not been modified. Hash matches.
                                    </p>
                                </>
                            ) : (
                                <>
                                    <XCircle className="mx-auto mb-4 h-8 w-8 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                                    <h2 id="snapshot-verify-title" className="mb-2 text-heading text-re-text-primary">
                                        Integrity Check Failed
                                    </h2>
                                    <p className="mb-6 text-ui text-re-text-secondary">
                                        Warning: The snapshot data may have been modified.
                                    </p>
                                </>
                            )}

                            <div className="mb-6 space-y-3 rounded-md bg-re-surface-inset p-4 text-left">
                                <div>
                                    <span className="text-label text-re-text-muted">Stored Hash:</span>
                                    <p className="break-all font-mono text-[0.8125rem] text-re-text-secondary">
                                        {verifyResult.stored_hash}
                                    </p>
                                </div>
                                <div>
                                    <span className="text-label text-re-text-muted">Computed Hash:</span>
                                    <p className="break-all font-mono text-[0.8125rem] text-re-text-secondary">
                                        {verifyResult.computed_hash}
                                    </p>
                                </div>
                                <div className="flex items-center justify-between gap-3 text-ui">
                                    <span className="text-re-text-muted">Verified by:</span>
                                    <span className="truncate text-re-text-secondary">{verifyResult.verified_by}</span>
                                </div>
                            </div>

                            <Button variant="secondary" onClick={() => setShowVerifyModal(false)}>
                                Close
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* FDA Response Modal */}
            {showFdaModal && (
                <div
                    data-testid="snapshot-fda-modal"
                    className="fixed inset-0 z-50 flex items-center justify-center bg-re-surface-overlay p-4"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="snapshot-fda-title"
                        className="max-h-[80vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-re-border bg-re-surface-elevated p-6"
                    >
                        <h2 id="snapshot-fda-title" className="mb-4 flex items-center gap-3 text-heading text-re-text-primary">
                            <ClipboardList className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            FDA Response Template
                        </h2>
                        <p className="mb-4 text-ui text-re-text-secondary">
                            Copy this pre-formatted text directly into your FDA response.
                        </p>

                        <pre className="mb-4 max-h-96 overflow-y-auto whitespace-pre-wrap break-all rounded-md bg-re-surface-inset p-4 font-mono text-[0.8125rem] text-re-text-secondary">
                            {fdaResponse}
                        </pre>

                        <div className="flex items-center justify-end gap-2">
                            <Button variant="ghost" onClick={() => setShowFdaModal(false)}>
                                Close
                            </Button>
                            <Button
                                onClick={() => copyToClipboard(fdaResponse)}
                                leadingIcon={<ClipboardList strokeWidth={1.75} aria-hidden="true" />}
                            >
                                Copy to Clipboard
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* Diff Modal */}
            {showDiffModal && diffResult && (
                <div
                    data-testid="snapshot-diff-modal"
                    className="fixed inset-0 z-50 flex items-center justify-center bg-re-surface-overlay p-4"
                >
                    <div
                        role="dialog"
                        aria-modal="true"
                        aria-labelledby="snapshot-diff-title"
                        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-re-border bg-re-surface-elevated p-6"
                    >
                        <h2 id="snapshot-diff-title" className="mb-4 flex items-center gap-3 text-heading text-re-text-primary">
                            <GitCompare className="h-5 w-5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            Snapshot Comparison
                        </h2>

                        <div className="mb-6 flex flex-wrap items-center justify-between gap-3 text-ui">
                            <div className="text-re-text-secondary">
                                <span className="text-re-text-muted">From:</span> {diffResult.snapshot_a?.name}
                            </div>
                            <span className="text-re-text-tertiary" aria-hidden="true">→</span>
                            <div className="text-re-text-secondary">
                                <span className="text-re-text-muted">To:</span> {diffResult.snapshot_b?.name}
                            </div>
                        </div>

                        {diffResult.changes?.length === 0 ? (
                            <EmptyState
                                size="sm"
                                bare
                                title="No changes detected between snapshots."
                            />
                        ) : (
                            <div className="space-y-3">
                                {diffResult.changes?.map((change: DiffChange, index: number) => (
                                    <div
                                        key={index}
                                        className={cn(
                                            'rounded-md border border-l-[3px] border-re-border bg-re-surface-card p-4',
                                            change.severity === 'critical' ? 'border-l-re-danger' :
                                                change.severity === 'high' ? 'border-l-re-warning' :
                                                    change.severity === 'positive' ? 'border-l-re-success' :
                                                        'border-l-re-border-strong'
                                        )}
                                    >
                                        <div className="mb-2 text-subheading text-re-text-primary">{change.label}</div>
                                        <div className="flex flex-wrap items-center gap-3 text-ui">
                                            <span className="text-re-text-tertiary line-through">{change.before}</span>
                                            <span className="text-re-text-muted" aria-hidden="true">→</span>
                                            <span className="text-re-text-primary">{change.after}</span>
                                            {change.diff && (
                                                <span className="font-mono text-[0.8125rem] text-re-text-secondary">
                                                    ({change.diff})
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}

                        <div className="mt-6 flex items-center justify-end">
                            <Button
                                variant="secondary"
                                onClick={() => {
                                    setShowDiffModal(false);
                                    setDiffResult(null);
                                    setSelectedForDiff([]);
                                }}
                            >
                                Close
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </PageContainer>
    );
}
