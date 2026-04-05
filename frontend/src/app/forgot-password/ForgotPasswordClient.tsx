'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiClient } from '@/lib/api-client';
import { Loader2, CheckCircle, Mail } from 'lucide-react';

export default function ForgotPasswordClient() {
    const [email, setEmail] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [isSubmitted, setIsSubmitted] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!email.trim()) {
            setError('Email is required.');
            return;
        }

        setIsLoading(true);
        try {
            await apiClient.forgotPassword(email);
            setIsSubmitted(true);
        } catch (err: unknown) {
            console.error('Forgot password error:', err);
            const axiosError = err as { response?: { status?: number } };
            if (axiosError.response?.status === 429) {
                setError('Too many requests. Please wait a moment and try again.');
            } else {
                setError('An unexpected error occurred. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    if (isSubmitted) {
        return (
            <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center p-4">
                <Card className="w-full max-w-md border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 text-center">
                    <CardHeader>
                        <div className="flex justify-center mb-4">
                            <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                                <CheckCircle className="h-8 w-8 text-[var(--re-brand)]" />
                            </div>
                        </div>
                        <CardTitle className="text-[var(--re-text-primary)]">Check your email</CardTitle>
                        <CardDescription className="text-[var(--re-text-muted)]">
                            If an account exists for <span className="font-medium text-[var(--re-text-secondary)]">{email}</span>,
                            we&apos;ve sent a password reset link. The link expires in 1 hour.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Link href="/login">
                            <Button className="w-full">Back to Login</Button>
                        </Link>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center p-4">
            <Card className="w-full max-w-md border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95">
                <CardHeader className="text-center">
                    <div className="flex justify-center mb-3">
                        <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                            <Mail className="h-7 w-7 text-[var(--re-brand)]" />
                        </div>
                    </div>
                    <CardTitle className="text-[var(--re-text-primary)]">Forgot Password</CardTitle>
                    <CardDescription className="text-[var(--re-text-muted)]">
                        Enter your email address and we&apos;ll send you a reset link.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        {error && (
                            <div
                                role="alert"
                                className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-500 dark:border-red-800 dark:bg-red-900/10"
                            >
                                {error}
                            </div>
                        )}

                        <div className="space-y-2">
                            <label className="text-sm font-medium leading-none" htmlFor="email">
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
                                className="h-11"
                            />
                        </div>

                        <Button className="h-11 w-full" type="submit" disabled={isLoading}>
                            {isLoading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Sending...
                                </>
                            ) : (
                                'Send Reset Link'
                            )}
                        </Button>

                        <div className="text-center text-sm text-[var(--re-text-muted)]">
                            <Link href="/login" className="font-medium text-[var(--re-brand)] hover:underline">
                                Back to Login
                            </Link>
                        </div>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
