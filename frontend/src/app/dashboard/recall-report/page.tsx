'use client';

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Link from 'next/link';
import { PageContainer } from '@/components/layout/page-container';
import { PageHeader } from '@/components/layout/page-header';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeTone } from '@/components/ui/badge';
import { EmptyState } from '@/components/ui/empty-state';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { fetchRecallReport } from '@/lib/api-hooks';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import {
    Download,
    Timer,
    Database,
    ShieldCheck,
    Users,
    Upload,
    GraduationCap,
    AlertTriangle,
    ArrowUp,
    Play,
    Package,
    MapPin,
    Clock,
    CheckCircle2,
    ShoppingCart,
    Zap,
    Info,
    ChevronDown,
    ChevronUp,
    RefreshCw,
} from 'lucide-react';

/* ── API Response Types ── */

interface RecallDimension {
    id: string;
    name: string;
    score: number;
    grade: string;
    status: string;
    findings: string[];
    recommendations: string[];
}

interface RecallReport {
    tenant_id: string;
    generated_at: string;
    overall_score: number;
    overall_grade: string;
    overall_status: string;
    time_to_respond_estimate: string;
    dimensions: RecallDimension[];
    executive_summary: string;
    action_items: Array<{ priority: string; action: string; impact: string; effort: string }>;
    demo_mode: boolean;
    demo_disclaimer?: string | null;
}

/* ── Icon + tone mappings ── */

const DIMENSION_ICONS: Record<string, React.ElementType> = {
    trace_speed: Timer,
    data_completeness: Database,
    chain_integrity: ShieldCheck,
    supplier_coverage: Users,
    export_readiness: Upload,
    team_readiness: GraduationCap,
};

/**
 * Notice recipe.
 *
 * Inlined rather than imported from `@/components/ui/callout`:
 * `src/__tests__/pages/recall-report.test.tsx` replaces `lucide-react` with a
 * partial factory mock, and Callout (like StatusBadge, StatTile and DataTable,
 * which imports Callout) builds its icon map at module scope, so importing any
 * of them throws before the suite runs. Classes match the primitive exactly.
 */
const NOTICE_BASE =
    'flex gap-3 rounded-md border border-l-[3px] border-re-border px-4 py-3 text-ui text-re-text-secondary';

/* ── Demo Fallback Data (shown only when demo_mode=true from API) ── */

const DEMO_INVESTIGATION = {
    scenario: 'Romaine Lettuce (E. coli O157:H7)',
    initiated: '2026-03-15T08:30:00Z',
    response_time_hours: 4.2,
    sla_target: 24,
    lots_at_risk: 12,
    suppliers_impacted: 3,
    facilities_in_chain: 8,
    consumers_potentially_affected: '~2,400',
    total_quantity: '18,200 lbs',
};

const DEMO_AFFECTED_LOTS = [
    { tlc: 'LOT-ROM-2026-0312A', product: 'Organic Romaine Hearts', facility: 'Salinas Valley Farms', status: 'traced', cte_count: 6, last_event: 'Retail Distribution', risk: 'high' },
    { tlc: 'LOT-ROM-2026-0312B', product: 'Chopped Romaine Mix', facility: 'FreshCut Processing', status: 'traced', cte_count: 5, last_event: 'Transformation', risk: 'high' },
    { tlc: 'LOT-ROM-2026-0311C', product: 'Romaine Hearts 3-Pack', facility: 'Salinas Valley Farms', status: 'traced', cte_count: 4, last_event: 'Shipping', risk: 'medium' },
    { tlc: 'LOT-ROM-2026-0310D', product: 'Organic Romaine Bulk', facility: 'Pacific Coast Growers', status: 'partial', cte_count: 3, last_event: 'Receiving', risk: 'medium' },
    { tlc: 'LOT-ROM-2026-0309E', product: 'Romaine Salad Kit', facility: 'FreshCut Processing', status: 'partial', cte_count: 2, last_event: 'Transformation', risk: 'low' },
];

