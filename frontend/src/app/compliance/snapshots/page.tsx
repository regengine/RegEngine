'use client';

import { useState, useEffect } from 'react';
import { useTenant } from '@/lib/tenant-context';
import { generateBrandedPDF, type PDFSection } from '@/lib/pdf-report';
import {
    Camera,
    Shield,
    ShieldCheck,
    CheckCircle2,
    XCircle,
    Download,
    Clock,
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

/**
 * Get current user email from session storage.
 * TODO: Replace with proper auth session context (e.g., next-auth useSession)
 * once user authentication is fully integrated.
 */
function getUserEmail(tenantId: string): string {
    if (typeof window !== 'undefined') {
        const stored = localStorage.getItem('regengine_user_email');
        if (stored) return stored;
    }
    return `admin@tenant-${tenantId.slice(0, 8)}.regengine.io`;
}

export default function SnapshotsPage() {
    const { tenantId } = useTenant();
    const userEmail = getUserEmail(tenantId);
    const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
    const [loading, setLoading] = useState(true);
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
        fetchSnapshots();
        // Refresh countdown every 30 seconds
        const interval = setInterval(fetchSnapshots, 30000);
        return () => clearInterval(interval);
    }, [tenantId]);

    const fetchSnapshots = async () => {
        try {
            const response = await fetch(`/api/admin/v1/compliance/snapshots/${tenantId}`);
            if (response.ok) {
                const data = await response.json();
                // Handle both direct array and paginated {items: []} format
                if (Array.isArray(data)) {
                    setSnapshots(data);
                } else if (data && Array.isArray(data.items)) {
                    setSnapshots(data.items);
                } else {
                    setSnapshots([]);
                }
            }
        } catch (error) {
            console.log('Using mock snapshots (backend unavailable)');
            setSnapshots([]);
        } finally {
            setLoading(false);
        }
    };

    const createSnapshot = async () => {
        if (!snapshotName.trim()) return;

        setCreating(true);
        try {
            const response = await fetch(`/api/admin/v1/compliance/snapshots/${tenantId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    snapshot_name: snapshotName,
                    snapshot_reason: snapshotReason || undefined,
                    created_by: userEmail,
                }),
            });

            if (response.ok) {
                await fetchSnapshots();
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
            const response = await fetch(`/api/admin/v1/compliance/snapshots/${tenantId}/${attestingSnapshotId}/attest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    attested_by: attestName,
                    attestation_title: attestTitle,
                }),
            });

            if (response.ok) {
                await fetchSnapshots();
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
            const response = await fetch(
                `/api/admin/v1/compliance/snapshots/${tenantId}/${snapshotId}/verify?verified_by=${encodeURIComponent(userEmail)}`
            );

            if (response.ok) {
                const result = await response.json();
                setVerifyResult(result);
                setShowVerifyModal(true);
                await fetchSnapshots();
            }
        } catch (error) {
            console.error('Failed to verify snapshot:', error);
        }
    };

    const downloadAuditPack = async (snapshotId: string, snapshotName: string) => {
        try {
            const response = await fetch(
                `/api/admin/v1/compliance/snapshots/${tenantId}/${snapshotId}/audit-pack`
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
            const response = await fetch(
                `/api/admin/v1/compliance/snapshots/${tenantId}/${snapshotId}/export`
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

                generateBrandedPDF({
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
            const response = await fetch(
                `/api/admin/v1/compliance/snapshots/${tenantId}/${snapshotId}/refreeze`,
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ created_by: userEmail }),
                }
            );

            if (response.ok) {
                await fetchSnapshots();
            }
        } catch (error) {
            console.error('Failed to refreeze snapshot:', error);
        }
    };

    const getFdaResponse = async (snapshotId: string) => {
        try {
            const response = await fetch(
                `/api/admin/v1/compliance/snapshots/${tenantId}/${snapshotId}/fda-response`
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
            const response = await fetch(
                `/api/admin/v1/compliance/snapshots/${tenantId}/diff?snapshot_a=${selectedForDiff[0]}&snapshot_b=${selectedForDiff[1]}`
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

    const getStatusColor = (status: string) => {
        switch (status) {
            case 'COMPLIANT': return 'bg-green-500/10 text-green-400 border-green-500/30';
            case 'AT_RISK': return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30';
            case 'NON_COMPLIANT': return 'bg-red-500/10 text-red-400 border-red-500/30';
            default: return 'bg-gray-500/10 text-gray-400 border-gray-500/30';
        }
    };

    const getCountdownColor = (seconds?: number) => {
        if (!seconds) return 'text-gray-400';
        if (seconds <= 0) return 'text-red-500 animate-pulse';
        if (seconds < 3600) return 'text-red-400';  // < 1 hour
        if (seconds < 14400) return 'text-orange-400';  // < 4 hours
        return 'text-yellow-400';
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-950 via-gray-900 to-gray-950 text-white p-8">
            <div className="max-w-6xl mx-auto">
                {/* Header */}
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h1 className="text-3xl font-bold flex items-center gap-3">
                            <Camera className="h-8 w-8 text-purple-400" />
                            Compliance Snapshots
                        </h1>
                        <p className="text-gray-400 mt-2">
                            Point-in-time compliance state capture for audit defense
                        </p>
                    </div>

                    <div className="flex items-center gap-3">
                        {selectedForDiff.length === 2 && (
                            <button
                                onClick={compareSnapshots}
                                className="flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 rounded-xl font-medium transition-all"
                            >
                                Compare Selected
                            </button>
                        )}
                        {selectedForDiff.length > 0 && selectedForDiff.length < 2 && (
                            <span className="text-gray-400 text-sm">Select 1 more to compare</span>
                        )}
                        <button
                            onClick={() => setShowCreateModal(true)}
                            className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-500 rounded-xl font-medium transition-all"
                        >
                            <Plus className="h-5 w-5" />
                            Manual Freeze
                        </button>
                    </div>
                </div>

                {/* Info Banner */}
                <div className="bg-purple-900/20 border border-purple-500/30 rounded-xl p-4 mb-8">
                    <div className="flex items-start gap-3">
                        <Shield className="h-6 w-6 text-purple-400 mt-0.5" />
                        <div>
                            <h3 className="font-semibold text-purple-300">Living Compliance Artifacts</h3>
                            <p className="text-sm text-gray-400 mt-1">
                                Snapshots are automatically created when CRITICAL or HIGH alerts trigger.
                                Each requires <strong>owner attestation</strong> before the alert can be resolved.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Snapshots List */}
                {loading ? (
                    <div className="text-center py-12 text-gray-400">Loading snapshots...</div>
                ) : snapshots.length === 0 ? (
                    <div className="text-center py-16 bg-white/5 rounded-xl border border-white/10">
                        <Camera className="h-16 w-16 text-gray-600 mx-auto mb-4" />
                        <h3 className="text-xl font-semibold text-gray-300 mb-2">No Snapshots Yet</h3>
                        <p className="text-gray-500 mb-2">
                            Snapshots auto-create when CRITICAL/HIGH alerts trigger.
                        </p>
                        <p className="text-gray-600 text-sm">
                            Or create a manual snapshot for proactive audit prep.
                        </p>
                    </div>
                ) : (
                    <div className="space-y-4">
                        {snapshots.map((snapshot) => (
                            <div
                                key={snapshot.id}
                                className={`bg-white/5 rounded-xl border p-6 transition-all ${snapshot.is_auto_created && !snapshot.is_attested
                                    ? 'border-orange-500/50 shadow-lg shadow-orange-500/10'
                                    : 'border-white/10 hover:border-white/20'
                                    }`}
                            >
                                <div className="flex items-start justify-between">
                                    <div className="flex-1">
                                        {/* Header Row */}
                                        <div className="flex items-center gap-3 mb-2 flex-wrap">
                                            <h3 className="text-xl font-semibold">{snapshot.snapshot_name}</h3>
                                            {/* Degradation State Badge */}
                                            <span
                                                className={`px-2 py-1 rounded-full text-sm border cursor-help ${snapshot.snapshot_state === 'VALID'
                                                    ? 'bg-green-500/10 text-green-400 border-green-500/30'
                                                    : snapshot.snapshot_state === 'STALE'
                                                        ? 'bg-orange-500/10 text-orange-400 border-orange-500/30'
                                                        : 'bg-red-500/10 text-red-400 border-red-500/30'
                                                    }`}
                                                title={snapshot.degradation_reason || `${snapshot.age_hours}h old`}
                                            >
                                                {snapshot.state_emoji} {snapshot.snapshot_state}
                                            </span>
                                            <span className={`px-3 py-1 rounded-full text-sm border ${getStatusColor(snapshot.compliance_status)}`}>
                                                {snapshot.compliance_status_emoji} {snapshot.compliance_status}
                                            </span>
                                            {snapshot.is_auto_created && (
                                                <span className="px-2 py-1 bg-orange-500/20 text-orange-400 text-xs rounded-full border border-orange-500/30">
                                                    AUTO-TRIGGERED
                                                </span>
                                            )}
                                            {snapshot.integrity_verified && (
                                                <span className="flex items-center gap-1.5 px-3 py-1 bg-green-500/10 text-green-400 text-xs font-bold rounded-full border border-green-500/30 shadow-sm shadow-green-500/20">
                                                    <ShieldCheck className="h-3.5 w-3.5" />
                                                    INTEGRITY VERIFIED
                                                </span>
                                            )}
                                            {snapshot.is_attested ? (
                                                <span className="flex items-center gap-1 text-green-400 text-sm">
                                                    <CheckCircle2 className="h-4 w-4" />
                                                    Attested by {snapshot.attested_by}
                                                </span>
                                            ) : snapshot.is_auto_created && (
                                                <span className="flex items-center gap-1 text-orange-400 text-sm animate-pulse">
                                                    <AlertTriangle className="h-4 w-4" />
                                                    Awaiting Attestation
                                                </span>
                                            )}
                                        </div>


                                        {/* Deadline + Citation Row */}
                                        {snapshot.deadline && (
                                            <div className="flex items-center gap-4 mb-3 bg-black/30 rounded-lg px-4 py-2 w-fit">
                                                <span className={`flex items-center gap-2 font-mono text-lg font-bold ${getCountdownColor(snapshot.countdown_seconds)}`}>
                                                    <Timer className="h-5 w-5" />
                                                    {snapshot.countdown_display || 'EXPIRED'}
                                                </span>
                                                {snapshot.regulatory_citation && (
                                                    <span className="flex items-center gap-1 text-blue-400 text-sm">
                                                        <BookOpen className="h-4 w-4" />
                                                        {snapshot.regulatory_citation}
                                                    </span>
                                                )}
                                            </div>
                                        )}

                                        {/* Metadata Row */}
                                        <div className="flex flex-wrap items-center gap-4 text-sm text-gray-400 mt-3">
                                            <span className="flex items-center gap-1">
                                                <Calendar className="h-4 w-4" />
                                                {formatDate(snapshot.captured_at)}
                                            </span>
                                            <span className="flex items-center gap-1">
                                                <User className="h-4 w-4" />
                                                {snapshot.created_by}
                                            </span>
                                            <span className="flex items-center gap-1 font-mono text-xs">
                                                <Hash className="h-4 w-4" />
                                                {snapshot.content_hash}
                                            </span>
                                        </div>

                                        <div className="flex items-center gap-4 mt-4 text-sm">
                                            <span className="text-gray-400">
                                                {snapshot.active_alert_count} active alerts
                                            </span>
                                            {snapshot.critical_alert_count > 0 && (
                                                <span className="text-red-400">
                                                    {snapshot.critical_alert_count} critical
                                                </span>
                                            )}
                                        </div>
                                    </div>

                                    <div className="flex flex-col items-end gap-2">
                                        {/* Primary Action: Attest if not attested */}
                                        {snapshot.is_auto_created && !snapshot.is_attested && (
                                            <button
                                                onClick={() => {
                                                    setAttestingSnapshotId(snapshot.id);
                                                    setShowAttestModal(true);
                                                }}
                                                className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white rounded-lg transition-all font-medium"
                                            >
                                                <PenLine className="h-4 w-4" />
                                                Attest Now
                                            </button>
                                        )}

                                        {/* Re-freeze button for degraded snapshots */}
                                        {(snapshot.snapshot_state === 'STALE' || snapshot.snapshot_state === 'INVALID') && (
                                            <button
                                                onClick={() => refreezeSnapshot(snapshot.id)}
                                                className="flex items-center gap-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-500 text-white rounded-lg transition-all font-medium"
                                            >
                                                <Camera className="h-4 w-4" />
                                                Re-freeze
                                            </button>
                                        )}

                                        <div className="flex items-center gap-2">
                                            {/* Compare checkbox */}
                                            <button
                                                onClick={() => toggleDiffSelection(snapshot.id)}
                                                className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${selectedForDiff.includes(snapshot.id)
                                                    ? 'bg-blue-600 text-white'
                                                    : 'bg-gray-600/20 hover:bg-gray-600/30 text-gray-400'
                                                    }`}
                                            >
                                                {selectedForDiff.includes(snapshot.id) ? '✓' : '○'}
                                            </button>
                                            <button
                                                onClick={() => getFdaResponse(snapshot.id)}
                                                className="flex items-center gap-2 px-4 py-2 bg-purple-600/20 hover:bg-purple-600/30 text-purple-400 rounded-lg transition-all"
                                                title="Generate FDA Response"
                                            >
                                                📋 FDA
                                            </button>
                                            <button
                                                onClick={() => verifySnapshot(snapshot.id)}
                                                className="flex items-center gap-2 px-4 py-2 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg transition-all"
                                            >
                                                <FileCheck className="h-4 w-4" />
                                                Verify
                                            </button>
                                            <button
                                                onClick={() => downloadAuditPack(snapshot.id, snapshot.snapshot_name)}
                                                className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-all font-bold shadow-lg shadow-purple-500/20 border border-purple-400/30"
                                                title="Generate Zero-Trust Audit Pack"
                                            >
                                                <ShieldCheck className="h-4 w-4" />
                                                Audit Pack
                                            </button>
                                            <button
                                                onClick={() => exportSnapshot(snapshot.id, snapshot.snapshot_name)}
                                                className="flex items-center gap-2 px-4 py-2 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg transition-all"
                                            >
                                                <Download className="h-4 w-4" />
                                                PDF
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                {/* Create Modal */}
                {showCreateModal && (
                    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                        <div className="bg-gray-900 rounded-2xl border border-white/10 p-8 max-w-lg w-full mx-4">
                            <h2 className="text-2xl font-bold mb-2 flex items-center gap-3">
                                <Camera className="h-6 w-6 text-purple-400" />
                                Manual Compliance Freeze
                            </h2>
                            <p className="text-gray-400 mb-6">
                                Create a manual snapshot for proactive audit preparation.
                                Note: CRITICAL/HIGH alerts auto-create bound snapshots.
                            </p>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-2">
                                        Snapshot Name *
                                    </label>
                                    <input
                                        type="text"
                                        value={snapshotName}
                                        onChange={(e) => setSnapshotName(e.target.value)}
                                        placeholder="e.g., Pre-Audit Q1 2026"
                                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-2">
                                        Reason (optional)
                                    </label>
                                    <textarea
                                        value={snapshotReason}
                                        onChange={(e) => setSnapshotReason(e.target.value)}
                                        placeholder="e.g., FDA audit scheduled for next week"
                                        rows={3}
                                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none resize-none"
                                    />
                                </div>
                            </div>

                            <div className="flex items-center justify-end gap-3 mt-8">
                                <button
                                    onClick={() => setShowCreateModal(false)}
                                    className="px-6 py-2 text-gray-400 hover:text-white transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={createSnapshot}
                                    disabled={!snapshotName.trim() || creating}
                                    className="flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl font-medium transition-all"
                                >
                                    {creating ? (
                                        <>
                                            <Clock className="h-4 w-4 animate-spin" />
                                            Creating...
                                        </>
                                    ) : (
                                        <>
                                            <Camera className="h-4 w-4" />
                                            Create Snapshot
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Attest Modal */}
                {showAttestModal && (
                    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                        <div className="bg-gray-900 rounded-2xl border border-orange-500/30 p-8 max-w-lg w-full mx-4">
                            <h2 className="text-2xl font-bold mb-2 flex items-center gap-3 text-orange-400">
                                <PenLine className="h-6 w-6" />
                                Owner Attestation Required
                            </h2>
                            <p className="text-gray-400 mb-2">
                                By attesting, you take <strong>personal accountability</strong> for this compliance state.
                            </p>
                            <p className="text-gray-500 text-sm mb-6">
                                Your name will be permanently attached to this snapshot for regulatory review.
                            </p>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-2">
                                        Your Full Name *
                                    </label>
                                    <input
                                        type="text"
                                        value={attestName}
                                        onChange={(e) => setAttestName(e.target.value)}
                                        placeholder="e.g., Jane Smith"
                                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-300 mb-2">
                                        Your Title/Role *
                                    </label>
                                    <input
                                        type="text"
                                        value={attestTitle}
                                        onChange={(e) => setAttestTitle(e.target.value)}
                                        placeholder="e.g., VP Operations"
                                        className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-xl focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none"
                                    />
                                </div>
                            </div>

                            <div className="bg-red-900/20 border border-red-500/30 rounded-xl p-4 mt-6">
                                <p className="text-red-400 text-sm">
                                    ⚠️ This action cannot be undone. Once attested, your name is permanently on record.
                                </p>
                            </div>

                            <div className="flex items-center justify-end gap-3 mt-8">
                                <button
                                    onClick={() => {
                                        setShowAttestModal(false);
                                        setAttestingSnapshotId(null);
                                        setAttestName('');
                                        setAttestTitle('');
                                    }}
                                    className="px-6 py-2 text-gray-400 hover:text-white transition-all"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={attestSnapshot}
                                    disabled={!attestName.trim() || !attestTitle.trim()}
                                    className="flex items-center gap-2 px-6 py-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-xl font-medium transition-all"
                                >
                                    <PenLine className="h-4 w-4" />
                                    I Attest to This State
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Verify Result Modal */}
                {showVerifyModal && verifyResult && (
                    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                        <div className="bg-gray-900 rounded-2xl border border-white/10 p-8 max-w-lg w-full mx-4">
                            <div className="text-center">
                                {verifyResult.is_valid ? (
                                    <>
                                        <CheckCircle2 className="h-16 w-16 text-green-400 mx-auto mb-4" />
                                        <h2 className="text-2xl font-bold text-green-400 mb-2">
                                            Integrity Verified ✅
                                        </h2>
                                        <p className="text-gray-400 mb-6">
                                            The snapshot data has not been modified. Hash matches.
                                        </p>
                                    </>
                                ) : (
                                    <>
                                        <XCircle className="h-16 w-16 text-red-400 mx-auto mb-4" />
                                        <h2 className="text-2xl font-bold text-red-400 mb-2">
                                            Integrity Check Failed ❌
                                        </h2>
                                        <p className="text-gray-400 mb-6">
                                            Warning: The snapshot data may have been modified.
                                        </p>
                                    </>
                                )}

                                <div className="bg-white/5 rounded-xl p-4 text-left space-y-3 mb-6">
                                    <div>
                                        <span className="text-gray-500 text-sm">Stored Hash:</span>
                                        <p className="font-mono text-xs text-gray-300 break-all">
                                            {verifyResult.stored_hash}
                                        </p>
                                    </div>
                                    <div>
                                        <span className="text-gray-500 text-sm">Computed Hash:</span>
                                        <p className="font-mono text-xs text-gray-300 break-all">
                                            {verifyResult.computed_hash}
                                        </p>
                                    </div>
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="text-gray-500">Verified by:</span>
                                        <span className="text-gray-300">{verifyResult.verified_by}</span>
                                    </div>
                                </div>

                                <button
                                    onClick={() => setShowVerifyModal(false)}
                                    className="px-6 py-2 bg-white/10 hover:bg-white/20 rounded-xl transition-all"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* FDA Response Modal */}
                {showFdaModal && (
                    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                        <div className="bg-gray-900 rounded-2xl border border-purple-500/30 p-8 max-w-3xl w-full mx-4 max-h-[80vh] overflow-y-auto">
                            <h2 className="text-2xl font-bold mb-4 flex items-center gap-3 text-purple-400">
                                📋 FDA Response Template
                            </h2>
                            <p className="text-gray-400 mb-4">
                                Copy this pre-formatted text directly into your FDA response.
                            </p>

                            <pre className="bg-black/50 p-4 rounded-xl font-mono text-xs text-gray-300 whitespace-pre-wrap break-all mb-4 max-h-96 overflow-y-auto">
                                {fdaResponse}
                            </pre>

                            <div className="flex items-center justify-end gap-3">
                                <button
                                    onClick={() => setShowFdaModal(false)}
                                    className="px-6 py-2 text-gray-400 hover:text-white transition-all"
                                >
                                    Close
                                </button>
                                <button
                                    onClick={() => copyToClipboard(fdaResponse)}
                                    className="flex items-center gap-2 px-6 py-2 bg-purple-600 hover:bg-purple-500 rounded-xl font-medium transition-all"
                                >
                                    📋 Copy to Clipboard
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* Diff Modal */}
                {showDiffModal && diffResult && (
                    <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50">
                        <div className="bg-gray-900 rounded-2xl border border-blue-500/30 p-8 max-w-2xl w-full mx-4">
                            <h2 className="text-2xl font-bold mb-4 flex items-center gap-3 text-blue-400">
                                📊 Snapshot Comparison
                            </h2>

                            <div className="flex items-center justify-between mb-6 text-sm">
                                <div className="text-gray-400">
                                    <span className="text-gray-500">From:</span> {diffResult.snapshot_a?.name}
                                </div>
                                <span className="text-gray-600">→</span>
                                <div className="text-gray-400">
                                    <span className="text-gray-500">To:</span> {diffResult.snapshot_b?.name}
                                </div>
                            </div>

                            {diffResult.changes?.length === 0 ? (
                                <div className="text-center py-8 text-gray-400">
                                    No changes detected between snapshots.
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {diffResult.changes?.map((change: DiffChange, index: number) => (
                                        <div
                                            key={index}
                                            className={`p-4 rounded-xl border ${change.severity === 'critical' ? 'border-red-500/50 bg-red-500/10' :
                                                change.severity === 'high' ? 'border-orange-500/50 bg-orange-500/10' :
                                                    change.severity === 'positive' ? 'border-green-500/50 bg-green-500/10' :
                                                        'border-white/10 bg-white/5'
                                                }`}
                                        >
                                            <div className="font-medium mb-2">{change.label}</div>
                                            <div className="flex items-center gap-4 text-sm">
                                                <span className="text-red-400 line-through">{change.before}</span>
                                                <span className="text-gray-500">→</span>
                                                <span className="text-green-400">{change.after}</span>
                                                {change.diff && (
                                                    <span className={`font-mono ${change.diff.startsWith('+') ? 'text-red-400' : 'text-green-400'
                                                        }`}>
                                                        ({change.diff})
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}

                            <div className="flex items-center justify-end mt-6">
                                <button
                                    onClick={() => {
                                        setShowDiffModal(false);
                                        setDiffResult(null);
                                        setSelectedForDiff([]);
                                    }}
                                    className="px-6 py-2 bg-white/10 hover:bg-white/20 rounded-xl transition-all"
                                >
                                    Close
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
