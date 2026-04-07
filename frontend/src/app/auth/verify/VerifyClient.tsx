'use client';

/**
 * VerifyClient — token-hash password reset verification
 *
 * WHY THIS EXISTS:
 * Email clients (Gmail, Outlook SafeLinks, etc.) prefetch every link in an
 * email within seconds of delivery to scan for phishing. If the reset link
 * goes directly to Supabase's /auth/v1/verify endpoint, the prefetcher
 * consumes the one-time OTP before the user ever clicks — making the link
 * appear "expired" immediately.
 *
 * FIX:
 * The email links to THIS page (/auth/verify?token=HASH&type=recovery).
 * Email clients fetch the page and see static HTML with a button. Buttons
 * cannot be "prefetched" — only the user can click them. The actual
 * verifyOtp() API call is made from JavaScript on click, so the OTP token
 * is never consumed until the user deliberately acts.
 *
 * This also eliminates the PKCE code-verifier mismatch problem (user clicks
 * link on a different device than where they requested the reset), because
 * verifyOtp({ token_hash }) exchanges the token directly for a session
 * without needing a PKCE verifier stored in the browser.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Loader2, ShieldCheck, AlertTriangle } from 'lucide-react';

type VerifyClientProps = {
    tokenHash: string;
    type: string;
};

export default function VerifyClient({ tokenHash, type }: VerifyClientProps) {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const supabase = createSupabaseBrowserClient();

    const handleVerify = async () => {
        setLoading(true);
        setError(null);

        const { error: verifyError } = await supabase.auth.verifyOtp({
            token_hash: tokenHash,
            type: type === 'recovery' ? 'recovery' : 'recovery',
        });

        if (verifyError) {
            // Token already used or expired
            router.push('/forgot-password?error=link_expired');
            return;
        }

        // Session is now active — send to the reset form
        router.push('/reset-password');
    };

    if (!tokenHash) {
        return (
            <div className="relative overflow-hidden bg-[var(--re-surface-base)]">
                <section className="relative z-[1] mx-auto flex min-h-[80vh] max-w-md items-center px-6 py-14">
                    <Card className="w-full border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                        <CardHeader className="space-y-1 pb-4">
                            <div className="mb-3 flex justify-center">
                                <div className="rounded-full border border-red-300/30 bg-red-500/10 p-3">
                                    <AlertTriangle className="h-7 w-7 text-red-500" />
                                </div>
                            </div>
                            <h2 className="text-center text-2xl font-semibold text-[var(--re-text-primary)]">
                                Invalid reset link
                            </h2>
                        </CardHeader>
                        <CardContent className="space-y-4 text-center">
                            <p className="text-sm text-[var(--re-text-muted)]">
                                This link is missing required parameters. Please request a new reset link.
                            </p>
                            <Button className="w-full" onClick={() => router.push('/forgot-password')}>
                                Request a new link
                            </Button>
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
                <Card className="w-full border-[var(--re-surface-border)] bg-[var(--re-surface-card)] shadow-[0_16px_70px_rgba(0,0,0,0.25)]">
                    <CardHeader className="space-y-1 pb-4">
                        <div className="mb-3 flex justify-center">
                            <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                                <ShieldCheck className="h-7 w-7 text-[var(--re-brand)]" />
                            </div>
                        </div>
                        <h2 className="text-center text-2xl font-semibold leading-none tracking-tight text-[var(--re-text-primary)]">
                            Reset your password
                        </h2>
                        <p className="text-center text-sm text-[var(--re-text-muted)]">
                            Click below to open your password reset form
                        </p>
                    </CardHeader>

                    <CardContent className="space-y-4">
                        {error && (
                            <div
                                role="alert"
                                className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-500 dark:border-red-800 dark:bg-red-900/10"
                            >
                                {error}
                            </div>
                        )}

                        <Button
                            className="h-11 w-full"
                            onClick={handleVerify}
                            disabled={loading}
                        >
                            {loading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Verifying…
                                </>
                            ) : (
                                'Continue to reset password'
                            )}
                        </Button>

                        <p className="text-center text-xs text-[var(--re-text-muted)]">
                            This link expires in 1 hour.{' '}
                            <a
                                href="/forgot-password"
                                className="underline underline-offset-2 hover:text-[var(--re-brand)]"
                            >
                                Request a new one
                            </a>{' '}
                            if it no longer works.
                        </p>
                    </CardContent>
                </Card>
            </section>
        </div>
    );
}
