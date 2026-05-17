'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { createSupabaseBrowserClient, isSupabaseConfigured } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import {
    ArrowRight,
    CheckCircle2,
    Eye,
    EyeOff,
    Fingerprint,
    KeyRound,
    LayoutDashboard,
    LockKeyhole,
    Loader2,
    Mail,
    PackageCheck,
    ShieldCheck,
    TimerReset,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import type { LoginResponse } from '@/types/api';

// QA presets are code-split into a separate chunk via dynamic import.
// In production builds without the opt-in env var, the chunk is never
// loaded — removing preset code from the main bundle entirely.
const qaPresetsEnabled =
    process.env.NODE_ENV !== 'production' ||
    process.env.NEXT_PUBLIC_ENABLE_QA_LOGIN_PRESETS === '1';

const QALoginPresets = qaPresetsEnabled
    ? dynamic(() => import('./QALoginPresets'), { ssr: false })
    : null;

type AuthMode = 'password' | 'email-code';

function extractApiErrorMessage(data: unknown): string | null {
    if (typeof data === 'string') {
        return sanitizeErrorMessage(data);
    }

    if (!data || typeof data !== 'object') {
        return null;
    }

    const payload = data as { detail?: unknown; error?: unknown; message?: unknown };
    const candidate = payload.detail ?? payload.error ?? payload.message;
    if (typeof candidate !== 'string') {
        return null;
    }

    return sanitizeErrorMessage(candidate);
}

function sanitizeErrorMessage(message: string): string {
    const cleaned = message.replace(/\s+/g, ' ').trim();
    if (!cleaned) {
        return 'Authentication request failed';
    }
    return cleaned.length > 220 ? `${cleaned.slice(0, 217)}...` : cleaned;
}

function resolveSafeNextPath(nextPath: string | null): string | null {
    if (!nextPath) {
        return null;
    }

    const trimmed = nextPath.trim();
    if (!trimmed.startsWith('/') || trimmed.startsWith('//') || /[\u0000-\u001F\u007F\\]/.test(trimmed)) {
        return null;
    }

    try {
        const origin = typeof window !== 'undefined' && window.location?.origin
            ? window.location.origin
            : 'http://localhost';
        const parsed = new URL(trimmed, origin);
        if (parsed.origin !== origin) {
            return null;
        }

        const destination = `${parsed.pathname}${parsed.search}${parsed.hash}`;
        if (parsed.pathname === '/login' || parsed.pathname.startsWith('/login/')) {
            return null;
        }
        return destination;
    } catch {
        return null;
    }
}

function getStoredTenantId(): string | null {
    if (typeof window === 'undefined') {
        return null;
    }

    try {
        const storage = window.localStorage;
        if (!storage || typeof storage.getItem !== 'function') {
            return null;
        }
        return storage.getItem('regengine_tenant_id');
    } catch {
        return null;
    }
}

