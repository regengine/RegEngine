'use client';

import React from 'react';
import {
    AlertTriangle,
    Bot,
    CheckCircle2,
    CircleHelp,
    Copy,
    Eye,
    Filter,
    GitBranch,
    RefreshCw,
    Search,
    ShieldAlert,
    ShieldCheck,
    XCircle,
} from 'lucide-react';

import { useAgentReviewDecision, useAgentReviewItems } from '@/hooks/use-agent-reviews';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { cn } from '@/lib/utils';
import type {
    AgentArtifactType,
    AgentReviewDecisionStatus,
    AgentReviewItem,
    AgentReviewStatus,
} from '@/types/agent-review';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Spinner } from '@/components/ui/spinner';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';

const REVIEW_STATUS_OPTIONS: Array<{ value: AgentReviewStatus | 'all'; label: string }> = [
    { value: 'all', label: 'All statuses' },
    { value: 'pending', label: 'Pending' },
    { value: 'needs_more_evidence', label: 'Needs evidence' },
    { value: 'accepted', label: 'Accepted' },
    { value: 'rejected', label: 'Rejected' },
];

const ARTIFACT_TYPE_OPTIONS: Array<{ value: AgentArtifactType | 'all'; label: string }> = [
    { value: 'all', label: 'All artifact types' },
    { value: 'field_mapping_suggestion', label: 'Field mapping' },
    { value: 'identity_match_suggestion', label: 'Identity match' },
    { value: 'validation_explanation', label: 'Validation explanation' },
    { value: 'review_routing_suggestion', label: 'Review routing' },
    { value: 'export_readiness_summary', label: 'Export readiness' },
];

const REVIEW_STATUS_LABELS: Record<AgentReviewStatus, string> = {
    pending: 'Pending',
    accepted: 'Accepted',
    rejected: 'Rejected',
    needs_more_evidence: 'Needs evidence',
};

function formatArtifactType(value: AgentArtifactType) {
    return value
        .split('_')
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(' ');
}

function shortId(value: string | null | undefined, length = 8) {
    if (!value) return 'None';
    return value.length <= length ? value : `${value.slice(0, length)}...`;
}

function formatDate(value: string | null | undefined) {
    if (!value) return 'None';
    return new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    }).format(new Date(value));
}

function riskTone(score: number) {
    if (score >= 75) {
        return {
            label: 'Critical',
            badge: 'border-[var(--re-danger-border)] bg-[var(--re-danger-bg)] text-[var(--re-danger)]',
            bar: 'bg-[var(--re-danger)]',
        };
    }
    if (score >= 45) {
        return {
            label: 'Elevated',
            badge: 'border-[var(--re-warning-border)] bg-[var(--re-warning-bg)] text-[var(--re-warning)]',
            bar: 'bg-[var(--re-warning)]',
        };
    }
    return {
        label: 'Low',
        badge: 'border-[var(--re-success-border)] bg-[var(--re-success-bg)] text-[var(--re-success)]',
        bar: 'bg-[var(--re-success)]',
    };
}

function statusTone(status: AgentReviewStatus) {
    if (status === 'accepted') return 'border-[var(--re-success-border)] bg-[var(--re-success-bg)] text-[var(--re-success)]';
    if (status === 'rejected') return 'border-[var(--re-danger-border)] bg-[var(--re-danger-bg)] text-[var(--re-danger)]';
    if (status === 'needs_more_evidence') return 'border-[var(--re-warning-border)] bg-[var(--re-warning-bg)] text-[var(--re-warning)]';
    return 'border-[var(--re-info-border)] bg-[var(--re-info-bg)] text-[var(--re-info)]';
}

function chainBadge(item: AgentReviewItem) {
    if (item.chain_valid === true) {
        return {
            icon: CheckCircle2,
            label: 'Valid',
            className: 'border-[var(--re-success-border)] bg-[var(--re-success-bg)] text-[var(--re-success)]',
        };
    }
    if (item.chain_valid === false) {
        return {
            icon: XCircle,
            label: 'Broken',
            className: 'border-[var(--re-danger-border)] bg-[var(--re-danger-bg)] text-[var(--re-danger)]',
        };
    }
    return {
        icon: CircleHelp,
        label: 'Unlinked',
        className: 'border-[var(--re-warning-border)] bg-[var(--re-warning-bg)] text-[var(--re-warning)]',
    };
}

