'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card';
import { Loader2, Mail, ShieldCheck, ArrowLeft } from 'lucide-react';
import Link from 'next/link';

export default function ForgotPasswordClient() {
    const [email, setEmail] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [submitted, setSubmitted] = useState(false);
    const router = useRouter();
    const searchParams = useSearchParams();
    const linkExpired = searchParams.get('error') === 'link_expired';
    // Use the SSR-aware browser client (PKCE flow) so the recovery email sends a
    // ?code= query param that /auth/callback can exchange server-side. The plain
    // @supabase/supabase-js client defaults to the legacy implicit flow which puts
    // tokens in the URL hash — invisible to the server and incompatible with our
    // /auth/callback route handler.
    const supabase = createSupabaseBrowserClient();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        const trimmed = email.trim();
        if (!trimmed) {
            setError('Email is required.');
            return;
        }

        setIsLoading(true);
        setError(null);

        try {
            // Build the redirect URL so Supabase routes through our /auth/callback
            // handler, which exchanges the recovery code for a session and then
            // forwards to /reset-password.
            const origin =
                typeof window !== 'undefined'
                    ? window.location.origin
                    : process.env.NEXT_PUBLIC_SITE_URL ?? 'https://regengine.co';
            const redirectTo = `${origin}/auth/callback?next=/reset-password`;

            const { error: supabaseError } = await supabase.auth.resetPasswordForEmail(
                trimmed,
                { redirectTo }
            );

            if (supabaseError) {
                setError(supabaseError.message || 'Failed to send reset email. Please try again.');
                return;
            }

            setSubmitted(true);
        } catch {
            setError('An unexpected error occurred. Please try again.');
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

            <section className="relative z-[1] mx-auto flex min-h-[80vh] max-w-md items-center px-6 py-14">
                <Card className="w-full border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                    <CardHeader className="space-y-1 pb-4">
                        <div className="mb-3 flex justify-center">
                            <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                                <Mail className="h-7 w-7 text-[var(--re-brand)]" />
                            </div>
                        </div>
                        <h2 className="text-center text-2xl font-semibold leading-none tracking-tight text-[var(--re-text-primary)]">
                            Reset your password
                        </h2>
                        <CardDescription className="text-center text-[var(--re-text-muted)]">
                            Enter your email and we&apos;ll send a reset link
                        </CardDescription>
                    </CardHeader>

                    <CardContent>
                        {linkExpired && !submitted && (
                            <div className="mb-4 rounded-md border border-amber-200 bg-re-warning-muted p-3 text-sm text-re-warning dark:border-amber-800 dark:bg-re-warning/10 dark:text-re-warning">
                                Your reset link has expired. Enter your email to receive a new one.
                            </div>
                        )}
                        {submitted ? (
                            <div className="space-y-5 text-center">
                                <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-re-brand-muted">
                                    <ShieldCheck className="h-7 w-7 text-re-brand" />
                                </div>
                                <div className="space-y-1">
                                    <p className="font-medium text-[var(--re-text-primary)]">Check your inbox</p>
                                    <p className="text-sm text-[var(--re-text-muted)]">
                                        If <span className="font-mono text-[var(--re-text-secondary)]">{email}</span> is
                                        registered, you&apos;ll receive a reset link within a minute.
                                    </p>
                                </div>
                                <p className="text-xs text-[var(--re-text-muted)]">
                                    The link expires in 1 hour. Check your spam folder if you don&apos;t see it.
                                </p>
                                <Button
                                    variant="outline"
                                    className="w-full"
                                    onClick={() => router.push('/login')}
                                >
                                    Back to sign in
                                </Button>
                            </div>
                        ) : (
                            <form onSubmit={handleSubmit} className="space-y-4">
                                {error && (
                                    <div
                                        role="alert"
                                        aria-live="polite"
                                        className="animate-in fade-in slide-in-from-top-2 rounded-md border border-re-danger bg-re-danger-muted p-3 text-sm text-re-danger dark:border-re-danger dark:bg-re-danger/10"
                                    >
                                        {error}
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label
                                        className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                                        htmlFor="email"
                                    >
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
                                        autoFocus
                                        className="h-11"
                                    />
                                </div>

                                <Button className="h-11 w-full" type="submit" disabled={isLoading}>
                                    {isLoading ? (
                                        <>
                                            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                            Sending reset link...
                                        </>
                                    ) : (
                                        'Send reset link'
                                    )}
                                </Button>

                                <Link
                                    href="/login"
                                    className="flex items-center justify-center gap-1 text-sm text-[var(--re-text-muted)] transition hover:text-[var(--re-brand)]"
                                >
                                    <ArrowLeft className="h-3.5 w-3.5" />
                                    Back to sign in
                                </Link>
                            </form>
                        )}
                    </CardContent>
                </Card>
            </section>
        </div>
    );
}
