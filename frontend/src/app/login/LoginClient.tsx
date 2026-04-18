'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Loader2, Lock, LayoutDashboard, ArrowRight, ShieldCheck, CalendarClock, GitBranch } from 'lucide-react';
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

export default function LoginPage() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const searchParams = useSearchParams();
    const nextParam = searchParams.get('next');
    const { login, user, isHydrated, clearCredentials } = useAuth();

    // Receives an email string from QALoginPresets (dynamically loaded chunk).
    // The email→preset mapping lives exclusively in that chunk so test addresses
    // are absent from the production bundle.
    const applyPreset = useCallback((email: string) => {
        setEmail(email);
        setPassword('');
        setError(null);
    }, []);

    // When middleware redirects here with session_expired, clear the stale
    // Supabase session so the user gets a clean login form without redirect loops.
    useEffect(() => {
        const errorParam = searchParams.get('error');
        if (errorParam === 'session_expired' || errorParam === 'token_invalid') {
            import('@/lib/supabase/client').then(({ createSupabaseBrowserClient }) => {
                const sb = createSupabaseBrowserClient();
                sb.auth.signOut().catch(() => {});
            });
        }
    }, [searchParams]);

    useEffect(() => {
        if (!isHydrated || !user) {
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
        const tid = typeof window !== 'undefined' ? localStorage.getItem('regengine_tenant_id') : null;
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
    }, [isHydrated, user, nextParam, router, searchParams]);

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
        setError(null);

        // #1077 Snapshot the error param that was present when this attempt
        // started. Rapid retries can cause a late success-handler to fire
        // after the URL has been re-decorated with a newer ?error= -- only
        // strip the param we saw, not whatever is currently there.
        const attemptErrorParam = searchParams.get('error');

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
                // #1072 Supabase auth failed — RegEngine credentials matched
                // but Supabase did not (out-of-sync passwords, Supabase flaky,
                // user absent in Supabase). The RegEngine JWT cookie is set,
                // so the user thinks login "worked" — but middleware enforces
                // cross-auth (#538) and will bounce any protected nav to
                // /login?error=session_expired, producing the classic
                // "login is broken" redirect loop.
                //
                // Surface the failure in the form rather than silently
                // proceeding. Structured log so support can correlate in
                // telemetry.
                console.error('[login] Supabase session sync failed', {
                    message: sbError.message,
                    status: sbError.status,
                    code: sbError.code,
                });
                setError(
                    "We signed you in, but couldn't establish your secure " +
                    'session. Please try again — if the problem persists, ' +
                    'reset your password or contact support.',
                );
                // Clear the half-set cookies so the retry is clean and the
                // user isn't stuck in a half-authenticated state that the
                // middleware will reject on the next nav.
                clearCredentials();
                setIsLoading(false);
                return;
            }

            // Clear the specific error param that was present when this
            // attempt started (e.g. ?error=session_expired from middleware)
            // so the redirect useEffect doesn't block navigation after a
            // successful re-login.
            //
            // #1077: Only strip the snapshotted value, not whatever is
            // currently on the URL. In a rapid retry scenario, attempt #1's
            // success handler firing after attempt #2 wrote a fresh
            // ?error=... would otherwise erase the new error and leave the
            // user staring at a blank form with no feedback.
            if (attemptErrorParam) {
                const url = new URL(window.location.href);
                if (url.searchParams.get('error') === attemptErrorParam) {
                    url.searchParams.delete('error');
                    router.replace(url.pathname + url.search);
                }
            }

            // Ensure the middleware picks up the newly-set cookie before
            // the useEffect redirect fires.
            router.refresh();
        } catch (err: unknown) {
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
            } else {
                setError(errorDetail || 'An unexpected error occurred. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="relative overflow-hidden bg-[var(--re-surface-base)]">
            <div className="pointer-events-none absolute inset-0">
                <div className="absolute -top-16 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full bg-[var(--re-brand)]/10 blur-3xl" />
                <div className="absolute right-12 top-28 h-48 w-48 rounded-full bg-cyan-400/10 blur-3xl" />
            </div>

            <section className="relative z-[1] mx-auto max-w-6xl px-6 py-14 lg:py-20">
                <div className="grid items-stretch gap-6 lg:grid-cols-[1.05fr_0.95fr]">
                    <div className="rounded-3xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/70 p-8 shadow-[0_20px_80px_rgba(0,0,0,0.25)] lg:p-10">
                        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--re-brand)]">
                            RegEngine
                        </div>

                        <h1 className="mt-4 text-3xl font-bold leading-tight text-[var(--re-text-primary)] lg:text-4xl">
                            API-first regulatory compliance.
                        </h1>
                        <p className="mt-3 max-w-[58ch] text-sm leading-relaxed text-[var(--re-text-muted)] lg:text-base">
                            Sign in to continue your FSMA 204 workflow, run traceability checks, and export audit-ready records with cryptographic proof.
                        </p>

                        <div className="mt-7 grid gap-3 sm:grid-cols-2">
                            <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3">
                                <div className="mb-1 inline-flex items-center gap-2 text-xs font-semibold text-[var(--re-text-primary)]">
                                    <CalendarClock className="h-3.5 w-3.5 text-[var(--re-brand)]" />
                                    Deadline Focus
                                </div>
                                <p className="text-xs text-[var(--re-text-muted)]">FSMA 204 deadline: July 20, 2028</p>
                            </div>
                            <div className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3">
                                <div className="mb-1 inline-flex items-center gap-2 text-xs font-semibold text-[var(--re-text-primary)]">
                                    <GitBranch className="h-3.5 w-3.5 text-[var(--re-brand)]" />
                                    Verifiable by Design
                                </div>
                                <p className="text-xs text-[var(--re-text-muted)]">Every record is cryptographically signed and auditable.</p>
                            </div>
                        </div>

                        <div className="mt-7 space-y-3">
                            {[
                                'Capture and validate all 7 FSMA 204 CTE types',
                                'Track supplier onboarding and compliance gaps in real time',
                                'Generate FDA-ready exports without manual spreadsheet cleanup',
                            ].map((item) => (
                                <div key={item} className="flex items-start gap-3">
                                    <ShieldCheck className="mt-0.5 h-4 w-4 text-[var(--re-brand)]" />
                                    <p className="text-sm text-[var(--re-text-secondary)]">{item}</p>
                                </div>
                            ))}
                        </div>

                        <div className="mt-8 flex flex-wrap items-center gap-3 text-xs text-[var(--re-text-muted)]">
                            <span>New to RegEngine?</span>
                            <Link href="/onboarding/supplier-flow" className="inline-flex items-center gap-1 rounded-full border border-[var(--re-brand)]/40 px-3 py-1 font-semibold text-[var(--re-brand)] transition hover:bg-[var(--re-brand)]/10">
                                Get Started (Supplier Flow)
                                <ArrowRight className="h-3 w-3" />
                            </Link>
                        </div>
                    </div>

                    <Card className="border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                        <CardHeader className="space-y-1 pb-4">
                            <div className="mb-3 flex justify-center">
                                <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                                    <Lock className="h-7 w-7 text-[var(--re-brand)]" />
                                </div>
                            </div>
                            <h2 className="text-center text-2xl font-semibold leading-none tracking-tight text-[var(--re-text-primary)]">Welcome back</h2>
                            <CardDescription className="text-center text-[var(--re-text-muted)]">
                                Sign in to your RegEngine account
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            {searchParams.get('error') === 'auth_config' && (
                                <div className="mb-4 rounded-md border border-re-warning bg-re-warning-muted p-3 text-sm text-re-warning dark:border-re-warning dark:bg-re-warning/10 dark:text-re-warning">
                                    Authentication is misconfigured (AUTH_SECRET_KEY not set). Contact your administrator.
                                </div>
                            )}
                            {searchParams.get('error') === 'token_invalid' && (
                                <div className="mb-4 rounded-md border border-re-warning bg-re-warning-muted p-3 text-sm text-re-warning dark:border-re-warning dark:bg-re-warning/10 dark:text-re-warning">
                                    Your session could not be verified. Please sign in again.
                                </div>
                            )}
                            {searchParams.get('error') === 'session_expired' && (
                                <div className="mb-4 rounded-md border border-blue-200 bg-re-info-muted p-3 text-sm text-re-info dark:border-blue-800 dark:bg-re-info/10 dark:text-re-info">
                                    Your session has expired. Please sign in again.
                                </div>
                            )}
                            {searchParams.get('error') === 'auth_failed' && (
                                <div className="mb-4 rounded-md border border-re-danger bg-re-danger-muted p-3 text-sm text-re-danger dark:border-re-danger dark:bg-re-danger/10 dark:text-re-danger">
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
                                        className="animate-in fade-in slide-in-from-top-2 rounded-md border border-re-danger bg-re-danger-muted p-3 text-sm text-re-danger dark:border-re-danger dark:bg-re-danger/10"
                                    >
                                        {error}
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="email">
                                        Email
                                    </label>
                                    <Input
                                        id="email"
                                        type="email"
                                        placeholder="name@example.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        disabled={isLoading}
                                        required
                                        autoComplete="email"
                                        aria-invalid={!!error}
                                        aria-describedby={error ? 'login-error' : undefined}
                                        className="h-11"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="password">
                                        Password
                                    </label>
                                    <Input
                                        id="password"
                                        type="password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        disabled={isLoading}
                                        required
                                        autoComplete="current-password"
                                        aria-invalid={!!error}
                                        aria-describedby={error ? 'login-error' : undefined}
                                        className="h-11"
                                    />
                                </div>

                                <div className="flex items-center justify-between text-xs text-[var(--re-text-muted)]">
                                    <Link href="/accept-invite" className="transition hover:text-[var(--re-brand)]">
                                        Have an invite?
                                    </Link>
                                    <Link href="/forgot-password" className="transition hover:text-[var(--re-brand)]">
                                        Forgot password?
                                    </Link>
                                </div>

                                <Button className="h-11 w-full" type="submit" disabled={isLoading}>
                                    {isLoading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Signing in...
                                        </>
                                    ) : (
                                        'Sign In'
                                    )}
                                </Button>

                                {QALoginPresets && <QALoginPresets onApplyPreset={applyPreset} />}

                                <div className="pt-2 text-center text-sm text-muted-foreground">
                                    <p className="mb-2">
                                        New here?{" "}
                                        <Link href="/signup" className="font-medium text-[var(--re-brand)] hover:underline">
                                            Create an account
                                        </Link>
                                    </p>
                                    <Link href="/" className="flex items-center justify-center gap-2 transition-colors hover:text-primary">
                                        <LayoutDashboard className="h-4 w-4" />
                                        Return to public site
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
