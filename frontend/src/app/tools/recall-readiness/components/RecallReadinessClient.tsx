'use client';

import { useState } from 'react';
import { FSMAToolShell } from '@/components/fsma/FSMAToolShell';
import { ToolConfig } from '@/types/fsma-tools';
import { motion, useReducedMotion } from 'framer-motion';
import { Shield, AlertCircle, AlertTriangle, CheckCircle2, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { Input, fieldControlClasses } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import { RelatedTools } from '@/components/layout/related-tools';
import { FREE_TOOLS } from '@/lib/fsma-tools-data';
import { submitAssessment, AssessmentFormData } from '@/app/actions/submit-assessment';

const READINESS_TOOL_CONFIG: ToolConfig = {
    id: 'recall-readiness',
    title: 'FSMA 204 Readiness Self-Check',
    description: 'Self-check your readiness to provide a sortable electronic spreadsheet to FDA within 24 hours of request, per §1.1455(c).',
    icon: 'Shield',
    stages: {
        questions: [
            {
                id: 'pull_24h',
                text: 'Can you provide all required traceability records to the FDA within 24 hours of request?',
                type: 'select',
                hint: 'Ref: 21 CFR §1.1455(c)(1)',
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
                hint: 'Ref: 21 CFR §1.1455(c)(3)(ii)',
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
                text: 'Have you performed a successful traceability drill in the past 12 months?',
                type: 'select',
                options: [
                    { label: 'Yes, drill complete', value: 'yes', weight: 4 },
                    { label: 'No', value: 'no', weight: 0 },
                ]
            }
        ],
        /* leadGate removed — using inline lead capture form in results instead */
    }
};

export function RecallReadinessClient() {
    const reduceMotion = useReducedMotion();
    const [leadSubmitted, setLeadSubmitted] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState('');
    const [lastScore, setLastScore] = useState<{ score: number; grade: string }>({ score: 0, grade: 'F' });
    const [lastAnswers, setLastAnswers] = useState<Record<string, any>>({});

    function calcScore(answers: Record<string, any>) {
        let totalScore = 0;
        READINESS_TOOL_CONFIG.stages.questions.forEach(q => {
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
        const form = new FormData(e.currentTarget);
        const data: AssessmentFormData = {
            name: form.get('name') as string,
            email: form.get('email') as string,
            company: form.get('company') as string,
            role: form.get('role') as string,
            facilityCount: form.get('facilityCount') as string,
            phone: form.get('phone') as string,
            quizScore: lastScore.score,
            quizGrade: lastScore.grade,
            quizAnswers: lastAnswers,
            source: 'recall-readiness',
        };
        const result = await submitAssessment(data);
        setSubmitting(false);
        if (result.success) {
            setLeadSubmitted(true);
        } else {
            setSubmitError(result.error || 'Something went wrong.');
        }
    };

    const evaluateResults = (answers: Record<string, any>) => {
        const { score: totalScore, grade } = calcScore(answers);
        // Store for lead form
        if (lastScore.score !== totalScore) {
            setLastScore({ score: totalScore, grade });
            setLastAnswers(answers);
        }

        const gaps: string[] = [];
        if (answers.pull_24h !== 'yes') gaps.push('Gap indicated: self-reported inability to assemble required records within 24 hours (21 CFR §1.1455(c)(1))');
        if (answers.sortable_spreadsheet !== 'yes') gaps.push('Gap indicated: no electronic sortable spreadsheet workflow reported (21 CFR §1.1455(c)(3)(ii))');
        if (answers.digital_search !== 'yes') gaps.push('Risk indicated: manual/paper records make a 24-hour assembly harder');
        if (answers.tlc_stability === 'no') gaps.push('Gap indicated: TLC stability concern reported — risks data linkage breaks');
        if (answers.cte_coverage === 'no') gaps.push('Gap indicated: missing Critical Tracking Event recordkeeping for your role');

        const gapCount = gaps.length;
        // Non-verdict indicator: it counts what the operator told us was missing.
        // It is never a letter grade, a percentage or a pass/fail mark.
        const indicatorRing = gapCount === 0
            ? 'border-re-border-strong text-re-text-primary'
            : 'border-re-warning text-re-warning';

        return (
            <div className="space-y-8">
                <div className="py-6 text-center">
                    <motion.div
                        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.18 }}
                        className={cn(
                            'mb-4 inline-flex h-24 w-24 items-center justify-center rounded-full border-2',
                            indicatorRing
                        )}
                    >
                        <span className="px-2 text-center text-heading leading-tight">
                            {gapCount === 0 ? 'No gaps' : `${gapCount} gap${gapCount === 1 ? '' : 's'}`}
                        </span>
                    </motion.div>
                    <h3 className="text-heading text-re-text-primary">Self-Check Result</h3>
                    <p className="mt-1 text-ui text-re-text-tertiary">Based on your self-reported answers — not a compliance verdict.</p>
                </div>

                {/* Lead capture form - gate detailed results */}
                {!leadSubmitted && (
                    <Card>
                        <CardContent className="p-6">
                            <div className="mb-5 text-center">
                                <h3 className="text-subheading text-re-text-primary">Get a follow-up from the RegEngine team</h3>
                                <p className="mt-1 text-small text-re-text-tertiary">
                                    Share your details if you want a follow-up from the RegEngine team about your readiness results and next steps.
                                </p>
                            </div>
                            <form onSubmit={handleLeadSubmit} className="space-y-3">
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="rr-name" className="sr-only">Full Name</label>
                                        <Input id="rr-name" name="name" required placeholder="Full Name" size="lg" />
                                    </div>
                                    <div>
                                        <label htmlFor="rr-email" className="sr-only">Work Email</label>
                                        <Input id="rr-email" name="email" type="email" required placeholder="Work Email" size="lg" />
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="rr-company" className="sr-only">Company Name</label>
                                        <Input id="rr-company" name="company" required placeholder="Company Name" size="lg" />
                                    </div>
                                    <div>
                                        <label htmlFor="rr-role" className="sr-only">Your Role</label>
                                        <select id="rr-role" name="role" className={cn(fieldControlClasses, 'h-11')}>
                                            <option value="">Your Role</option>
                                            <option value="qa-food-safety">QA / Food Safety</option>
                                            <option value="operations">Operations</option>
                                            <option value="compliance">Compliance / Regulatory</option>
                                            <option value="supply-chain">Supply Chain</option>
                                            <option value="executive">Executive / Owner</option>
                                            <option value="it">IT / Engineering</option>
                                            <option value="other">Other</option>
                                        </select>
                                    </div>
                                </div>
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                                    <div>
                                        <label htmlFor="rr-facility-count" className="sr-only">Number of Facilities</label>
                                        <select id="rr-facility-count" name="facilityCount" className={cn(fieldControlClasses, 'h-11')}>
                                            <option value="">Number of Facilities</option>
                                            <option value="1">1 facility</option>
                                            <option value="2-5">2–5 facilities</option>
                                            <option value="6-20">6–20 facilities</option>
                                            <option value="20+">20+ facilities</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label htmlFor="rr-phone" className="sr-only">Phone (optional)</label>
                                        <Input id="rr-phone" name="phone" type="tel" placeholder="Phone (optional)" size="lg" />
                                    </div>
                                </div>
                                {submitError && (
                                    <Callout tone="danger" role="alert">{submitError}</Callout>
                                )}
                                <Button
                                    type="submit"
                                    size="lg"
                                    loading={submitting}
                                    trailingIcon={<ArrowRight aria-hidden="true" strokeWidth={1.75} />}
                                    className="mt-2 w-full"
                                >
                                    {submitting ? 'Submitting...' : 'Send Me My Self-Check Summary'}
                                </Button>
                                <p className="text-center text-label tracking-normal text-re-text-muted">We&apos;ll only use your details to follow up on this self-check. See our Privacy Policy.</p>
                            </form>
                        </CardContent>
                    </Card>
                )}

                {/* Detailed results - shown after lead capture */}
                {leadSubmitted && (
                    <>
                        <Callout tone="success" role="status" icon={CheckCircle2}>
                            Self-check submitted. We&apos;ll follow up with notes on your self-reported answers. This is not a compliance determination.
                        </Callout>

                        {gaps.length > 0 && (
                            <div className="space-y-4">
                                <h4 className="text-label text-re-text-muted">Self-Reported Gaps</h4>
                                <div className="space-y-2">
                                    {gaps.map((gap, i) => (
                                        <Callout key={i} tone="warning" icon={AlertCircle}>
                                            {gap}
                                        </Callout>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                            <Callout tone="warning" role="note" icon={AlertTriangle} title="Regulatory Risks">
                                <ul className="space-y-3 text-small text-re-text-tertiary">
                                    <li>Potential citations for <a href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455" target="_blank" rel="noopener noreferrer" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">21 CFR §1.1455</a> violations</li>
                                    <li>Delayed response times during active recalls</li>
                                    <li>Operational chaos during FDA audits</li>
                                </ul>
                            </Callout>
                            <Card>
                                <CardContent>
                                    <h4 className="mb-3 text-subheading text-re-text-primary">RegEngine Platform</h4>
                                    <p className="mb-4 text-small leading-relaxed text-re-text-secondary">
                                        RegEngine helps teams organize KDEs and prepare sortable spreadsheet exports to support FSMA 204 records requests.
                                    </p>
                                    <Button asChild variant="secondary" size="sm" className="w-full">
                                        <a
                                            href="https://calendly.com/regengine/fsma-strategy-session"
                                            target="_blank"
                                            rel="noopener noreferrer"
                                        >
                                            Book a strategy call
                                        </a>
                                    </Button>
                                </CardContent>
                            </Card>
                        </div>

                        <div className="flex flex-col items-center gap-3 pt-4">
                            <Card className="w-full">
                                <CardContent className="text-center">
                                    <p className="mb-2 text-label text-re-text-muted">Recommended Next Step:</p>
                                    <Button asChild variant="secondary" size="lg" className="w-full gap-2">
                                        <Link href="/tools/kde-checker">
                                            Generate Your KDE Checklist <ArrowRight aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
                                        </Link>
                                    </Button>
                                </CardContent>
                            </Card>
                            <Link href="/tools" className="text-ui text-re-text-secondary underline underline-offset-[3px] decoration-re-border-strong hover:text-re-text-primary hover:decoration-re-brand">
                                Back to Toolkit Hub
                            </Link>
                        </div>
                    </>
                )}
            </div>
        );
    };

    return (
        <>
            <FSMAToolShell
                config={READINESS_TOOL_CONFIG}
                renderResults={evaluateResults}
            />

            <RelatedTools
                tools={FREE_TOOLS.filter(t => ['tlc-validator', 'drill-simulator', 'roi-calculator'].includes(t.id))}
            />
        </>
    );
}
