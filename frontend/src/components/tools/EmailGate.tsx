'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import Link from 'next/link';
import { useState, useEffect, useRef, useCallback } from 'react';
import { Mail, ArrowRight, Loader2, ChevronDown, ChevronUp } from 'lucide-react';

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
                    }),
                });

                const data = await res.json();
                if (!res.ok) {
                    setError(data.error || 'Something went wrong. Please try again.');
                    return;
                }

                setStep('code');
                setResendCountdown(30);
            } catch {
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
                if (!res.ok) {
                    setError(data.error || 'Invalid code. Please try again.');
                    setCode('');
                    codeInputRef.current?.focus();
                    return;
                }

                setStep('verified');
            } catch {
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
                }),
            });

            if (!res.ok) {
                const data = await res.json();
                setError(data.error || 'Failed to resend code.');
                return;
            }

            setResendCountdown(30);
            setCode('');
        } catch {
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
                <div className="w-full overflow-hidden rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-re-lg">
                    {/* Header */}
                    <div className="px-6 pt-8 pb-2 text-center">
                        <div className="mx-auto mb-4 w-12 h-12 rounded-xl bg-[var(--re-brand-muted)] flex items-center justify-center">
                            <Mail className="h-6 w-6 text-[var(--re-brand)]" />
                        </div>
                        <h2 className="font-display text-xl font-bold text-[var(--re-text-primary)] mb-1">
                            Save your {resultLabel}
                        </h2>
                        <p className="text-sm text-[var(--re-text-tertiary)]">
                            {step === 'email'
                                ? 'Enter your work email to save results and receive a verification code. No account required, no credit card, no spam.'
                                : (
                                    <>
                                        Check your inbox — we sent a 6-digit code to{' '}
                                        <span className="text-[var(--re-text-primary)] font-medium">{email}</span>
                                    </>
                                )}
                        </p>
                    </div>

                    {/* Body */}
                    <div className="px-6 py-5">
                        {step === 'email' ? (
                            <form onSubmit={handleEmailSubmit} className="space-y-4">
                                <div>
                                    <input
                                        type="email"
                                        value={email}
                                        onChange={(e) => {
                                            setEmail(e.target.value);
                                            if (error) setError('');
                                        }}
                                        placeholder="you@company.com"
                                        required
                                        autoComplete="email"
                                        className="w-full px-4 py-3 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent transition-all"
                                    />
                                </div>

                                {error && (
                                    <p className="text-sm text-re-danger">{error}</p>
                                )}

                                <button
                                    type="submit"
                                    disabled={loading || !email.includes('@')}
                                    className="w-full flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-5 py-3 rounded-lg text-sm font-semibold hover:bg-[var(--re-brand-dark)] disabled:opacity-50 disabled:cursor-not-allowed transition-all min-h-[48px]"
                                >
                                    {loading ? (
                                        <Loader2 className="h-4 w-4 animate-spin" />
                                    ) : (
                                        <>
                                            Send verification code
                                            <ArrowRight className="h-4 w-4" />
                                        </>
                                    )}
                                </button>
                                <div className="text-center">
                                    <Link
                                        href="/tools"
                                        className="text-xs text-[var(--re-text-muted)] underline-offset-4 hover:text-[var(--re-text-secondary)] hover:underline"
                                    >
                                        Back to tools
                                    </Link>
                                </div>
                            </form>
                        ) : (
                            <div className="space-y-4">
                                <div>
                                    <input
                                        ref={codeInputRef}
                                        type="text"
                                        inputMode="numeric"
                                        value={code}
                                        onChange={(e) => handleCodeChange(e.target.value)}
                                        placeholder="000000"
                                        maxLength={6}
                                        autoComplete="one-time-code"
                                        className="w-full px-4 py-3 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] text-center text-xl font-mono tracking-[0.5em] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:border-transparent transition-all"
                                    />
                                </div>

                                {error && (
                                    <p className="text-sm text-re-danger">{error}</p>
                                )}

                                {loading && (
                                    <div className="flex justify-center">
                                        <Loader2 className="h-5 w-5 animate-spin text-[var(--re-brand)]" />
                                    </div>
                                )}

                                <div className="flex items-center justify-between text-xs">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setStep('email');
                                            setCode('');
                                            setError('');
                                        }}
                                        className="text-[var(--re-text-muted)] hover:text-[var(--re-text-secondary)] transition-colors"
                                    >
                                        Change email
                                    </button>
                                    <button
                                        type="button"
                                        onClick={handleResend}
                                        disabled={resendCountdown > 0}
                                        className="text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] disabled:text-[var(--re-text-disabled)] disabled:cursor-not-allowed transition-colors"
                                    >
                                        {resendCountdown > 0
                                            ? `Resend in ${resendCountdown}s`
                                            : 'Resend code'}
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Why do we ask? */}
                    <div className="px-6 pb-6">
                        <button
                            type="button"
                            onClick={() => setWhyExpanded(!whyExpanded)}
                            className="flex items-center gap-1.5 text-xs text-[var(--re-text-muted)] hover:text-[var(--re-text-secondary)] transition-colors"
                        >
                            {whyExpanded ? (
                                <ChevronUp className="h-3 w-3" />
                            ) : (
                                <ChevronDown className="h-3 w-3" />
                            )}
                            Why do we ask?
                        </button>
                        {whyExpanded && (
                            <p className="mt-2 text-xs text-[var(--re-text-muted)] leading-relaxed">
                                We use your work email to verify you&apos;re a food industry professional.
                                Your email is never sold or shared. You&apos;ll receive your verification
                                code and nothing else.
                            </p>
                        )}
                    </div>
                </div>
            </section>
        </>
    );
}
