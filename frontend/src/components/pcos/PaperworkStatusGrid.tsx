/**
 * Paperwork Status Grid Component
 * 
 * Displays document completion status for all engagements in a project.
 */

import React, { useState, useEffect } from 'react';

interface Document {
    requirement_code: string;
    requirement_name: string;
    document_type: string;
    is_required: boolean;
    status: 'pending' | 'requested' | 'received' | 'verified' | 'expired' | 'waived';
    received_at: string | null;
}

interface EngagementStatus {
    engagement_id: string;
    person_name: string;
    role_title: string;
    classification: string;
    documents: Document[];
    received_count: number;
    pending_count: number;
    completion_pct: number;
}

interface PaperworkStatus {
    project_id: string;
    engagements: EngagementStatus[];
    overall_completion_pct: number;
    total_docs: number;
    total_received: number;
    total_pending: number;
}

interface Props {
    projectId: string;
    onRequestDocument?: (engagementId: string, requirementCode: string) => void;
}

const statusIcons: Record<string, string> = {
    pending: '⏳',
    requested: '📧',
    received: '📥',
    verified: '✅',
    expired: '⚠️',
    waived: '↪️',
};

const statusColors: Record<string, string> = {
    pending: 'bg-slate-100 text-slate-600',
    requested: 'bg-blue-100 text-blue-700',
    received: 'bg-amber-100 text-amber-700',
    verified: 'bg-emerald-100 text-emerald-700',
    expired: 'bg-red-100 text-red-700',
    waived: 'bg-slate-100 text-slate-500',
};

export function PaperworkStatusGrid({ projectId, onRequestDocument }: Props) {
    const [status, setStatus] = useState<PaperworkStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [expandedEngagement, setExpandedEngagement] = useState<string | null>(null);

    useEffect(() => {
        loadStatus();
    }, [projectId]);

    async function loadStatus() {
        try {
            setLoading(true);
            const response = await fetch(`/api/pcos/projects/${projectId}/paperwork-status`);
            if (!response.ok) throw new Error('Failed to load paperwork status');
            const data = await response.json();
            setStatus(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Unknown error');
        } finally {
            setLoading(false);
        }
    }

    if (loading) {
        return (
            <div className="animate-pulse space-y-4">
                <div className="h-24 bg-slate-100 rounded-xl"></div>
                <div className="h-64 bg-slate-100 rounded-xl"></div>
            </div>
        );
    }

    if (error || !status) {
        return (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                <p className="font-medium">Error loading paperwork status</p>
                <p className="text-sm">{error}</p>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Summary Bar */}
            <div className="bg-white rounded-xl border border-slate-200 p-6">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Paperwork Completion</h2>
                        <p className="text-sm text-slate-500 mt-1">
                            {status.total_received} of {status.total_docs} documents received
                        </p>
                    </div>

                    <div className="flex items-center gap-6">
                        {/* Progress Ring */}
                        <div className="relative w-16 h-16">
                            <svg className="w-full h-full transform -rotate-90">
                                <circle
                                    cx="32" cy="32" r="28"
                                    className="fill-none stroke-slate-100"
                                    strokeWidth="8"
                                />
                                <circle
                                    cx="32" cy="32" r="28"
                                    className="fill-none stroke-indigo-500"
                                    strokeWidth="8"
                                    strokeDasharray={`${status.overall_completion_pct * 1.76} 176`}
                                    strokeLinecap="round"
                                />
                            </svg>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <span className="text-lg font-bold text-slate-900">
                                    {Math.round(status.overall_completion_pct)}%
                                </span>
                            </div>
                        </div>

                        <div className="text-right">
                            <div className="text-2xl font-bold text-amber-600">{status.total_pending}</div>
                            <div className="text-xs text-slate-500">Pending</div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Engagement List */}
            <div className="space-y-3">
                {status.engagements.map((eng) => (
                    <div
                        key={eng.engagement_id}
                        className="bg-white rounded-xl border border-slate-200 overflow-hidden"
                    >
                        {/* Header */}
                        <button
                            onClick={() => setExpandedEngagement(
                                expandedEngagement === eng.engagement_id ? null : eng.engagement_id
                            )}
                            className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors"
                        >
                            <div className="flex items-center gap-4">
                                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-semibold ${eng.completion_pct === 100 ? 'bg-emerald-500' :
                                        eng.completion_pct >= 50 ? 'bg-amber-500' : 'bg-red-500'
                                    }`}>
                                    {eng.completion_pct === 100 ? '✓' : `${Math.round(eng.completion_pct)}%`}
                                </div>
                                <div className="text-left">
                                    <div className="font-medium text-slate-900">{eng.person_name}</div>
                                    <div className="text-sm text-slate-500">
                                        {eng.role_title} • {eng.classification}
                                    </div>
                                </div>
                            </div>

                            <div className="flex items-center gap-4">
                                <div className="flex gap-1">
                                    <span className="px-2 py-1 bg-emerald-100 text-emerald-700 text-xs font-medium rounded">
                                        {eng.received_count} ✓
                                    </span>
                                    {eng.pending_count > 0 && (
                                        <span className="px-2 py-1 bg-amber-100 text-amber-700 text-xs font-medium rounded">
                                            {eng.pending_count} pending
                                        </span>
                                    )}
                                </div>
                                <span className="text-slate-400">{expandedEngagement === eng.engagement_id ? '▲' : '▼'}</span>
                            </div>
                        </button>

                        {/* Document Details */}
                        {expandedEngagement === eng.engagement_id && (
                            <div className="border-t border-slate-200 p-4 bg-slate-50">
                                <div className="grid gap-2">
                                    {eng.documents.map((doc) => (
                                        <div
                                            key={doc.requirement_code}
                                            className="flex items-center justify-between p-3 bg-white rounded-lg border border-slate-100"
                                        >
                                            <div className="flex items-center gap-3">
                                                <span className="text-lg">{statusIcons[doc.status]}</span>
                                                <div>
                                                    <div className="font-medium text-slate-900">{doc.requirement_name}</div>
                                                    <div className="text-xs text-slate-500">
                                                        {doc.document_type} {doc.is_required ? '(Required)' : '(Optional)'}
                                                    </div>
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-3">
                                                <span className={`px-2 py-1 text-xs font-medium rounded capitalize ${statusColors[doc.status]}`}>
                                                    {doc.status}
                                                </span>
                                                {doc.received_at && (
                                                    <span className="text-xs text-slate-500">
                                                        {new Date(doc.received_at).toLocaleDateString()}
                                                    </span>
                                                )}
                                                {doc.status === 'pending' && onRequestDocument && (
                                                    <button
                                                        onClick={() => onRequestDocument(eng.engagement_id, doc.requirement_code)}
                                                        className="px-3 py-1 bg-indigo-600 text-white text-xs font-medium rounded hover:bg-indigo-700"
                                                    >
                                                        Request
                                                    </button>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {status.engagements.length === 0 && (
                <div className="text-center py-12 text-slate-500">
                    No engagements found for this project
                </div>
            )}
        </div>
    );
}

export default PaperworkStatusGrid;
