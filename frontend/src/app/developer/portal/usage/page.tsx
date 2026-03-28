'use client';

import { useEffect, useState, useCallback } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { useAuth } from '@/lib/auth-context';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingUp, Clock, AlertCircle, Activity } from 'lucide-react';

interface UsageRow {
    endpoint: string;
    method: string;
    status_code: number;
    response_time_ms: number | null;
    created_at: string;
}

interface EndpointSummary {
    endpoint: string;
    method: string;
    count: number;
    avgLatency: number;
    errorRate: number;
}

export default function UsagePage() {
    const supabase = createSupabaseBrowserClient();
    const { user: authUser } = useAuth();
    const [usage, setUsage] = useState<UsageRow[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [timeRange, setTimeRange] = useState<'24h' | '7d' | '30d'>('7d');

    const loadUsage = useCallback(async () => {
        setIsLoading(true);
        if (!authUser) return;

        const { data: profile } = await supabase
            .from('developer_profiles')
            .select('id')
            .eq('auth_user_id', authUser.id)
            .single();

        if (!profile) return;

        const since = new Date();
        if (timeRange === '24h') since.setHours(since.getHours() - 24);
        else if (timeRange === '7d') since.setDate(since.getDate() - 7);
        else since.setDate(since.getDate() - 30);

        const { data } = await supabase
            .from('developer_api_usage')
            .select('endpoint, method, status_code, response_time_ms, created_at')
            .eq('developer_id', profile.id)
            .gte('created_at', since.toISOString())
            .order('created_at', { ascending: false })
            .limit(1000);

        setUsage(data || []);
        setIsLoading(false);
    }, [supabase, authUser, timeRange]);

    useEffect(() => { loadUsage(); }, [loadUsage]);

    // Compute summary stats
    const totalRequests = usage.length;
    const errorCount = usage.filter(r => r.status_code >= 400).length;
    const errorRate = totalRequests > 0 ? ((errorCount / totalRequests) * 100).toFixed(1) : '0';
    const avgLatency = totalRequests > 0
        ? Math.round(usage.reduce((sum, r) => sum + (r.response_time_ms || 0), 0) / totalRequests)
        : 0;

    // Group by endpoint
    const endpointMap = new Map<string, UsageRow[]>();
    usage.forEach(row => {
        const key = `${row.method} ${row.endpoint}`;
        if (!endpointMap.has(key)) endpointMap.set(key, []);
        endpointMap.get(key)!.push(row);
    });

    const endpoints: EndpointSummary[] = Array.from(endpointMap.entries())
        .map(([, rows]) => ({
            endpoint: rows[0].endpoint,
            method: rows[0].method,
            count: rows.length,
            avgLatency: Math.round(rows.reduce((s, r) => s + (r.response_time_ms || 0), 0) / rows.length),
            errorRate: (rows.filter(r => r.status_code >= 400).length / rows.length) * 100,
        }))
        .sort((a, b) => b.count - a.count);

    if (isLoading) {
        return <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" style={{ color: 'var(--re-text-muted)' }} /></div>;
    }

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>API Usage</h1>
                    <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
                        Monitor your API request volume, latency, and error rates.
                    </p>
                </div>
                <div className="flex gap-1 p-1 rounded-md" style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    {(['24h', '7d', '30d'] as const).map(range => (
                        <button
                            key={range}
                            onClick={() => setTimeRange(range)}
                            className="px-3 py-1 text-xs font-medium rounded transition-colors"
                            style={{
                                background: timeRange === range ? 'rgba(16,185,129,0.15)' : 'transparent',
                                color: timeRange === range ? 'var(--re-brand)' : 'var(--re-text-muted)',
                            }}
                        >
                            {range}
                        </button>
                    ))}
                </div>
            </div>

            {/* Summary cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <Activity className="w-4 h-4" style={{ color: 'var(--re-brand)' }} />
                            <span className="text-xs font-medium" style={{ color: 'var(--re-text-muted)' }}>Requests</span>
                        </div>
                        <p className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>{totalRequests.toLocaleString()}</p>
                    </CardContent>
                </Card>
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <Clock className="w-4 h-4" style={{ color: '#60a5fa' }} />
                            <span className="text-xs font-medium" style={{ color: 'var(--re-text-muted)' }}>Avg Latency</span>
                        </div>
                        <p className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>{avgLatency}ms</p>
                    </CardContent>
                </Card>
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <AlertCircle className="w-4 h-4" style={{ color: '#f87171' }} />
                            <span className="text-xs font-medium" style={{ color: 'var(--re-text-muted)' }}>Error Rate</span>
                        </div>
                        <p className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>{errorRate}%</p>
                    </CardContent>
                </Card>
                <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardContent className="py-4">
                        <div className="flex items-center gap-2 mb-1">
                            <TrendingUp className="w-4 h-4" style={{ color: '#a78bfa' }} />
                            <span className="text-xs font-medium" style={{ color: 'var(--re-text-muted)' }}>Endpoints Hit</span>
                        </div>
                        <p className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>{endpoints.length}</p>
                    </CardContent>
                </Card>
            </div>

            {/* Endpoint breakdown */}
            <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <CardHeader>
                    <CardTitle className="text-sm" style={{ color: 'var(--re-text-primary)' }}>Endpoint Breakdown</CardTitle>
                </CardHeader>
                <CardContent>
                    {endpoints.length === 0 ? (
                        <p className="text-sm text-center py-8" style={{ color: 'var(--re-text-muted)' }}>
                            No API activity in this time period. Make your first request to see usage data.
                        </p>
                    ) : (
                        <div className="space-y-2">
                            {endpoints.map((ep, i) => (
                                <div key={i} className="flex items-center gap-3 py-2 px-3 rounded" style={{ background: 'rgba(0,0,0,0.15)' }}>
                                    <Badge
                                        variant="outline"
                                        className="font-mono text-xs w-14 justify-center"
                                        style={{
                                            color: ep.method === 'POST' ? 'var(--re-brand)' : '#60a5fa',
                                            borderColor: ep.method === 'POST' ? 'rgba(16,185,129,0.3)' : 'rgba(96,165,250,0.3)',
                                        }}
                                    >
                                        {ep.method}
                                    </Badge>
                                    <code className="text-xs font-mono flex-1 truncate" style={{ color: 'var(--re-text-primary)' }}>{ep.endpoint}</code>
                                    <span className="text-xs tabular-nums" style={{ color: 'var(--re-text-muted)' }}>{ep.count.toLocaleString()} req</span>
                                    <span className="text-xs tabular-nums w-16 text-right" style={{ color: 'var(--re-text-disabled)' }}>{ep.avgLatency}ms</span>
                                    <span className="text-xs tabular-nums w-12 text-right" style={{ color: ep.errorRate > 5 ? '#f87171' : 'var(--re-text-disabled)' }}>
                                        {ep.errorRate.toFixed(1)}%
                                    </span>
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
