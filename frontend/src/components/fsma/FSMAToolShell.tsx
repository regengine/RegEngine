'use client';

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams } from 'next/navigation';
import { usePostHog } from '@/lib/posthog-provider';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { ChevronRight, ChevronLeft, Lock, Mail, ArrowRight, CheckCircle2 } from 'lucide-react';
import { isValidEmail } from '@/lib/validation';
import { ToolConfig, ToolStatus, LeadData } from '@/types/fsma-tools';
import { cn } from '@/lib/utils';
import {
    FSMA_204_COMPLIANCE_DATE,
    FSMA_204_ENFORCEMENT_FLOOR,
    FSMA_204_CITATION
} from '@/lib/fsma-tools-data';

const CALENDLY_LINK = 'https://calendly.com/regengine/fsma-strategy-session';

interface FSMAToolShellProps {
    config: ToolConfig;
    onLeadCapture?: (lead: LeadData) => void;
    renderResults: (answers: Record<string, any>) => React.ReactNode;
}

/** Question option rows share the Input/Card surface language (SPEC §4). */
const optionClasses = (selected: boolean) =>
    cn(
        'w-full rounded-md border p-4 text-left text-ui transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card motion-reduce:transition-none',
        selected
            ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
            : 'border-re-border bg-re-surface-card text-re-text-secondary hover:border-re-border-strong hover:bg-re-surface-inset'
    );

