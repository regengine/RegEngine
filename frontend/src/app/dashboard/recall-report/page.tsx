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
import { getErrorRequestId } from '@/lib/api-error';
import { ErrorState } from '@/components/ui/error-state';
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
    Clock,
    Info,
    ChevronDown,
    ChevronUp,
    RefreshCw,
} from 'lucide-react';
import { NOT_SET, NO_DATA_YET } from '@/lib/empty-values';

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
    demo_disclaimer: string | null;
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

/* ── Helpers ── */

/** Grade as a badge tone. Numbers stay ink; only the grade pill carries colour. */
function gradeTone(grade: string): BadgeTone {
    if (grade === 'A' || grade === 'B') return 'success';
    if (grade === 'C') return 'warning';
    if (grade === '—' || grade === 'N/A') return 'neutral';
    return 'danger';
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
        staleTime: 5 * 60 * 1000, // 5 min: report is expensive to compute
    });

    if (error || (!isLoading && !report)) {
        return (
            <PageContainer>
                <div>
                    <PageHeader title="Recall report unavailable" />
                    <ErrorState message="We could not load this page." onRetry={() => refetch()} requestId={getErrorRequestId(error)} />
                </div>
            </PageContainer>
        );
    }

    const isDemo = report?.demo_mode === true;
    // Backend PR #3536: no recall evidence => status "no_data", score 0,
    // grade "N/A", demo_mode false, demo_disclaimer null. Treat legacy demo
    // responses the same way and never render a demo disclaimer.
    const isNoData = isDemo || report?.overall_status === 'no_data';
    const dimensions = report?.dimensions ?? [];
    const actionItems = report?.action_items ?? [];
    const overallScore = report?.overall_score ?? 0;
    const overallGrade = report?.overall_grade ?? '—';
    // Display-only: the sentinel above feeds gradeTone and the comparisons below;
    // this derived value is what the empty state renders.
    const overallGradeDisplay =
        overallGrade === '—' || overallGrade === 'N/A' ? NO_DATA_YET : overallGrade;
    const responseTimeStr = report?.time_to_respond_estimate ?? NOT_SET;

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
                // code - 402 is the billing gate, and users saw
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
                badge: this page only renders its own header. */}
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
                        {/* ── Empty state: API reports no recall evidence (status "no_data") ── */}
                        {isNoData && (
                            <EmptyState
                                icon={ShieldCheck}
                                title={NO_DATA_YET}
                                description="Recall evidence appears here after your traceability records are imported."
                                action={
                                    <Link href="/tools/data-import">
                                        <Button size="sm" leadingIcon={<Upload strokeWidth={1.75} aria-hidden="true" />}>
                                            Import Records
                                        </Button>
                                    </Link>
                                }
                            />
                        )}

                        {/* ── Readiness Score + Dimensions ── */}
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
                                        {overallGrade !== '—' && overallGrade !== 'N/A' ? (
                                            <Badge tone={gradeTone(overallGrade)}>{overallGrade}</Badge>
                                        ) : (
                                            <span className="text-ui text-re-text-tertiary">{overallGradeDisplay}</span>
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
                                    {report?.executive_summary && (
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
                                            Personalized recommendations based on your traceability data
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
