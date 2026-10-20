'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import Link from 'next/link';
import { useState, useEffect, useRef, useCallback } from 'react';
import { ArrowRight, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Field } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { getConversionAttribution, trackEmailCaptureSubmit } from '@/lib/conversion-events';

function verificationErrorCode(status: number): 'validation' | 'rate_limited' | 'server' {
    if (status === 400 || status === 422) return 'validation';
    if (status === 429) return 'rate_limited';
    return 'server';
}

interface EmailGateProps {
    toolName: string;
    children: React.ReactNode;
}

type GateStep = 'checking' | 'email' | 'code' | 'verified';

const TOOL_RESULT_LABELS: Record<string, string> = {
    ask: 'AI traceability answers',
    'cte-mapper': 'CTE map',
    'data-import': 'import mapping report',
    'drill-simulator': 'recall drill result',
    export: 'FDA export package',
    'fsma-unified': 'cold-chain anomaly report',
    'ftl-checker': 'FTL coverage result',
    'kde-checker': 'KDE checklist',
    'knowledge-graph': 'traceability graph',
    'label-scanner': 'label scan result',
    'notice-validator': 'FDA request review',
    'obligation-scanner': 'obligation scan',
    'readiness-assessment': 'readiness assessment',
    'recall-readiness': 'recall readiness score',
    'retailer-readiness': 'retailer readiness assessment',
    'roi-calculator': 'ROI calculation',
    scan: 'GS1 scan result',
    'sop-generator': 'SOP draft',
    'tlc-validator': 'TLC validation result',
};

async function fetchWithCsrfTimeout(
    input: RequestInfo | URL,
    options: RequestInit = {},
    timeoutMs = 12000,
) {
    if (typeof AbortController === 'undefined') {
        return fetchWithCsrf(input, options);
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetchWithCsrf(input, {
            ...options,
            signal: controller.signal,
        });
    } finally {
        window.clearTimeout(timeoutId);
    }
}

/**
 * Optional email verification panel for free tools.
 *
 * Checks for the re_tool_access HTTP-only cookie on mount.
 * Tool content is always rendered first so public pages have meaningful SSR
 * HTML for visitors, crawlers, and no-JS fallbacks.
 */
