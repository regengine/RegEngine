'use client';

import { experimentalFeaturesEnabled } from '@/lib/experimental-features';
import { FeatureNotEnabled } from '@/components/experimental/FeatureNotEnabled';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { EmptyState } from '@/components/ui/empty-state';
import { ErrorState } from '@/components/ui/error-state';
import { StatTile } from '@/components/ui/stat-tile';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
import {
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
import { getErrorRequestId } from '@/lib/api-error';
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

/* Severity and recall class are semantic tones on a Badge (icon + label),
   never a hard-coded hex piped through an inline style. */

const SEVERITY_CONFIG: Record<string, { tone: BadgeTone; label: string }> = {
    critical: { tone: 'danger', label: 'Critical' },
    warning: { tone: 'warning', label: 'Warning' },
    info: { tone: 'info', label: 'Info' },
};

const CATEGORY_ICONS: Record<string, React.ElementType> = {
    compliance: ShieldAlert,
    temperature: ThermometerSun,
    deadline: Link2,
    score: TrendingDown,
    overdue: Clock,
    fda_recall: Siren,
};

// Classification tones for FDA recalls
const RECALL_CLASS_CONFIG: Record<string, { tone: BadgeTone; label: string }> = {
    'Class I': { tone: 'danger', label: 'Class I' },
    'Class II': { tone: 'warning', label: 'Class II' },
    'Class III': { tone: 'neutral', label: 'Class III' },
};

const SUMMARY_TILES: { label: string; filter: Exclude<SeverityFilter, 'all' | 'fda_recall'> }[] = [
    { label: 'Critical', filter: 'critical' },
    { label: 'Warnings', filter: 'warning' },
    { label: 'Info', filter: 'info' },
];

const CHIP_CLASSES =
    'flex h-9 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 text-ui font-medium transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-base motion-reduce:transition-none';

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

function AlertsDashboardPageContent() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();
    const isLoggedIn = isAuthenticated;

    const alertsQueryClient = useQueryClient();

    const [filter, setFilter] = useState<SeverityFilter>('all');

    const { data: alertsData, isLoading: loading, error: alertsError, refetch: loadAlerts, isFetching, isSuccess } = useQuery({
        queryKey: ['alerts', tenantId],
        queryFn: async () => {
            const data = (await fetchAlerts(tenantId)) as AlertsResponse;
            return data.alerts || [];
        },
        enabled: isLoggedIn && !!tenantId,
        retry: false,
    });

    const alerts = alertsData ?? [];
    const fetchFailed = !!alertsError;

    const [ackError, setAckError] = useState<string | null>(null);

    const acknowledgeMutation = useMutation({
        mutationFn: (alertId: string) => acknowledgeAlert(tenantId, null, alertId),
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

    const tileCounts: Record<string, number> = {
        critical: criticalCount,
        warning: warningCount,
        info: infoCount,
    };

    return (
        <PageContainer>
            <PageHeader
                title="Alerts & Notifications"
                description={`${unackCount} unacknowledged alert${unackCount !== 1 ? 's' : ''}`}
                meta={
                    <Badge tone="neutral" size="sm">
                        <Activity className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        Live
                    </Badge>
                }
                secondaryActions={
                    <Button variant="secondary" size="sm" onClick={() => loadAlerts()} disabled={loading}>
                        <RefreshCw
                            className={cn('h-4 w-4', loading && 'animate-spin motion-reduce:animate-none')}
                            strokeWidth={1.75}
                            aria-hidden="true"
                        />
                        Refresh
                    </Button>
                }
            />

            <div className="space-y-6">
                {/* Loading */}
                {loading && alerts.length === 0 && (
                    <div className="flex justify-center py-16">
                        <Spinner size="lg" />
                    </div>
                )}

                {/* Error */}
                {fetchFailed && (
                    <ErrorState
                        message="We could not load your alerts."
                        onRetry={() => loadAlerts()}
                        retrying={isFetching}
                        requestId={getErrorRequestId(alertsError)}
                    />
                )}

                {isLoggedIn && !loading && alerts.length > 0 && (
                    <>
                        {/* Summary tiles - each one also toggles its severity filter */}
                        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                            {SUMMARY_TILES.map((item) => (
                                <button
                                    key={item.label}
                                    type="button"
                                    aria-pressed={filter === item.filter}
                                    onClick={() => setFilter(filter === item.filter ? 'all' : item.filter)}
                                    className={cn(
                                        'rounded-lg text-left transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-base motion-reduce:transition-none',
                                        filter === item.filter && '[&>div]:border-re-border-strong [&>div]:bg-re-surface-inset'
                                    )}
                                >
                                    <StatTile label={item.label} value={tileCounts[item.filter]} />
                                </button>
                            ))}
                        </div>

                        {/* Filter chips */}
                        <div className="no-scrollbar flex items-center gap-2 overflow-x-auto">
                            <Filter
                                className="h-4 w-4 shrink-0 text-re-text-muted"
                                strokeWidth={1.75}
                                aria-hidden="true"
                            />
                            {(['all', 'critical', 'warning', 'info'] as const).map((f) => (
                                <button
                                    key={f}
                                    type="button"
                                    aria-pressed={filter === f}
                                    onClick={() => setFilter(f)}
                                    className={cn(
                                        CHIP_CLASSES,
                                        filter === f
                                            ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
                                            : 'border-re-border bg-re-surface-card text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
                                    )}
                                >
                                    {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                                </button>
                            ))}
                            {fdaRecallCount > 0 && (
                                <button
                                    type="button"
                                    aria-pressed={filter === 'fda_recall'}
                                    onClick={() => setFilter(filter === 'fda_recall' ? 'all' : 'fda_recall')}
                                    className={cn(
                                        CHIP_CLASSES,
                                        filter === 'fda_recall'
                                            ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
                                            : 'border-re-border bg-re-surface-card text-re-text-secondary hover:bg-re-surface-inset hover:text-re-text-primary'
                                    )}
                                >
                                    <Siren className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                    FDA Recalls
                                    <span className="font-mono text-label tabular-nums text-re-text-tertiary">
                                        {fdaRecallCount}
                                    </span>
                                </button>
                            )}
                        </div>

                        {ackError && (
                            <Callout tone="danger" role="alert">
                                Couldn&apos;t acknowledge. Retry.
                            </Callout>
                        )}

                        {/* Alert list */}
                        <div className="space-y-3">
                            {filtered.map((alert) => {
                                const config = SEVERITY_CONFIG[alert.severity] || SEVERITY_CONFIG.info;
                                const Icon = CATEGORY_ICONS[alert.category] || AlertTriangle;
                                const isRecall = alert.category === 'fda_recall';

                                const meta = (alert.metadata as Record<string, string>) ?? {};
                                const classification = meta.classification ?? '';
                                const recallClass = RECALL_CLASS_CONFIG[classification] ?? RECALL_CLASS_CONFIG['Class I'];
                                const recallNumber = meta.recall_number ?? '';
                                const recallingFirm = (meta.recalling_firm as string) ?? '';
                                const matchedBy: string[] = (meta.matched_by as unknown as string[]) ?? [];
                                const matchTier = matchedBy.find(r => r.startsWith('match_tier:'))?.replace('match_tier:', '') ?? 'profile';
                                const fdaUrl = recallNumber
                                    ? `https://www.accessdata.fda.gov/scripts/ires/index.cfm?event=ires.dspBriefRecallNumber&RecallNumber=${recallNumber}`
                                    : undefined;

                                return (
                                    <Card
                                        key={alert.id}
                                        padding="compact"
                                        className={cn(alert.acknowledged && 'opacity-60')}
                                    >
                                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                                          <div className="flex min-w-0 flex-1 items-start gap-3">
                                            <Icon
                                                className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary"
                                                strokeWidth={1.75}
                                                aria-hidden="true"
                                            />
                                            <div className="min-w-0 flex-1">
                                                <div className="flex flex-wrap items-center gap-2">
                                                    <span className="text-ui font-medium text-re-text-primary">
                                                        {alert.title}
                                                    </span>
                                                    {isRecall ? (
                                                        <>
                                                            <Badge tone={recallClass.tone} size="sm">
                                                                <Siren
                                                                    className="h-3.5 w-3.5 shrink-0"
                                                                    strokeWidth={1.75}
                                                                    aria-hidden="true"
                                                                />
                                                                {recallClass.label}
                                                            </Badge>
                                                            <Badge tone="neutral" size="sm">FDA Recall</Badge>
                                                        </>
                                                    ) : (
                                                        <Badge tone={config.tone} size="sm">
                                                            <AlertTriangle
                                                                className="h-3.5 w-3.5 shrink-0"
                                                                strokeWidth={1.75}
                                                                aria-hidden="true"
                                                            />
                                                            {config.label}
                                                        </Badge>
                                                    )}
                                                    {alert.acknowledged && (
                                                        <Badge tone="neutral" size="sm">
                                                            <CheckCircle2
                                                                className="h-3.5 w-3.5 shrink-0"
                                                                strokeWidth={1.75}
                                                                aria-hidden="true"
                                                            />
                                                            Acknowledged
                                                        </Badge>
                                                    )}
                                                </div>

                                                <p className="mt-1 line-clamp-2 text-ui text-re-text-secondary">
                                                    {alert.message}
                                                </p>

                                                {isRecall && (
                                                    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-small text-re-text-tertiary">
                                                        {recallingFirm && (
                                                            <span className="flex items-center gap-1">
                                                                <Building2
                                                                    className="h-3.5 w-3.5"
                                                                    strokeWidth={1.75}
                                                                    aria-hidden="true"
                                                                />
                                                                {recallingFirm}
                                                            </span>
                                                        )}
                                                        {recallNumber && (
                                                            <span className="flex items-center gap-1 font-mono">
                                                                <Hash
                                                                    className="h-3.5 w-3.5"
                                                                    strokeWidth={1.75}
                                                                    aria-hidden="true"
                                                                />
                                                                {recallNumber}
                                                            </span>
                                                        )}
                                                        <span className="flex items-center gap-1">
                                                            Match:{' '}
                                                            <strong className="font-medium text-re-text-secondary">
                                                                {matchTier === 'lot_code' ? 'Lot Code' : matchTier === 'supplier' ? 'Supplier' : 'Product Profile'}
                                                            </strong>
                                                        </span>
                                                    </div>
                                                )}

                                                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-small text-re-text-tertiary">
                                                    <span>{formatTimeAgo(alert.triggered_at)}</span>
                                                    {isRecall && fdaUrl && (
                                                        <a
                                                            href={fdaUrl}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="flex items-center gap-1 text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand"
                                                        >
                                                            FDA page
                                                            <ExternalLink
                                                                className="h-3.5 w-3.5"
                                                                strokeWidth={1.75}
                                                                aria-hidden="true"
                                                            />
                                                        </a>
                                                    )}
                                                </div>
                                            </div>
                                          </div>

                                            {!alert.acknowledged && (
                                                <Button
                                                    variant="secondary"
                                                    size="sm"
                                                    className="shrink-0 sm:self-start"
                                                    onClick={() => handleAcknowledge(alert.id)}
                                                >
                                                    Acknowledge
                                                </Button>
                                            )}
                                        </div>
                                    </Card>
                                );
                            })}
                        </div>
                    </>
                )}

                {isLoggedIn && !loading && filtered.length === 0 && alerts.length > 0 && (
                    <EmptyState
                        icon={CheckCircle2}
                        title="All clear"
                        description={`No ${filter === 'all' ? '' : filter} alerts to show`}
                    />
                )}

                {isLoggedIn && !loading && alerts.length === 0 && isSuccess && (
                    <EmptyState
                        icon={CheckCircle2}
                        title="No alerts"
                        description="Everything looks good: no active alerts"
                    />
                )}
            </div>
        </PageContainer>
    );
}

export default function AlertsDashboardPage() {
    return experimentalFeaturesEnabled()
        ? <AlertsDashboardPageContent />
        : <FeatureNotEnabled featureName="Alerts" backHref="/dashboard" backLabel="Back to dashboard" />;
}
