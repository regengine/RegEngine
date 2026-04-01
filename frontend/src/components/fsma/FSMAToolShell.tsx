'use client';

import { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useSearchParams } from 'next/navigation';
import { usePostHog } from 'posthog-js/react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Shield, ChevronRight, ChevronLeft, Lock, Mail, ArrowRight, CheckCircle2 } from 'lucide-react';
import { isValidEmail } from '@/lib/validation';
import { ToolConfig, ToolStatus, LeadData } from '@/types/fsma-tools';
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
        <Card className="max-w-3xl mx-auto border-[var(--re-border-default)] bg-[var(--re-surface-card)] overflow-hidden">
            <AnimatePresence mode="wait">
                {status === 'START' && (
                    <motion.div
                        key="start"
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -20 }}
                        className="p-8 space-y-6"
                    >
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-xl bg-[var(--re-brand-muted)]">
                                <Shield className="h-8 w-8 text-[var(--re-brand)]" />
                            </div>
                            <div>
                                <CardTitle className="text-3xl font-bold">{config.title}</CardTitle>
                                <p className="text-[var(--re-text-tertiary)] mt-1">{config.description}</p>
                            </div>
                        </div>
                        <div className="py-4 border-y border-[var(--re-border-default)]">
                            <p className="text-sm italic text-[var(--re-text-muted)]">
                                Informational purposes only. This tool does not constitute legal advice.
                                Your compliance obligations depend on specific facts and FDA exemptions.
                            </p>
                        </div>
                        <div className="p-4 rounded-xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 text-left space-y-2">
                            <p className="text-[10px] uppercase font-bold text-[var(--re-brand)] tracking-widest">Regulatory Context</p>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <p className="text-[9px] text-[var(--re-text-muted)] uppercase">Compliance Date</p>
                                    <p className="text-xs font-semibold">{FSMA_204_COMPLIANCE_DATE}</p>
                                </div>
                                <div>
                                    <p className="text-[9px] text-[var(--re-text-muted)] uppercase">Enforcement Floor</p>
                                    <p className="text-xs font-semibold">{FSMA_204_ENFORCEMENT_FLOOR}</p>
                                </div>
                            </div>
                            <p className="text-[9px] text-[var(--re-text-muted)] italic pt-1">
                                Reference: {FSMA_204_CITATION}
                            </p>
                        </div>
                        <Button
                            className="w-full h-12 text-lg bg-[var(--re-brand)] hover:brightness-110"
                            onClick={() => {
                                setStatus('QUESTIONS');
                                trackToolEvent('TOOL_START');
                            }}
                        >
                            Start Tool <ChevronRight className="ml-2 h-5 w-5" />
                        </Button>
                    </motion.div>
                )}

                {status === 'QUESTIONS' && !showLeadGate && (
                    <motion.div
                        key="questions"
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: -20 }}
                        className="p-8 space-y-6"
                    >
                        <div className="space-y-2">
                            <div className="flex justify-between text-xs text-[var(--re-text-muted)]">
                                <span>Step {currentStep + 1} of {questions.length}</span>
                                <span>{Math.round(progress)}% Complete</span>
                            </div>
                            <Progress value={progress} className="h-1.5" />
                        </div>

                        <div className="min-h-[200px] flex flex-col justify-center">
                            <h3 className="text-xl font-semibold mb-6">
                                {questions[currentStep].text}
                            </h3>

                            <div className="space-y-3">
                                {questions[currentStep].type === 'select' && questions[currentStep].options?.map(opt => (
                                    <button
                                        key={String(opt.value)}
                                        onClick={() => {
                                            setAnswers(prev => ({ ...prev, [questions[currentStep].id]: opt.value }));
                                            handleNext();
                                        }}
                                        className={`w-full p-4 rounded-xl text-left border transition-all duration-200 ${answers[questions[currentStep].id] === opt.value
                                            ? 'border-[var(--re-brand)] bg-[var(--re-brand-muted)] text-[var(--re-brand)]'
                                            : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-border-subtle)]'
                                            }`}
                                    >
                                        <div className="flex justify-between items-center">
                                            <span className="font-medium">{opt.label}</span>
                                            <ArrowRight className="h-4 w-4 opacity-0 group-hover:opacity-100" />
                                        </div>
                                    </button>
                                ))}

                                {questions[currentStep].type === 'text' && (
                                    <div className="space-y-4">
                                        <Input
                                            placeholder={questions[currentStep].placeholder || 'Type here...'}
                                            value={answers[questions[currentStep].id] || ''}
                                            onChange={(e) => setAnswers(prev => ({ ...prev, [questions[currentStep].id]: e.target.value }))}
                                            className="h-12 border-[var(--re-border-default)] focus:border-[var(--re-brand)]"
                                            autoFocus
                                        />
                                        {questions[currentStep].hint && (
                                            <p className="text-xs text-[var(--re-text-muted)] italic">{questions[currentStep].hint}</p>
                                        )}
                                    </div>
                                )}

                                {questions[currentStep].type === 'multi-select' && questions[currentStep].options?.map(opt => {
                                    const isSelected = (answers[questions[currentStep].id] || []).includes(opt.value);
                                    return (
                                        <button
                                            key={String(opt.value)}
                                            onClick={() => toggleAnswer(questions[currentStep].id, opt.value)}
                                            className={`w-full p-4 rounded-xl text-left border transition-all duration-200 ${isSelected
                                                ? 'border-[var(--re-brand)] bg-[var(--re-brand-muted)] text-[var(--re-brand)]'
                                                : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-border-subtle)]'
                                                }`}
                                        >
                                            <div className="flex justify-between items-center">
                                                <span className="font-medium">{opt.label}</span>
                                                {isSelected && <CheckCircle2 className="h-4 w-4 text-[var(--re-brand)]" />}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                        </div>

                        <div className="flex justify-between pt-4">
                            <Button variant="ghost" onClick={handleBack}>
                                <ChevronLeft className="mr-2 h-4 w-4" /> Back
                            </Button>
                            {(questions[currentStep].type === 'multi-select' || questions[currentStep].type === 'text') && (
                                <Button
                                    onClick={handleNext}
                                    disabled={
                                        questions[currentStep].type === 'multi-select'
                                            ? !(answers[questions[currentStep].id]?.length > 0)
                                            : !answers[questions[currentStep].id]
                                    }
                                >
                                    Next <ChevronRight className="ml-2 h-4 w-4" />
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
                        className="p-8 text-center space-y-6"
                    >
                        <div className="mx-auto w-16 h-16 rounded-full bg-[var(--re-info-muted)] flex items-center justify-center">
                            <Mail className="h-8 w-8 text-[var(--re-info)]" />
                        </div>
                        <h3 className="text-2xl font-bold">{config.stages.leadGate?.title}</h3>
                        <p className="text-[var(--re-text-tertiary)]">{config.stages.leadGate?.description}</p>

                        <div className="max-w-md mx-auto space-y-4">
                            <Input
                                type="email"
                                placeholder="you@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="h-12 border-[var(--re-border-default)]"
                            />
                            <Button
                                className="w-full h-12 bg-[var(--re-brand)]"
                                disabled={!isValidEmail(email)}
                                onClick={submitLead}
                            >
                                {config.stages.leadGate?.cta} <ArrowRight className="ml-2 h-4 w-4" />
                            </Button>
                            <button
                                className="text-xs text-[var(--re-text-muted)] hover:underline"
                                onClick={() => setStatus('RESULTS')}
                            >
                                Skip to results
                            </button>
                        </div>
                    </motion.div>
                )}

                {status === 'RESULTS' && (
                    <motion.div
                        key="results"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="p-8"
                    >
                        {renderResults(answers)}

                        <div className="mt-8 pt-6 border-t border-[var(--re-border-default)] flex justify-between items-center">
                            <Button variant="outline" onClick={() => {
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
                                    className="bg-[var(--re-brand)]"
                                    onClick={() => {
                                        trackToolEvent('DEMO_CLICK');
                                        window.open(CALENDLY_LINK, '_blank');
                                    }}
                                >
                                    Book a Demo
                                </Button>
                                <div className="hidden sm:flex items-center gap-2 text-xs text-[var(--re-text-muted)]">
                                    <Lock className="h-3 w-3" /> Secure and Private
                                </div>
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </Card >
    );
}
