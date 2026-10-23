'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { Callout } from '@/components/ui/callout';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { StatTile } from '@/components/ui/stat-tile';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';
import { Spinner } from '@/components/ui/spinner';
import {
    AlertTriangle,
    ShieldAlert,
    XCircle,
    CheckCircle2,
    RefreshCw,
    FileWarning,
    Users,
    Link2,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useTenant } from '@/lib/tenant-context';

/* ── Types ── */

interface Blocker {
    type: string;
    message: string;
    event_id?: string;
    rule_id?: string;
    rule_title?: string;
    citation?: string;
    exception_id?: string;
    supplier?: string;
    review_id?: string;
    entity_a?: string;
    entity_b?: string;
    similarity?: number;
    signoff_type?: string;
}

interface Warning {
    type: string;
    message: string;
    count?: number;
}

interface DeadlineCase {
    request_case_id: string;
    package_status: string;
    requesting_party: string;
    scope_description: string;
    hours_remaining: number;
    countdown_display: string;
    urgency: 'overdue' | 'critical' | 'urgent' | 'normal';
    gap_count: number;
    active_exception_count: number;
}

interface BlockerCheck {
    can_submit: boolean;
    blockers: Blocker[];
    warnings: Warning[];
    blocker_count: number;
    warning_count: number;
}

/* ── Tone maps ──
   State is carried by a StatusBadge / Badge tone (icon + label), never by a
   hard-coded hex applied through an inline style. */

const BLOCKER_CONFIG: Record<string, { icon: React.ElementType; tone: BadgeTone; label: string }> = {
    critical_rule_failure: { icon: XCircle, tone: 'danger', label: 'Rule Failure' },
    unresolved_critical_exception: { icon: FileWarning, tone: 'warning', label: 'Exception' },
    unevaluated_event: { icon: ShieldAlert, tone: 'neutral', label: 'Unevaluated' },
    missing_signoff: { icon: Users, tone: 'info', label: 'Missing Signoff' },
    identity_ambiguity: { icon: Link2, tone: 'neutral', label: 'Identity' },
};

const URGENCY_CONFIG: Record<string, { state: ComplianceState; label: string }> = {
    overdue: { state: 'non-compliant', label: 'OVERDUE' },
    critical: { state: 'at-risk', label: 'CRITICAL' },
    urgent: { state: 'pending', label: 'URGENT' },
    normal: { state: 'compliant', label: 'ON TRACK' },
};

/* ── Page ── */

