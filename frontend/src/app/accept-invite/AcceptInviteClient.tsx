
'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiClient } from '@/lib/api-client';
import { Loader2, CheckCircle, AlertCircle } from 'lucide-react';

function readInviteTokenFromLocation(): string | null {
    if (typeof window === 'undefined') return null;

    const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
    const hashToken = hashParams.get('token');
    if (hashToken) return hashToken;

    return new URLSearchParams(window.location.search).get('token');
}

function scrubSensitiveInviteUrl(): void {
    if (typeof window === 'undefined') return;

    const url = new URL(window.location.href);
    const hashParams = new URLSearchParams(url.hash.replace(/^#/, ''));
    const hasSensitiveParams = url.searchParams.has('token') || url.searchParams.has('email') || hashParams.has('token');
    if (!hasSensitiveParams) return;

    url.searchParams.delete('token');
    url.searchParams.delete('email');
    url.hash = '';
    window.history.replaceState(null, document.title, `${url.pathname}${url.search}`);
}

export default function AcceptInvitePage() {
    const MIN_PASSWORD_LENGTH = 12;
    const router = useRouter();

    const [isLoading, setIsLoading] = useState(false);
    const [step, setStep] = useState<'verify' | 'form' | 'success'>('form');
    const [error, setError] = useState<string | null>(null);
    const [token, setToken] = useState<string | null | undefined>(undefined);

    const [password, setPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [name, setName] = useState('');

    useEffect(() => {
        const inviteToken = readInviteTokenFromLocation();
        setToken(inviteToken);
        scrubSensitiveInviteUrl();
        if (!inviteToken) {
            setError("Invalid invitation link.");
        }
    }, []);

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
            if (!token) {
                setError("Invalid invitation link.");
                return;
            }

            await apiClient.acceptInvite({
                token,
                password,
                name
            });

            setStep('success');
        } catch (err: unknown) {
            if (process.env.NODE_ENV !== 'production') {
                console.error(err);
            }
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
                        <Button className="w-full" onClick={() => router.push('/login')}>
                            Go to Login
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
                    {token === undefined ? (
                        <div className="flex items-center gap-2 text-muted-foreground p-4">
                            <Loader2 className="h-5 w-5 animate-spin" />
                            <span>Checking invitation...</span>
                        </div>
                    ) : !token ? (
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