function chainValidityLabel(value: AgentReviewItem['chain_valid']) {
    if (value === true) return 'valid';
    if (value === false) return 'broken';
    return 'unknown';
}

function buildAgentReviewAuditCopy(item: AgentReviewItem) {
    const lines = [
        `artifact_id=${item.artifact_id}`,
        item.ingestion_run_id ? `ingestion_run_id=${item.ingestion_run_id}` : null,
        item.receipt_hash ? `receipt_hash=${item.receipt_hash}` : null,
        `chain_valid=${chainValidityLabel(item.chain_valid)}`,
        item.evidence_ids.length > 0 ? `evidence_ids=${item.evidence_ids.join(',')}` : null,
        item.canonical_event_ids.length > 0 ? `canonical_event_ids=${item.canonical_event_ids.join(',')}` : null,
        item.source_hashes.length > 0 ? `source_hashes=${item.source_hashes.join(',')}` : null,
    ];

    return lines.filter((line): line is string => Boolean(line)).join('\n');
}

function sortAgentReviewItems(items: AgentReviewItem[]): AgentReviewItem[] {
    return [...items].sort((a, b) => {
        const reviewPriority = Number(b.requires_human_review) - Number(a.requires_human_review);
        if (reviewPriority !== 0) return reviewPriority;

        const riskPriority = b.risk_score - a.risk_score;
        if (riskPriority !== 0) return riskPriority;

        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    });
}

function MetricCard({
    label,
    value,
    tone,
    icon: Icon,
}: {
    label: string;
    value: string | number;
    tone: string;
    icon: React.ComponentType<{ className?: string }>;
}) {
    return (
        <Card className="border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
            <CardContent className="flex items-center justify-between gap-4 p-4">
                <div>
                    <p className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                        {label}
                    </p>
                    <p className="mt-1 text-2xl font-semibold text-[var(--re-text-primary)]">{value}</p>
                </div>
                <div className={cn('grid h-10 w-10 place-items-center rounded-md border', tone)}>
                    <Icon className="h-5 w-5" />
                </div>
            </CardContent>
        </Card>
    );
}

function RiskScore({ score }: { score: number }) {
    const tone = riskTone(score);
    const width = `${Math.max(0, Math.min(100, Math.round(score)))}%`;

    return (
        <div className="min-w-[124px]">
            <div className="flex items-center gap-2">
                <span className="text-xl font-semibold tabular-nums text-[var(--re-text-primary)]">
                    {score.toFixed(1)}
                </span>
                <Badge className={cn('px-2 py-0.5', tone.badge)}>{tone.label}</Badge>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--re-border-subtle)]">
                <div className={cn('h-full rounded-full', tone.bar)} style={{ width }} />
            </div>
        </div>
    );
}

function EvidenceAnchorSummary({ item }: { item: AgentReviewItem }) {
    const anchorCount = item.evidence_ids.length + item.canonical_event_ids.length + item.source_hashes.length;
    const firstHash = item.source_hashes[0];

    return (
        <div className="min-w-[160px] space-y-1">
            <div className="flex flex-wrap gap-1.5">
                <Badge variant="outline" className="border-[var(--re-border-default)]">
                    {item.evidence_ids.length} evidence
                </Badge>
                <Badge variant="outline" className="border-[var(--re-border-default)]">
                    {item.source_hashes.length} hashes
                </Badge>
            </div>
            <p className="font-mono text-[11px] text-[var(--re-text-muted)]">
                {anchorCount > 0 ? shortId(firstHash ?? item.evidence_ids[0] ?? item.canonical_event_ids[0], 12) : 'No anchors'}
            </p>
        </div>
    );
}