export default function IssuesPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();

    const { data: issuesData, isLoading: loading, error: issuesError, refetch: loadIssues } = useQuery({
        queryKey: ['issues', tenantId],
        queryFn: async () => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const signal = AbortSignal.timeout(8000);
            const requestInit = { credentials: 'include' as const, signal };

            const deadlineSearch = new URLSearchParams({ tenant_id: tenantId || '' });

            const [deadlineRes, pendingRes] = await Promise.allSettled([
                fetchWithCsrf(`${base}/api/v1/requests/deadlines?${deadlineSearch}`, requestInit),
                fetchWithCsrf(`${base}/api/v1/compliance/pending-reviews/${tenantId}`, requestInit),
            ]);

            let deadlines: DeadlineCase[] = [];
            const allBlockers: Blocker[] = [];
            const allWarnings: Warning[] = [];
            let pendingReviews: Record<string, number> = {};

            if (deadlineRes.status === 'fulfilled' && deadlineRes.value.ok) {
                const data = await deadlineRes.value.json();
                deadlines = data.cases || [];

                for (const c of deadlines.slice(0, 5)) {
                    try {
                        const bRes = await fetchWithCsrf(
                            `${base}/api/v1/requests/${c.request_case_id}/blockers`,
                            { credentials: 'include', signal: AbortSignal.timeout(5000) }
                        );
                        if (bRes.ok) {
                            const bData: BlockerCheck = await bRes.json();
                            allBlockers.push(...bData.blockers);
                            allWarnings.push(...bData.warnings);
                        }
                    } catch { /* individual case blocker fetch failed -- continue */ }
                }
            }

            if (pendingRes.status === 'fulfilled' && pendingRes.value.ok) {
                const data = await pendingRes.value.json();
                pendingReviews = data.breakdown || {};
            }

            return { deadlines, blockers: allBlockers, warnings: allWarnings, pendingReviews };
        },
        enabled: !!tenantId && isAuthenticated,
        retry: false,
    });

    const deadlines = issuesData?.deadlines ?? [];
    const blockers = issuesData?.blockers ?? [];
    const warnings = issuesData?.warnings ?? [];
    const pendingReviews = issuesData?.pendingReviews ?? {};
    const error = issuesError?.message ?? null;

    const overdueCount = deadlines.filter(d => d.urgency === 'overdue').length;
    const criticalCount = deadlines.filter(d => d.urgency === 'critical').length;
    const pendingReviewCount = Object.values(pendingReviews).reduce((s, v) => s + v, 0);

    const deadlineColumns: DataTableColumn<DeadlineCase>[] = [
        {
            key: 'urgency',
            header: 'Status',
            width: '11rem',
            cell: (c) => {
                const cfg = URGENCY_CONFIG[c.urgency] ?? URGENCY_CONFIG.normal;
                return <StatusBadge state={cfg.state} label={cfg.label} size="sm" />;
            },
        },
        {
            key: 'case',
            header: 'Case',
            cell: (c) => (
                <span className="font-medium text-re-text-primary">
                    {c.requesting_party}: {c.scope_description || c.package_status}
                </span>
            ),
        },
        {
            key: 'countdown',
            header: 'Countdown',
            width: '18rem',
            cell: (c) => (
                <span className="text-re-text-tertiary">
                    {c.countdown_display} · {c.gap_count} gaps · {c.active_exception_count} exceptions
                </span>
            ),
        },
    ];

    const blockerColumns: DataTableColumn<Blocker>[] = [
        {
            key: 'type',
            header: 'Type',
            width: '11rem',
            cell: (b) => {
                const cfg = BLOCKER_CONFIG[b.type] || BLOCKER_CONFIG.critical_rule_failure;
                const Icon = cfg.icon;
                return (
                    <Badge tone={cfg.tone} size="sm">
                        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                        {cfg.label}
                    </Badge>
                );
            },
        },
        {
            key: 'message',
            header: 'Blocker',
            cell: (b) => (
                <div className="min-w-0">
                    <p className="font-medium text-re-text-primary">{b.message}</p>
                    {b.rule_title && (
                        <p className="mt-0.5 text-small text-re-text-tertiary">Rule: {b.rule_title}</p>
                    )}
                    {b.supplier && (
                        <p className="mt-0.5 text-small text-re-text-tertiary">Supplier: {b.supplier}</p>
                    )}
                </div>
            ),
        },
        {
            key: 'citation',
            header: 'Citation',
            width: '12rem',
            mono: true,
            cell: (b) => b.citation ?? '—',
        },
    ];

    return (
        <PageContainer>
            <PageHeader
                title="Issues"
                description="Everything preventing compliant submission. Fix these first."
                secondaryActions={
                    <Button
                        variant="ghost"
                        size="icon"
                        aria-label="Refresh issues"
                        onClick={() => loadIssues()}
                        disabled={loading}
                    >
                        <RefreshCw
                            className={loading ? 'animate-spin motion-reduce:animate-none' : undefined}
                            strokeWidth={1.75}
                            aria-hidden="true"
                        />
                    </Button>
                }
            />

            <div className="space-y-6">
                {error && (
                    <Callout tone="danger" role="alert">
                        {error}
                    </Callout>
                )}

                {/* Summary */}
                <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                    <StatTile label="Blocking Defects" value={blockers.length} />
                    <StatTile label="Urgent Deadlines" value={overdueCount + criticalCount} />
                    <StatTile label="Warnings" value={warnings.length} />
                    <StatTile label="Pending Reviews" value={pendingReviewCount} />
                </div>

                {loading && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {/* Deadline urgency */}
                {deadlines.length > 0 && (
                    <section className="space-y-3">
                        <h3 className="text-subheading text-re-text-primary">Active Deadlines</h3>
                        <DataTable
                            caption="Active regulator request deadlines, most urgent first"
                            columns={deadlineColumns}
                            data={deadlines}
                            rowKey={(c) => c.request_case_id}
                            minWidth="640px"
                            stickyFirstColumn
                        />
                    </section>
                )}

                {/* Blocking defects */}
                {blockers.length > 0 && (
                    <section className="space-y-3">
                        <h3 className="text-subheading text-re-text-primary">
                            Blocking Defects: Must Fix Before Submission
                        </h3>
                        <DataTable
                            caption="Blocking defects that must be fixed before submission"
                            columns={blockerColumns}
                            data={blockers}
                            rowKey={(b, i) => `${b.type}-${i}`}
                            minWidth="640px"
                            stickyFirstColumn
                        />
                    </section>
                )}

                {/* Warnings */}
                {warnings.length > 0 && (
                    <Card>
                        <CardHeader>
                            <CardTitle>Warnings (Non-Blocking)</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <ul className="divide-y divide-re-border-subtle">
                                {warnings.map((w, i) => (
                                    <li key={i} className="flex items-start gap-2.5 px-5 py-3 text-ui text-re-text-secondary">
                                        <AlertTriangle
                                            className="mt-0.5 h-4 w-4 shrink-0 text-re-warning"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                        {w.message}
                                    </li>
                                ))}
                            </ul>
                        </CardContent>
                    </Card>
                )}

                {/* Pending reviews breakdown */}
                {Object.keys(pendingReviews).length > 0 && (
                    <Card>
                        <CardHeader>
                            <CardTitle>Pending Reviews</CardTitle>
                        </CardHeader>
                        <CardContent className="p-0">
                            <dl className="grid grid-cols-2 md:grid-cols-4">
                                {Object.entries(pendingReviews).map(([key, count]) => (
                                    <div
                                        key={key}
                                        className="border-b border-r border-re-border-subtle px-5 py-4 last:border-r-0"
                                    >
                                        <dt className="text-label text-re-text-muted">{key.replace(/_/g, ' ')}</dt>
                                        <dd className="mt-1 text-title tabular-nums text-re-text-primary">{count}</dd>
                                    </div>
                                ))}
                            </dl>
                        </CardContent>
                    </Card>
                )}

                {/* Empty state */}
                {!loading && blockers.length === 0 && deadlines.length === 0 && warnings.length === 0 && (
                    <EmptyState
                        icon={CheckCircle2}
                        title="No issues in the current view"
                        titleAs="h2"
                        description="No blocking defects, urgent deadlines, or warnings were returned for this workspace at the moment."
                    />
                )}
            </div>
        </PageContainer>
    );
}
