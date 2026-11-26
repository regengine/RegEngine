'use client';

import { useState } from 'react';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { motion, useReducedMotion } from 'framer-motion';
import { Shield, AlertCircle, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { StatTile } from '@/components/ui/stat-tile';
import { BookCallLink } from '@/components/conversion/BookCallLink';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';
import { submitAssessment, AssessmentFormData } from '@/app/actions/submit-assessment';
import { getConversionAttribution, getReferrerHostname, trackEmailCaptureSubmit } from '@/lib/conversion-events';

const RECORDS_REQUEST_TOOL_CONFIG: ToolConfig = {
    id: 'records-request-checklist',
    title: 'Records Request Checklist',
    description: '§1.1455 is the FDA records request rule. Teams often keep a sortable electronic spreadsheet so they can answer a records request. This page is a self reported checklist. It is not a 24 hour capability test, not a recall readiness score, and not legal advice.',
    icon: 'Shield',
    stages: {
        questions: [
            {
                id: 'pull_records',
                text: 'Can you provide all required traceability records to the FDA when requested?',
                type: 'select',
                hint: '§1.1455 is the FDA records request rule. This checklist does not test whether you can meet the 24 hour clock.',
                options: [
                    { label: 'Yes, systematically', value: 'yes', weight: 20 },
                    { label: 'Mostly (delayed)', value: 'mostly', weight: 10 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            },
            {
                id: 'sortable_spreadsheet',
                text: 'Can you produce an electronic sortable spreadsheet of requested Key Data Element (KDE) fields?',
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
                text: 'Do you capture all applicable Critical Tracking Event (CTE) types for your supply chain role?',
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
    const reduceMotion = useReducedMotion();
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
        const attribution = getConversionAttribution();
        const data: AssessmentFormData = {
            name: formData.get('name') as string,
            email: formData.get('email') as string,
            company: formData.get('company') as string || '',
            role: formData.get('role') as string || 'Unknown',
            phone: formData.get('phone') as string || '',
            source: 'records-request-checklist',
            utmSource: attribution.utm_source,
            utmMedium: attribution.utm_medium,
            utmCampaign: attribution.utm_campaign,
            referrer: getReferrerHostname(),
            toolInputs: {
                score: lastScore.score,
                grade: lastScore.grade,
                answers: lastAnswers
            }
        };
        try {
            const result = await submitAssessment(data);
            if (result.success) {
                trackEmailCaptureSubmit({ form: 'lead_gate', step: 'gate', tool: 'records-request-checklist', outcome: 'success' });
                setLeadSubmitted(true);
            } else {
                trackEmailCaptureSubmit({
                    form: 'lead_gate', step: 'gate', tool: 'records-request-checklist', outcome: 'error',
                    error_code: result.error?.includes('valid email') ? 'validation' : 'server',
                });
                setSubmitError(result.error || 'Submission failed. Please try again.');
            }
        } catch {
            trackEmailCaptureSubmit({ form: 'lead_gate', step: 'gate', tool: 'records-request-checklist', outcome: 'error', error_code: 'server' });
            setSubmitError('Submission failed. Please try again.');
        } finally {
            setSubmitting(false);
        }
    };

    const renderResults = (answers: Record<string, any>) => {
        const { score, grade } = calcScore(answers);
        setLastScore({ score, grade });
        setLastAnswers(answers);

        return (
            <motion.div
                initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18 }}
            >
                <div className="mb-6">
                    <div className="px-1">
                        <div className="mb-6 text-center">
                            <h3 className="text-heading text-re-text-primary">What You Reported</h3>
                            <p className="mt-1 text-ui text-re-text-tertiary">
                                Summary of your self reported answers. Not a readiness score, not a regulatory determination.
                            </p>
                            <div className="mx-auto mt-4 max-w-[70ch] text-ui text-re-text-tertiary">
                                <p>FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.</p>
                            </div>
                        </div>

                        <div className="mb-8 grid gap-4 md:grid-cols-2">
                            <StatTile label="Self Reported Points" value={score} />
                            <Card variant="inset">
                                <CardContent>
                                    <h4 className="mb-2 text-subheading text-re-text-primary">What This Is Not</h4>
                                    <ul className="space-y-1 text-ui text-re-text-tertiary">
                                        <li className="flex items-start gap-2">
                                            <AlertCircle aria-hidden="true" size={16} strokeWidth={1.75} className="mt-0.5 flex-shrink-0" />
                                            <span>Not a 24 hour capability test</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                            <AlertCircle aria-hidden="true" size={16} strokeWidth={1.75} className="mt-0.5 flex-shrink-0" />
                                            <span>Not a recall readiness score</span>
                                        </li>
                                        <li className="flex items-start gap-2">
                                            <AlertCircle aria-hidden="true" size={16} strokeWidth={1.75} className="mt-0.5 flex-shrink-0" />
                                            <span>Not legal advice</span>
                                        </li>
                                    </ul>
                                </CardContent>
                            </Card>
                        </div>

                        <div className="space-y-3">
                            {RECORDS_REQUEST_TOOL_CONFIG.stages.questions.map(q => {
                                const selectedValue = answers[q.id];
                                const option = q.options?.find(opt => opt.value === selectedValue);
                                const isComplete = selectedValue === 'yes';
                                return (
                                    <div key={q.id} className="flex items-start gap-3 rounded-md border border-re-border bg-re-surface-card p-4">
                                        {isComplete ? (
                                            <CheckCircle2 aria-hidden="true" size={20} strokeWidth={1.75} className="mt-0.5 flex-shrink-0 text-re-text-tertiary" />
                                        ) : (
                                            <AlertTriangle aria-hidden="true" size={20} strokeWidth={1.75} className="mt-0.5 flex-shrink-0 text-re-warning" />
                                        )}
                                        <div className="flex-1">
                                            <p className="mb-1 text-ui font-medium text-re-text-primary">{q.text}</p>
                                            <p className="text-ui text-re-text-tertiary">
                                                You reported: <strong className="font-medium text-re-text-secondary">{option?.label || 'No answer'}</strong>
                                            </p>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>

                        <Callout tone="neutral" role="note" icon={Shield} title="Next Steps" className="mt-8">
                            <p className="text-ui text-re-text-tertiary">
                                We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455.
                            </p>
                            <div className="mt-4">
                                <Button asChild variant="secondary" size="sm">
                                    <BookCallLink href="/contact" placement="records_request_checklist" tool="records-request-checklist">
                                        Book a 30-min Call
                                        <ArrowRight aria-hidden="true" size={16} strokeWidth={1.75} className="ml-2" />
                                    </BookCallLink>
                                </Button>
                            </div>
                        </Callout>
                    </div>
                </div>

                {!leadSubmitted && (
                    <div className="border-t border-re-border-subtle pt-8">
                        <div>
                            <h3 className="mb-4 text-center text-subheading text-re-text-primary">Want to Discuss Your Checklist?</h3>
                            <form onSubmit={handleLeadSubmit} className="mx-auto max-w-md space-y-4">
                                <div>
                                    <label htmlFor="rrc-name" className="sr-only">Full Name</label>
                                    <Input
                                        id="rrc-name"
                                        type="text"
                                        name="name"
                                        placeholder="Full Name"
                                        required
                                        size="lg"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="rrc-email" className="sr-only">Work Email</label>
                                    <Input
                                        id="rrc-email"
                                        type="email"
                                        name="email"
                                        placeholder="Work Email"
                                        required
                                        size="lg"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="rrc-company" className="sr-only">Company (Optional)</label>
                                    <Input
                                        id="rrc-company"
                                        type="text"
                                        name="company"
                                        placeholder="Company (Optional)"
                                        size="lg"
                                    />
                                </div>
                                <div>
                                    <label htmlFor="rrc-phone" className="sr-only">Phone (Optional)</label>
                                    <Input
                                        id="rrc-phone"
                                        type="tel"
                                        name="phone"
                                        placeholder="Phone (Optional)"
                                        size="lg"
                                    />
                                </div>
                                <input
                                    type="hidden"
                                    name="role"
                                    value="Unknown"
                                />
                                {submitError && (
                                    <Callout tone="danger" role="alert">{submitError}</Callout>
                                )}
                                <Button type="submit" size="lg" loading={submitting} className="w-full">
                                    {submitting ? 'Submitting...' : 'Send My Checklist'}
                                </Button>
                            </form>
                        </div>
                    </div>
                )}

                {leadSubmitted && (
                    <motion.div
                        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18 }}
                    >
                        <div className="border-t border-re-border-subtle pt-8 text-center">
                            <CheckCircle2 aria-hidden="true" size={24} strokeWidth={1.75} className="mx-auto mb-4 text-re-text-tertiary" />
                            <h3 className="mb-2 text-subheading text-re-text-primary">Thank You!</h3>
                            <p className="text-ui text-re-text-tertiary">
                                We&apos;ll be in touch soon to discuss your checklist.
                            </p>
                        </div>
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