function AgentReviewDetailDialog({
    item,
    open,
    onOpenChange,
    onDecision,
    pendingDecision,
    decisionError,
}: {
    item: AgentReviewItem | null;
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onDecision: (status: AgentReviewDecisionStatus) => Promise<void>;
    pendingDecision: AgentReviewDecisionStatus | null;
    decisionError: string | null;
}) {
    const [copyState, setCopyState] = React.useState<'idle' | 'copied' | 'failed'>('idle');

    React.useEffect(() => {
        setCopyState('idle');
    }, [item?.artifact_id]);

    if (!item) return null;

    const chain = chainBadge(item);
    const ChainIcon = chain.icon;
    const isSubmittingDecision = pendingDecision !== null;

    const handleAuditCopy = async () => {
        try {
            await navigator.clipboard.writeText(buildAgentReviewAuditCopy(item));
            setCopyState('copied');
        } catch {
            setCopyState('failed');
        }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-h-[86vh] max-w-5xl overflow-y-auto p-0">
                <DialogHeader className="border-b border-[var(--re-border-subtle)] p-5 pr-12">
                    <DialogTitle className="flex items-center gap-2 text-xl">
                        <Bot className="h-5 w-5 text-[var(--re-brand)]" />
                        Agent artifact review
                    </DialogTitle>
                    <DialogDescription className="font-mono text-xs">
                        {item.artifact_id}
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_320px]">
                    <div className="space-y-5">
                        <section>
                            <h3 className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                                Suggestion
                            </h3>
                            <p className="mt-2 text-sm leading-6 text-[var(--re-text-primary)]">{item.suggestion}</p>
                        </section>

                        <section className="grid gap-3 sm:grid-cols-2">
                            <KeyValue label="Agent" value={`${item.agent_name} · ${formatArtifactType(item.artifact_type)}`} />
                            <KeyValue label="Created" value={formatDate(item.created_at)} />
                            <KeyValue label="Ingestion run" value={item.ingestion_run_id ?? 'None'} mono />
                            <KeyValue label="Receipt hash" value={item.receipt_hash ?? 'None'} mono />
                        </section>

                        <section>
                            <h3 className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                                Evidence anchors
                            </h3>
                            <AnchorList title="Evidence IDs" values={item.evidence_ids} />
                            <AnchorList title="Canonical Event IDs" values={item.canonical_event_ids} />
                            <AnchorList title="Source Hashes" values={item.source_hashes} />
                        </section>
                    </div>

                    <aside className="space-y-4">
                        <div className="rounded-md border border-[var(--re-border-default)] bg-[var(--re-surface-base)] p-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                                        Review decision
                                    </p>
                                    <p className="mt-1 text-sm text-[var(--re-text-secondary)]">
                                        Current: {REVIEW_STATUS_LABELS[item.review_status]}
                                    </p>
                                </div>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={handleAuditCopy}
                                    className="min-w-[112px]"
                                >
                                    {copyState === 'copied' ? (
                                        <CheckCircle2 className="mr-2 h-4 w-4 text-[var(--re-success)]" />
                                    ) : (
                                        <Copy className="mr-2 h-4 w-4" />
                                    )}
                                    {copyState === 'copied' ? 'Copied' : copyState === 'failed' ? 'Copy failed' : 'Copy audit'}
                                </Button>
                            </div>

                            <div className="mt-4 grid gap-2 sm:grid-cols-3 lg:grid-cols-1">
                                <Button
                                    type="button"
                                    size="sm"
                                    onClick={() => {
                                        void onDecision('accepted');
                                    }}
                                    disabled={isSubmittingDecision}
                                    className="min-w-[120px] border-[var(--re-success-border)] bg-[var(--re-success)] text-white hover:bg-[var(--re-success)]"
                                >
                                    {pendingDecision === 'accepted' ? (
                                        <Spinner className="mr-2 border-white border-t-transparent" size="sm" />
                                    ) : (
                                        <CheckCircle2 className="mr-2 h-4 w-4" />
                                    )}
                                    Accept
                                </Button>
                                <Button
                                    type="button"
                                    variant="destructive"
                                    size="sm"
                                    onClick={() => {
                                        void onDecision('rejected');
                                    }}
                                    disabled={isSubmittingDecision}
                                    className="min-w-[120px]"
                                >
                                    {pendingDecision === 'rejected' ? (
                                        <Spinner className="mr-2 border-white border-t-transparent" size="sm" />
                                    ) : (
                                        <XCircle className="mr-2 h-4 w-4" />
                                    )}
                                    Reject
                                </Button>
                                <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                        void onDecision('needs_more_evidence');
                                    }}
                                    disabled={isSubmittingDecision}
                                    className="min-w-[120px] border-[var(--re-warning-border)] text-[var(--re-warning)] hover:bg-[var(--re-warning-bg)]"
                                >
                                    {pendingDecision === 'needs_more_evidence' ? (
                                        <Spinner className="mr-2 border-[var(--re-warning)] border-t-transparent" size="sm" />
                                    ) : (
                                        <CircleHelp className="mr-2 h-4 w-4" />
                                    )}
                                    Needs evidence
                                </Button>
                            </div>

                            {decisionError && (
                                <p className="mt-3 rounded-md border border-[var(--re-danger-border)] bg-[var(--re-danger-bg)] px-3 py-2 text-xs leading-5 text-[var(--re-danger)]">
                                    {decisionError}
                                </p>
                            )}
                        </div>

                        <div className="rounded-md border border-[var(--re-border-default)] bg-[var(--re-surface-base)] p-4">
                            <div className="flex items-center justify-between gap-3">
                                <div>
                                    <p className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                                        Risk score
                                    </p>
                                    <p className="mt-1 text-3xl font-semibold tabular-nums">{item.risk_score.toFixed(1)}</p>
                                </div>
                                <Badge className={riskTone(item.risk_score).badge}>{riskTone(item.risk_score).label}</Badge>
                            </div>
                            <dl className="mt-4 grid gap-2 text-xs">
                                <BreakdownRow label="Confidence" value={item.risk_breakdown.confidence_risk} />
                                <BreakdownRow label="Review" value={item.risk_breakdown.review_risk} />
                                <BreakdownRow label="Artifact" value={item.risk_breakdown.artifact_type_risk} />
                                <BreakdownRow label="Evidence" value={item.risk_breakdown.evidence_gap_risk} />
                                <BreakdownRow label="Rule" value={item.risk_breakdown.rule_gap_risk} />
                            </dl>
                        </div>

                        <div className="rounded-md border border-[var(--re-border-default)] bg-[var(--re-surface-base)] p-4">
                            <div className="flex items-center justify-between gap-3">
                                <span className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                                    Chain validity
                                </span>
                                <Badge className={chain.className}>
                                    <ChainIcon className="mr-1 h-3.5 w-3.5" />
                                    {chain.label}
                                </Badge>
                            </div>
                            <div className="mt-3 space-y-2 text-xs text-[var(--re-text-muted)]">
                                <p>Receipt state: {item.advisory_receipt_state ?? 'None'}</p>
                                <p>Run state: {item.ingestion_run_status ?? 'None'}</p>
                            </div>
                        </div>

                        <div className="rounded-md border border-[var(--re-border-default)] bg-[var(--re-surface-base)] p-4">
                            <p className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                                Compliance gaps
                            </p>
                            <div className="mt-3 space-y-2">
                                {item.compliance_gaps.length > 0 ? (
                                    item.compliance_gaps.map((gap) => (
                                        <div key={gap.code} className="rounded-md border border-[var(--re-warning-border)] bg-[var(--re-warning-bg)] p-2">
                                            <p className="font-mono text-[11px] font-medium text-[var(--re-warning)]">{gap.code}</p>
                                            <p className="mt-1 text-xs leading-5 text-[var(--re-text-secondary)]">{gap.message}</p>
                                        </div>
                                    ))
                                ) : (
                                    <p className="text-sm text-[var(--re-text-muted)]">No deterministic gaps.</p>
                                )}
                            </div>
                        </div>
                    </aside>
                </div>
            </DialogContent>
        </Dialog>
    );
}