export function EmailGate({ toolName, children }: EmailGateProps) {
    const [step, setStep] = useState<GateStep>('checking');
    const [email, setEmail] = useState('');
    const [code, setCode] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [resendCountdown, setResendCountdown] = useState(0);
    const [whyExpanded, setWhyExpanded] = useState(false);

    const codeInputRef = useRef<HTMLInputElement>(null);
    const resultLabel = TOOL_RESULT_LABELS[toolName] ?? 'free-tool result';

    // Check cookie on mount
    useEffect(() => {
        let cancelled = false;

        fetchWithCsrfTimeout('/api/tools/check-access', {}, 4000)
            .then((res) => res.json())
            .then((data) => {
                if (!cancelled) setStep(data.hasAccess ? 'verified' : 'email');
            })
            .catch(() => {
                if (!cancelled) setStep('email');
            });

        return () => {
            cancelled = true;
        };
    }, []);

    // Resend countdown timer
    useEffect(() => {
        if (resendCountdown <= 0) return;
        const t = setTimeout(() => setResendCountdown((c) => c - 1), 1000);
        return () => clearTimeout(t);
    }, [resendCountdown]);

    // Auto-focus code input
    useEffect(() => {
        if (step === 'code') codeInputRef.current?.focus();
    }, [step]);

    const handleEmailSubmit = useCallback(
        async (e: React.FormEvent) => {
            e.preventDefault();
            setError('');
            setLoading(true);

            try {
                const res = await fetchWithCsrfTimeout('/api/tools/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: 'verify',
                        email: email.trim(),
                        tool_name: toolName,
                        source_url: window.location.href,
                        ...getConversionAttribution(),
                    }),
                });

                const data = await res.json();
                if (!res.ok) {
                    trackEmailCaptureSubmit({ form: 'email_gate', step: 'verify', tool: toolName, outcome: 'error', error_code: verificationErrorCode(res.status) });
                    setError(data.error || 'Something went wrong. Please try again.');
                    return;
                }

                trackEmailCaptureSubmit({ form: 'email_gate', step: 'verify', tool: toolName, outcome: 'success' });
                setStep('code');
                setResendCountdown(30);
            } catch {
                trackEmailCaptureSubmit({ form: 'email_gate', step: 'verify', tool: toolName, outcome: 'error', error_code: 'server' });
                setError('Network error. Please check your connection.');
            } finally {
                setLoading(false);
            }
        },
        [email, toolName],
    );

    const handleCodeSubmit = useCallback(
        async (submittedCode: string) => {
            if (submittedCode.length !== 6) return;
            setError('');
            setLoading(true);

            try {
                const res = await fetchWithCsrfTimeout('/api/tools/verify', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        action: 'confirm',
                        email: email.trim(),
                        code: submittedCode,
                        tool_name: toolName,
                    }),
                });

                const data = await res.json();
                if (!res.ok || data.status !== 'verified') {
                    trackEmailCaptureSubmit({ form: 'email_gate', step: 'confirm', tool: toolName, outcome: 'error', error_code: verificationErrorCode(res.status) });
                    setError(data.error || 'Invalid code. Please try again.');
                    setCode('');
                    codeInputRef.current?.focus();
                    return;
                }

                trackEmailCaptureSubmit({ form: 'email_gate', step: 'confirm', tool: toolName, outcome: 'success' });
                setStep('verified');
            } catch {
                trackEmailCaptureSubmit({ form: 'email_gate', step: 'confirm', tool: toolName, outcome: 'error', error_code: 'server' });
                setError('Network error. Please check your connection.');
            } finally {
                setLoading(false);
            }
        },
        [email, toolName],
    );

    const handleCodeChange = useCallback(
        (value: string) => {
            const digits = value.replace(/\D/g, '').slice(0, 6);
            setCode(digits);
            if (digits.length === 6) handleCodeSubmit(digits);
        },
        [handleCodeSubmit],
    );

    const handleResend = useCallback(async () => {
        if (resendCountdown > 0) return;
        setError('');
        setLoading(true);

        try {
            const res = await fetchWithCsrfTimeout('/api/tools/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    action: 'verify',
                    email: email.trim(),
                    tool_name: toolName,
                    ...getConversionAttribution(),
                }),
            });

            if (!res.ok) {
                trackEmailCaptureSubmit({ form: 'email_gate', step: 'verify', tool: toolName, outcome: 'error', error_code: verificationErrorCode(res.status) });
                const data = await res.json();
                setError(data.error || 'Failed to resend code.');
                return;
            }

            trackEmailCaptureSubmit({ form: 'email_gate', step: 'verify', tool: toolName, outcome: 'success' });
            setResendCountdown(30);
            setCode('');
        } catch {
            trackEmailCaptureSubmit({ form: 'email_gate', step: 'verify', tool: toolName, outcome: 'error', error_code: 'server' });
            setError('Network error.');
        } finally {
            setLoading(false);
        }
    }, [email, toolName, resendCountdown]);

    // Verified or still checking — render only the public tool/page content.
    if (step === 'verified' || step === 'checking') {
        return <>{children}</>;
    }

    return (
        <>
            {children}
            <section className="mx-auto my-10 w-full max-w-xl px-4">
                <Card className="w-full overflow-hidden">
                    {/* Header */}
                    <div className="px-6 pb-2 pt-8 text-center">
                        <h2 className="mb-1 text-heading text-re-text-primary">
                            Save your {resultLabel}
                        </h2>
                        <p className="text-ui text-re-text-tertiary">
                            {step === 'email'
                                ? 'Enter your work email to save results and receive a verification code. No account required, no credit card, no spam.'
                                : (
                                    <>
                                        Check your inbox. We sent a 6-digit code to{' '}
                                        <span className="font-medium text-re-text-primary">{email}</span>
                                    </>
                                )}
                        </p>
                    </div>

                    {/* Body */}
                    <div className="px-6 py-5">
                        {step === 'email' ? (
                            <form onSubmit={handleEmailSubmit} className="space-y-4">
                                <Field label="Work email" htmlFor="email-gate-email" error={error || undefined}>
                                    <Input
                                        type="email"
                                        size="lg"
                                        value={email}
                                        onChange={(e) => {
                                            setEmail(e.target.value);
                                            if (error) setError('');
                                        }}
                                        placeholder="you@company.com"
                                        required
                                        autoComplete="email"
                                    />
                                </Field>

                                <Button
                                    type="submit"
                                    size="lg"
                                    className="w-full"
                                    disabled={loading || !email.includes('@')}
                                    loading={loading}
                                    trailingIcon={<ArrowRight strokeWidth={1.75} aria-hidden="true" />}
                                >
                                    Send verification code
                                </Button>
                                <div className="text-center">
                                    <Link
                                        href="/tools"
                                        className="text-small text-re-text-muted underline-offset-4 hover:text-re-text-secondary hover:underline"
                                    >
                                        Back to tools
                                    </Link>
                                </div>
                            </form>
                        ) : (
                            <div className="space-y-4">
                                <Field label="Verification code" htmlFor="email-gate-code" error={error || undefined}>
                                    <Input
                                        ref={codeInputRef}
                                        type="text"
                                        size="lg"
                                        inputMode="numeric"
                                        value={code}
                                        onChange={(e) => handleCodeChange(e.target.value)}
                                        placeholder="000000"
                                        maxLength={6}
                                        autoComplete="one-time-code"
                                        className="text-center font-mono text-heading tracking-[0.5em]"
                                    />
                                </Field>

                                {loading && (
                                    <div className="flex justify-center">
                                        <Loader2
                                            className="h-5 w-5 animate-spin text-re-text-tertiary motion-reduce:animate-none"
                                            aria-hidden="true"
                                        />
                                    </div>
                                )}

                                <div className="flex items-center justify-between gap-2">
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => {
                                            setStep('email');
                                            setCode('');
                                            setError('');
                                        }}
                                    >
                                        Change email
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="link"
                                        size="sm"
                                        onClick={handleResend}
                                        disabled={resendCountdown > 0}
                                    >
                                        {resendCountdown > 0
                                            ? `Resend in ${resendCountdown}s`
                                            : 'Resend code'}
                                    </Button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Why do we ask? */}
                    <div className="px-6 pb-6">
                        <button
                            type="button"
                            aria-expanded={whyExpanded}
                            onClick={() => setWhyExpanded(!whyExpanded)}
                            className="flex items-center gap-1.5 rounded-sm text-small text-re-text-muted transition-colors duration-120 hover:text-re-text-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                        >
                            {whyExpanded ? (
                                <ChevronUp className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                            ) : (
                                <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                            )}
                            Why do we ask?
                        </button>
                        {whyExpanded && (
                            <p className="mt-2 text-small text-re-text-muted">
                                We use your work email to verify you&apos;re a food industry professional.
                                Your email is never sold or shared. You&apos;ll receive your verification
                                code and nothing else.
                            </p>
                        )}
                    </div>
                </Card>
            </section>
        </>
    );
}
