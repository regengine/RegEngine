'use client';

import { useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiClient } from '@/lib/api-client';
import { Loader2, CheckCircle, AlertCircle, KeyRound } from 'lucide-react';

const MIN_PASSWORD_LENGTH = 12;

export default function ResetPasswordClient() {
    const searchParams = useSearchParams();
    const token = searchParams.get('token');

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [step, setStep] = useState<'form' | 'success'>('form');
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (password !== confirmPassword) {
            setError('Passwords do not match.');
            return;
        }

        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
            return;
        }

        setIsLoading(true);
        try {
            await apiClient.resetPassword(token!, password);
            setStep('success');
        } catch (err: unknown) {
            console.error('Reset password error:', err);
            const axiosError = err as { response?: { status?: number; data?: { detail?: string } } };
            if (axiosError.response?.data?.detail) {
                setError(axiosError.response.data.detail);
            } else if (axiosError.response?.status === 429) {
                setError('Too many requests. Please wait a moment and try again.');
            } else {
                setError('An unexpected error occurred. Please try again.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    if (step === 'success') {
        return (
            <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center p-4">
                <Card className="w-full max-w-md border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 text-center">
                    <CardHeader>
                        <div className="flex justify-center mb-4">
                            <div className="rounded-full border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/10 p-3">
                                <CheckCircle className="h-8 w-8 text-[var(--re-brand)]" />
                            </div>
                        </div>
                        <CardTitle className="text-[var(--re-text-primary)]">Password Reset Successfully</CardTitle>
                        <CardDescription className="text-[var(--re-text-muted)]">
                            Your password has been updated. All existing sessions have been signed out for security.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Link href="/login">
                            <Button className="w-full">Sign In</Button>
                        </Link>
                    </CardContent>
                </Card>
            </div>
        );
    }

    if (!token) {
        return (
            <div className="min-h-screen bg-[var(--re-surface-base)] flex items-center justify-center p-4">
                <Card className="w-full max-w-md border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 text-center">
                    <CardHeader>
                        <div className="flex justify-center mb-4">
                            <div className="rounded-full border border-red-300 bg-red-50 p-3 dark:border-red-800 dark:bg-red-900/20">
                                <AlertCircle className="h-8 w-8 text-red-500" />
                            </div>
                        </div>
                        <CardTitle className="text-[var(--re-text-primary)]">Invalid Reset Link</CardTitle>
                        <CardDescription className="text-[var(--re-text-muted)]">
                            This password reset link is invalid. Please request a new one.
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Link href="/forgot-password">
                            <Button className="w-full">Request New Reset Link</Button>
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
                            <KeyRound className="h-7 w-7 text-[var(--re-brand)]" />
                        </div>
                    </div>
                    <CardTitle className="text-[var(--re-text-primary)]">Reset Password</CardTitle>
                    <CardDescription className="text-[var(--re-text-muted)]">
                        Enter your new password below.
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
                            <label className="text-sm font-medium leading-none" htmlFor="password">
                                New Password
                            </label>
                            <Input
                                id="password"
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                disabled={isLoading}
                                required
                                autoComplete="new-password"
                                minLength={MIN_PASSWORD_LENGTH}
                                className="h-11"
                            />
                        </div>

                        <div className="space-y-2">
                            <label className="text-sm font-medium leading-none" htmlFor="confirmPassword">
                                Confirm Password
                            </label>
                            <Input
                                id="confirmPassword"
                                type="password"
                                value={confirmPassword}
                                onChange={(e) => setConfirmPassword(e.target.value)}
                                disabled={isLoading}
                                required
                                minLength={MIN_PASSWORD_LENGTH}
                                className="h-11"
                            />
                        </div>

                        <p className="text-xs text-[var(--re-text-muted)]">
                            At least {MIN_PASSWORD_LENGTH} characters with uppercase, lowercase, digit, and special character.
                        </p>

                        <Button className="h-11 w-full" type="submit" disabled={isLoading}>
                            {isLoading ? (
                                <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Resetting...
                                </>
                            ) : (
                                'Reset Password'
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
