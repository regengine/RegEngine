'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import {
    AlertTriangle,
    ShieldAlert,
    Clock,
    XCircle,
    CheckCircle2,
    RefreshCw,
    FileWarning,
    Users,
    Link2,
    ChevronRight,
    Timer,
    Shield,
} from 'lucide-react';

import { useAuth } from '@/lib/auth-context';
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

/* ── Helpers ── */

const BLOCKER_CONFIG: Record<string, { icon: React.ElementType; color: string; label: string }> = {
    critical_rule_failure: { icon: XCircle, color: '#ef4444', label: 'Rule Failure' },
    unresolved_critical_exception: { icon: FileWarning, color: '#f59e0b', label: 'Exception' },
    unevaluated_event: { icon: ShieldAlert, color: '#8b5cf6', label: 'Unevaluated' },
    missing_signoff: { icon: Users, color: '#3b82f6', label: 'Missing Signoff' },
    identity_ambiguity: { icon: Link2, color: '#ec4899', label: 'Identity' },
};

const URGENCY_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
    overdue: { color: '#ef4444', bg: 'bg-red-500/10', label: 'OVERDUE' },
    critical: { color: '#f59e0b', bg: 'bg-amber-500/10', label: 'CRITICAL' },
    urgent: { color: '#3b82f6', bg: 'bg-blue-500/10', label: 'URGENT' },
    normal: { color: '#10b981', bg: 'bg-emerald-500/10', label: 'ON TRACK' },
};

/* ── Page ── */