const DEMO_TIMELINE = [
    { time: '08:30', label: 'FDA Request Received', desc: 'FSMA 204 records request for romaine lettuce lots from Salinas Valley region', icon: AlertTriangle, done: true },
    { time: '08:35', label: 'Automated Trace Initiated', desc: 'RegEngine backward trace from retail to harvest across 8 facilities', icon: Zap, done: true },
    { time: '08:42', label: '12 Lots Identified', desc: 'Forward trace mapped all downstream distribution; 3 supplier origins confirmed', icon: Package, done: true },
    { time: '09:15', label: 'Supplier Notifications Sent', desc: '3 suppliers contacted: Salinas Valley Farms, Pacific Coast Growers, FreshCut Processing', icon: Users, done: true },
    { time: '10:00', label: 'FDA CSV Export Generated', desc: '24-hour response package with all CTEs, KDEs, and chain hashes', icon: Download, done: true },
    { time: '—', label: 'Retailer EPCIS Notification', desc: 'GS1 EPCIS 2.0 export package ready for retailer portal upload. Confirm specific format with each buyer', icon: ShoppingCart, done: false },
    { time: '—', label: 'Investigation Closed', desc: 'All affected lots accounted for, remediation verified', icon: CheckCircle2, done: false },
];

/* ── Helpers ── */

/** Grade as a badge tone. Numbers stay ink; only the grade pill carries colour. */
function gradeTone(grade: string): BadgeTone {
    if (grade === 'A' || grade === 'B') return 'success';
    if (grade === 'C') return 'warning';
    if (grade === '—') return 'neutral';
    return 'danger';
}

function riskTone(risk: string): BadgeTone {
    if (risk === 'high') return 'danger';
    if (risk === 'medium') return 'warning';
    return 'success';
}

function priorityTone(priority: string): BadgeTone {
    if (priority === 'HIGH') return 'danger';
    if (priority === 'MEDIUM') return 'warning';
    return 'info';
}

/* ── Page Component ── */

