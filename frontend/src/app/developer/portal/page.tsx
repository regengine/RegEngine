'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Key, BarChart3, BookOpen, ArrowRight } from 'lucide-react';

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
    const [profile, setProfile] = useState<DeveloperProfile | null>(null);
    const [stats, setStats] = useState<DashboardStats>({ totalKeys: 0, activeKeys: 0, totalRequests: 0 });

    useEffect(() => {
        async function load() {
            const { data: { user } } = await supabase.auth.getUser();
            if (!user) return;

            const { data: prof } = await supabase
                .from('developer_profiles')
                .select('*')
                .eq('auth_user_id', user.id)
                .single();

            if (prof) {
                setProfile(prof);

                const { data: keys } = await supabase
                    .from('developer_api_keys')
                    .select('id, enabled, total_requests')
                    .eq('developer_id', prof.id);

                if (keys) {
                    setStats({
                        totalKeys: keys.length,
                        activeKeys: keys.filter(k => k.enabled).length,
                        totalRequests: keys.reduce((sum, k) => sum + (k.total_requests || 0), 0),
                    });
                }
            }
        }
        load();
    }, [supabase]);

    const greeting = profile?.display_name || profile?.email?.split('@')[0] || 'Developer';

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>
                    Welcome back, {greeting}
                </h1>
                <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
                    {profile?.company_name ? `${profile.company_name} · ` : ''}Manage your API keys, monitor usage, and explore the docs.
                </p>
            </div>

            {/* Stats cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium" style={{ color: 'var(--re-text-muted)' }}>Active API Keys</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-3xl font-bold" style={{ color: 'var(--re-text-primary)' }}>{stats.activeKeys}</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--re-text-disabled)' }}>{stats.totalKeys} total</p>
                    </CardContent>
                </Card>
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium" style={{ color: 'var(--re-text-muted)' }}>Total Requests</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-3xl font-bold" style={{ color: 'var(--re-text-primary)' }}>{stats.totalRequests.toLocaleString()}</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--re-text-disabled)' }}>all time</p>
                    </CardContent>
                </Card>
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium" style={{ color: 'var(--re-text-muted)' }}>Account Status</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <p className="text-3xl font-bold" style={{ color: 'var(--re-brand)' }}>Active</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--re-text-disabled)' }}>
                            since {profile?.created_at ? new Date(profile.created_at).toLocaleDateString() : '—'}
                        </p>
                    </CardContent>
                </Card>
            </div>

            {/* Quick links */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Link href="/developer/portal/keys">
                    <Card className="cursor-pointer transition-colors hover:border-emerald-500/30" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <CardContent className="flex items-center gap-3 py-4">
                            <Key className="w-5 h-5" style={{ color: 'var(--re-brand)' }} />
                            <div className="flex-1">
                                <p className="text-sm font-medium" style={{ color: 'var(--re-text-primary)' }}>Manage API Keys</p>
                                <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>Generate, revoke, and rotate</p>
                            </div>
                            <ArrowRight className="w-4 h-4" style={{ color: 'var(--re-text-disabled)' }} />
                        </CardContent>
                    </Card>
                </Link>
                <Link href="/developer/portal/usage">
                    <Card className="cursor-pointer transition-colors hover:border-emerald-500/30" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <CardContent className="flex items-center gap-3 py-4">
                            <BarChart3 className="w-5 h-5" style={{ color: 'var(--re-brand)' }} />
                            <div className="flex-1">
                                <p className="text-sm font-medium" style={{ color: 'var(--re-text-primary)' }}>View Usage</p>
                                <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>Requests, latency, errors</p>
                            </div>
                            <ArrowRight className="w-4 h-4" style={{ color: 'var(--re-text-disabled)' }} />
                        </CardContent>
                    </Card>
                </Link>
                <Link href="/developer/portal/docs">
                    <Card className="cursor-pointer transition-colors hover:border-emerald-500/30" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                        <CardContent className="flex items-center gap-3 py-4">
                            <BookOpen className="w-5 h-5" style={{ color: 'var(--re-brand)' }} />
                            <div className="flex-1">
                                <p className="text-sm font-medium" style={{ color: 'var(--re-text-primary)' }}>API Docs</p>
                                <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>Endpoints, examples, SDKs</p>
                            </div>
                            <ArrowRight className="w-4 h-4" style={{ color: 'var(--re-text-disabled)' }} />
                        </CardContent>
                    </Card>
                </Link>
            </div>
        </div>
    );
}
