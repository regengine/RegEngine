'use client';

import { useState } from 'react';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { motion } from 'framer-motion';
import { Shield, AlertCircle, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';
import { submitAssessment, AssessmentFormData } from '@/app/actions/submit-assessment';

const RECORDS_REQUEST_TOOL_CONFIG: ToolConfig = {
    id: 'records-request-checklist',
    title: 'Records-Request Checklist',
    description: '§1.1455 is the FDA records-request rule. Teams often keep a sortable electronic spreadsheet so they can answer a records request. This page is a self-reported checklist. It is not a 24-hour capability test, not a recall-readiness score, and not legal advice.',
    icon: 'Shield',
    stages: {
        questions: [
            {
                id: 'pull_records',
                text: 'Can you provide all required traceability records to the FDA when requested?',
                type: 'select',
                hint: '§1.1455 is the FDA records-request rule. This checklist does not test whether you can meet the 24-hour clock.',
                options: [
                    { label: 'Yes, systematically', value: 'yes', weight: 20 },
                    { label: 'Mostly (delayed)', value: 'mostly', weight: 10 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'sortable_spreadsheet',
                text: 'Can you produce an electronic sortable spreadsheet of requested KDEs?',
                type: 'select',
                hint: 'Teams often keep a sortable electronic spreadsheet.',
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
                text: 'Do you systematically receive KDEs from suppliers and provide them to customers?',
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
                    { label: 'Yes, documented', value: 'yes', weight: 4 },
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
                text: 'Have you performed a traceability drill in the past 12 months?',
                type: 'select',
                options: [
                    { label: 'Yes, drill complete', value: 'yes', weight: 4 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            }
        ],
    }
};

export function RecordsRequestChecklistClient() {
    const [leadSubmitted, setLeadSubmitted] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState('');
    const [lastScore, setLastScore] = useState<{ score: number; grade: string }>({ score: 0, grade: 'F' });
    const [lastAnswers, setLastAnswers] = useState<Record<string, any>>({});

    function calcScore(answers: Record<string, any>) {
        let totalScore = 0;
        RECORDS_REQUEST_TOOL_CONFIG.stages.questions.forEach(q => {
            const selectedValue = answers[q.id];
            const option = q.options?.find(opt => opt.value === selectedValue);
            if (option?.weight) totalScore += option.weight;
        });
        let grade = 'F';
        if (totalScore >= 90) grade = 'A';
        else if (totalScore >= 80) grade = 'B';
        else if (totalScore >= 70) grade = 'C';
        else if (totalScore >= 55) grade = 'D';
        return { score: totalScore, grade };
    }

    const handleLeadSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        setSubmitting(true);
        setSubmitError('');
        const formData = new FormData(e.currentTarget);
        const data: AssessmentFormData = {
            email: formData.get('email') as string,
            firstName: formData.get('firstName') as string,
            lastName: formData.get('lastName') as string,
            company: formData.get('company') as string || '',
            phone: formData.get('phone') as string || '',
            industryRole: 'Unknown',
            toolContext: {
                source: 'records-request-checklist',
                score: lastScore.score,
                grade: lastScore.grade,
                answers: lastAnswers
            }
        };
        const result = await submitAssessment(data);
        if (result.success) {
            setLeadSubmitted(true);
        } else {
            setSubmitError(result.error || 'Submission failed. Please try again.');
        }
        setSubmitting(false);
    };

    const renderResults = (answers: Record<string, any>) => {
        const { score, grade } = calcScore(answers);
        setLastScore({ score, grade });
        setLastAnswers(answers);

        return (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
                <div className="re-panel p-8 mb-6">
                    <div className="text-center mb-6">
                        <h3 className="re-title-2 mb-2">What You Reported</h3>
                        <p className="re-copy text-sm text-[var(--re-text-muted)]">
                            Summary of your self-reported answers. Not a readiness score, not a regulatory determination.
                        </p>
                        <div className="mt-4 text-sm text-[var(--re-text-muted)] max-w-2xl mx-auto">
                            <p>The federal Food Traceability Rule compliance date is <strong>July 20, 2028</strong>.</p>
                        </div>
                    </div>

                    <div className="grid md:grid-cols-2 gap-4 mb-8">
                        <div className="re-panel p-6 text-center">
                            <div className="text-5xl font-bold mb-2" style={{ color: 'var(--re-brand)' }}>{score}</div>
                            <div className="text-sm text-[var(--re-text-muted)]">Self-Reported Points</div>
                        </div>
                        <div className="re-panel p-6">
                            <h4 className="font-semibold mb-2 text-[var(--re-text-primary)]">What This Is Not</h4>
                            <ul className="text-sm space-y-1 text-[var(--re-text-muted)]">
                                <li className="flex items-start gap-2">
                                    <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                                    <span>Not a 24-hour capability test</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                                    <span>Not a recall-readiness score</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <AlertCircle size={16} className="mt-0.5 flex-shrink-0" />
                                    <span>Not legal advice</span>
                                </li>
                            </ul>
                        </div>
                    </div>

                    <div className="space-y-4">
                        {RECORDS_REQUEST_TOOL_CONFIG.stages.questions.map(q => {
                            const selectedValue = answers[q.id];
                            const option = q.options?.find(opt => opt.value === selectedValue);
                            const isComplete = selectedValue === 'yes';
                            return (
                                <div key={q.id} className="re-panel p-4 flex items-start gap-3">
                                    {isComplete ? (
                                        <CheckCircle2 size={20} className="text-re-brand mt-0.5 flex-shrink-0" />
                                    ) : (
                                        <AlertTriangle size={20} className="text-re-warning mt-0.5 flex-shrink-0" />
                                    )}
                                    <div className="flex-1">
                                        <p className="font-medium text-sm text-[var(--re-text-primary)] mb-1">{q.text}</p>
                                        <p className="text-sm text-[var(--re-text-muted)]">
                                            You reported: <strong>{option?.label || 'No answer'}</strong>
                                        </p>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    <div className="mt-8 p-6 rounded-xl bg-[var(--re-brand-muted)] border border-[var(--re-brand-muted)]">
                        <div className="flex items-start gap-3">
                            <Shield size={24} className="text-re-brand mt-0.5 flex-shrink-0" />
                            <div>
                                <h4 className="font-semibold mb-2 text-[var(--re-text-primary)]">Next Steps</h4>
                                <p className="text-sm text-[var(--re-text-muted)] mb-4">
                                    We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455.
                                </p>
                                <Link href="/contact">
                                    <Button size="sm" className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)]">
                                        Book a 30-min Call
                                        <ArrowRight size={16} className="ml-2" />
                                    </Button>
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>

                {!leadSubmitted && (
                    <div className="re-panel p-8">
                        <h3 className="re-title-3 mb-4 text-center">Want to Discuss Your Checklist?</h3>
                        <form onSubmit={handleLeadSubmit} className="max-w-md mx-auto space-y-4">
                            <div className="grid grid-cols-2 gap-4">
                                <input
                                    type="text"
                                    name="firstName"
                                    placeholder="First Name"
                                    required
                                    className="re-input"
                                />
                                <input
                                    type="text"
                                    name="lastName"
                                    placeholder="Last Name"
                                    required
                                    className="re-input"
                                />
                            </div>
                            <input
                                type="email"
                                name="email"
                                placeholder="Work Email"
                                required
                                className="re-input w-full"
                            />
                            <input
                                type="text"
                                name="company"
                                placeholder="Company (Optional)"
                                className="re-input w-full"
                            />
                            <input
                                type="tel"
                                name="phone"
                                placeholder="Phone (Optional)"
                                className="re-input w-full"
                            />
                            {submitError && (
                                <div className="text-sm text-re-danger">{submitError}</div>
                            )}
                            <Button type="submit" disabled={submitting} className="w-full">
                                {submitting ? 'Submitting...' : 'Send My Checklist'}
                            </Button>
                        </form>
                    </div>
                )}

                {leadSubmitted && (
                    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="re-panel p-8 text-center">
                        <CheckCircle2 size={48} className="text-re-brand mx-auto mb-4" />
                        <h3 className="re-title-3 mb-2">Thank You!</h3>
                        <p className="re-copy text-[var(--re-text-muted)]">
                            We'll be in touch soon to discuss your checklist.
                        </p>
                    </motion.div>
                )}
            </motion.div>
        );
    };

    return (
        <FSMAToolShell
            config={RECORDS_REQUEST_TOOL_CONFIG}
            renderResults={renderResults}
        />
    );
}