export default function RecallReportPage() {
    const { isAuthenticated } = useAuth();
    const { tenantId } = useTenant();
    const [expanded, setExpanded] = useState<string | null>(null);
    const [exporting, setExporting] = useState(false);
    const [exportError, setExportError] = useState<string | null>(null);

    const { data: report, isLoading, error, refetch } = useQuery<RecallReport>({
        queryKey: ['recall-report', tenantId],
        queryFn: () => fetchRecallReport(tenantId!) as Promise<RecallReport>,
        enabled: !!tenantId && isAuthenticated,
        staleTime: 5 * 60 * 1000, // 5 min — report is expensive to compute
    });

    if (error || (!isLoading && !report)) {
        return (
            <PageContainer>
                <div role="alert">
                    <PageHeader title="Recall report unavailable" />
                    <div className={`${NOTICE_BASE} border-l-re-danger bg-re-danger-bg`}>
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                        <div className="min-w-0 flex-1">
                            <p>No recall result could be loaded. Try again when your connection is available.</p>
                            <div className="mt-3">
                                <Button variant="outline" size="sm" onClick={() => refetch()}>Retry</Button>
                            </div>
                        </div>
                    </div>
                </div>
            </PageContainer>
        );
    }

    const isDemo = report?.demo_mode === true;
    const dimensions = report?.dimensions ?? [];
    const actionItems = report?.action_items ?? [];
    const overallScore = report?.overall_score ?? 0;
    const overallGrade = report?.overall_grade ?? '—';
    const responseTimeStr = report?.time_to_respond_estimate ?? '—';

    // Demo-mode fallback stats for summary banner
    const demoSlaPercent = Math.round((DEMO_INVESTIGATION.response_time_hours / DEMO_INVESTIGATION.sla_target) * 100);
    const gaugeCircumference = 2 * Math.PI * 80;

    const handleExport = async () => {
        if (!tenantId) return;
        setExporting(true);
        setExportError(null);
        try {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const res = await fetchWithCsrf(
                `${base}/api/v1/fda/export/all?tenant_id=${tenantId}&format=csv`,
                { credentials: 'include' }
            );
            if (!res.ok) {
                // Surface the real reason instead of a bare status
                // code — 402 is the billing gate, and users saw
                // "Export failed: Export failed: 402" with no way
                // to tell what to do about it.
                if (res.status === 402) {
                    throw new Error(
                        'FDA export requires an active plan. Choose one under Settings → Manage Plan, then retry.'
                    );
                }
                let detail = '';
                try {
                    const payload = await res.json();
                    detail = payload?.error?.message || payload?.detail || '';
                } catch {
                    /* non-JSON body */
                }
                throw new Error(detail || `The export service returned status ${res.status}. Try again or check system health.`);
            }
            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `fda_24hr_response_${new Date().toISOString().slice(0, 10)}.csv`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            setExportError(err instanceof Error ? err.message : 'Export failed');
        } finally {
            setExporting(false);
        }
    };

    return (
        <PageContainer>
            {/* The dashboard shell owns the breadcrumb and the service-health
                badge — this page only renders its own header. */}
            <PageHeader
                title="Recall Report"
                description={<>FSMA 204 Traceability Response &amp; Readiness Assessment</>}
                secondaryActions={
                    <>
                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => refetch()}
                            disabled={isLoading}
                            leadingIcon={
                                <RefreshCw
                                    className={isLoading ? 'animate-spin motion-reduce:animate-none' : undefined}
                                    strokeWidth={1.75}
                                    aria-hidden="true"
                                />
                            }
                        >
                            Refresh
                        </Button>
                        <Link href="/dashboard/recall-drills">
                            <Button variant="outline" size="sm" leadingIcon={<Play strokeWidth={1.75} aria-hidden="true" />}>
                                Run Recall Drill
                            </Button>
                        </Link>
                    </>
                }
                primaryAction={
                    <Button
                        variant="danger"
                        size="sm"
                        disabled={exporting || isDemo}
                        onClick={handleExport}
                        leadingIcon={
                            exporting
                                ? <Clock className="animate-spin motion-reduce:animate-none" strokeWidth={1.75} aria-hidden="true" />
                                : <Download strokeWidth={1.75} aria-hidden="true" />
                        }
                    >
                        {exporting
                            ? 'Generating...'
                            : isDemo ? 'Connect Live Data To Enable FDA Export' : 'Generate FDA 24-Hour Response'}
                    </Button>
                }
            />

            <div className="space-y-6">
                {/* Export error */}
                {exportError && (
                    <div className={`${NOTICE_BASE} border-l-re-danger bg-re-danger-bg`} role="alert">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                        <span>{exportError}</span>
                    </div>
                )}

                {/* Demo notice */}
                {isDemo && !isLoading && (
                    <div className={`${NOTICE_BASE} border-l-re-info bg-re-surface-card`}>
                        <Info className="mt-0.5 h-4 w-4 shrink-0 text-re-info" strokeWidth={1.75} aria-hidden="true" />
                        <span>
                            {report?.demo_disclaimer ??
                                'Sample scenario only. Live recall evidence appears after data and export workflows are connected for this workspace.'}
                        </span>
                    </div>
                )}

                {/* Loading */}
                {isLoading && (
                    <div className="space-y-4" aria-busy="true">
                        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                            {[0, 1, 2, 3, 4].map((tile) => (
                                <Skeleton key={tile} className="h-24 w-full" />
                            ))}
                        </div>
                        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                            <Skeleton className="h-[320px] w-full" />
                            <Skeleton className="h-[320px] w-full lg:col-span-2" />
                        </div>
                    </div>
                )}

                {!isLoading && (
                    <>
                        {/* ── DEMO ONLY: Risk Summary Banner ── */}
                        {isDemo && (
                            <dl className="grid grid-cols-2 gap-3 md:grid-cols-5">
                                {[
                                    { label: 'Lots at Risk', value: DEMO_INVESTIGATION.lots_at_risk },
                                    { label: 'Suppliers Impacted', value: DEMO_INVESTIGATION.suppliers_impacted },
                                    { label: 'Facilities in Chain', value: DEMO_INVESTIGATION.facilities_in_chain },
                                    { label: 'Consumers at Risk', value: DEMO_INVESTIGATION.consumers_potentially_affected },
                                    { label: 'Response Time', value: `${DEMO_INVESTIGATION.response_time_hours}h` },
                                ].map((tile) => (
                                    <Card key={tile.label} padding="compact">
                                        <dt className="text-label text-re-text-muted">{tile.label}</dt>
                                        <dd className="mt-2 text-title tabular-nums text-re-text-primary">{tile.value}</dd>
                                    </Card>
                                ))}
                            </dl>
                        )}

                        {/* ── DEMO ONLY: SLA Gauge + Timeline ── */}
                        {isDemo && (
                            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                                {/* SLA Gauge */}
                                <Card>
                                    <CardHeader>
                                        <div className="min-w-0">
                                            <CardTitle>24-Hour Response Status</CardTitle>
                                        </div>
                                    </CardHeader>
                                    <CardContent className="flex flex-col items-center">
                                        <div className="relative h-36 w-36 sm:h-44 sm:w-44">
                                            <svg className="h-full w-full -rotate-90 text-re-brand" viewBox="0 0 200 200" aria-hidden="true">
                                                <circle cx="100" cy="100" r="80" className="stroke-re-border" strokeWidth="10" fill="none" />
                                                <circle
                                                    cx="100" cy="100" r="80"
                                                    stroke="currentColor"
                                                    strokeWidth="12" fill="none" strokeLinecap="round"
                                                    strokeDasharray={gaugeCircumference}
                                                    strokeDashoffset={gaugeCircumference - (demoSlaPercent / 100) * gaugeCircumference}
                                                />
                                            </svg>
                                            <div className="absolute inset-0 flex flex-col items-center justify-center">
                                                <div className="text-title tabular-nums text-re-text-primary">{DEMO_INVESTIGATION.response_time_hours}h</div>
                                                <div className="mt-0.5 text-label text-re-text-muted">of 24h SLA</div>
                                            </div>
                                        </div>
                                        <Badge tone="success" size="sm" className="mt-3">
                                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                            SLA Met: {(24 - DEMO_INVESTIGATION.response_time_hours).toFixed(1)}h to spare
                                        </Badge>
                                    </CardContent>
                                </Card>

                                {/* Investigation Timeline */}
                                <Card className="lg:col-span-2">
                                    <CardHeader>
                                        <div className="min-w-0">
                                            <CardTitle>Investigation Timeline</CardTitle>
                                            <CardDescription>
                                                {DEMO_INVESTIGATION.scenario}
                                            </CardDescription>
                                        </div>
                                    </CardHeader>
                                    <CardContent className="p-0">
                                        <ol className="divide-y divide-re-border-subtle">
                                            {DEMO_TIMELINE.map((evt, i) => {
                                                const Icon = evt.icon;
                                                return (
                                                    <li key={i} className="flex gap-3 px-5 py-3">
                                                        <Icon
                                                            className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary"
                                                            strokeWidth={1.75}
                                                            aria-hidden="true"
                                                        />
                                                        <div className="min-w-0 flex-1">
                                                            <div className="flex flex-wrap items-center gap-2">
                                                                <span className={evt.done ? 'text-ui font-medium text-re-text-primary' : 'text-ui font-medium text-re-text-tertiary'}>{evt.label}</span>
                                                                {evt.done && (
                                                                    <Badge tone="success" size="sm">Done</Badge>
                                                                )}
                                                            </div>
                                                            <p className="mt-0.5 text-small text-re-text-tertiary">{evt.desc}</p>
                                                            <span className="font-mono text-label text-re-text-muted">{evt.time}</span>
                                                        </div>
                                                    </li>
                                                );
                                            })}
                                        </ol>
                                    </CardContent>
                                </Card>
                            </div>
                        )}

                        {/* ── DEMO ONLY: Affected Lots ── */}
                        {isDemo && (
                            <Card>
                                <CardHeader>
                                    <div className="min-w-0">
                                        <CardTitle>Affected Lots ({DEMO_AFFECTED_LOTS.length})</CardTitle>
                                    </div>
                                    <span className="shrink-0 font-mono text-label text-re-text-muted">{DEMO_INVESTIGATION.total_quantity} total</span>
                                </CardHeader>
                                <CardContent className="p-0">
                                    <ul className="divide-y divide-re-border-subtle">
                                        {DEMO_AFFECTED_LOTS.map((lot) => (
                                            <li
                                                key={lot.tlc}
                                                className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:gap-4"
                                            >
                                                <div className="min-w-0 flex-1">
                                                    <div className="truncate font-mono text-[0.8125rem] text-re-text-primary">{lot.tlc}</div>
                                                    <div className="truncate text-small text-re-text-tertiary">{lot.product}</div>
                                                </div>
                                                <div className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
                                                    <span className="flex items-center gap-1 text-small text-re-text-tertiary">
                                                        <MapPin className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" /> {lot.facility}
                                                    </span>
                                                    <Badge size="sm">{lot.cte_count} CTEs</Badge>
                                                    <Badge tone={riskTone(lot.risk)} size="sm" className="capitalize">
                                                        {lot.risk}
                                                    </Badge>
                                                    <Badge
                                                        tone={lot.status === 'traced' ? 'success' : 'warning'}
                                                        size="sm"
                                                        className="capitalize"
                                                    >
                                                        {lot.status === 'traced' ? (
                                                            <CheckCircle2 className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                        ) : (
                                                            <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                                        )}
                                                        {lot.status}
                                                    </Badge>
                                                </div>
                                            </li>
                                        ))}
                                    </ul>
                                </CardContent>
                            </Card>
                        )}

                        {/* ── LIVE ONLY: No Active Recall Empty State ── */}
                        {!isDemo && (
                            <EmptyState
                                icon={ShieldCheck}
                                title="No Active Recall Report"
                                description={'This drill measures how quickly you could assemble a 24-hour FDA records-request package. Run a recall drill to validate your team’s response speed.'}
                                action={
                                    <Link href="/dashboard/recall-drills">
                                        <Button size="sm" leadingIcon={<Play strokeWidth={1.75} aria-hidden="true" />}>
                                            Run Recall Drill
                                        </Button>
                                    </Link>
                                }
                            />
                        )}

                        {/* ── Readiness Score + Dimensions (always shown, live or demo) ── */}
                        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                            {/* Overall Score */}
                            <Card>
                                <CardContent>
                                    <div className="text-label text-re-text-muted">Recall Response Readiness</div>
                                    <div className="mt-2 flex flex-wrap items-baseline gap-3">
                                        <span className="text-[3.5rem] leading-none tracking-[-0.02em] tabular-nums text-re-text-primary">
                                            {overallScore}
                                        </span>
                                        <span className="text-ui text-re-text-tertiary">/100</span>
                                        {overallGrade !== '—' && (
                                            <Badge tone={gradeTone(overallGrade)}>{overallGrade}</Badge>
                                        )}
                                    </div>
                                    <div className="mt-3 text-ui text-re-text-secondary">
                                        Response time: <strong className="font-medium text-re-text-primary">{responseTimeStr}</strong>
                                    </div>
                                    <div className="mt-1 font-mono text-label text-re-text-muted">
                                        21 CFR 1.1455 Assessment ·{' '}
                                        {report?.generated_at
                                            ? new Date(report.generated_at).toLocaleDateString()
                                            : new Date().toLocaleDateString()}
                                    </div>
                                    {!isDemo && report?.executive_summary && (
                                        <p className="mt-3 border-t border-re-border-subtle pt-3 text-small text-re-text-tertiary">
                                            {report.executive_summary}
                                        </p>
                                    )}
                                </CardContent>
                            </Card>

                            {/* Dimension Grid */}
                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:col-span-2">
                                {dimensions.map((dim) => {
                                    const Icon = DIMENSION_ICONS[dim.id] ?? Timer;
                                    const isExpanded = expanded === dim.id;
                                    return (
                                        <Card
                                            key={dim.id}
                                            variant="interactive"
                                            className={`h-full ${isExpanded ? 'sm:col-span-2' : ''}`}
                                        >
                                            <button
                                                type="button"
                                                aria-expanded={isExpanded}
                                                onClick={() => setExpanded(isExpanded ? null : dim.id)}
                                                className="w-full p-4 text-left focus-visible:outline-none"
                                            >
                                                <div className="mb-2 flex items-center justify-between gap-2">
                                                    <div className="flex min-w-0 items-center gap-2">
                                                        <Icon className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                        <span className="truncate text-ui font-medium text-re-text-primary">{dim.name}</span>
                                                    </div>
                                                    <div className="flex shrink-0 items-center gap-1.5">
                                                        <span className="text-ui font-medium tabular-nums text-re-text-primary">{dim.score}</span>
                                                        <Badge tone={gradeTone(dim.grade)} size="sm">{dim.grade}</Badge>
                                                        {isExpanded
                                                            ? <ChevronUp className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                                            : <ChevronDown className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />}
                                                    </div>
                                                </div>
                                                {/* Score bar */}
                                                <div
                                                    className="h-1.5 w-full overflow-hidden rounded-full bg-re-surface-inset"
                                                    role="progressbar"
                                                    aria-valuemin={0}
                                                    aria-valuemax={100}
                                                    aria-valuenow={dim.score}
                                                    aria-label={`${dim.name} score`}
                                                >
                                                    <div
                                                        className="h-full rounded-full bg-re-text-tertiary"
                                                        style={{ width: `${dim.score}%` }}
                                                    />
                                                </div>
                                                {isExpanded && (
                                                    <div className="mt-3 space-y-3">
                                                        <div>
                                                            <div className="mb-1 text-label text-re-text-muted">Findings</div>
                                                            <ul className="space-y-1 text-small text-re-text-tertiary">
                                                                {dim.findings.map((f, i) => (
                                                                    <li key={i} className="flex items-start gap-1.5">
                                                                        <span aria-hidden="true">•</span> {f}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                        <div>
                                                            <div className="mb-1 text-label text-re-text-muted">Recommendations</div>
                                                            <ul className="space-y-1 text-small text-re-text-secondary">
                                                                {dim.recommendations.map((r, i) => (
                                                                    <li key={i} className="flex items-start gap-1.5">
                                                                        <ArrowUp className="mt-0.5 h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" /> {r}
                                                                    </li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    </div>
                                                )}
                                            </button>
                                        </Card>
                                    );
                                })}
                            </div>
                        </div>

                        {/* Action Items */}
                        {actionItems.length > 0 && (
                            <Card>
                                <CardHeader>
                                    <div className="min-w-0">
                                        <CardTitle>Prioritized Actions</CardTitle>
                                        <CardDescription>
                                            {isDemo ? 'Address these to improve recall readiness' : 'Personalized recommendations based on your traceability data'}
                                        </CardDescription>
                                    </div>
                                </CardHeader>
                                <CardContent className="p-0">
                                    <ul className="divide-y divide-re-border-subtle">
                                        {actionItems.map((item, i) => (
                                            <li key={i} className="flex items-center gap-3 px-5 py-3">
                                                <Badge tone={priorityTone(item.priority)} size="sm" mono className="shrink-0">
                                                    {item.priority}
                                                </Badge>
                                                <div className="min-w-0 flex-1">
                                                    <div className="text-ui text-re-text-primary">{item.action}</div>
                                                    <div className="text-small text-re-text-tertiary">{item.impact} · {item.effort} effort</div>
                                                </div>
                                            </li>
                                        ))}
                                    </ul>
                                </CardContent>
                            </Card>
                        )}

                        {/* What This Means */}
                        {overallScore > 0 && (
                            <Card variant="inset">
                                <CardContent>
                                    <div className="flex items-start gap-3">
                                        <Info className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <div className="max-w-[70ch] text-ui text-re-text-secondary">
                                            <span className="font-medium text-re-text-primary">What this means for your facility: </span>
                                            {overallScore >= 80
                                                ? 'Your facility can respond to an FDA 204 records request well within the 24-hour mandate. Trace-back, lot identification, and export packaging are all functional. Continue running monthly mock drills to maintain readiness.'
                                                : overallScore >= 60
                                                    ? 'Your facility has basic recall capabilities but gaps in supplier coverage and trace speed could delay an FDA response. Address the high-priority actions above to reduce risk before your next audit or inspection.'
                                                    : 'Critical gaps in your traceability system would likely prevent a timely response to an FDA records request. Immediate action on supplier onboarding and data completeness is recommended to avoid regulatory exposure.'}
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        )}
                    </>
                )}

                {/* Regulatory Footer */}
                <div className="space-y-0.5 py-4 text-center text-small text-re-text-tertiary">
                    <div>Per 21 CFR Part 1, Subpart S · 21 CFR 1.1455 (24-hour mandate) · FSMA Section 204</div>
                    <div>This report is generated from traceability data in your RegEngine instance.</div>
                </div>
            </div>
        </PageContainer>
    );
}
