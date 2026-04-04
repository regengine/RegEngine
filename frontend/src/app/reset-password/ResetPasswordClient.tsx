'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Loader2, Lock, ShieldCheck, Eye, EyeOff } from 'lucide-react';

function getPasswordStrength(password: string): { score: number; label: string; color: string } {
    let score = 0;
    if (password.length >= 8) score++;
    if (password.length >= 12) score++;
    if (/[A-Z]/.test(password)) score++;
    if (/[0-9]/.test(password)) score++;
    if (/[^A-Za-z0-9]/.test(password)) score++;

    if (score <= 1) return { score, label: 'Weak', color: 'bg-red-500' };
    if (score <= 2) return { score, label: 'Fair', color: 'bg-amber-500' };
    if (score <= 3) return { score, label: 'Good', color: 'bg-yellow-400' };
    return { score, label: 'Strong', color: 'bg-emerald-500' };
}

export default function ResetPasswordClient() {
    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);
    const [sessionReady, setSessionReady] = useState(false);
    const [sessionError, setSessionError] = useState(false);
    const router = useRouter();
    // SSR-aware browser client — matches the PKCE flow used by ForgotPasswordClient.
    const supabase = createSupabaseBrowserClient();

    // When Supabase redirects back after password reset it passes a recovery
    // session in one of two ways:
    //
    //  • PKCE flow  — /auth/callback exchanges the ?code= param server-side and
    //    sets session cookies before redirecting here.  getSession() resolves
    //    immediately with the session from those cookies.
    //
    //  • Implicit flow (legacy emails sent before PKCE migration) — /auth/callback
    //    serves a small HTML shim that reads the #access_token=...&type=recovery
    //    hash and redirects to /reset-password keeping the hash.  createBrowserClient
    //    has detectSessionInUrl: true by default, so it processes the hash on init.
    //    We wait one tick with setTimeout to let the SDK finish that processing
    //    before calling getSession().
    useEffect(() => {
        const check = () => {
            supabase.auth.getSession().then(({ data: { session } }) => {
                if (session) {
                    setSessionReady(true);
                } else {
                    setSessionError(true);
                }
            });
        };
        // Give detectSessionInUrl one event-loop tick to process any hash tokens.
        const tid = setTimeout(check, 50);
        return () => clearTimeout(tid);
    }, []);

    const strength = getPasswordStrength(password);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        if (password.length < 8) {
            setError('Password must be at least 8 characters.');
            return;
        }
        if (password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            const { error: updateError } = await supabase.auth.updateUser({ password });

            if (updateError) {
                setError(updateError.message || 'Failed to update password. The reset link may have expired.');
                return;
            }

            // Sign out so the user logs in fresh with the new password
            await supabase.auth.signOut();
            setSuccess(true);
        } catch {
            setError('An unexpected error occurred. Please try again.');
        } finally {
            setIsLoading(false);
        }
    };

    if (sessionError) {
        return (
            <div className="relative overflow-hidden bg-[var(--re-surface-base)]">
                <section className="relative z-[1] mx-auto flex min-h-[80vh] max-w-md items-center px-6 py-14">
                    <Card className="w-full border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                        <CardContent className="pt-8">
                            <div className="space-y-4 text-center">
                                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-red-500/10">
                                    <Lock className="h-7 w-7 text-red-500" />
                                </div>
                                <div className="space-y-1">
                                    <p className="font-medium text-[var(--re-text-primary)]">Reset link expired</p>
                                    <p className="text-sm text-[var(--re-text-muted)]">
                                        This password reset link is invalid or has expired. Reset links are valid for 1 hour.
                                    </p>
                                </div>
                                <Button className="w-full" onClick={() => router.push('/forgot-password')}>
                                    Request a new link
                                </Button>
                                <Button variant="outline" className="w-full" onClick={() => router.push('/login')}>
                                    Back to sign in
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </section>
            </div>
        );
    }

    if (success) {
        return (
            <div className="relative overflow-hidden bg-[var(--re-surface-base)]">
                <section className="relative z-[1] mx-auto flex min-h-[80vh] max-w-md items-center px-6 py-14">
                    <Card className="w-full border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                        <CardContent className="pt-8">
                            <div className="space-y-4 text-center">
                                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/10">
                                    <ShieldCheck className="h-7 w-7 text-emerald-500" />
                                </div>
                                <div className="space-y-1">
                                    <p className="font-medium text-[var(--re-text-primary)]">Password updated</p>
                                    <p className="text-sm text-[var(--re-text-muted)]">
                                        Your password has been changed successfully. Sign in with your new password.
                                    </p>
                                </div>
                                <Button className="w-full" onClick={() => router.push('/login')}>
                                    Sign in
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </section>
            </div>
        );
    }

    return (
        <div className="relative overflow-hidden bg-[var(--re-surface-base)]">
            <div className="pointer-events-none absolute inset-0">
                <div className="absolute -top-16 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full bg-[var(--re-brand)]/10 blur-3xl" />
                <div className="absolute right-12 top-28 h-48 w-48 rounded-full bg-cyan-400/10 blur-3xl" />
            </div>

            <section className="relative z-[1] mx-auto flex min-h-[80vh] max-w-md items-center px-6 py-14">
                <Card className="w-full border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                    <CardHeader className="space-y-1 pb-4">
                        <div className="mb-3 flex justify-center">
                            <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                                <Lock className="h-7 w-7 text-[var(--re-brand)]" />
                            </div>
                        </div>
                        <h2 className="text-center text-2xl font-semibold leading-none tracking-tight text-[var(--re-text-primary)]">
                            Set new password
                        </h2>
                        <CardDescription className="text-center text-[var(--re-text-muted)]">
                            Choose a strong password for your account
                        </CardDescription>
                    </CardHeader>

                    <CardContent>
                        {!sessionReady ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-[var(--re-brand)]" />
                            </div>
                        ) : (
                            <form onSubmit={handleSubmit} className="space-y-4">
                                {error && (
                                    <div
                                        role="alert"
                                        aria-live="polite"
                                        className="animate-in fade-in slide-in-from-top-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-500 dark:border-red-800 dark:bg-red-900/10"
                                    >
                                        {error}
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label
                                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                        htmlFor="password"
                                    >
                                        New password
                                    </label>
                                    <div className="relative">
                                        <Input
                                            id="password"
                                            type={showPassword ? 'text' : 'password'}
                                            value={password}
                                            onChange={(e) => setPassword(e.target.value)}
                                            disabled={isLoading}
                                            required
                                            autoComplete="new-password"
                                            autoFocus
                                            className="h-11 pr-10"
                                            placeholder="Min. 8 characters"
                                        />
                                        <button
                                            type="button"
                                            onClick={() => setShowPassword((v) => !v)}
                                            className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--re-text-muted)] transition hover:text-[var(--re-text-primary)]"
                                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                                        >
                                            {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                                        </button>
                                    </div>
                                    {password.length > 0 && (
                                        <div className="space-y-1">
                                            <div className="flex gap-1">
                                                {[1, 2, 3, 4].map((i) => (
                                                    <div
                                                        key={i}
                                                        className={`h-1 flex-1 rounded-full transition-colors ${
                                                            i <= strength.score ? strength.color : 'bg-[var(--re-surface-border)]'
                                                        }`}
                                                    />
                                                ))}
                                            </div>
                                            <p className="text-xs text-[var(--re-text-muted)]">
                                                Strength: <span className="font-medium">{strength.label}</span>
                                            </p>
                                        </div>
                                    )}
                                </div>

                                <div className="space-y-2">
                                    <label
                                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                        htmlFor="confirm-password"
                                    >
                                        Confirm new password
                                    </label>
                                    <Input
                                        id="confirm-password"
                                        type={showPassword ? 'text' : 'password'}
                                        value={confirmPassword}
                                        onChange={(e) => setConfirmPassword(e.target.value)}
                                        disabled={isLoading}
                                        required
                                        autoComplete="new-password"
                                        className="h-11"
                                        placeholder="Repeat your password"
                                    />
                                    {confirmPassword.length > 0 && password !== confirmPassword && (
                                        <p className="text-xs text-red-500">Passwords do not match</p>
                                    )}
                                </div>

                                <Button
                                    className="h-11 w-full"
                                    type="submit"
                                    disabled={isLoading || !sessionReady}
                                >
                                    {isLoading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Updating password...
                                        </>
                                    ) : (
                                        'Update password'
                                    )}
                                </Button>
                            </form>
                        )}
                    </CardContent>
                </Card>
            </section>
        </div>
    );
}
