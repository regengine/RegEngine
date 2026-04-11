
'use client';

import { useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiClient } from '@/lib/api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

export default function AcceptInvitePage() {
    const MIN_PASSWORD_LENGTH = 12;
    const router = useRouter();
    const searchParams = useSearchParams();
    const token = searchParams.get('token');
    const emailParam = searchParams.get('email');

    const [isLoading, setIsLoading] = useState(false);
    const [step, setStep] = useState<'verify' | 'form' | 'success'>('form');
    const [error, setError] = useState<string | null>(null);

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [name, setName] = useState('');

    useEffect(() => {
        if (!token) {
            setError("Invalid invitation link.");
        }
    }, [token]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (password !== confirmPassword) {
            setError("Passwords do not match");
            return;
        }

        if (password.length < MIN_PASSWORD_LENGTH) {
            setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters`);
            return;
        }

        setIsLoading(true);
        try {
            await apiClient.acceptInvite({
                token: token!,
                password,
                name
            });

            // Automatically sign the user in so they don't have to re-enter credentials
            if (emailParam) {
                const supabase = createSupabaseBrowserClient();
                const { error: signInError } = await supabase.auth.signInWithPassword({
                    email: emailParam,
                    password,
                });
                if (!signInError) {
                    router.push('/dashboard');
                    return;
                }
            }

            // Fallback to success screen if auto-login is not possible
            setStep('success');
        } catch (err: unknown) {
            console.error(err);
            const axiosError = err as { response?: { data?: { detail?: string } } };
            if (axiosError?.response?.data?.detail) {
                setError(axiosError.response.data.detail);
            } else {
                setError("Failed to accept invite. It may have expired or been revoked.");
            }
        } finally {
            setIsLoading(false);
        }
    };

    if (step === 'success') {
        return (
            <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
                <Card className="w-full max-w-md text-center">
                    <CardHeader>
                        <div className="flex justify-center mb-4">
                            <CheckCircle className="h-12 w-12 text-re-success" />
                        </div>
                        <CardTitle>Welcome Aboard!</CardTitle>
                        <CardDescription>Your account has been created successfully.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Button className="w-full" onClick={() => router.push('/dashboard')}>
                            Go to Dashboard
                        </Button>
                    </CardContent>
                </Card>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
            <Card className="w-full max-w-md">
                <CardHeader>
                    <CardTitle>Accept Invitation</CardTitle>
                    <CardDescription>Create your account to join the workspace.</CardDescription>
                </CardHeader>
                <CardContent>
                    {!token ? (
                        <div className="flex items-center gap-2 text-destructive bg-destructive/10 p-4 rounded-md">
                            <AlertCircle className="h-5 w-5" />
                            <span>Missing invitation token. Please check your link.</span>
                        </div>
                    ) : (
                        <form onSubmit={handleSubmit} className="space-y-4">
                            {error && (
                                <div className="text-sm text-re-danger bg-re-danger-muted p-3 rounded-md border border-re-danger">
                                    {error}
                                </div>
                            )}

                            <div className="space-y-2">
                                <label className="text-sm font-medium">Full Name</label>
                                <Input
                                    value={name}
                                    onChange={e => setName(e.target.value)}
                                    placeholder="John Doe"
                                    required
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium">Create Password</label>
                                <Input
                                    type="password"
                                    value={password}
                                    onChange={e => setPassword(e.target.value)}
                                    required
                                    minLength={MIN_PASSWORD_LENGTH}
                                />
                            </div>

                            <div className="space-y-2">
                                <label className="text-sm font-medium">Confirm Password</label>
                                <Input
                                    type="password"
                                    value={confirmPassword}
                                    onChange={e => setConfirmPassword(e.target.value)}
                                    required
                                    minLength={MIN_PASSWORD_LENGTH}
                                />
                            </div>

                            <Button type="submit" className="w-full" disabled={isLoading}>
                                {isLoading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                                Create Account
                            </Button>
                        </form>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
