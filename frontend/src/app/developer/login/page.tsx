'use client';

import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, ShieldCheck, ArrowLeft } from 'lucide-react';

function LoginForm() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(
        searchParams.get('error') === 'no_profile'
            ? 'No developer profile found. Please register first.'
            : null
    );

    const supabase = createSupabaseBrowserClient();

    async function handleLogin(e: React.FormEvent) {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        const { error: authError } = await supabase.auth.signInWithPassword({
            email: email.trim(),
            password,
        });

        if (authError) {
            setError(authError.message);
            setIsLoading(false);
            return;
        }

        const next = searchParams.get('next') || '/developer/portal';
        router.push(next);
        router.refresh();
    }

    return (
        <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
            <CardHeader>
                <CardTitle style={{ color: 'var(--re-text-primary)', fontSize: '16px' }}>Sign In</CardTitle>
                <CardDescription style={{ color: 'var(--re-text-muted)' }}>
                    Use your developer account credentials
                </CardDescription>
            </CardHeader>
            <CardContent>
                <form onSubmit={handleLogin} className="space-y-4">
                    <div>
                        <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--re-text-muted)' }}>Email</label>
                        <Input
                            type="email"
                            required
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
                        />
                    </div>
                    <div>
                        <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--re-text-muted)' }}>Password</label>
                        <Input
                            type="password"
                            required
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
                        />
                    </div>
                    {error && <p className="text-sm text-red-400">{error}</p>}
                    <Button
                        type="submit"
                        disabled={isLoading}
                        className="w-full"
                        style={{ background: 'var(--re-brand)', color: '#000', fontWeight: 600 }}
                    >
                        {isLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                        Sign In
                    </Button>
                </form>

                <div className="mt-4 pt-4 text-center" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                    <p className="text-sm" style={{ color: 'var(--re-text-muted)' }}>
                        Have an invite code?{' '}
                        <Link href="/developer/register" style={{ color: 'var(--re-brand)' }}>Register</Link>
                    </p>
                </div>
            </CardContent>
        </Card>
    );
}

export default function DeveloperLoginPage() {
    return (
        <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'var(--re-surface-base)' }}>
            <div className="w-full max-w-md">
                <div className="text-center mb-8">
                    <Link href="/" className="inline-flex items-center gap-2 text-sm mb-6" style={{ color: 'var(--re-text-muted)' }}>
                        <ArrowLeft className="w-4 h-4" /> Back to RegEngine
                    </Link>
                    <div className="flex items-center justify-center gap-2 mb-2">
                        <ShieldCheck className="w-6 h-6" style={{ color: 'var(--re-brand)' }} />
                        <h1 className="text-xl font-bold" style={{ color: 'var(--re-text-primary)' }}>Developer Portal</h1>
                    </div>
                    <p className="text-sm" style={{ color: 'var(--re-text-muted)' }}>
                        Sign in to manage your API keys and usage
                    </p>
                </div>

                <Suspense fallback={
                    <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <CardContent className="py-12 flex justify-center">
                            <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--re-text-muted)' }} />
                        </CardContent>
                    </Card>
                }>
                    <LoginForm />
                </Suspense>
            </div>
        </div>
    );
}
