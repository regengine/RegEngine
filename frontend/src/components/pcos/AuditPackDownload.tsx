/**
 * Audit Pack Download Component
 * 
 * UI for generating and downloading comprehensive audit packs.
 */

import React, { useState } from 'react';
import { generateBrandedPDF, type PDFSection } from '@/lib/pdf-report';

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

    function downloadAsPDF() {
        if (!auditPack) return;

        const sections: PDFSection[] = [
            { type: 'heading', text: 'Project Summary', level: 2 },
            {
                type: 'keyValue',
                pairs: [
                    { key: 'Project Name', value: auditPack.project.project_name },
                    { key: 'Project Code', value: auditPack.project.project_code },
                    {
                        key: 'Gate State',
                        value: auditPack.project.gate_state,
                        status:
                            auditPack.project.gate_state === 'greenlit'
                                ? 'success'
                                : auditPack.project.gate_state === 'approved'
                                    ? 'warning'
                                    : 'neutral',
                    },
                    { key: 'Risk Score', value: `${auditPack.project.risk_score}` },
                    { key: 'Pack Version', value: auditPack.pack_version },
                    { key: 'Generated At', value: new Date(auditPack.generated_at).toLocaleString() },
                ],
            },
        ];

        if (auditPack.compliance_summary) {
            sections.push({ type: 'divider' });
            sections.push({ type: 'heading', text: 'Compliance Summary', level: 2 });
            sections.push({
                type: 'keyValue',
                pairs: [
                    {
                        key: 'Overall Status',
                        value: auditPack.compliance_summary.overall_status,
                        status: auditPack.compliance_summary.overall_status.toLowerCase().includes('pass')
                            ? 'success'
                            : auditPack.compliance_summary.overall_status.toLowerCase().includes('fail')
                                ? 'danger'
                                : 'warning',
                    },
                    { key: 'Overall Score', value: `${auditPack.compliance_summary.overall_score}%` },
                    { key: 'Rules Evaluated', value: `${auditPack.compliance_summary.metrics.total_rules_evaluated}` },
                    { key: 'Passed', value: `${auditPack.compliance_summary.metrics.passed}`, status: 'success' },
                    { key: 'Failed', value: `${auditPack.compliance_summary.metrics.failed}`, status: 'danger' },
                    { key: 'Warnings', value: `${auditPack.compliance_summary.metrics.warnings}`, status: 'warning' },
                ],
            });
        }

        if (auditPack.budget_summary) {
            sections.push({ type: 'divider' });
            sections.push({ type: 'heading', text: 'Budget Summary', level: 2 });
            sections.push({
                type: 'keyValue',
                pairs: [
                    { key: 'Grand Total', value: `$${auditPack.budget_summary.grand_total.toLocaleString()}` },
                    { key: 'Line Items', value: `${auditPack.budget_summary.line_item_count}` },
                ],
            });
        }

        if (auditPack.evidence_inventory && auditPack.evidence_inventory.length > 0) {
            sections.push({ type: 'divider' });
            sections.push({ type: 'heading', text: 'Evidence Inventory', level: 2 });
            sections.push({
                type: 'table',
                headers: ['Evidence ID', 'Title', 'Type', 'File Name'],
                rows: auditPack.evidence_inventory.map((evidence) => [
                    evidence.evidence_id,
                    evidence.title,
                    evidence.document_type,
                    evidence.file_name,
                ]),
            });
        }

        const packWithExtras = auditPack as AuditPack & {
            rule_evaluations?: Array<Record<string, unknown>>;
        };
        if (packWithExtras.rule_evaluations && packWithExtras.rule_evaluations.length > 0) {
            const rows = packWithExtras.rule_evaluations;
            const headers = Array.from(
                new Set(rows.flatMap((row) => Object.keys(row))),
            ).slice(0, 6);

            sections.push({ type: 'divider' });
            sections.push({ type: 'heading', text: 'Rule Evaluations', level: 2 });
            sections.push({
                type: 'table',
                headers: headers.map((header) => header.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())),
                rows: rows.slice(0, 40).map((row) => headers.map((header) => String(row[header] ?? '-'))),
            });
        }

        generateBrandedPDF({
            title: 'Audit Pack Report',
            subtitle: `${auditPack.project.project_name} (${auditPack.project.project_code})`,
            reportType: 'RegEngine Audit Pack',
            sections,
            footer: {
                left: 'Confidential',
                right: 'regengine.co',
                legalLine: 'Generated from RegEngine audit pack data',
            },
            filename: `audit-pack-${projectId}-${new Date().toISOString().split('T')[0]}`,
        });
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
                                onClick={downloadAsPDF}
                                className="flex-1 py-2 bg-slate-100 text-slate-700 font-medium rounded-lg hover:bg-slate-200 flex items-center justify-center gap-2"
                            >
                                📑 Download PDF Report
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
