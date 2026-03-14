'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, ShieldCheck, ArrowLeft } from 'lucide-react';

export default function DeveloperRegisterPage() {
    const router = useRouter();
    const [inviteCode, setInviteCode] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [companyName, setCompanyName] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [step, setStep] = useState<'invite' | 'details'>('invite');
    const [validatedCodeId, setValidatedCodeId] = useState<string | null>(null);

    const supabase = createSupabaseBrowserClient();

    async function validateInviteCode() {
        setIsLoading(true);
        setError(null);

        const { data, error: queryError } = await supabase
            .from('developer_invite_codes')
            .select('id, code, max_uses, used_count, expires_at')
            .eq('code', inviteCode.trim().toUpperCase())
            .single();

        if (queryError || !data) {
            setError('Invalid invite code.');
            setIsLoading(false);
            return;
        }

        if (data.used_count >= data.max_uses) {
            setError('This invite code has reached its usage limit.');
            setIsLoading(false);
            return;
        }

        if (data.expires_at && new Date(data.expires_at) < new Date()) {
            setError('This invite code has expired.');
            setIsLoading(false);
            return;
        }

        setValidatedCodeId(data.id);
        setStep('details');
        setIsLoading(false);
    }

    async function handleRegister(e: React.FormEvent) {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        // 1. Sign up with Supabase Auth
        const { data: authData, error: authError } = await supabase.auth.signUp({
            email: email.trim(),
            password,
        });

        if (authError) {
            setError(authError.message);
            setIsLoading(false);
            return;
        }

        if (!authData.user) {
            setError('Registration failed. Please try again.');
            setIsLoading(false);
            return;
        }

        // 2. Create developer profile
        const { error: profileError } = await supabase
            .from('developer_profiles')
            .insert({
                auth_user_id: authData.user.id,
                email: email.trim(),
                company_name: companyName.trim() || null,
                display_name: displayName.trim() || null,
                invite_code_id: validatedCodeId,
            });

        if (profileError) {
            setError('Profile creation failed: ' + profileError.message);
            setIsLoading(false);
            return;
        }

        // 3. Increment invite code usage
        await supabase.rpc('increment_invite_usage', { code_id: validatedCodeId });

        // 4. Redirect to portal
        router.push('/developer/portal');
    }

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
                        Invite-only access to RegEngine APIs
                    </p>
                </div>

                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardHeader>
                        <CardTitle style={{ color: 'var(--re-text-primary)', fontSize: '16px' }}>
                            {step === 'invite' ? 'Enter Invite Code' : 'Create Your Account'}
                        </CardTitle>
                        <CardDescription style={{ color: 'var(--re-text-muted)' }}>
                            {step === 'invite'
                                ? 'You need a valid invite code to register.'
                                : 'Complete your developer profile.'}
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {step === 'invite' ? (
                            <div className="space-y-4">
                                <Input
                                    placeholder="e.g. REGDEV-ALPHA-2026"
                                    value={inviteCode}
                                    onChange={(e) => setInviteCode(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && validateInviteCode()}
                                    className="font-mono tracking-wider uppercase"
                                    style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
                                />
                                {error && <p className="text-sm text-red-400">{error}</p>}
                                <Button
                                    onClick={validateInviteCode}
                                    disabled={!inviteCode.trim() || isLoading}
                                    className="w-full"
                                    style={{ background: 'var(--re-brand)', color: '#000', fontWeight: 600 }}
                                >
                                    {isLoading ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                                    Validate Code
                                </Button>
                            </div>
                        ) : (
                            <form onSubmit={handleRegister} className="space-y-4">
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
                                        minLength={8}
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--re-text-muted)' }}>Your Name</label>
                                    <Input
                                        value={displayName}
                                        onChange={(e) => setDisplayName(e.target.value)}
                                        style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', color: 'var(--re-text-primary)' }}
                                    />
                                </div>
                                <div>
                                    <label className="text-xs font-medium mb-1 block" style={{ color: 'var(--re-text-muted)' }}>Company (optional)</label>
                                    <Input
                                        value={companyName}
                                        onChange={(e) => setCompanyName(e.target.value)}
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
                                    Create Account
                                </Button>
                            </form>
                        )}

                        <div className="mt-4 pt-4 text-center" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                            <p className="text-sm" style={{ color: 'var(--re-text-muted)' }}>
                                Already have an account?{' '}
                                <Link href="/developer/login" style={{ color: 'var(--re-brand)' }}>Sign in</Link>
                            </p>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
