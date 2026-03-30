'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/auth-context';
import {
    Key, BarChart3, BookOpen, ArrowRight, Terminal, Zap,
    CheckCircle2, Circle, Webhook, Package, Loader2,
} from 'lucide-react';

interface DeveloperProfile {
    id: string;
    email: string;
    display_name: string | null;
    company_name: string | null;
    created_at: string;
}

interface DashboardStats {
    totalKeys: number;
    activeKeys: number;
    totalRequests: number;
}

export default function DeveloperPortalDashboard() {
    const supabase = createSupabaseBrowserClient();
    const { user: authUser } = useAuth();
    const [profile, setProfile] = useState<DeveloperProfile | null>(null);
    const [stats, setStats] = useState<DashboardStats>({ totalKeys: 0, activeKeys: 0, totalRequests: 0 });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function load() {
            if (!authUser) return;

            const { data: prof, error: profError } = await supabase
                .from('developer_profiles')
                .select('*')
                .eq('auth_user_id', authUser.id)
                .maybeSingle();

            if (profError) {
                console.error('Failed to fetch developer profile:', profError.message);
            }
            if (prof) {
                setProfile(prof);
                const { data: keys, error: keysError } = await supabase
                    .from('developer_api_keys')
                    .select('id, enabled, total_requests')
                    .eq('developer_id', prof.id);

                if (keysError) {
                    console.error('Failed to fetch API keys:', keysError.message);
                }

                if (keys) {
                    setStats({
                        totalKeys: keys.length,
                        activeKeys: keys.filter(k => k.enabled).length,
                        totalRequests: keys.reduce((sum, k) => sum + (k.total_requests || 0), 0),
                    });
                }
            }
            setLoading(false);
        }
        load();
    }, [supabase, authUser]);

    const greeting = profile?.display_name || profile?.email?.split('@')[0] || 'Developer';

    // Onboarding checklist
    const onboardingSteps = [
        { label: 'Create your account', done: true, href: '#' },
        { label: 'Generate an API key', done: stats.activeKeys > 0, href: '/developer/portal/keys' },
        { label: 'Send your first event', done: stats.totalRequests > 0, href: '/docs' },
        { label: 'Try the API Playground', done: false, href: '/developer/portal/playground' },
        { label: 'Set up webhooks', done: false, href: '/docs/webhooks' },
    ];
    const completedSteps = onboardingSteps.filter(s => s.done).length;
    const progress = Math.round((completedSteps / onboardingSteps.length) * 100);

    if (loading) {
        return (
            <div className="flex justify-center py-20">
                <Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--re-text-muted)' }} />
            </div>
        );
    }

    return (
        <div className="space-y-8">
            {/* Welcome */}
            <div>
                <h1 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>
                    Welcome back, {greeting}
                </h1>
                <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
                    {profile?.company_name ? `${profile.company_name} · ` : ''}Your developer dashboard for RegEngine.
                </p>
            </div>

            {/* Onboarding checklist */}
            {completedSteps < onboardingSteps.length && (
                <div className="rounded-lg p-5" style={{
                    background: 'rgba(16,185,129,0.04)',
                    border: '1px solid rgba(16,185,129,0.12)',
                }}>
                    <div className="flex items-center justify-between mb-4">
                        <div>
                            <h2 className="text-sm font-semibold" style={{ color: 'var(--re-text-primary)' }}>Getting Started</h2>
                            <p className="text-xs mt-0.5" style={{ color: 'var(--re-text-muted)' }}>
                                {completedSteps} of {onboardingSteps.length} steps complete
                            </p>
                        </div>
                        <div className="flex items-center gap-2">
                            <div className="w-24 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                                <div className="h-full rounded-full transition-all" style={{
                                    width: `${progress}%`,
                                    background: 'var(--re-brand)',
                                }} />
                            </div>
                            <span className="text-xs font-medium" style={{ color: 'var(--re-brand)' }}>{progress}%</span>
                        </div>
                    </div>
                    <div className="space-y-2">
                        {onboardingSteps.map((step) => (
                            <Link key={step.label} href={step.href} className="flex items-center gap-3 py-1.5 no-underline group">
                                {step.done
                                    ? <CheckCircle2 className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--re-brand)' }} />
                                    : <Circle className="w-4 h-4 flex-shrink-0" style={{ color: 'var(--re-text-disabled)' }} />
                                }
                                <span className="text-sm" style={{
                                    color: step.done ? 'var(--re-text-disabled)' : 'var(--re-text-primary)',
                                    textDecoration: step.done ? 'line-through' : 'none',
                                }}>
                                    {step.label}
                                </span>
                                {!step.done && <ArrowRight className="w-3 h-3 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--re-text-muted)' }} />}
                            </Link>
                        ))}
                    </div>
                </div>
            )}

            {/* Stats cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {[
                    { label: 'Active API Keys', value: stats.activeKeys, sub: `${stats.totalKeys} total`, color: 'var(--re-brand)' },
                    { label: 'Total Requests', value: stats.totalRequests.toLocaleString(), sub: 'all time', color: '#60a5fa' },
                    { label: 'Account Status', value: 'Active', sub: `since ${profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : '—'}`, color: 'var(--re-brand)' },
                ].map((card) => (
                    <div key={card.label} className="rounded-lg p-5" style={{
                        background: 'rgba(255,255,255,0.02)',
                        border: '1px solid rgba(255,255,255,0.06)',
                    }}>
                        <p className="text-xs font-medium mb-2" style={{ color: 'var(--re-text-muted)' }}>{card.label}</p>
                        <p className="text-2xl font-bold" style={{ color: card.color }}>{card.value}</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--re-text-disabled)' }}>{card.sub}</p>
                    </div>
                ))}
            </div>

            {/* Quick links */}
            <div>
                <h2 className="text-xs font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--re-text-disabled)' }}>
                    Quick Links
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {[
                        { label: 'API Keys', desc: 'Generate, revoke, and rotate', href: '/developer/portal/keys', icon: Key },
                        { label: 'Usage & Logs', desc: 'Requests, latency, errors', href: '/developer/portal/usage', icon: BarChart3 },
                        { label: 'Quickstart', desc: '60-second integration guide', href: '/docs', icon: Zap },
                        { label: 'API Reference', desc: 'All endpoints documented', href: '/docs/api', icon: BookOpen },
                        { label: 'Playground', desc: 'Test endpoints live', href: '/developer/portal/playground', icon: Terminal },
                        { label: 'Webhooks', desc: 'Real-time event delivery', href: '/docs/webhooks', icon: Webhook },
                    ].map((item) => (
                        <Link key={item.href} href={item.href} className="group flex items-center gap-3 rounded-lg p-4 no-underline transition-all" style={{
                            background: 'rgba(255,255,255,0.02)',
                            border: '1px solid rgba(255,255,255,0.06)',
                        }}>
                            <item.icon className="w-5 h-5 flex-shrink-0" style={{ color: 'var(--re-brand)' }} />
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium" style={{ color: 'var(--re-text-primary)' }}>{item.label}</p>
                                <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>{item.desc}</p>
                            </div>
                            <ArrowRight className="w-4 h-4 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" style={{ color: 'var(--re-text-disabled)' }} />
                        </Link>
                    ))}
                </div>
            </div>
        </div>
    );
}
