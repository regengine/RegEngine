'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import {
    ArrowRight,
    CheckCircle2,
    ClipboardCheck,
    Eye,
    EyeOff,
    FileCheck2,
    KeyRound,
    LayoutDashboard,
    LockKeyhole,
    Loader2,
    Mail,
    ShieldCheck,
} from 'lucide-react';
import Link from 'next/link';
import dynamic from 'next/dynamic';

// QA presets are code-split into a separate chunk via dynamic import.
// In production builds without the opt-in env var, the chunk is never
// loaded — removing preset code from the main bundle entirely.
const qaPresetsEnabled =
    process.env.NODE_ENV !== 'production' ||
    process.env.NEXT_PUBLIC_ENABLE_QA_LOGIN_PRESETS === '1';

const QALoginPresets = qaPresetsEnabled
    ? dynamic(() => import('./QALoginPresets'), { ssr: false })
    : null;

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
    if (!trimmed.startsWith('/') || trimmed.startsWith('//')) {
        return null;
    }
    if (trimmed.startsWith('/login')) {
        return null;
    }

    return trimmed;
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
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
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
        setError(null);
    }, []);

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

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

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

            // Update auth context FIRST — sets re_access_token (RegEngine JWT)
            // cookie and updates React state. Must complete before Supabase
            // signIn so the onAuthStateChange guard (accessToken check) prevents
            // the Supabase callback from overwriting re_access_token with a
            // Supabase JWT that the middleware can't verify.
            await login(
                response.access_token,
                response.user,
                response.tenant_id
            );

            // #538 fix: Establish Supabase session alongside custom JWT.
            // The middleware cross-validates both auth systems — a valid
            // re_access_token JWT without a Supabase cookie triggers a
            // session_expired redirect. This sets the Supabase cookies that
            // hasSomeSupabaseCookie() checks for.
            //
            // Runs AFTER login() so React state is set, which prevents the
            // onAuthStateChange callback from clobbering re_access_token.
            const supabase = createSupabaseBrowserClient();
            const { error: sbError } = await supabase.auth.signInWithPassword({ email, password });
            if (sbError) {
                if (process.env.NODE_ENV !== 'production') {
                    console.error('[login] Supabase session sync failed:', sbError.message);
                }
                clearCredentials();
                throw new Error('Secure session could not be established. Please try again.');
            }

            // Clear any error params (e.g. ?error=session_expired) left by
            // middleware so the redirect useEffect doesn't block navigation
            // after a successful re-login.
            const url = new URL(window.location.href);
            if (url.searchParams.has('error')) {
                url.searchParams.delete('error');
                router.replace(url.pathname + url.search);
            }

            // Ensure the middleware picks up the newly-set cookie before
            // the useEffect redirect fires.
            setIsSessionSyncing(false);
            router.refresh();
        } catch (err: unknown) {
            setIsSessionSyncing(false);
            if (process.env.NODE_ENV !== 'production') {
                console.error('Login error:', err);
            }
            const apiError = err as {
                response?: { status?: number; data?: unknown };
                message?: string;
                code?: string;
            };
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

    return (
        <div className="min-h-[calc(100vh-1px)] bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
            <section className="mx-auto flex min-h-[calc(100vh-1px)] w-full max-w-7xl items-center px-4 py-6 sm:px-6 lg:px-8">
                <div className="grid w-full overflow-hidden rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-lg lg:grid-cols-[minmax(0,0.92fr)_minmax(440px,1.08fr)]">
                    <aside className="re-auth-rail hidden min-h-[680px] border-r border-white/10 bg-[var(--re-brand)] p-8 text-white lg:flex lg:flex-col lg:justify-between">
                        <div>
                            <Link href="/" className="inline-flex items-center gap-3 text-white no-underline">
                                <div className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-white/20 bg-white text-[var(--re-brand)]">
                                    <ClipboardCheck className="h-5 w-5" />
                                </div>
                                <div>
                                    <p className="text-lg font-semibold leading-none">RegEngine</p>
                                    <p className="mt-1 font-mono text-[11px] uppercase tracking-[0.14em] text-white/60">Command center</p>
                                </div>
                            </Link>

                            <h1 className="mt-10 max-w-md text-4xl font-semibold leading-tight tracking-normal">
                                Evidence-ready access for regulated teams.
                            </h1>
                            <p className="mt-4 max-w-md text-sm leading-6 text-white/72">
                                Sign in to validate traceability records, resolve readiness blockers, and prepare tenant-scoped audit evidence.
                            </p>
                        </div>

                        <div className="mt-10 grid gap-4">
                            <div className="re-auth-check rounded-lg border border-white/15 p-4">
                                <div className="mb-3 flex items-center justify-between">
                                    <p className="text-sm font-semibold">Evidence checklist</p>
                                    <span className="rounded-full border border-emerald-300/30 bg-emerald-400/10 px-2 py-1 text-[11px] font-medium text-emerald-200">Live</span>
                                </div>
                                {[
                                    ['Supplier onboarding', 'All suppliers verified', 'Complete'],
                                    ['Foreign Traceability', '2 lots awaiting FTL', 'Review'],
                                    ['Recall readiness', 'Exercises current', 'Complete'],
                                ].map(([title, detail, status]) => (
                                    <div key={title} className="flex items-center gap-3 border-t border-white/10 py-3 first:border-t-0 first:pt-0 last:pb-0">
                                        {status === 'Complete' ? (
                                            <CheckCircle2 className="h-4 w-4 flex-shrink-0 text-emerald-300" />
                                        ) : (
                                            <FileCheck2 className="h-4 w-4 flex-shrink-0 text-amber-300" />
                                        )}
                                        <div className="min-w-0 flex-1">
                                            <p className="text-sm font-medium text-white">{title}</p>
                                            <p className="mt-0.5 text-xs text-white/55">{detail}</p>
                                        </div>
                                        <span className="rounded-full border border-white/15 px-2 py-1 text-[11px] text-white/72">{status}</span>
                                    </div>
                                ))}
                            </div>

                            <div className="re-auth-check rounded-lg border border-white/15 p-4">
                                <div className="mb-3 flex items-center justify-between">
                                    <p className="text-sm font-semibold">Traceability status</p>
                                    <span className="font-mono text-[11px] text-white/55">3 events</span>
                                </div>
                                <div className="grid grid-cols-[1fr_88px_74px] gap-x-3 border-b border-white/10 pb-2 font-mono text-[10px] uppercase tracking-[0.08em] text-white/45">
                                    <span>Lot</span>
                                    <span>Status</span>
                                    <span>CTE</span>
                                </div>
                                {[
                                    ['LOT-24-0512', 'Compliant', 'Shipping'],
                                    ['LOT-24-0511', 'Compliant', 'Cooling'],
                                    ['LOT-24-0510', 'Warning', 'Receiving'],
                                ].map(([lot, status, cte]) => (
                                    <div key={lot} className="grid grid-cols-[1fr_88px_74px] gap-x-3 border-b border-white/10 py-2 text-xs last:border-b-0">
                                        <span className="font-mono text-white/80">{lot}</span>
                                        <span className="inline-flex items-center gap-1.5 text-white/72">
                                            <span className={status === 'Compliant' ? 'h-2 w-2 rounded-full bg-emerald-300' : 'h-2 w-2 rounded-full bg-amber-300'} />
                                            {status}
                                        </span>
                                        <span className="text-white/60">{cte}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="grid grid-cols-3 gap-4 border-t border-white/10 pt-5 text-xs text-white/58">
                            <div className="flex gap-2">
                                <ShieldCheck className="h-4 w-4 flex-shrink-0 text-white/70" />
                                <span>Enterprise security</span>
                            </div>
                            <div className="flex gap-2">
                                <LockKeyhole className="h-4 w-4 flex-shrink-0 text-white/70" />
                                <span>Encrypted session</span>
                            </div>
                            <div className="flex gap-2">
                                <FileCheck2 className="h-4 w-4 flex-shrink-0 text-white/70" />
                                <span>Audit-ready evidence</span>
                            </div>
                        </div>
                    </aside>

                    <Card className="border-0 bg-[var(--re-surface-elevated)] shadow-none">
                        <CardHeader className="px-5 pb-3 pt-6 text-left sm:px-10 sm:pt-10 lg:px-16 lg:pt-16">
                            <Link href="/" className="mb-8 inline-flex items-center gap-3 text-[var(--re-text-primary)] no-underline sm:mb-10">
                                <div className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-[var(--re-brand)] text-white">
                                    <ClipboardCheck className="h-5 w-5" />
                                </div>
                                <div>
                                    <p className="text-lg font-semibold leading-none">RegEngine</p>
                                    <p className="mt-1 text-xs text-[var(--re-text-muted)] lg:hidden">Command center</p>
                                </div>
                            </Link>

                            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-[var(--re-info-border)] bg-[var(--re-info-bg)] px-3 py-1 text-xs font-medium text-[var(--re-info)]">
                                <KeyRound className="h-3.5 w-3.5" />
                                Protected workspace
                            </div>
                            <h2 className="mt-5 text-4xl font-semibold leading-tight tracking-normal text-[var(--re-text-primary)]">Sign in</h2>
                            <CardDescription className="mt-2 text-base leading-7 text-[var(--re-text-muted)]">
                                Access your regulated workspace with a synchronized secure session.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="px-5 pb-6 sm:px-10 sm:pb-10 lg:px-16">
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
                                            onChange={(e) => setEmail(e.target.value)}
                                            disabled={submitBusy}
                                            required
                                            autoComplete="email"
                                            aria-invalid={!!error}
                                            aria-describedby={error ? 'login-error' : undefined}
                                            className="h-12 pl-10"
                                        />
                                    </div>
                                </div>

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
                                            {isSessionSyncing ? 'Securing session...' : 'Signing in...'}
                                        </>
                                    ) : (
                                        <>
                                            Sign in
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
                                        Return to RegEngine.com
                                    </Link>
                                </div>
                            </form>
                        </CardContent>
                    </Card>
                </div>
            </section>
        </div>
    );
}
