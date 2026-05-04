'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState, useEffect, useRef, useCallback } from 'react';
import { Mail, ArrowRight, Loader2, ChevronDown, ChevronUp } from 'lucide-react';

interface EmailGateProps {
    toolName: string;
    children: React.ReactNode;
}

type GateStep = 'checking' | 'email' | 'code' | 'verified';

/**
 * Email verification gate for free tools.
 *
 * Checks for the re_tool_access HTTP-only cookie on mount.
 * If missing, shows a modal requiring work email verification
 * before the tool content (children) is rendered.
 *
 * The modal cannot be dismissed — email is the cost of entry.
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

    // Check cookie on mount
    useEffect(() => {
        fetchWithCsrf('/api/tools/check-access', {
            signal: AbortSignal.timeout(4000),
        })
            .then((res) => res.json())
            .then((data) => setStep(data.hasAccess ? 'verified' : 'email'))
            .catch(() => setStep('email'));
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
                const res = await fetchWithCsrf('/api/tools/verify', {
                    method: 'POST',
                    signal: AbortSignal.timeout(12000),
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
                const res = await fetchWithCsrf('/api/tools/verify', {
                    method: 'POST',
                    signal: AbortSignal.timeout(12000),
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
            const res = await fetchWithCsrf('/api/tools/verify', {
                method: 'POST',
                signal: AbortSignal.timeout(12000),
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

    // Loading state while checking cookie
    if (step === 'checking') {
        return (
            <div className="flex items-center justify-center min-h-[40vh]">
                <Loader2 className="h-6 w-6 animate-spin text-[var(--re-text-muted)]" />
            </div>
        );
    }

    // Verified — render the tool
    if (step === 'verified') {
        return <>{children}</>;
    }

    // Gate modal
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
            <div className="w-full max-w-md bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl shadow-re-lg overflow-hidden">
                {/* Header */}
                <div className="px-6 pt-8 pb-2 text-center">
                    <div className="mx-auto mb-4 w-12 h-12 rounded-xl bg-[var(--re-brand-muted)] flex items-center justify-center">
                        <Mail className="h-6 w-6 text-[var(--re-brand)]" />
                    </div>
                    <h2 className="font-display text-xl font-bold text-[var(--re-text-primary)] mb-1">
                        Unlock free compliance tools
                    </h2>
                    <p className="text-sm text-[var(--re-text-tertiary)]">
                        {step === 'email'
                            ? 'Enter your work email — no account required, no credit card, no spam.'
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
                                    autoFocus
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
        </div>
    );
}