export default function IssuesPage() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();

    const { data: issuesData, isLoading: loading, error: issuesError, refetch: loadIssues } = useQuery({
        queryKey: ['issues', tenantId],
        queryFn: async () => {
            const { getServiceURL } = await import('@/lib/api-config');
            const base = getServiceURL('ingestion');
            const headers = { 'Content-Type': 'application/json', 'X-RegEngine-API-Key': apiKey! };

            const [deadlineRes, pendingRes] = await Promise.allSettled([
                fetch(`${base}/api/v1/requests/deadlines?tenant_id=${tenantId}`, { headers }),
                fetch(`${base}/api/v1/compliance/pending-reviews/${tenantId}`, { headers }),
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
                        const bRes = await fetch(
                            `${base}/api/v1/requests/${c.request_case_id}/blockers?tenant_id=${tenantId}`,
                            { headers }
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
        enabled: !!tenantId && !!apiKey,
    });

    const deadlines = issuesData?.deadlines ?? [];
    const blockers = issuesData?.blockers ?? [];
    const warnings = issuesData?.warnings ?? [];
    const pendingReviews = issuesData?.pendingReviews ?? {};
    const error = issuesError?.message ?? null;

    const totalIssues = blockers.length + deadlines.filter(d => d.urgency === 'overdue' || d.urgency === 'critical').length;
    const overdueCount = deadlines.filter(d => d.urgency === 'overdue').length;
    const criticalCount = deadlines.filter(d => d.urgency === 'critical').length;

    return (
        <div className="min-h-screen bg-background p-4 md:p-8 pt-4">
            <div className="mx-auto max-w-5xl space-y-6">
                <Breadcrumbs items={[
                    { label: 'Dashboard', href: '/dashboard' },
                    { label: 'Issues' },
                ]} />

                {/* Header */}
                <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
                    <div>
                        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight flex items-center gap-2">
                            <AlertTriangle className="h-6 w-6 sm:h-7 sm:w-7 text-amber-400" />
                            Issues & Blockers
                        </h1>
                        <p className="mt-1 text-sm text-muted-foreground">
                            Everything preventing compliant submission — fix these first.
                        </p>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => loadIssues()} disabled={loading} className="h-8 w-8 p-0">
                        <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    </Button>
                </div>

                {/* Summary Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-3">
                    <div className="p-3 sm:p-4 rounded-xl bg-red-500/[0.06] border border-red-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-red-400 tabular-nums">{blockers.length}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Blocking Defects</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-amber-500/[0.06] border border-amber-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-amber-400 tabular-nums">{overdueCount + criticalCount}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Urgent Deadlines</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-blue-500/[0.06] border border-blue-500/20 text-center">
                        <div className="text-2xl sm:text-3xl font-bold text-blue-400 tabular-nums">{warnings.length}</div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Warnings</div>
                    </div>
                    <div className="p-3 sm:p-4 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                        <div className="text-2xl sm:text-3xl font-bold tabular-nums">
                            {Object.values(pendingReviews).reduce((s, v) => s + v, 0)}
                        </div>
                        <div className="text-[11px] text-muted-foreground mt-0.5">Pending Reviews</div>
                    </div>
                </div>

                {loading && (
                    <div className="flex justify-center py-16"><Spinner size="lg" /></div>
                )}

                {error && (
                    <Card className="border-red-500/30">
                        <CardContent className="py-4">
                            <div className="flex items-center gap-3 text-red-400">
                                <AlertTriangle className="h-5 w-5" />
                                <p className="text-sm">{error}</p>
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Deadline Urgency */}
                {deadlines.length > 0 && (
                    <Card className="border-[var(--re-border-default)]">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                                <Timer className="h-4 w-4 text-amber-400" />
                                Active Deadlines
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {deadlines.map((c) => {
                                const cfg = URGENCY_CONFIG[c.urgency] || URGENCY_CONFIG.normal;
                                return (
                                    <div
                                        key={c.request_case_id}
                                        className={`flex items-center justify-between p-3 rounded-xl border border-[var(--re-border-default)] ${cfg.bg}`}
                                    >
                                        <div className="flex items-center gap-3 min-w-0">
                                            <Badge
                                                className="text-[9px] px-1.5 py-0 font-bold"
                                                style={{ background: `${cfg.color}20`, color: cfg.color }}
                                            >
                                                {cfg.label}
                                            </Badge>
                                            <div className="min-w-0">
                                                <div className="text-sm font-medium truncate">
                                                    {c.requesting_party} — {c.scope_description || c.package_status}
                                                </div>
                                                <div className="text-[11px] text-muted-foreground">
                                                    {c.countdown_display} · {c.gap_count} gaps · {c.active_exception_count} exceptions
                                                </div>
                                            </div>
                                        </div>
                                        <ChevronRight className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                                    </div>
                                );
                            })}
                        </CardContent>
                    </Card>
                )}

                {/* Blocking Defects */}
                {blockers.length > 0 && (
                    <Card className="border-red-500/20">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2 text-red-400">
                                <XCircle className="h-4 w-4" />
                                Blocking Defects — Must Fix Before Submission
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {blockers.map((b, i) => {
                                const cfg = BLOCKER_CONFIG[b.type] || BLOCKER_CONFIG.critical_rule_failure;
                                const Icon = cfg.icon;
                                return (
                                    <motion.div
                                        key={`${b.type}-${i}`}
                                        initial={{ opacity: 0, y: 6 }}
                                        animate={{ opacity: 1, y: 0 }}
                                        transition={{ delay: i * 0.03 }}
                                        className="p-3 rounded-xl border border-[var(--re-border-default)] hover:border-red-500/30 transition-all"
                                    >
                                        <div className="flex items-start gap-2.5">
                                            <div
                                                className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5"
                                                style={{ background: `${cfg.color}15` }}
                                            >
                                                <Icon className="h-3.5 w-3.5" style={{ color: cfg.color }} />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-1.5 mb-0.5">
                                                    <Badge
                                                        className="text-[9px] px-1.5 py-0"
                                                        style={{ background: `${cfg.color}15`, color: cfg.color }}
                                                    >
                                                        {cfg.label}
                                                    </Badge>
                                                    {b.citation && (
                                                        <span className="text-[9px] text-muted-foreground font-mono">{b.citation}</span>
                                                    )}
                                                </div>
                                                <p className="text-xs text-foreground">{b.message}</p>
                                                {b.rule_title && (
                                                    <p className="text-[10px] text-muted-foreground mt-0.5">Rule: {b.rule_title}</p>
                                                )}
                                                {b.supplier && (
                                                    <p className="text-[10px] text-muted-foreground mt-0.5">Supplier: {b.supplier}</p>
                                                )}
                                            </div>
                                        </div>
                                    </motion.div>
                                );
                            })}
                        </CardContent>
                    </Card>
                )}

                {/* Warnings */}
                {warnings.length > 0 && (
                    <Card className="border-amber-500/20">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2 text-amber-400">
                                <AlertTriangle className="h-4 w-4" />
                                Warnings — Non-Blocking
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-2">
                            {warnings.map((w, i) => (
                                <div key={i} className="p-3 rounded-xl border border-[var(--re-border-default)] text-xs text-muted-foreground">
                                    {w.message}
                                </div>
                            ))}
                        </CardContent>
                    </Card>
                )}

                {/* Pending Reviews Breakdown */}
                {Object.keys(pendingReviews).length > 0 && (
                    <Card className="border-[var(--re-border-default)]">
                        <CardHeader>
                            <CardTitle className="text-base flex items-center gap-2">
                                <Shield className="h-4 w-4 text-[var(--re-brand)]" />
                                Pending Reviews
                            </CardTitle>
                        </CardHeader>
                        <CardContent>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                                {Object.entries(pendingReviews).map(([key, count]) => (
                                    <div key={key} className="p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] text-center">
                                        <div className="text-lg font-bold tabular-nums">{count}</div>
                                        <div className="text-[10px] text-muted-foreground capitalize">
                                            {key.replace(/_/g, ' ')}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>
                )}

                {/* Empty State */}
                {!loading && blockers.length === 0 && deadlines.length === 0 && warnings.length === 0 && (
                    <motion.div
                        className="flex flex-col items-center justify-center py-16 text-center"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                    >
                        <CheckCircle2 className="h-12 w-12 text-emerald-400 mb-4" />
                        <h2 className="text-lg font-semibold">No Issues Found</h2>
                        <p className="text-sm text-muted-foreground mt-1 max-w-md">
                            All systems clear. No blocking defects, no overdue deadlines, no pending reviews.
                        </p>
                    </motion.div>
                )}
            </div>
        </div>
    );
}
