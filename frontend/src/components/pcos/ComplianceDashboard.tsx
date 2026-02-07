/**
 * Compliance Dashboard Component
 * 
 * Displays project compliance status with gate progression,
 * risk indicators, and quick actions.
 */

import React, { useState, useEffect } from 'react';

interface ComplianceSnapshot {
    id: string;
    snapshot_type: string;
    snapshot_name: string;
    compliance_status: 'compliant' | 'partial' | 'non_compliant' | 'unknown';
    overall_score: number;
    rules_evaluated: number;
    passed: number;
    failed: number;
    warnings: number;
    is_attested: boolean;
    created_at: string;
}

interface CategoryScore {
    evaluated: number;
    passed: number;
    failed: number;
    warning: number;
    score: number;
}

interface Props {
    projectId: string;
    onCreateSnapshot?: () => void;
    onViewSnapshot?: (snapshotId: string) => void;
}

const statusColors = {
    compliant: { bg: 'bg-emerald-50', text: 'text-emerald-700', border: 'border-emerald-200' },
    partial: { bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200' },
    non_compliant: { bg: 'bg-red-50', text: 'text-red-700', border: 'border-red-200' },
    unknown: { bg: 'bg-slate-50', text: 'text-slate-700', border: 'border-slate-200' },
};

const statusLabels = {
    compliant: 'Compliant',
    partial: 'Partial Compliance',
    non_compliant: 'Non-Compliant',
    unknown: 'Unknown',
};

export function ComplianceDashboard({ projectId, onCreateSnapshot, onViewSnapshot }: Props) {
    const [snapshots, setSnapshots] = useState<ComplianceSnapshot[]>([]);
    const [categoryScores, setCategoryScores] = useState<Record<string, CategoryScore>>({});
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [creatingSnapshot, setCreatingSnapshot] = useState(false);

    const latestSnapshot = snapshots[0];

    useEffect(() => {
        loadSnapshots();
    }, [projectId]);

    async function loadSnapshots() {
        try {
            setLoading(true);
            const response = await fetch(`/api/pcos/projects/${projectId}/compliance-snapshots?limit=5`);
            if (!response.ok) throw new Error('Failed to load snapshots');
            const data = await response.json();
            setSnapshots(data);

            // Load category scores from latest snapshot
            if (data.length > 0) {
                const detailRes = await fetch(`/api/pcos/compliance-snapshots/${data[0].id}`);
                if (detailRes.ok) {
                    const detail = await detailRes.json();
                    setCategoryScores(detail.category_scores || {});
                }
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    }

    async function handleCreateSnapshot() {
        try {
            setCreatingSnapshot(true);
            const response = await fetch(`/api/pcos/projects/${projectId}/compliance-snapshots`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!response.ok) throw new Error('Failed to create snapshot');
            await loadSnapshots();
            onCreateSnapshot?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to create snapshot');
        } finally {
            setCreatingSnapshot(false);
        }
    }

    if (loading) {
        return (
            <div className="animate-pulse space-y-4">
                <div className="h-32 bg-slate-100 rounded-xl"></div>
                <div className="h-48 bg-slate-100 rounded-xl"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                <p className="font-medium">Error loading compliance data</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Overall Compliance Status */}
            <div className={`rounded-xl border-2 p-6 ${latestSnapshot ? statusColors[latestSnapshot.compliance_status].bg : 'bg-slate-50'} ${latestSnapshot ? statusColors[latestSnapshot.compliance_status].border : 'border-slate-200'}`}>
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Compliance Status</h2>
                        {latestSnapshot ? (
                            <>
                                <p className={`text-2xl font-bold mt-1 ${statusColors[latestSnapshot.compliance_status].text}`}>
                                    {statusLabels[latestSnapshot.compliance_status]}
                                </p>
                                <p className="text-sm text-slate-500 mt-1">
                                    Score: {latestSnapshot.overall_score}% • Last updated: {new Date(latestSnapshot.created_at).toLocaleDateString()}
                                </p>
                            </>
                        ) : (
                            <p className="text-slate-500 mt-1">No compliance snapshots yet</p>
                        )}
                    </div>

                    <div className="flex items-center gap-3">
                        {latestSnapshot && (
                            <div className="text-center px-4 py-2 bg-white rounded-lg shadow-sm">
                                <div className="text-3xl font-bold text-slate-900">{latestSnapshot.overall_score}%</div>
                                <div className="text-xs text-slate-500">Score</div>
                            </div>
                        )}
                        <button
                            onClick={handleCreateSnapshot}
                            disabled={creatingSnapshot}
                            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 font-medium text-sm"
                        >
                            {creatingSnapshot ? 'Creating...' : 'New Snapshot'}
                        </button>
                    </div>
                </div>

                {/* Rule Summary */}
                {latestSnapshot && (
                    <div className="grid grid-cols-4 gap-4 mt-6">
                        <div className="bg-white/80 rounded-lg p-3 text-center">
                            <div className="text-2xl font-semibold text-slate-900">{latestSnapshot.rules_evaluated}</div>
                            <div className="text-xs text-slate-500">Rules Checked</div>
                        </div>
                        <div className="bg-white/80 rounded-lg p-3 text-center">
                            <div className="text-2xl font-semibold text-emerald-600">{latestSnapshot.passed}</div>
                            <div className="text-xs text-slate-500">Passed</div>
                        </div>
                        <div className="bg-white/80 rounded-lg p-3 text-center">
                            <div className="text-2xl font-semibold text-red-600">{latestSnapshot.failed}</div>
                            <div className="text-xs text-slate-500">Failed</div>
                        </div>
                        <div className="bg-white/80 rounded-lg p-3 text-center">
                            <div className="text-2xl font-semibold text-amber-600">{latestSnapshot.warnings}</div>
                            <div className="text-xs text-slate-500">Warnings</div>
                        </div>
                    </div>
                )}
            </div>

            {/* Category Breakdown */}
            {Object.keys(categoryScores).length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <h3 className="text-lg font-semibold text-slate-900 mb-4">Compliance by Category</h3>
                    <div className="space-y-3">
                        {Object.entries(categoryScores).map(([category, scores]) => (
                            <div key={category} className="flex items-center gap-4">
                                <div className="w-40 text-sm font-medium text-slate-700 capitalize">
                                    {category.replace(/_/g, ' ')}
                                </div>
                                <div className="flex-1 h-3 bg-slate-100 rounded-full overflow-hidden">
                                    <div
                                        className={`h-full rounded-full ${scores.score >= 80 ? 'bg-emerald-500' : scores.score >= 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                                        style={{ width: `${scores.score}%` }}
                                    />
                                </div>
                                <div className="w-12 text-right text-sm font-semibold text-slate-900">
                                    {scores.score}%
                                </div>
                                <div className="w-24 text-right text-xs text-slate-500">
                                    {scores.passed}/{scores.evaluated}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Snapshot History */}
            {snapshots.length > 0 && (
                <div className="bg-white rounded-xl border border-slate-200 p-6">
                    <h3 className="text-lg font-semibold text-slate-900 mb-4">Snapshot History</h3>
                    <div className="space-y-2">
                        {snapshots.map((snapshot) => (
                            <button
                                key={snapshot.id}
                                onClick={() => onViewSnapshot?.(snapshot.id)}
                                className="w-full flex items-center justify-between p-3 bg-slate-50 hover:bg-slate-100 rounded-lg transition-colors text-left"
                            >
                                <div className="flex items-center gap-3">
                                    <div className={`w-2 h-2 rounded-full ${snapshot.compliance_status === 'compliant' ? 'bg-emerald-500' :
                                            snapshot.compliance_status === 'partial' ? 'bg-amber-500' : 'bg-red-500'
                                        }`} />
                                    <div>
                                        <div className="font-medium text-slate-900">{snapshot.snapshot_name || 'Snapshot'}</div>
                                        <div className="text-xs text-slate-500">
                                            {snapshot.snapshot_type} • {new Date(snapshot.created_at).toLocaleString()}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-4">
                                    <div className="text-right">
                                        <div className="font-semibold text-slate-900">{snapshot.overall_score}%</div>
                                        <div className="text-xs text-slate-500">{snapshot.rules_evaluated} rules</div>
                                    </div>
                                    {snapshot.is_attested && (
                                        <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-xs font-medium rounded">
                                            Attested
                                        </span>
                                    )}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>
            )}

            {/* Quick Actions */}
            <div className="grid grid-cols-3 gap-4">
                <a
                    href={`/pcos/projects/${projectId}/audit-pack`}
                    className="block p-4 bg-white border border-slate-200 rounded-xl hover:border-indigo-300 hover:shadow-sm transition-all text-center"
                >
                    <div className="text-2xl mb-2">📋</div>
                    <div className="font-medium text-slate-900">Audit Pack</div>
                    <div className="text-xs text-slate-500">Generate full report</div>
                </a>
                <a
                    href={`/pcos/projects/${projectId}/paperwork-status`}
                    className="block p-4 bg-white border border-slate-200 rounded-xl hover:border-indigo-300 hover:shadow-sm transition-all text-center"
                >
                    <div className="text-2xl mb-2">📄</div>
                    <div className="font-medium text-slate-900">Paperwork</div>
                    <div className="text-xs text-slate-500">Document status</div>
                </a>
                <a
                    href={`/pcos/projects/${projectId}/audit-events`}
                    className="block p-4 bg-white border border-slate-200 rounded-xl hover:border-indigo-300 hover:shadow-sm transition-all text-center"
                >
                    <div className="text-2xl mb-2">📜</div>
                    <div className="font-medium text-slate-900">Audit Log</div>
                    <div className="text-xs text-slate-500">Event history</div>
                </a>
            </div>
        </div>
    );
}

export default ComplianceDashboard;
