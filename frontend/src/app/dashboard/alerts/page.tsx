'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import {
    Bell,
    AlertTriangle,
    ShieldAlert,
    ThermometerSun,
    Clock,
    CheckCircle2,
    Link2,
    TrendingDown,
    Activity,
    Filter,
    RefreshCw,
    Siren,
    ExternalLink,
    Building2,
    Hash,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { fetchAlerts, acknowledgeAlert } from '@/lib/api-hooks';

/* ── Types matching AlertsResponse from backend ── */

interface Alert {
    id: string;
    rule_id: string;
    rule_name: string;
    severity: string;
    category: string;
    title: string;
    message: string;
    triggered_at: string;
    acknowledged: boolean;
    acknowledged_at: string | null;
    acknowledged_by: string | null;
    metadata: Record<string, unknown>;
}

interface AlertsResponse {
    tenant_id: string;
    total: number;
    unacknowledged: number;
    alerts: Alert[];
}

type SeverityFilter = 'critical' | 'warning' | 'info' | 'fda_recall' | 'all';

const SEVERITY_CONFIG: Record<string, { color: string; bg: string; border: string; label: string }> = {
    critical: { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.2)', label: 'Critical' },
    warning: { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.2)', label: 'Warning' },
    info: { color: '#3b82f6', bg: 'rgba(59,130,246,0.08)', border: 'rgba(59,130,246,0.2)', label: 'Info' },
};

const CATEGORY_ICONS: Record<string, React.ElementType> = {
    compliance: ShieldAlert,
    temperature: ThermometerSun,
    deadline: Link2,
    score: TrendingDown,
    overdue: Clock,
    fda_recall: Siren,
};

// Classification badge colours for FDA recalls
const RECALL_CLASS_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
    'Class I':   { color: '#ef4444', bg: 'rgba(239,68,68,0.12)',  label: 'Class I'   },
    'Class II':  { color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', label: 'Class II'  },
    'Class III': { color: '#6b7280', bg: 'rgba(107,114,128,0.12)', label: 'Class III' },
};

function formatTimeAgo(iso: string): string {
    try {
        const diff = Date.now() - new Date(iso).getTime();
        const mins = Math.floor(diff / 60000);
        if (mins < 60) return `${mins} min ago`;
        const hours = Math.floor(mins / 60);
        if (hours < 24) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
        const days = Math.floor(hours / 24);
        return `${days} day${days !== 1 ? 's' : ''} ago`;
    } catch {
        return iso;
    }
}

