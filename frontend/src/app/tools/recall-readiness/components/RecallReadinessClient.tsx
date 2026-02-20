'use client';

import { useState } from 'react';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { motion } from 'framer-motion';
import { Shield, AlertCircle, AlertTriangle, CheckCircle2, ArrowRight, Download } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';

const READINESS_TOOL_CONFIG: ToolConfig = {
    id: 'recall-readiness',
    title: 'Recall Readiness Score',
    description: 'Evaluate your ability to respond to an FDA FSMA 204 records request within the mandated 24-hour window.',
    icon: 'Shield',
    stages: {
        questions: [
            {
                id: 'pull_24h',
                text: 'Can you provide all required traceability records to the FDA within 24 hours of request?',
                type: 'select',
                hint: 'Ref: 21 CFR §1.1455(b)(3)',
                options: [
                    { label: 'Yes, systematically', value: 'yes', weight: 20 },
                    { label: 'Mostly (delayed)', value: 'mostly', weight: 10 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'sortable_spreadsheet',
                text: 'Can you produce an electronic sortable spreadsheet of requested KDEs within 24 hours?',
                type: 'select',
                hint: 'Ref: 21 CFR §1.1455(b)(3)(ii)',
                options: [
                    { label: 'Yes, one-click export', value: 'yes', weight: 15 },
                    { label: 'Manual assembly required', value: 'mostly', weight: 5 },
                    { label: 'No electronic capability', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'digital_search',
                text: 'Are your traceability records stored in a format that allows for automated keyword searching?',
                type: 'select',
                hint: 'Includes data in databases or OCR-enabled digital systems.',
                options: [
                    { label: 'Fully indexed/searchable', value: 'yes', weight: 15 },
                    { label: 'Partial (mixed digital/paper)', value: 'mostly', weight: 7 },
                    { label: 'No (paper/PDF files)', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'tlc_stability',
                text: 'Does your Traceability Lot Code (TLC) remain stable through your facility without relabeling?',
                type: 'select',
                hint: 'Stability is required unless food is "transformed" (processed/mixed).',
                options: [
                    { label: 'Stable through facility', value: 'yes', weight: 15 },
                    { label: 'We re-lot on receipt', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'cte_coverage',
                text: 'Do you capture all applicable Critical Tracking Events (CTEs) for your supply chain role?',
                type: 'select',
                options: [
                    { label: 'Full CTE coverage', value: 'yes', weight: 10 },
                    { label: 'Significant gaps', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'written_plan',
                text: 'Do you have a written Traceability Plan including procedures and contact points?',
                type: 'select',
                hint: 'Ref: 21 CFR §1.1315',
                options: [
                    { label: 'Yes, written & current', value: 'yes', weight: 7 },
                    { label: 'In draft', value: 'mostly', weight: 2 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'partner_exchange',
                text: 'Do you systematicallly receive KDEs from suppliers and provide them to customers?',
                type: 'select',
                options: [
                    { label: 'Yes, digital exchange', value: 'yes', weight: 6 },
                    { label: 'Partial/Manual', value: 'mostly', weight: 2 },
                    { label: 'No systematic exchange', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'retention_2y',
                text: 'Are you maintaining records for at least 2 years after creation or procurement?',
                type: 'select',
                hint: 'Ref: 21 CFR §1.1460',
                options: [
                    { label: 'Yes, guaranteed', value: 'yes', weight: 4 },
                    { label: 'Unsure/No', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'tlc_source',
                text: 'Can you provide the TLC Source Reference (e.g. Invoice #) for all received lots?',
                type: 'select',
                options: [
                    { label: 'Always linked', value: 'yes', weight: 4 },
                    { label: 'Sometimes', value: 'mostly', weight: 1 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'mock_drill',
                text: 'Have you performed a successful traceability drill in the past 12 months?',
                type: 'select',
                options: [
                    { label: 'Yes, drill complete', value: 'yes', weight: 4 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            }
        ],
        leadGate: {
            title: 'Get Your Official Readiness Scorecard',
            description: 'We will send you a detailed A–F grade report plus a step-by-step gap remediation checklist rooted in CFR citations.',
            cta: 'Generate My Report'
        }
    }
};

export function RecallReadinessClient() {
    const evaluateResults = (answers: Record<string, any>) => {
        // Calculate score based on weights
        let totalScore = 0;
        READINESS_TOOL_CONFIG.stages.questions.forEach(q => {
            const selectedValue = answers[q.id];
            const option = q.options?.find(opt => opt.value === selectedValue);
            if (option?.weight) {
                totalScore += option.weight;
            }
        });

        let grade = 'F';
        let color = 'var(--re-danger)';
        if (totalScore >= 90) { grade = 'A'; color = 'var(--re-brand)'; }
        else if (totalScore >= 80) { grade = 'B'; color = 'var(--re-brand)'; }
        else if (totalScore >= 70) { grade = 'C'; color = 'var(--re-warning)'; }
        else if (totalScore >= 55) { grade = 'D'; color = 'var(--re-warning)'; }

        const gaps = [];
        if (answers.pull_24h !== 'yes') gaps.push('Non-compliant: Cannot meet 24-hour FDA records retrieval mandate (21 CFR §1.1455(b)(3))');
        if (answers.sortable_spreadsheet !== 'yes') gaps.push('Non-compliant: Missing electronic sortable spreadsheet capability (21 CFR §1.1455(b)(3)(ii))');
        if (answers.digital_search !== 'yes') gaps.push('Fragility Risk: Manual/Paper records significantly delay outbreak investigations');
        if (answers.tlc_stability === 'no') gaps.push('Compliance Gap: Improper TLC stability creates data linkage breaks');
        if (answers.cte_coverage === 'no') gaps.push('Critical Gap: Missing Critical Tracking Event (CTE) recordkeeping for your role');

        return (
            <div className="space-y-8">
                <div className="text-center py-6">
                    <motion.div
                        initial={{ scale: 0.5, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        className="inline-flex items-center justify-center w-24 h-24 rounded-full border-4 mb-4"
                        style={{ borderColor: color, color }}
                    >
                        <span className="text-5xl font-black">{grade}</span>
                    </motion.div>
                    <h3 className="text-2xl font-bold">Your Readiness Grade</h3>
                    <p className="text-[var(--re-text-tertiary)] mt-1">Total score: {totalScore} / 100</p>
                </div>

                {gaps.length > 0 && (
                    <div className="space-y-4">
                        <h4 className="text-sm font-semibold uppercase tracking-wider text-[var(--re-text-muted)]">Critical Gaps Detected</h4>
                        <div className="space-y-2">
                            {gaps.map((gap, i) => (
                                <div key={i} className="flex items-center gap-3 p-3 rounded-lg bg-[var(--re-danger-muted)] border border-[var(--re-danger)] / 20 text-sm">
                                    <AlertCircle className="h-4 w-4 shrink-0 text-[var(--re-danger)]" />
                                    <span className="text-[var(--re-text-primary)]">{gap}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div className="p-6 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]">
                        <h4 className="font-bold mb-3 flex items-center gap-2">
                            <AlertTriangle className="h-4 w-4 text-[var(--re-warning)]" /> Regulatory Risks
                        </h4>
                        <ul className="text-xs space-y-3 text-[var(--re-text-tertiary)]">
                            <li>• Potential citations for 21 CFR §1.1455 violations</li>
                            <li>• Delayed response times during active recalls</li>
                            <li>• Operational chaos during FDA audits</li>
                        </ul>
                    </div>
                    <div className="p-6 rounded-2xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)] / 20">
                        <h4 className="font-bold mb-3 flex items-center gap-2">
                            <Shield className="h-4 w-4 text-[var(--re-brand)]" /> RegEngine Solution
                        </h4>
                        <p className="text-xs text-[var(--re-text-secondary)] leading-relaxed mb-4">
                            RegEngine automates KDE capture and guarantees 24-hour retrieval with one-click sortable spreadsheet exports.
                        </p>
                        <Button className="w-full bg-[var(--re-brand)] text-xs h-8">
                            Book a Compliance Audit
                        </Button>
                    </div>
                </div>

                <div className="flex flex-col items-center gap-3 pt-4">
                    <Button variant="outline" className="w-full gap-2">
                        <Download className="h-4 w-4" /> Download PDF Report
                    </Button>
                    <div className="w-full p-4 rounded-xl border border-[var(--re-brand)] bg-[var(--re-brand-muted)] text-center">
                        <p className="text-xs font-bold mb-2">Recommended Next Step:</p>
                        <Link href="/tools/kde-checker">
                            <Button className="w-full bg-[var(--re-brand)] gap-2">
                                Generate Your KDE Checklist <ArrowRight className="h-4 w-4" />
                            </Button>
                        </Link>
                    </div>
                    <Link href="/tools" className="text-sm text-[var(--re-text-muted)] hover:text-[var(--re-brand)] underline">
                        Back to Toolkit Hub
                    </Link>
                </div>
            </div>
        );
    };

    return (
        <div className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <FSMAToolShell
                config={READINESS_TOOL_CONFIG}
                renderResults={evaluateResults}
            />

            <div className="max-w-3xl mx-auto">
                <RelatedTools
                    tools={FREE_TOOLS.filter(t => ['tlc-validator', 'drill-simulator', 'roi-calculator'].includes(t.id))}
                />
            </div>
        </div>
    );
}
