/**
 * Audit Pack Download Component
 * 
 * UI for generating and downloading comprehensive audit packs.
 */

import React, { useState } from 'react';

interface AuditPack {
    generated_at: string;
    pack_version: string;
    project: {
        project_name: string;
        project_code: string;
        gate_state: string;
        risk_score: number;
    };
    compliance_summary?: {
        overall_status: string;
        overall_score: number;
        metrics: {
            total_rules_evaluated: number;
            passed: number;
            failed: number;
            warnings: number;
        };
    };
    budget_summary?: {
        grand_total: number;
        line_item_count: number;
    };
    evidence_inventory?: Array<{
        evidence_id: string;
        title: string;
        document_type: string;
        file_name: string;
    }>;
}

interface Props {
    projectId: string;
}

export function AuditPackDownload({ projectId }: Props) {
    const [generating, setGenerating] = useState(false);
    const [auditPack, setAuditPack] = useState<AuditPack | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [options, setOptions] = useState({
        includeEvidence: true,
        includeBudget: true,
    });

    async function generatePack() {
        try {
            setGenerating(true);
            setError(null);

            const params = new URLSearchParams({
                include_evidence: options.includeEvidence.toString(),
                include_budget: options.includeBudget.toString(),
            });

            const response = await fetch(`/api/pcos/projects/${projectId}/audit-pack?${params}`);
            if (!response.ok) throw new Error('Failed to generate audit pack');

            const data = await response.json();
            setAuditPack(data);
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to generate pack');
        } finally {
            setGenerating(false);
        }
    }

    function downloadAsJSON() {
        if (!auditPack) return;

        const blob = new Blob([JSON.stringify(auditPack, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `audit-pack-${projectId}-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="bg-gradient-to-r from-indigo-500 to-purple-600 rounded-xl p-6 text-white">
                <h2 className="text-xl font-bold">Audit Pack Generator</h2>
                <p className="text-indigo-100 mt-1">
                    Generate comprehensive compliance documentation for audit purposes
                </p>
            </div>

            {/* Options */}
            <div className="bg-white rounded-xl border border-slate-200 p-6">
                <h3 className="font-semibold text-slate-900 mb-4">Include in Pack</h3>

                <div className="space-y-3">
                    <label className="flex items-center gap-3 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={options.includeEvidence}
                            onChange={(e) => setOptions({ ...options, includeEvidence: e.target.checked })}
                            className="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <div>
                            <div className="font-medium text-slate-900">Evidence Inventory</div>
                            <div className="text-sm text-slate-500">List of all uploaded documents and permits</div>
                        </div>
                    </label>

                    <label className="flex items-center gap-3 cursor-pointer">
                        <input
                            type="checkbox"
                            checked={options.includeBudget}
                            onChange={(e) => setOptions({ ...options, includeBudget: e.target.checked })}
                            className="w-5 h-5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <div>
                            <div className="font-medium text-slate-900">Budget Summary</div>
                            <div className="text-sm text-slate-500">Budget totals and department breakdown</div>
                        </div>
                    </label>
                </div>

                <button
                    onClick={generatePack}
                    disabled={generating}
                    className="mt-6 w-full py-3 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                    {generating ? (
                        <>
                            <span className="animate-spin">⟳</span>
                            Generating...
                        </>
                    ) : (
                        <>
                            📋 Generate Audit Pack
                        </>
                    )}
                </button>
            </div>

            {/* Error */}
            {error && (
                <div className="bg-red-50 border border-red-200 rounded-xl p-4 text-red-700">
                    <p className="font-medium">Error</p>
                    <p className="text-sm">{error}</p>
                </div>
            )}

            {/* Generated Pack Preview */}
            {auditPack && (
                <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                    <div className="p-4 bg-emerald-50 border-b border-emerald-100 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <span className="text-emerald-600 text-xl">✅</span>
                            <span className="font-semibold text-emerald-800">Audit Pack Generated</span>
                        </div>
                        <span className="text-sm text-slate-500">
                            {new Date(auditPack.generated_at).toLocaleString()}
                        </span>
                    </div>

                    <div className="p-6 space-y-4">
                        {/* Project Info */}
                        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
                            <div>
                                <h3 className="font-semibold text-slate-900">{auditPack.project.project_name}</h3>
                                <p className="text-sm text-slate-500">{auditPack.project.project_code}</p>
                            </div>
                            <span className={`px-3 py-1 rounded-full text-sm font-medium ${auditPack.project.gate_state === 'greenlit' ? 'bg-emerald-100 text-emerald-700' :
                                    auditPack.project.gate_state === 'approved' ? 'bg-blue-100 text-blue-700' :
                                        'bg-slate-100 text-slate-700'
                                }`}>
                                {auditPack.project.gate_state}
                            </span>
                        </div>

                        {/* Compliance Summary */}
                        {auditPack.compliance_summary && (
                            <div className="grid grid-cols-4 gap-4">
                                <div className="text-center p-3 bg-slate-50 rounded-lg">
                                    <div className="text-2xl font-bold text-slate-900">
                                        {auditPack.compliance_summary.overall_score}%
                                    </div>
                                    <div className="text-xs text-slate-500">Score</div>
                                </div>
                                <div className="text-center p-3 bg-emerald-50 rounded-lg">
                                    <div className="text-2xl font-bold text-emerald-600">
                                        {auditPack.compliance_summary.metrics.passed}
                                    </div>
                                    <div className="text-xs text-slate-500">Passed</div>
                                </div>
                                <div className="text-center p-3 bg-red-50 rounded-lg">
                                    <div className="text-2xl font-bold text-red-600">
                                        {auditPack.compliance_summary.metrics.failed}
                                    </div>
                                    <div className="text-xs text-slate-500">Failed</div>
                                </div>
                                <div className="text-center p-3 bg-amber-50 rounded-lg">
                                    <div className="text-2xl font-bold text-amber-600">
                                        {auditPack.compliance_summary.metrics.warnings}
                                    </div>
                                    <div className="text-xs text-slate-500">Warnings</div>
                                </div>
                            </div>
                        )}

                        {/* Budget Summary */}
                        {auditPack.budget_summary && (
                            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                                <span className="text-slate-600">Budget Total</span>
                                <span className="font-semibold text-slate-900">
                                    ${auditPack.budget_summary.grand_total.toLocaleString()}
                                </span>
                            </div>
                        )}

                        {/* Evidence Count */}
                        {auditPack.evidence_inventory && (
                            <div className="flex items-center justify-between p-3 bg-slate-50 rounded-lg">
                                <span className="text-slate-600">Documents</span>
                                <span className="font-semibold text-slate-900">
                                    {auditPack.evidence_inventory.length} files
                                </span>
                            </div>
                        )}

                        {/* Download Buttons */}
                        <div className="flex gap-3 pt-4 border-t border-slate-100">
                            <button
                                onClick={downloadAsJSON}
                                className="flex-1 py-2 bg-slate-100 text-slate-700 font-medium rounded-lg hover:bg-slate-200 flex items-center justify-center gap-2"
                            >
                                📄 Download JSON
                            </button>
                            <button
                                disabled
                                className="flex-1 py-2 bg-slate-100 text-slate-400 font-medium rounded-lg cursor-not-allowed flex items-center justify-center gap-2"
                                title="Coming soon"
                            >
                                📑 Download PDF
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Info Note */}
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-4">
                <div className="flex gap-3">
                    <span className="text-blue-500">ℹ️</span>
                    <div className="text-sm text-blue-700">
                        <p className="font-medium">About Audit Packs</p>
                        <p className="mt-1">
                            Audit packs compile all compliance data, rule evaluations with source authorities,
                            and supporting documentation into a single exportable format for auditors and legal review.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default AuditPackDownload;