export default function AlertsDashboardPage() {
    const { isAuthenticated, apiKey } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = isAuthenticated;

    const alertsQueryClient = useQueryClient();

    const [filter, setFilter] = useState<SeverityFilter>('all');

    const { data: alertsData, isLoading: loading, error: alertsError, refetch: loadAlerts, isSuccess } = useQuery({
        queryKey: ['alerts', tenantId],
        queryFn: async () => {
            const data = (await fetchAlerts(tenantId, apiKey || '')) as AlertsResponse;
            return data.alerts || [];
        },
        enabled: isLoggedIn && !!tenantId,
    });

    const alerts = alertsData ?? [];
    const error = alertsError?.message ?? null;
    const fetchFailed = !!alertsError;

    const [ackError, setAckError] = useState<string | null>(null);

    const acknowledgeMutation = useMutation({
        mutationFn: (alertId: string) => acknowledgeAlert(tenantId, apiKey || '', alertId),
        onSuccess: (_data, alertId) => {
            setAckError(null);
            alertsQueryClient.setQueryData<Alert[]>(['alerts', tenantId], (old) =>
                (old ?? []).map(a => a.id === alertId ? { ...a, acknowledged: true } : a)
            );
        },
        onError: (err: Error) => {
            setAckError(err.message || 'Failed to acknowledge alert');
        },
    });

    const handleAcknowledge = (alertId: string) => {
        acknowledgeMutation.mutate(alertId);
    };

    const filtered = filter === 'all'
        ? alerts
        : filter === 'fda_recall'
            ? alerts.filter(a => a.category === 'fda_recall')
            : alerts.filter(a => a.severity === filter);
    const criticalCount = alerts.filter(a => a.severity === 'critical' && !a.acknowledged).length;
    const warningCount = alerts.filter(a => a.severity === 'warning' && !a.acknowledged).length;
    const infoCount = alerts.filter(a => a.severity === 'info' && !a.acknowledged).length;
    const fdaRecallCount = alerts.filter(a => a.category === 'fda_recall' && !a.acknowledged).length;
    const unackCount = alerts.filter(a => !a.acknowledged).length;

    return (
        <div className="min-h-screen bg-background py-6 sm:py-10 px-4 sm:px-6 lg:px-8">
            <div className="max-w-5xl mx-auto space-y-5 sm:space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                    <div>
                        <h1 className="text-xl sm:text-2xl font-bold flex items-center gap-2 sm:gap-3">
                            <Bell className="h-5 w-5 sm:h-6 sm:w-6 text-[var(--re-brand)]" />
                            Alerts & Notifications
                        </h1>
                        <p className="text-xs sm:text-sm text-muted-foreground mt-1">
                            {unackCount} unacknowledged alert{unackCount !== 1 ? 's' : ''}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" className="rounded-xl min-h-[44px]" onClick={() => loadAlerts()} disabled={loading}>
                            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Refresh
                        </Button>
                        <Badge variant="outline" className="text-xs py-1.5 min-h-[44px] flex items-center">
                            <Activity className="h-3 w-3 mr-1" /> Live
                        </Badge>
                    </div>
                </div>

                {/* Auth gate */}
                {!isLoggedIn && (
                    <Card className="border-orange-300 dark:border-orange-700">
                        <CardContent className="py-6 text-center text-sm text-muted-foreground">
                            Sign in to view alerts.
                        </CardContent>
                    </Card>
                )}

                {/* Loading */}
                {loading && alerts.length === 0 && (
                    <div className="flex justify-center py-16">
                        <Spinner size="lg" />
                    </div>
                )}

                {/* Error */}
                {fetchFailed && (
                    <Card className="border-red-400 dark:border-red-700">
                        <CardContent className="py-4">
                            <div className="flex items-center justify-between gap-3">
                                <div className="flex items-center gap-3 text-red-600 dark:text-red-400">
                                    <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                                    <p className="text-sm font-medium">Unable to load alerts. Your compliance status may have changed.</p>
                                </div>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    className="rounded-xl text-xs flex-shrink-0 min-h-[44px] border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950"
                                    onClick={() => loadAlerts()}
                                    disabled={loading}
                                >
                                    <RefreshCw className={`h-3.5 w-3.5 mr-1 ${loading ? 'animate-spin' : ''}`} /> Retry
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {isLoggedIn && !loading && alerts.length > 0 && (
                    <>
                        {/* Summary Cards */}
                        <div className="grid grid-cols-3 gap-2 sm:gap-4">
                            {[
                                { label: 'Critical', count: criticalCount, color: '#ef4444', f: 'critical' as const },
                                { label: 'Warnings', count: warningCount, color: '#f59e0b', f: 'warning' as const },
                                { label: 'Info', count: infoCount, color: '#3b82f6', f: 'info' as const },
                            ].map((item) => (
                                <button
                                    key={item.label}
                                    onClick={() => setFilter(filter === item.f ? 'all' : item.f)}
                                    className={`p-3 sm:p-4 rounded-xl border transition-all text-left min-h-[48px] active:scale-[0.97] ${
                                        filter === item.f
                                            ? 'border-[var(--re-brand)] bg-[color-mix(in_srgb,var(--re-brand)_5%,transparent)]'
                                            : 'border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] hover:border-[var(--re-brand)]'
                                    }`}
                                >
                                    <div className="text-xl sm:text-2xl font-bold" style={{ color: item.color }}>{item.count}</div>
                                    <div className="text-[11px] sm:text-xs text-muted-foreground">{item.label}</div>
                                </button>
                            ))}
                        </div>

                        {/* Filter Bar */}
                        <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto no-scrollbar">
                            <Filter className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                            {(['all', 'critical', 'warning', 'info'] as const).map((f) => (
                                <button
                                    key={f}
                                    onClick={() => setFilter(f)}
                                    className={`px-3 min-h-[44px] rounded-full text-xs font-medium border transition-all whitespace-nowrap active:scale-[0.96] ${
                                        filter === f
                                            ? 'bg-[var(--re-brand)] text-white border-[var(--re-brand)]'
                                            : 'border-[var(--re-border-default)] hover:border-[var(--re-brand)]'
                                    }`}
                                >
                                    {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                                </button>
                            ))}
                            {fdaRecallCount > 0 && (
                                <button
                                    onClick={() => setFilter(filter === 'fda_recall' ? 'all' : 'fda_recall')}
                                    className={`px-3 min-h-[44px] rounded-full text-xs font-medium border transition-all whitespace-nowrap active:scale-[0.96] flex items-center gap-1.5 ${
                                        filter === 'fda_recall'
                                            ? 'bg-re-danger text-white border-re-danger'
                                            : 'border-re-danger/40 text-re-danger hover:border-re-danger'
                                    }`}
                                >
                                    <Siren className="h-3 w-3" />
                                    FDA Recalls
                                    <span className="ml-0.5 bg-white/20 rounded-full px-1">{fdaRecallCount}</span>
                                </button>
                            )}
                        </div>

                        {/* Alert List */}
                        <div className="space-y-3">
                            <AnimatePresence>
                                {filtered.map((alert) => {
                                    const config = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
                                    const Icon = CATEGORY_ICONS[alert.category] || AlertTriangle;

                                    // ── FDA Recall card variant ──────────────────────────────────
                                    if (alert.category === 'fda_recall') {
                                        const meta = alert.metadata as Record<string, string> ?? {};
                                        const classification = meta.classification ?? '';
                                        const recallClass = RECALL_CLASS_CONFIG[classification] ?? RECALL_CLASS_CONFIG['Class I'];
                                        const recallNumber = meta.recall_number ?? '';
                                        const recallingFirm = meta.recalling_firm as string ?? '';
                                        const matchedBy: string[] = (meta.matched_by as unknown as string[]) ?? [];
                                        const matchTier = matchedBy.find(r => r.startsWith('match_tier:'))?.replace('match_tier:', '') ?? 'profile';
                                        const fdaUrl = recallNumber
                                            ? `https://www.accessdata.fda.gov/scripts/ires/index.cfm?event=ires.dspBriefRecallNumber&RecallNumber=${recallNumber}`
                                            : undefined;

                                        return (
                                            <motion.div
                                                key={alert.id}
                                                initial={{ opacity: 0, y: 10 }}
                                                animate={{ opacity: 1, y: 0 }}
                                                exit={{ opacity: 0, height: 0 }}
                                                className={`relative rounded-xl border-2 p-3 sm:p-4 transition-all ${alert.acknowledged ? 'opacity-50' : ''}`}
                                                style={{
                                                    borderColor: alert.acknowledged ? 'var(--re-border-default)' : recallClass.color,
                                                    background: alert.acknowledged ? 'transparent' : recallClass.bg,
                                                }}
                                            >
                                                <div className="flex items-start gap-2 sm:gap-3">
                                                    <div className="mt-0.5 flex-shrink-0" style={{ color: recallClass.color }}>
                                                        <Siren className="h-5 w-5" />
                                                    </div>
                                                    <div className="flex-1 min-w-0">
                                                        {/* Title row */}
                                                        <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                                                            <span className="text-xs sm:text-sm font-semibold">{alert.title}</span>
                                                            <Badge
                                                                className="text-[9px] px-1.5 py-0 font-bold"
                                                                style={{ background: recallClass.bg, color: recallClass.color, border: `1px solid ${recallClass.color}` }}
                                                            >
                                                                {recallClass.label}
                                                            </Badge>
                                                            <Badge variant="outline" className="text-[9px] px-1.5 py-0">
                                                                FDA Recall
                                                            </Badge>
                                                            {alert.acknowledged && (
                                                                <Badge variant="outline" className="text-[9px] px-1.5 py-0">
                                                                    <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" /> Acknowledged
                                                                </Badge>
                                                            )}
                                                        </div>

                                                        {/* Reason / summary */}
                                                        <p className="text-[11px] sm:text-xs text-muted-foreground line-clamp-2 mb-1.5">{alert.message}</p>

                                                        {/* Recall metadata strip */}
                                                        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-muted-foreground/80">
                                                            {recallingFirm && (
                                                                <span className="flex items-center gap-1">
                                                                    <Building2 className="h-3 w-3" /> {recallingFirm}
                                                                </span>
                                                            )}
                                                            {recallNumber && (
                                                                <span className="flex items-center gap-1">
                                                                    <Hash className="h-3 w-3" /> {recallNumber}
                                                                </span>
                                                            )}
                                                            <span className="flex items-center gap-1 capitalize">
                                                                Match: <strong>{matchTier === 'lot_code' ? 'Lot Code' : matchTier === 'supplier' ? 'Supplier' : 'Product Profile'}</strong>
                                                            </span>
                                                        </div>

                                                        {/* Footer row */}
                                                        <div className="flex items-center justify-between mt-2 gap-2">
                                                            <div className="flex items-center gap-3">
                                                                <span className="text-[10px] text-muted-foreground/60">
                                                                    {formatTimeAgo(alert.triggered_at)}
                                                                </span>
                                                                {fdaUrl && (
                                                                    <a
                                                                        href={fdaUrl}
                                                                        target="_blank"
                                                                        rel="noopener noreferrer"
                                                                        className="text-[10px] flex items-center gap-0.5 hover:underline"
                                                                        style={{ color: recallClass.color }}
                                                                    >
                                                                        FDA page <ExternalLink className="h-2.5 w-2.5" />
                                                                    </a>
                                                                )}
                                                            </div>
                                                            {!alert.acknowledged && (
                                                                <Button
                                                                    variant="outline"
                                                                    size="sm"
                                                                    className="rounded-xl text-xs flex-shrink-0 min-h-[44px] sm:hidden active:scale-[0.97]"
                                                                    onClick={() => handleAcknowledge(alert.id)}
                                                                >
                                                                    Acknowledge
                                                                </Button>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {!alert.acknowledged && (
                                                        <Button
                                                            variant="outline"
                                                            size="sm"
                                                            className="rounded-xl text-xs flex-shrink-0 min-h-[44px] hidden sm:flex active:scale-[0.97]"
                                                            onClick={() => handleAcknowledge(alert.id)}
                                                        >
                                                            Acknowledge
                                                        </Button>
                                                    )}
                                                </div>
                                            </motion.div>
                                        );
                                    }

                                    // ── Standard alert card ──────────────────────────────────────
                                    return (
                                        <motion.div
                                            key={alert.id}
                                            initial={{ opacity: 0, y: 10 }}
                                            animate={{ opacity: 1, y: 0 }}
                                            exit={{ opacity: 0, height: 0 }}
                                            className={`relative rounded-xl border p-3 sm:p-4 transition-all ${alert.acknowledged ? 'opacity-50' : ''}`}
                                            style={{
                                                borderColor: alert.acknowledged ? 'var(--re-border-default)' : config.border,
                                                background: alert.acknowledged ? 'transparent' : config.bg,
                                            }}
                                        >
                                            <div className="flex items-start gap-2 sm:gap-3">
                                                <div className="mt-0.5 flex-shrink-0" style={{ color: config.color }}>
                                                    <Icon className="h-5 w-5" />
                                                </div>
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-1.5 sm:gap-2 mb-1 flex-wrap">
                                                        <span className="text-xs sm:text-sm font-medium">{alert.title}</span>
                                                        <Badge
                                                            className="text-[9px] px-1.5 py-0"
                                                            style={{ background: config.bg, color: config.color, border: `1px solid ${config.border}` }}
                                                        >
                                                            {config.label}
                                                        </Badge>
                                                        {alert.acknowledged && (
                                                            <Badge variant="outline" className="text-[9px] px-1.5 py-0">
                                                                <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" /> Acknowledged
                                                            </Badge>
                                                        )}
                                                    </div>
                                                    <p className="text-[11px] sm:text-xs text-muted-foreground line-clamp-2">{alert.message}</p>
                                                    <div className="flex items-center justify-between mt-1.5 sm:mt-1 gap-2">
                                                        <span className="text-[10px] text-muted-foreground/60">
                                                            {formatTimeAgo(alert.triggered_at)}
                                                        </span>
                                                        {!alert.acknowledged && (
                                                            <Button
                                                                variant="outline"
                                                                size="sm"
                                                                className="rounded-xl text-xs flex-shrink-0 min-h-[44px] sm:hidden active:scale-[0.97]"
                                                                onClick={() => handleAcknowledge(alert.id)}
                                                            >
                                                                Acknowledge
                                                            </Button>
                                                        )}
                                                    </div>
                                                </div>
                                                {!alert.acknowledged && (
                                                    <Button
                                                        variant="outline"
                                                        size="sm"
                                                        className="rounded-xl text-xs flex-shrink-0 min-h-[44px] hidden sm:flex active:scale-[0.97]"
                                                        onClick={() => handleAcknowledge(alert.id)}
                                                    >
                                                        Acknowledge
                                                    </Button>
                                                )}
                                            </div>
                                        </motion.div>
                                    );
                                })}
                            </AnimatePresence>
                        </div>
                    </>
                )}

                {isLoggedIn && !loading && filtered.length === 0 && alerts.length > 0 && (
                    <div className="text-center py-12 text-muted-foreground">
                        <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-re-brand" />
                        <div className="font-medium">All clear</div>
                        <div className="text-sm">No {filter === 'all' ? '' : filter} alerts to show</div>
                    </div>
                )}

                {isLoggedIn && !loading && alerts.length === 0 && isSuccess && (
                    <div className="text-center py-12 text-muted-foreground">
                        <CheckCircle2 className="h-10 w-10 mx-auto mb-3 text-re-brand" />
                        <div className="font-medium">No alerts</div>
                        <div className="text-sm">Everything looks good — no active alerts</div>
                    </div>
                )}
            </div>
        </div>
    );
}
