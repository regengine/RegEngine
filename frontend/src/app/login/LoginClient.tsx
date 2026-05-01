'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Loader2, LayoutDashboard, ShieldCheck, KeyRound, ClipboardCheck } from 'lucide-react';
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
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const searchParams = useSearchParams();
    const nextParam = searchParams.get('next');
    const { login, user, isHydrated } = useAuth();
    const showQaPresets = Boolean(QALoginPresets && (searchParams.get('qa') === '1' || searchParams.get('preset')));
    const QaPresets = QALoginPresets;

    const applyPreset = useCallback((presetEmail: string) => {
        setEmail(presetEmail);
        setPassword('');
        setError(null);
    }, []);

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
                // Supabase auth failed — this means the user exists in RegEngine
                // but not in Supabase, or passwords are out of sync. Log it and
                // surface the issue rather than silently breaking middleware.
                console.error('[login] Supabase session sync failed:', sbError.message);
                // Don't throw — the RegEngine JWT is set and the user can still
                // reach public/free-tool routes. But protected routes will fail
                // until Supabase session is established.
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
        <div className="min-h-[calc(100vh-1px)] bg-slate-50 text-slate-950">
            <section className="mx-auto flex min-h-[calc(100vh-1px)] w-full max-w-6xl items-center px-4 py-8 sm:px-6 lg:px-8">
                <div className="grid w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:grid-cols-[minmax(0,0.9fr)_minmax(420px,0.7fr)]">
                    <div className="re-auth-rail hidden border-r border-[var(--re-border-strong)] bg-[var(--re-brand)] p-8 text-[var(--re-surface-base)] lg:flex lg:flex-col lg:justify-between">
                        <div>
                            <div className="inline-flex h-10 w-10 items-center justify-center rounded-sm border border-[var(--re-surface-base)] bg-[var(--re-surface-base)] text-[var(--re-brand)]">
                                <ClipboardCheck className="h-5 w-5" />
                            </div>
                            <h1 className="mt-8 max-w-md text-3xl font-semibold leading-tight tracking-normal">
                                RegEngine command center
                            </h1>
                            <p className="mt-3 max-w-md text-sm leading-6 text-[var(--re-surface-base)]">
                                Continue to your FSMA 204 workspace, validate traceability records, and prepare evidence from authenticated records.
                            </p>
                        </div>

                        <div className="grid gap-3 text-sm">
                            {[
                                'Secure tenant-scoped session',
                                'Authenticated traceability exports',
                                'Hash-chain audit evidence',
                            ].map((item) => (
                                <div key={item} className="flex items-center gap-3 rounded-sm border border-[var(--re-surface-base)]/25 bg-[var(--re-surface-base)]/[0.04] px-3 py-2">
                                    <ShieldCheck className="h-4 w-4 text-[var(--re-signal-green)]" />
                                    <span className="text-[var(--re-surface-base)]">{item}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <Card className="border-0 bg-white shadow-none">
                        <CardHeader className="space-y-2 px-5 pb-4 pt-6 sm:px-8 sm:pt-8">
                            <div className="flex items-center gap-3 lg:hidden">
                                <div className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600 text-white">
                                    <ClipboardCheck className="h-4 w-4" />
                                </div>
                                <div>
                                    <p className="text-sm font-semibold text-slate-950">RegEngine</p>
                                    <p className="text-xs text-slate-500">Command center</p>
                                </div>
                            </div>
                            <div className="inline-flex w-fit items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800">
                                <KeyRound className="h-3.5 w-3.5" />
                                Protected workspace
                            </div>
                            <h2 className="text-2xl font-semibold leading-tight tracking-normal text-slate-950">Sign in</h2>
                            <CardDescription className="text-sm leading-6 text-slate-600">
                                Use your RegEngine account to continue to the requested workspace.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="px-5 pb-6 sm:px-8 sm:pb-8">
                            {searchParams.get('error') === 'auth_config' && (
                                <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/10 dark:text-amber-400">
                                    Authentication is misconfigured (AUTH_SECRET_KEY not set). Contact your administrator.
                                </div>
                            )}
                            {searchParams.get('error') === 'token_invalid' && (
                                <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700 dark:border-amber-800 dark:bg-amber-900/10 dark:text-amber-400">
                                    Your session could not be verified. Please sign in again.
                                </div>
                            )}
                            {searchParams.get('error') === 'session_expired' && (
                                <div className="mb-4 rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-700 dark:border-blue-800 dark:bg-blue-900/10 dark:text-blue-400">
                                    Your session has expired. Please sign in again.
                                </div>
                            )}
                            {searchParams.get('error') === 'auth_failed' && (
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
                                        className="animate-in fade-in slide-in-from-top-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-500 dark:border-red-800 dark:bg-red-900/10"
                                    >
                                        {error}
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none text-slate-700 peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="email">
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
                                        className="h-11 border-slate-300 bg-white"
                                    />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-medium leading-none text-slate-700 peer-disabled:cursor-not-allowed peer-disabled:opacity-70" htmlFor="password">
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
                                        className="h-11 border-slate-300 bg-white"
                                    />
                                </div>

                                <div className="flex items-center justify-between text-xs text-slate-500">
                                    <Link href="/accept-invite" className="transition hover:text-emerald-700">
                                        Have an invite?
                                    </Link>
                                    <Link href="/forgot-password" className="transition hover:text-emerald-700">
                                        Forgot password?
                                    </Link>
                                </div>

                                <Button className="h-11 w-full bg-emerald-700 text-white hover:bg-emerald-800" type="submit" disabled={isLoading}>
                                    {isLoading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Signing in...
                                        </>
                                    ) : (
                                        'Sign In'
                                    )}
                                </Button>

                                {showQaPresets && QaPresets ? <QaPresets onApplyPreset={applyPreset} /> : null}

                                <div className="border-t border-slate-200 pt-4 text-center text-sm text-slate-500">
                                    <p className="mb-2">
                                        New here?{" "}
                                        <Link href="/signup" className="font-medium text-emerald-700 hover:underline">
                                            Create an account
                                        </Link>
                                    </p>
                                    <Link href="/" className="flex items-center justify-center gap-2 transition-colors hover:text-slate-950">
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