export function FSMAToolShell({ config, onLeadCapture, renderResults }: FSMAToolShellProps) {
    const [status, setStatus] = useState<ToolStatus>('START');
    const [currentStep, setCurrentStep] = useState(0);
    const [answers, setAnswers] = useState<Record<string, any>>({});
    const [showLeadGate, setShowLeadGate] = useState(false);
    const [email, setEmail] = useState('');

    const questions = config.stages.questions;
    const progress = ((currentStep + 1) / questions.length) * 100;
    const posthog = usePostHog();
    const searchParams = useSearchParams();

    const utmParams = useMemo(() => ({
        utm_source: searchParams.get('utm_source'),
        utm_medium: searchParams.get('utm_medium'),
        utm_campaign: searchParams.get('utm_campaign'),
        utm_content: searchParams.get('utm_content'),
        utm_term: searchParams.get('utm_term'),
    }), [searchParams]);

    const trackToolEvent = (eventName: string, metadata: Record<string, unknown> = {}) => {
        posthog.capture(`${config.id}_${eventName}`, {
            ...metadata,
            ...utmParams,
            tool_id: config.id,
            tool_title: config.title,
            timestamp: new Date().toISOString()
        });
    };

    const handleNext = () => {
        if (currentStep < questions.length - 1) {
            setCurrentStep(prev => prev + 1);
        } else {
            if (config.stages.leadGate) {
                setShowLeadGate(true);
            } else {
                setStatus('RESULTS');
            }
        }
    };

    const toggleAnswer = (questionId: string, value: string | number | boolean) => {
        setAnswers(prev => {
            const current = prev[questionId] || [];
            const updated = current.includes(value)
                ? current.filter((v: string | number | boolean) => v !== value)
                : [...current, value];
            return { ...prev, [questionId]: updated };
        });
    };

    const handleBack = () => {
        if (currentStep > 0) {
            setCurrentStep(prev => prev - 1);
        } else {
            setStatus('START');
        }
    };

    /**
     * Derive an intent score (0–100) for the lead.
     * Uses config.scoring when provided; otherwise approximates from answer
     * coverage (answered questions / total questions * 100), rounded to the
     * nearest integer. Returns null when no answers have been recorded yet.
     */
    const deriveIntentScore = (): number | null => {
        if (config.scoring) {
            const result = config.scoring(answers);
            if (typeof result === 'number' && isFinite(result)) {
                return Math.max(0, Math.min(100, Math.round(result)));
            }
        }
        const totalQuestions = config.stages.questions.length;
        if (totalQuestions === 0) return null;
        const answeredCount = Object.keys(answers).length;
        if (answeredCount === 0) return null;
        return Math.round(Math.min(answeredCount / totalQuestions, 1) * 100);
    };

    const submitLead = () => {
        if (onLeadCapture) {
            const intentScore = deriveIntentScore();
            onLeadCapture({
                email,
                toolId: config.id,
                intentScore: intentScore ?? 0,
                resultsSummary: 'User completed the flow',
                answers
            });
        }
        trackToolEvent('LEAD_CAPTURE', { email });
        setStatus('RESULTS');
    };

    return (
        <Card className="mx-auto max-w-3xl overflow-hidden">
            <AnimatePresence mode="wait">
                {status === 'START' && (
                    <motion.div
                        key="start"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className="space-y-6 p-6 sm:p-8"
                    >
                        <div>
                            <h1 className="text-title text-re-text-primary">{config.title}</h1>
                            <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">{config.description}</p>
                        </div>
                        <div className="border-y border-re-border-subtle py-4">
                            <p className="text-small italic text-re-text-muted">
                                Informational purposes only. This tool does not constitute legal advice.
                                Your compliance obligations depend on specific facts and FDA exemptions.
                            </p>
                        </div>
                        <Card variant="inset" className="space-y-2 p-4 text-left">
                            <p className="font-mono uppercase text-label text-re-text-muted">Regulatory Context</p>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="font-mono uppercase text-label text-re-text-muted">Compliance Date</p>
                                    <p className="mt-0.5 text-ui font-medium text-re-text-primary">{FSMA_204_COMPLIANCE_DATE}</p>
                                </div>
                                <div>
                                    <p className="font-mono uppercase text-label text-re-text-muted">Enforcement Floor</p>
                                    <p className="mt-0.5 text-ui font-medium text-re-text-primary">{FSMA_204_ENFORCEMENT_FLOOR}</p>
                                </div>
                            </div>
                            <p className="pt-1 text-small italic text-re-text-muted">
                                Reference: {FSMA_204_CITATION}
                            </p>
                        </Card>
                        <Button
                            size="lg"
                            className="w-full"
                            trailingIcon={<ChevronRight strokeWidth={1.75} aria-hidden="true" />}
                            onClick={() => {
                                setStatus('QUESTIONS');
                                trackToolEvent('TOOL_START');
                            }}
                        >
                            Start Tool
                        </Button>
                    </motion.div>
                )}

                {status === 'QUESTIONS' && !showLeadGate && (
                    <motion.div
                        key="questions"
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        className="space-y-6 p-6 sm:p-8"
                    >
                        <div className="space-y-2">
                            <div className="flex justify-between text-small text-re-text-muted">
                                <span>Step {currentStep + 1} of {questions.length}</span>
                                <span className="tabular-nums">{Math.round(progress)}% Complete</span>
                            </div>
                            <Progress value={progress} className="h-1.5" />
                        </div>

                        <div className="flex min-h-[200px] flex-col justify-center">
                            <h3 className="mb-6 text-heading text-re-text-primary">
                                {questions[currentStep].text}
                            </h3>

                            <div className="space-y-3">
                                {questions[currentStep].type === 'select' && questions[currentStep].options?.map(opt => (
                                    <button
                                        key={String(opt.value)}
                                        type="button"
                                        onClick={() => {
                                            setAnswers(prev => ({ ...prev, [questions[currentStep].id]: opt.value }));
                                            handleNext();
                                        }}
                                        className={optionClasses(answers[questions[currentStep].id] === opt.value)}
                                    >
                                        <div className="flex items-center justify-between gap-3">
                                            <span className="font-medium">{opt.label}</span>
                                            <ArrowRight
                                                className="h-4 w-4 shrink-0 text-re-text-tertiary"
                                                strokeWidth={1.75}
                                                aria-hidden="true"
                                            />
                                        </div>
                                    </button>
                                ))}

                                {questions[currentStep].type === 'text' && (
                                    <div className="space-y-4">
                                        <Field
                                            label={questions[currentStep].text}
                                            htmlFor={`fsma-tool-${questions[currentStep].id}`}
                                            className="[&>label]:sr-only"
                                        >
                                            <Input
                                                size="lg"
                                                placeholder={questions[currentStep].placeholder || 'Type here...'}
                                                value={answers[questions[currentStep].id] || ''}
                                                onChange={(e) => setAnswers(prev => ({ ...prev, [questions[currentStep].id]: e.target.value }))}
                                                autoFocus
                                            />
                                        </Field>
                                        {questions[currentStep].hint && (
                                            <p className="text-small italic text-re-text-muted">{questions[currentStep].hint}</p>
                                        )}
                                    </div>
                                )}

                                {questions[currentStep].type === 'multi-select' && questions[currentStep].options?.map(opt => {
                                    const isSelected = (answers[questions[currentStep].id] || []).includes(opt.value);
                                    return (
                                        <button
                                            key={String(opt.value)}
                                            type="button"
                                            aria-pressed={isSelected}
                                            onClick={() => toggleAnswer(questions[currentStep].id, opt.value)}
                                            className={optionClasses(isSelected)}
                                        >
                                            <div className="flex items-center justify-between gap-3">
                                                <span className="font-medium">{opt.label}</span>
                                                {isSelected && (
                                                    <CheckCircle2
                                                        className="h-4 w-4 shrink-0 text-re-text-primary"
                                                        strokeWidth={1.75}
                                                        aria-hidden="true"
                                                    />
                                                )}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        <div className="flex justify-between pt-4">
                            <Button
                                variant="ghost"
                                onClick={handleBack}
                                leadingIcon={<ChevronLeft strokeWidth={1.75} aria-hidden="true" />}
                            >
                                Back
                            </Button>
                            {(questions[currentStep].type === 'multi-select' || questions[currentStep].type === 'text') && (
                                <Button
                                    onClick={handleNext}
                                    trailingIcon={<ChevronRight strokeWidth={1.75} aria-hidden="true" />}
                                    disabled={
                                        questions[currentStep].type === 'multi-select'
                                            ? !(answers[questions[currentStep].id]?.length > 0)
                                            : !answers[questions[currentStep].id]
                                    }
                                >
                                    Next
                                </Button>
                            )}
                        </div>
                    </motion.div>
                )}

                {showLeadGate && (
                    <motion.div
                        key="lead"
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="space-y-6 p-6 text-center sm:p-8"
                    >
                        <Mail
                            className="mx-auto h-6 w-6 text-re-text-tertiary"
                            strokeWidth={1.75}
                            aria-hidden="true"
                        />
                        <h3 className="text-heading text-re-text-primary">{config.stages.leadGate?.title}</h3>
                        <p className="text-ui text-re-text-secondary">{config.stages.leadGate?.description}</p>

                        <div className="mx-auto max-w-md space-y-4 text-left">
                            <Field label="Work email" htmlFor="fsma-tool-lead-email" className="[&>label]:sr-only">
                                <Input
                                    type="email"
                                    size="lg"
                                    placeholder="you@company.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                />
                            </Field>
                            <Button
                                size="lg"
                                className="w-full"
                                disabled={!isValidEmail(email)}
                                trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                                onClick={submitLead}
                            >
                                {config.stages.leadGate?.cta}
                            </Button>
                            <div className="text-center">
                                <Button
                                    variant="link"
                                    size="sm"
                                    className="text-re-text-muted"
                                    onClick={() => setStatus('RESULTS')}
                                >
                                    Skip to results
                                </Button>
                            </div>
                        </div>
                    </motion.div>
                )}

                {status === 'RESULTS' && (
                    <motion.div
                        key="results"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="p-6 sm:p-8"
                    >
                        {renderResults(answers)}

                        <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-re-border-subtle pt-6">
                            <Button variant="secondary" onClick={() => {
                                setStatus('START');
                                setAnswers({});
                                setCurrentStep(0);
                                setShowLeadGate(false);
                                trackToolEvent('TOOL_RESTART');
                            }}>
                                Restart Tool
                            </Button>
                            <div className="flex items-center gap-4">
                                <Button
                                    onClick={() => {
                                        trackToolEvent('DEMO_CLICK');
                                        window.open(CALENDLY_LINK, '_blank');
                                    }}
                                >
                                    Book a Demo
                                </Button>
                                <div className="hidden items-center gap-2 text-small text-re-text-muted sm:flex">
                                    <Lock className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" /> Secure and Private
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </Card >
    );
}