export default function LoginPage() {
    const [authMode, setAuthMode] = useState<AuthMode>('email-code');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [emailCode, setEmailCode] = useState('');
    const [isEmailCodeSent, setIsEmailCodeSent] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [isSessionSyncing, setIsSessionSyncing] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const searchParams = useSearchParams();
    const nextParam = searchParams.get('next');
    const { clearCredentials, login, user, isHydrated } = useAuth();
    const showQaPresets = Boolean(QALoginPresets && (searchParams.get('qa') === '1' || searchParams.get('preset')));
    const QaPresets = QALoginPresets;

    const applyPreset = useCallback((presetEmail: string) => {
        setEmail(presetEmail);
        setPassword('');
        setEmailCode('');
        setIsEmailCodeSent(false);
        setError(null);
    }, []);

    const handleEmailValueChange = useCallback((value: string) => {
        setEmail(value);
        if (authMode === 'email-code') {
            setEmailCode('');
            setIsEmailCodeSent(false);
        }
    }, [authMode]);

    useEffect(() => {
        if (!isHydrated || !user || isSessionSyncing) {
            return;
        }

        // If the middleware redirected here with an error flag, the user
        // needs to re-authenticate — do NOT auto-redirect back.
        const errorParam = searchParams.get('error');
        if (errorParam === 'session_expired' || errorParam === 'auth_config' || errorParam === 'token_invalid') {
            return;
        }

        const safeNextPath = resolveSafeNextPath(nextParam);
        if (safeNextPath) {
            router.push(safeNextPath);
            return;
        }

        if (user.is_sysadmin) {
            router.push('/sysadmin');
            return;
        }

        // Check onboarding status — redirect to setup if incomplete
        const tid = getStoredTenantId();
        if (tid) {
            apiClient.getOnboardingStatus(tid).then((status) => {
                if (!status.is_complete) {
                    router.push('/onboarding/setup/welcome');
                } else {
                    router.push('/dashboard');
                }
            }).catch(() => {
                router.push('/dashboard');
            });
        } else {
            router.push('/dashboard');
        }
    }, [isHydrated, user, isSessionSyncing, nextParam, router, searchParams]);

    const establishSession = async (
        response: LoginResponse,
        options: { syncSupabasePassword?: string } = {},
    ) => {
        await login(
            response.access_token,
            response.user,
            response.tenant_id
        );

        if (options.syncSupabasePassword && isSupabaseConfigured()) {
            const supabase = createSupabaseBrowserClient();
            const { error: sbError } = await supabase.auth.signInWithPassword({
                email,
                password: options.syncSupabasePassword,
            });
            if (sbError) {
                if (process.env.NODE_ENV !== 'production') {
                    console.error('[login] Supabase session sync failed:', sbError.message);
                }
                await clearCredentials();
                throw new Error('Secure session could not be established. Please try again.');
            }
        }

        const url = new URL(window.location.href);
        if (url.searchParams.has('error')) {
            url.searchParams.delete('error');
            router.replace(url.pathname + url.search);
        }

        setIsSessionSyncing(false);
        router.refresh();
    };

    const handleEmailCodeSubmit = async () => {
        if (!email.trim()) {
            setError('Email is required.');
            return;
        }

        if (!isEmailCodeSent) {
            setIsLoading(true);
            setError(null);
            try {
                await apiClient.requestEmailLoginCode(email);
                setIsEmailCodeSent(true);
                setEmailCode('');
            } catch (err: unknown) {
                const apiError = err as { response?: { status?: number; data?: unknown }; code?: string; message?: string };
                const errorDetail = extractApiErrorMessage(apiError.response?.data);
                if (apiError.response?.status === 404) {
                    setError('Authentication service unavailable. Please try again shortly.');
                } else if (apiError.response?.status === 502) {
                    setError('Authentication service is unreachable. Please try again shortly.');
                } else if (apiError.code === 'ERR_NETWORK') {
                    setError('Unable to reach authentication service. Check API configuration and try again.');
                } else {
                    setError(errorDetail || 'Unable to send confirmation code. Please try again.');
                }
            } finally {
                setIsLoading(false);
            }
            return;
        }

        const normalizedCode = emailCode.trim();
        if (!/^\d{6}$/.test(normalizedCode)) {
            setError('Enter the 6-digit confirmation code.');
            return;
        }

        setIsLoading(true);
        setIsSessionSyncing(true);
        setError(null);

        try {
            const response = await apiClient.confirmEmailLoginCode(email, normalizedCode);
            await establishSession(response);
        } catch (err: unknown) {
            setIsSessionSyncing(false);
            const apiError = err as {
                response?: { status?: number; data?: unknown };
                message?: string;
                code?: string;
            };
            const errorDetail = extractApiErrorMessage(apiError.response?.data);
            if (apiError.response?.status === 401 || apiError.response?.status === 400) {
                setError('Invalid or expired confirmation code');
            } else if (apiError.response?.status === 404) {
                setError('Authentication service unavailable. Please try again shortly.');
            } else if (apiError.response?.status === 502) {
                setError('Authentication service is unreachable. Please try again shortly.');
            } else if (apiError.code === 'ERR_NETWORK') {
                setError('Unable to reach authentication service. Check API configuration and try again.');
            } else {
                setError(errorDetail || 'Unable to confirm code. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (authMode === 'email-code') {
            await handleEmailCodeSubmit();
            return;
        }

        if (!email.trim()) {
            setError('Email is required.');
            return;
        }
        if (!password) {
            setError('Password is required.');
            return;
        }

        setIsLoading(true);
        setIsSessionSyncing(true);
        setError(null);

        try {
            const response = await apiClient.login(email, password);
            await establishSession(response, { syncSupabasePassword: password });
        } catch (err: unknown) {
            setIsSessionSyncing(false);
            const apiError = err as {
                response?: { status?: number; data?: unknown };
                message?: string;
                code?: string;
            };
            const shouldLogUnexpectedError =
                process.env.NODE_ENV !== 'production' &&
                ![401, 403, 404, 502].includes(apiError.response?.status ?? -1) &&
                apiError.code !== 'ERR_NETWORK' &&
                apiError.message !== 'Secure session could not be established. Please try again.';

            if (shouldLogUnexpectedError) {
                console.error('Login error:', err);
            }
            const errorDetail = extractApiErrorMessage(apiError.response?.data);

            if (apiError.response?.status === 401) {
                setError('Invalid email or password');
            } else if (apiError.response?.status === 403) {
                setError('Account access disabled');
            } else if (apiError.response?.status === 404) {
                setError('Authentication service unavailable. Please try again shortly.');
            } else if (apiError.response?.status === 502) {
                setError('Authentication service is unreachable. Please try again shortly.');
            } else if (apiError.code === 'ERR_NETWORK') {
                setError('Unable to reach authentication service. Check API configuration and try again.');
            } else if (apiError.message?.includes('DNS_HOSTNAME_RESOLVED_PRIVATE')) {
                setError('Authentication service is misconfigured for public access.');
            } else if (apiError.message === 'Secure session could not be established. Please try again.') {
                setError(apiError.message);
            } else {
                setError(errorDetail || 'An unexpected error occurred. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    const queryError = searchParams.get('error');
    const submitBusy = isLoading || isSessionSyncing;
    const mobileSessionIndicators: Array<{ icon: LucideIcon; label: string }> = [
        { icon: LockKeyhole, label: 'JWT' },
        { icon: ShieldCheck, label: 'Secure' },
        { icon: TimerReset, label: 'Ready' },
    ];

    return (
        <div className="re-compliance-os min-h-screen overflow-x-hidden text-[var(--re-text-primary)]">
            <section className="mx-auto grid min-h-screen w-full max-w-7xl items-center gap-6 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(420px,0.72fr)] lg:px-8">
                <aside className="hidden lg:grid lg:gap-5" aria-label="Secure access context">
                    <Link href="/" className="inline-flex w-fit items-center text-[var(--re-text-primary)] no-underline">
                        <RegEngineWordmark size="md" />
                    </Link>

                    <div className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-6 shadow-sm">
                        <div className="inline-flex items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
                            <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                            Secure workspace access
                        </div>
                        <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-tight text-[var(--re-text-primary)]">
                            Access the traceability control room.
                        </h1>
                        <p className="mt-4 max-w-2xl text-sm leading-6 text-[var(--re-text-muted)]">
                            Sign in to resolve supplier gaps, verify KDE coverage, and commit export-ready evidence under tenant-scoped access controls.
                        </p>

                        <div className="mt-8 grid gap-3 sm:grid-cols-3">
                            {[
                                ['86%', 'KDE readiness'],
                                ['2', 'Open supplier gaps'],
                                ['24h', 'Recall clock target'],
                            ].map(([value, label]) => (
                                <div key={label} className="border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-4">
                                    <p className="font-mono text-2xl font-semibold leading-none text-[var(--re-text-primary)]">{value}</p>
                                    <p className="mt-2 text-xs leading-5 text-[var(--re-text-muted)]">{label}</p>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className="grid gap-5 xl:grid-cols-[0.88fr_1.12fr]">
                        <div className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5 shadow-sm">
                            <div className="flex items-center gap-2 text-sm font-semibold text-[var(--re-text-primary)]">
                                <ShieldCheck className="h-4 w-4 text-[var(--re-success)]" aria-hidden="true" />
                                Session preflight
                            </div>
                            <div className="mt-4 grid gap-3">
                                {[
                                    ['Identity verified', 'RegEngine JWT'],
                                    ['Secure cookie ready', 'Supabase session'],
                                    ['Tenant scope locked', 'Role-based access'],
                                ].map(([title, detail]) => (
                                    <div key={title} className="flex items-start gap-3 border-t border-[var(--re-border-subtle)] pt-3 first:border-t-0 first:pt-0">
                                        <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[var(--re-success)]" aria-hidden="true" />
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium text-[var(--re-text-primary)]">{title}</p>
                                            <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">{detail}</p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5 shadow-sm">
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2 text-sm font-semibold text-[var(--re-text-primary)]">
                                    <PackageCheck className="h-4 w-4 text-[var(--re-evidence)]" aria-hidden="true" />
                                    Evidence state
                                </div>
                                <span className="border border-[var(--re-success-border)] bg-[var(--re-success-bg)] px-2 py-1 font-mono text-[11px] font-medium text-[var(--re-success)]">READY</span>
                            </div>
                            <div className="mt-4 grid gap-2">
                                {[
                                    ['FTL coverage', '94%', 'Receiving, shipping, transformation'],
                                    ['Export gate', 'Eligible', '2 warnings require review'],
                                    ['Recall drill', 'Current', 'Last run 4 days ago'],
                                ].map(([label, value, detail]) => (
                                    <div key={label} className="grid grid-cols-[minmax(0,1fr)_92px] gap-3 border-t border-[var(--re-border-subtle)] pt-3 first:border-t-0 first:pt-0">
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium text-[var(--re-text-primary)]">{label}</p>
                                            <p className="mt-1 truncate text-xs text-[var(--re-text-muted)]">{detail}</p>
                                        </div>
                                        <span className="self-start text-right font-mono text-sm font-semibold text-[var(--re-text-primary)]">{value}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="rounded-lg border border-[var(--re-evidence-border)] bg-[var(--re-evidence-bg)] p-4">
                        <div className="flex items-start gap-3">
                            <Fingerprint className="mt-0.5 h-4 w-4 shrink-0 text-[var(--re-evidence)]" aria-hidden="true" />
                            <div className="min-w-0">
                                <p className="text-sm font-semibold text-[var(--re-text-primary)]">Access is part of the evidence chain.</p>
                                <p className="mt-1 text-xs leading-5 text-[var(--re-text-muted)]">
                                    Session handoff is verified before protected routes open, keeping audit activity tied to the right identity and tenant.
                                </p>
                            </div>
                        </div>
                    </div>
                </aside>

                <Card className="border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-lg">
                    <CardHeader className="px-5 pb-3 pt-6 text-left sm:px-9 sm:pt-9">
                        <Link href="/" className="mb-8 inline-flex w-fit items-center text-[var(--re-text-primary)] no-underline lg:hidden">
                            <RegEngineWordmark size="md" />
                        </Link>

                        <div className="inline-flex w-fit items-center gap-2 border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
                            <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
                            Protected workspace
                        </div>
                        <h2 className="mt-5 text-4xl font-semibold leading-tight text-[var(--re-text-primary)]">Sign in</h2>
                        <CardDescription className="mt-2 text-base leading-7 text-[var(--re-text-muted)]">
                            Open a synchronized RegEngine and secure workspace session before entering protected routes.
                        </CardDescription>

                        <div className="mt-5 grid grid-cols-3 gap-2 rounded-lg border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-2">
                            {mobileSessionIndicators.map(({ icon: Icon, label }) => (
                                <div key={label} className="flex min-w-0 flex-col items-center gap-1 border-r border-[var(--re-border-subtle)] px-2 py-2 text-center last:border-r-0">
                                    <Icon className="h-4 w-4 text-[var(--re-text-secondary)]" aria-hidden="true" />
                                    <span className="text-[11px] font-medium leading-4 text-[var(--re-text-muted)]">{label}</span>
                                </div>
                            ))}
                        </div>
                    </CardHeader>
                    <CardContent className="px-5 pb-6 sm:px-9 sm:pb-9">
                            {queryError === 'auth_config' && (
                                <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/10 dark:text-amber-400">
                                    Authentication is temporarily unavailable. Please contact your administrator.
                                </div>
                            )}
                            {queryError === 'token_invalid' && (
                                <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/10 dark:text-amber-400">
                                    Your session could not be verified. Please sign in again.
                                </div>
                            )}
                            {queryError === 'session_expired' && (
                                <div className="mb-4 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/10 dark:text-blue-400">
                                    Your session has expired. Please sign in again.
                                </div>
                            )}
                            {queryError === 'auth_failed' && (
                                <div className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/10 dark:text-red-400">
                                    Password reset link has expired or is invalid.{' '}
                                    <Link href="/forgot-password" className="font-medium underline underline-offset-2">
                                        Request a new one →
                                    </Link>
                                </div>
                            )}
                            <form onSubmit={handleSubmit} className="space-y-4">
                                <div className="grid grid-cols-2 gap-2 rounded-lg border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-1">
                                    <button
                                        type="button"
                                        aria-pressed={authMode === 'password'}
                                        onClick={() => {
                                            setAuthMode('password');
                                            setError(null);
                                        }}
                                        className={`inline-flex h-10 items-center justify-center gap-2 rounded-md text-sm font-medium transition ${authMode === 'password'
                                            ? 'bg-[var(--re-surface-elevated)] text-[var(--re-text-primary)] shadow-sm'
                                            : 'text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]'
                                        }`}
                                        disabled={submitBusy}
                                    >
                                        <LockKeyhole className="h-4 w-4" aria-hidden="true" />
                                        Password
                                    </button>
                                    <button
                                        type="button"
                                        aria-pressed={authMode === 'email-code'}
                                        onClick={() => {
                                            setAuthMode('email-code');
                                            setPassword('');
                                            setError(null);
                                        }}
                                        className={`inline-flex h-10 items-center justify-center gap-2 rounded-md text-sm font-medium transition ${authMode === 'email-code'
                                            ? 'bg-[var(--re-surface-elevated)] text-[var(--re-text-primary)] shadow-sm'
                                            : 'text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]'
                                        }`}
                                        disabled={submitBusy}
                                    >
                                        <Mail className="h-4 w-4" aria-hidden="true" />
                                        Email code
                                    </button>
                                </div>

                                {error && (
                                    <div
                                        id="login-error"
                                        role="alert"
                                        aria-live="polite"
                                        className="animate-in fade-in slide-in-from-top-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-600 dark:border-red-800 dark:bg-red-900/10"
                                    >
                                        {error}
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none text-[var(--re-text-secondary)] peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="email">
                                        Email address
                                    </label>
                                    <div className="relative">
                                        <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--re-text-muted)]" />
                                        <Input
                                            id="email"
                                            type="email"
                                            placeholder="name@company.com"
                                            value={email}
                                            onChange={(e) => handleEmailValueChange(e.target.value)}
                                            onInput={(e) => handleEmailValueChange(e.currentTarget.value)}
                                            disabled={submitBusy}
                                            required
                                            autoComplete="email"
                                            aria-invalid={!!error}
                                            aria-describedby={error ? 'login-error' : undefined}
                                            className="h-12 pl-10"
                                        />
                                    </div>
                                </div>

                                {authMode === 'password' ? (
                                    <div className="space-y-2">
                                        <label className="text-sm font-medium leading-none text-[var(--re-text-secondary)] peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="password">
                                            Password
                                        </label>
                                        <div className="relative">
                                            <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--re-text-muted)]" />
                                            <Input
                                                id="password"
                                                type={showPassword ? 'text' : 'password'}
                                                placeholder="Enter your password"
                                                value={password}
                                                onChange={(e) => setPassword(e.target.value)}
                                                onInput={(e) => setPassword(e.currentTarget.value)}
                                                disabled={submitBusy}
                                                required
                                                autoComplete="current-password"
                                                aria-invalid={!!error}
                                                aria-describedby={error ? 'login-error' : undefined}
                                                className="h-12 pl-10 pr-10"
                                            />
                                            <button
                                                type="button"
                                                aria-label={showPassword ? 'Hide password' : 'Show password'}
                                                className="absolute right-3 top-1/2 inline-flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md text-[var(--re-text-muted)] transition hover:bg-[var(--re-surface-base)] hover:text-[var(--re-text-primary)]"
                                                onClick={() => setShowPassword((value) => !value)}
                                                disabled={submitBusy}
                                            >
                                                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                            </button>
                                        </div>
                                    </div>
                                ) : null}

                                {authMode === 'email-code' && isEmailCodeSent ? (
                                    <div className="space-y-2">
                                        <label className="text-sm font-medium leading-none text-[var(--re-text-secondary)] peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="email-code">
                                            Confirmation code
                                        </label>
                                        <div className="relative">
                                            <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--re-text-muted)]" />
                                            <Input
                                                id="email-code"
                                                type="text"
                                                inputMode="numeric"
                                                pattern="[0-9]*"
                                                maxLength={6}
                                                placeholder="123456"
                                                value={emailCode}
                                                onChange={(e) => setEmailCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                                                disabled={submitBusy}
                                                required
                                                autoComplete="one-time-code"
                                                aria-invalid={!!error}
                                                aria-describedby={error ? 'login-error' : undefined}
                                                className="h-12 pl-10 font-mono tracking-[0.2em]"
                                            />
                                        </div>
                                    </div>
                                ) : null}

                                <div className="flex items-center justify-between gap-3 text-xs text-[var(--re-text-muted)]">
                                    <Link href="/accept-invite" className="transition hover:text-[var(--re-text-primary)]">
                                        Have an invite?
                                    </Link>
                                    <Link href="/forgot-password" className="transition hover:text-[var(--re-text-primary)]">
                                        Forgot password?
                                    </Link>
                                </div>

                                <Button className="h-12 w-full gap-2" type="submit" disabled={submitBusy}>
                                    {submitBusy ? (
                                        <>
                                            <Loader2 className="h-4 w-4 animate-spin" />
                                            {isSessionSyncing ? 'Securing session...' : authMode === 'email-code' && !isEmailCodeSent ? 'Sending code...' : 'Signing in...'}
                                        </>
                                    ) : (
                                        <>
                                            {authMode === 'email-code'
                                                ? (isEmailCodeSent ? 'Confirm code' : 'Send code')
                                                : 'Sign in'}
                                            <ArrowRight className="h-4 w-4" />
                                        </>
                                    )}
                                </Button>

                                <div className="rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] p-3">
                                    <div className="flex gap-3">
                                        <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--re-info)]" />
                                        <p className="text-xs leading-5 text-[var(--re-text-muted)]">
                                            We synchronize your RegEngine and secure workspace sessions before opening protected routes.
                                        </p>
                                    </div>
                                </div>

                                {showQaPresets && QaPresets ? <QaPresets onApplyPreset={applyPreset} /> : null}

                                <div className="border-t border-[var(--re-border-subtle)] pt-5 text-center text-sm text-[var(--re-text-muted)]">
                                    <p className="mb-3 flex flex-col items-center gap-1 sm:block">
                                        <span>New to RegEngine?</span>{" "}
                                        <Link href="/signup" className="font-medium text-[var(--re-text-primary)] hover:underline">
                                            Create an account
                                        </Link>
                                    </p>
                                    <Link href="/" className="inline-flex items-center justify-center gap-2 font-medium text-[var(--re-text-secondary)] transition-colors hover:text-[var(--re-text-primary)]">
                                        <LayoutDashboard className="h-4 w-4" />
                                        Return to RegEngine.co
                                    </Link>
                                </div>
                            </form>
                        </CardContent>
                    </Card>
            </section>
        </div>
    );
}