function KeyValue({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
    return (
        <div className="rounded-md border border-[var(--re-border-subtle)] bg-[var(--re-surface-base)] p-3">
            <dt className="font-mono text-[11px] font-medium uppercase tracking-[0.02em] text-[var(--re-text-muted)]">
                {label}
            </dt>
            <dd className={cn('mt-1 break-words text-sm text-[var(--re-text-primary)]', mono && 'font-mono text-xs')}>
                {value}
            </dd>
        </div>
    );
}

function AnchorList({ title, values }: { title: string; values: string[] }) {
    return (
        <div className="mt-3 rounded-md border border-[var(--re-border-subtle)] bg-[var(--re-surface-base)] p-3">
            <div className="flex items-center justify-between gap-2">
                <h4 className="text-sm font-medium">{title}</h4>
                <Badge variant="outline" className="border-[var(--re-border-default)]">{values.length}</Badge>
            </div>
            {values.length > 0 ? (
                <div className="mt-2 space-y-1">
                    {values.map((value) => (
                        <p key={value} className="break-all font-mono text-[11px] leading-5 text-[var(--re-text-muted)]">
                            {value}
                        </p>
                    ))}
                </div>
            ) : (
                <p className="mt-2 text-sm text-[var(--re-text-muted)]">None</p>
            )}
        </div>
    );
}

function BreakdownRow({ label, value }: { label: string; value: number }) {
    return (
        <div className="flex items-center justify-between gap-3">
            <dt className="text-[var(--re-text-muted)]">{label}</dt>
            <dd className="font-mono tabular-nums text-[var(--re-text-primary)]">{value.toFixed(1)}</dd>
        </div>
    );
}

export function AgentReviewDashboard() {
    const { hasTenantSession, isAuthenticated, user } = useAuth();
    const { tenantId } = useTenant();
    const isSysadmin = Boolean(user?.is_sysadmin);
    const [tenantFilter, setTenantFilter] = React.useState('');
    const [ingestionRunId, setIngestionRunId] = React.useState('');
    const [reviewStatus, setReviewStatus] = React.useState<AgentReviewStatus | 'all'>('all');
    const [artifactType, setArtifactType] = React.useState<AgentArtifactType | 'all'>('all');
    const [createdAfter, setCreatedAfter] = React.useState('');
    const [createdBefore, setCreatedBefore] = React.useState('');
    const [selectedItem, setSelectedItem] = React.useState<AgentReviewItem | null>(null);
    const [pendingDecision, setPendingDecision] = React.useState<{
        artifactId: string;
        status: AgentReviewDecisionStatus;
    } | null>(null);
    const [decisionError, setDecisionError] = React.useState<string | null>(null);
    const decisionMutation = useAgentReviewDecision();

    React.useEffect(() => {
        if (isSysadmin && !tenantFilter && tenantId) {
            setTenantFilter(tenantId);
        }
    }, [isSysadmin, tenantFilter, tenantId]);

    const effectiveTenantId = isSysadmin ? tenantFilter.trim() || tenantId : undefined;
    const queryEnabled = isAuthenticated && (isSysadmin ? Boolean(effectiveTenantId) : hasTenantSession);

    const query = useAgentReviewItems(
        {
            tenantId: effectiveTenantId,
            ingestionRunId,
            reviewStatus,
            artifactType,
            createdAfter: createdAfter ? `${createdAfter}T00:00:00Z` : undefined,
            createdBefore: createdBefore ? `${createdBefore}T23:59:59Z` : undefined,
            limit: 100,
            offset: 0,
        },
        queryEnabled,
    );

    const sortedItems = React.useMemo(() => sortAgentReviewItems(query.data?.items ?? []), [query.data?.items]);

    const handleDecision = React.useCallback(
        async (status: AgentReviewDecisionStatus) => {
            if (!selectedItem) return;

            const artifactId = selectedItem.artifact_id;
            setPendingDecision({ artifactId, status });
            setDecisionError(null);

            try {
                const result = await decisionMutation.mutateAsync({ artifactId, status });
                setSelectedItem((current) =>
                    current?.artifact_id === artifactId
                        ? {
                            ...current,
                            review_id: result.review_id ?? current.review_id,
                            review_status: result.review_status,
                            reviewed_by: result.reviewed_by ?? current.reviewed_by,
                            reviewed_at: result.reviewed_at ?? current.reviewed_at,
                        }
                        : current,
                );
                await query.refetch();
            } catch (error) {
                setDecisionError(error instanceof Error ? error.message : 'Unable to submit review decision.');
            } finally {
                setPendingDecision(null);
            }
        },
        [decisionMutation, query, selectedItem],
    );

    const metrics = React.useMemo(() => {
        const items = query.data?.items ?? [];
        const pending = items.filter((item) => item.review_status === 'pending' || item.review_status === 'needs_more_evidence').length;
        const highRisk = items.filter((item) => item.risk_score >= 75).length;
        const gaps = items.reduce((sum, item) => sum + item.compliance_gap_count, 0);
        const brokenChains = items.filter((item) => item.chain_valid === false).length;
        return { pending, highRisk, gaps, brokenChains };
    }, [query.data?.items]);

    return (
        <div className="min-h-screen bg-[var(--re-surface-base)]">
            <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
                <header className="flex flex-col gap-4 border-b border-[var(--re-border-subtle)] pb-5 lg:flex-row lg:items-end lg:justify-between">
                    <div>
                        <div className="flex items-center gap-2 text-[var(--re-brand)]">
                            <ShieldCheck className="h-5 w-5" />
                            <span className="font-mono text-[11px] font-medium uppercase tracking-[0.02em]">Operator dashboard</span>
                        </div>
                        <h1 className="mt-2 text-3xl font-semibold tracking-normal text-[var(--re-text-primary)]">
                            Agent reviews
                        </h1>
                        <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--re-text-secondary)]">
                            Agent activity, deterministic risk, evidence anchors, and receipt-chain status in one queue.
                        </p>
                    </div>
                    <Button
                        variant="outline"
                        onClick={() => query.refetch()}
                        disabled={!queryEnabled || query.isFetching}
                        className="w-full sm:w-fit"
                    >
                        <RefreshCw className={cn('mr-2 h-4 w-4', query.isFetching && 'animate-spin')} />
                        Refresh
                    </Button>
                </header>

                <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <MetricCard
                        label="Needs review"
                        value={metrics.pending}
                        icon={Eye}
                        tone="border-[var(--re-info-border)] bg-[var(--re-info-bg)] text-[var(--re-info)]"
                    />
                    <MetricCard
                        label="High risk"
                        value={metrics.highRisk}
                        icon={ShieldAlert}
                        tone="border-[var(--re-danger-border)] bg-[var(--re-danger-bg)] text-[var(--re-danger)]"
                    />
                    <MetricCard
                        label="Compliance gaps"
                        value={metrics.gaps}
                        icon={AlertTriangle}
                        tone="border-[var(--re-warning-border)] bg-[var(--re-warning-bg)] text-[var(--re-warning)]"
                    />
                    <MetricCard
                        label="Broken chains"
                        value={metrics.brokenChains}
                        icon={GitBranch}
                        tone="border-[var(--re-success-border)] bg-[var(--re-success-bg)] text-[var(--re-success)]"
                    />
                </section>

                <section className="rounded-md border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)]">
                    <div className="flex flex-col gap-3 border-b border-[var(--re-border-subtle)] p-4">
                        <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-2">
                                <Filter className="h-4 w-4 text-[var(--re-text-muted)]" />
                                <h2 className="text-sm font-semibold text-[var(--re-text-primary)]">Review queue</h2>
                            </div>
                            <Badge variant="outline" className="border-[var(--re-border-default)]">
                                {query.data?.total ?? sortedItems.length} total
                            </Badge>
                        </div>

                        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-6">
                            {isSysadmin && (
                                <Input
                                    aria-label="Tenant ID"
                                    value={tenantFilter}
                                    onChange={(event) => setTenantFilter(event.target.value)}
                                    placeholder="Tenant ID"
                                    className="xl:col-span-2"
                                />
                            )}
                            <div className="relative xl:col-span-2">
                                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--re-text-disabled)]" />
                                <Input
                                    aria-label="Ingestion run ID"
                                    value={ingestionRunId}
                                    onChange={(event) => setIngestionRunId(event.target.value)}
                                    placeholder="Ingestion run ID"
                                    className="pl-9"
                                />
                            </div>
                            <Select value={reviewStatus} onValueChange={(value) => setReviewStatus(value as AgentReviewStatus | 'all')}>
                                <SelectTrigger aria-label="Review status">
                                    <SelectValue placeholder="Review status" />
                                </SelectTrigger>
                                <SelectContent>
                                    {REVIEW_STATUS_OPTIONS.map((option) => (
                                        <SelectItem key={option.value} value={option.value}>
                                            {option.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <Select value={artifactType} onValueChange={(value) => setArtifactType(value as AgentArtifactType | 'all')}>
                                <SelectTrigger aria-label="Artifact type">
                                    <SelectValue placeholder="Artifact type" />
                                </SelectTrigger>
                                <SelectContent>
                                    {ARTIFACT_TYPE_OPTIONS.map((option) => (
                                        <SelectItem key={option.value} value={option.value}>
                                            {option.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            <Input
                                aria-label="Created after"
                                type="date"
                                value={createdAfter}
                                onChange={(event) => setCreatedAfter(event.target.value)}
                            />
                            <Input
                                aria-label="Created before"
                                type="date"
                                value={createdBefore}
                                onChange={(event) => setCreatedBefore(event.target.value)}
                            />
                        </div>
                    </div>

                    <CardContent className="p-0">
                        {!queryEnabled ? (
                            <EmptyState
                                icon={ShieldAlert}
                                title="Workspace context required"
                                body="Select a workspace or sign in with a workspace-scoped operator session."
                            />
                        ) : query.isLoading ? (
                            <div className="flex min-h-[340px] flex-col items-center justify-center gap-3 text-[var(--re-text-muted)]">
                                <Spinner />
                                <p className="text-sm">Loading agent reviews...</p>
                            </div>
                        ) : query.error ? (
                            <EmptyState
                                icon={AlertTriangle}
                                title="Review queue unavailable"
                                body={query.error instanceof Error ? query.error.message : 'Unable to load agent review items.'}
                            />
                        ) : sortedItems.length === 0 ? (
                            <EmptyState
                                icon={CheckCircle2}
                                title="No agent reviews"
                                body="The current filters did not return any advisory artifacts."
                            />
                        ) : (
                            <Table>
                                <TableHeader>
                                    <TableRow className="bg-[var(--re-surface-base)] hover:bg-[var(--re-surface-base)]">
                                        <TableHead className="min-w-[280px]">Agent Suggestion</TableHead>
                                        <TableHead className="min-w-[150px]">Risk Score</TableHead>
                                        <TableHead className="min-w-[130px]">Gap Count</TableHead>
                                        <TableHead className="min-w-[140px]">Review Status</TableHead>
                                        <TableHead className="min-w-[180px]">Ingestion Run ID</TableHead>
                                        <TableHead className="min-w-[180px]">Evidence Anchors</TableHead>
                                        <TableHead className="min-w-[170px]">Advisory Receipt</TableHead>
                                        <TableHead className="min-w-[130px]">Chain Validity</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {sortedItems.map((item) => {
                                        const chain = chainBadge(item);
                                        const ChainIcon = chain.icon;
                                        return (
                                            <TableRow
                                                key={item.artifact_id}
                                                className="cursor-pointer focus-within:bg-[var(--re-brand-muted)] hover:bg-[var(--re-brand-muted)]"
                                                onClick={() => setSelectedItem(item)}
                                            >
                                                <TableCell>
                                                    <button
                                                        type="button"
                                                        className="block w-full min-w-0 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--re-brand)]"
                                                        onClick={() => setSelectedItem(item)}
                                                    >
                                                        <span className="line-clamp-2 text-sm font-medium leading-5 text-[var(--re-text-primary)]">
                                                            {item.suggestion}
                                                        </span>
                                                        <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-[var(--re-text-muted)]">
                                                            <Bot className="h-3.5 w-3.5" />
                                                            {item.agent_name}
                                                            <span className="font-mono">{formatArtifactType(item.artifact_type)}</span>
                                                        </span>
                                                    </button>
                                                </TableCell>
                                                <TableCell>
                                                    <RiskScore score={item.risk_score} />
                                                </TableCell>
                                                <TableCell>
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-lg font-semibold tabular-nums">{item.compliance_gap_count}</span>
                                                        {item.compliance_gap_count > 0 ? (
                                                            <AlertTriangle className="h-4 w-4 text-[var(--re-warning)]" />
                                                        ) : (
                                                            <CheckCircle2 className="h-4 w-4 text-[var(--re-success)]" />
                                                        )}
                                                    </div>
                                                    <p className="mt-1 text-xs text-[var(--re-text-muted)]">
                                                        {item.compliance_gaps[0]?.code ?? 'clear'}
                                                    </p>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge className={statusTone(item.review_status)}>
                                                        {REVIEW_STATUS_LABELS[item.review_status]}
                                                    </Badge>
                                                    {item.requires_human_review && (
                                                        <p className="mt-2 text-xs text-[var(--re-text-muted)]">Human review</p>
                                                    )}
                                                </TableCell>
                                                <TableCell>
                                                    <p className="font-mono text-xs text-[var(--re-text-primary)]">
                                                        {shortId(item.ingestion_run_id, 12)}
                                                    </p>
                                                    <p className="mt-1 text-xs text-[var(--re-text-muted)]">
                                                        {item.ingestion_run_status ?? item.source_file_name ?? 'No run'}
                                                    </p>
                                                </TableCell>
                                                <TableCell>
                                                    <EvidenceAnchorSummary item={item} />
                                                </TableCell>
                                                <TableCell>
                                                    <Badge variant="outline" className="border-[var(--re-border-default)]">
                                                        {item.advisory_receipt_state ?? 'No receipt'}
                                                    </Badge>
                                                    <p className="mt-2 font-mono text-[11px] text-[var(--re-text-muted)]">
                                                        {shortId(item.receipt_hash, 12)}
                                                    </p>
                                                </TableCell>
                                                <TableCell>
                                                    <Badge className={chain.className}>
                                                        <ChainIcon className="mr-1 h-3.5 w-3.5" />
                                                        {chain.label}
                                                    </Badge>
                                                </TableCell>
                                            </TableRow>
                                        );
                                    })}
                                </TableBody>
                            </Table>
                        )}
                    </CardContent>
                </section>
            </div>

            <AgentReviewDetailDialog
                item={selectedItem}
                open={Boolean(selectedItem)}
                onOpenChange={(open) => {
                    if (!open) {
                        setSelectedItem(null);
                        setDecisionError(null);
                    }
                }}
                onDecision={handleDecision}
                pendingDecision={
                    selectedItem && pendingDecision?.artifactId === selectedItem.artifact_id ? pendingDecision.status : null
                }
                decisionError={decisionError}
            />
        </div>
    );
}

function EmptyState({
    icon: Icon,
    title,
    body,
}: {
    icon: React.ComponentType<{ className?: string }>;
    title: string;
    body: string;
}) {
    return (
        <div className="flex min-h-[340px] flex-col items-center justify-center gap-3 p-6 text-center">
            <div className="grid h-11 w-11 place-items-center rounded-md border border-[var(--re-border-default)] bg-[var(--re-surface-base)]">
                <Icon className="h-5 w-5 text-[var(--re-text-muted)]" />
            </div>
            <div>
                <h3 className="text-base font-semibold text-[var(--re-text-primary)]">{title}</h3>
                <p className="mt-1 max-w-md text-sm leading-6 text-[var(--re-text-muted)]">{body}</p>
            </div>
        </div>
    );
}
