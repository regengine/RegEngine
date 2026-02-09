'use client';

import React, { useState } from 'react';
import { Shield, Activity, RefreshCw, AlertTriangle, FileText, Database, Search, TrendingUp, BarChart3, Target } from 'lucide-react';
import {
    VerticalDashboardLayout,
    ComplianceMetricsGrid,
    RealTimeMonitor,
    ComplianceTimeline,
    AlertsWidget,
    QuickActionsPanel,
    ComplianceScoreGauge,
    ExportButton,
    type QuickAction,
} from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import {
    useDashboardMetrics,
    useHighRiskLots,
    useActivityTimeline,
    useSystemHealth,
    useCTECoverage,
    useTraceabilityTrend,
    useGapAnalysis,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View FSMA Guide', icon: FileText, href: '/docs/food-safety', variant: 'outline' },
];

// ============================================================================
// Analysis Sub-Components
// ============================================================================

function CTECoverageChart({ data }: { data: { event_type: string; coverage_pct: number; covered_lots: number; total_lots: number; status: string }[] }) {
    const statusColor: Record<string, string> = {
        excellent: '#22c55e',
        good: '#3b82f6',
        warning: '#f59e0b',
        critical: '#ef4444',
    };

    return (
        <div className="space-y-4">
            {data.map((item) => (
                <div key={item.event_type}>
                    <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm font-medium text-gray-300">{item.event_type}</span>
                        <div className="flex items-center gap-3">
                            <span className="text-xs text-gray-500 font-mono">
                                {item.covered_lots}/{item.total_lots}
                            </span>
                            <span
                                className="text-sm font-bold font-mono"
                                style={{ color: statusColor[item.status] || '#94a3b8' }}
                            >
                                {item.coverage_pct}%
                            </span>
                        </div>
                    </div>
                    <div className="h-2 rounded-full bg-gray-800 overflow-hidden">
                        <div
                            className="h-full rounded-full transition-all duration-1000 ease-out"
                            style={{
                                width: `${item.coverage_pct}%`,
                                background: `linear-gradient(90deg, ${statusColor[item.status]}88, ${statusColor[item.status]})`,
                            }}
                        />
                    </div>
                </div>
            ))}
        </div>
    );
}

function TrendChart({ data }: { data: { week: string; score: number; gaps: number; events_processed: number }[] }) {
    const maxScore = 100;
    const maxGaps = Math.max(...data.map(d => d.gaps)) * 1.2;
    const chartHeight = 140;

    // Build SVG path for the score line
    const scorePoints = data.map((d, i) => ({
        x: (i / (data.length - 1)) * 100,
        y: chartHeight - (d.score / maxScore) * chartHeight,
    }));
    const scorePath = `M ${scorePoints.map(p => `${p.x},${p.y}`).join(' L ')}`;

    return (
        <div>
            <div className="flex items-center gap-6 mb-4">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-0.5 rounded" style={{ background: '#22c55e' }} />
                    <span className="text-xs text-gray-500">Readiness Score</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded-sm" style={{ background: '#f59e0b33', border: '1px solid #f59e0b' }} />
                    <span className="text-xs text-gray-500">Open Gaps</span>
                </div>
            </div>
            <div className="relative" style={{ height: chartHeight + 30 }}>
                <svg
                    viewBox={`0 0 100 ${chartHeight}`}
                    className="w-full"
                    style={{ height: chartHeight }}
                    preserveAspectRatio="none"
                >
                    {/* Grid lines */}
                    {[90, 95, 100].map(v => (
                        <line
                            key={v}
                            x1="0" x2="100"
                            y1={chartHeight - (v / maxScore) * chartHeight}
                            y2={chartHeight - (v / maxScore) * chartHeight}
                            stroke="#1e293b" strokeWidth="0.3"
                        />
                    ))}
                    {/* Gap bars */}
                    {data.map((d, i) => {
                        const barWidth = 6;
                        const x = (i / (data.length - 1)) * 100 - barWidth / 2;
                        const barHeight = (d.gaps / maxGaps) * chartHeight;
                        return (
                            <rect
                                key={`gap-${i}`}
                                x={x} y={chartHeight - barHeight}
                                width={barWidth} height={barHeight}
                                rx="1"
                                fill="#f59e0b22"
                                stroke="#f59e0b44"
                                strokeWidth="0.3"
                            />
                        );
                    })}
                    {/* Score line */}
                    <path d={scorePath} fill="none" stroke="#22c55e" strokeWidth="0.8" strokeLinecap="round" />
                    {/* Score gradient fill */}
                    <defs>
                        <linearGradient id="scoreGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#22c55e" stopOpacity="0.2" />
                            <stop offset="100%" stopColor="#22c55e" stopOpacity="0" />
                        </linearGradient>
                    </defs>
                    <path
                        d={`${scorePath} L 100,${chartHeight} L 0,${chartHeight} Z`}
                        fill="url(#scoreGrad)"
                    />
                    {/* Data points */}
                    {scorePoints.map((p, i) => (
                        <circle key={i} cx={p.x} cy={p.y} r="1.2" fill="#22c55e" />
                    ))}
                </svg>
                {/* X-axis labels */}
                <div className="flex justify-between mt-2 px-0">
                    {data.map((d) => (
                        <span key={d.week} className="text-[10px] text-gray-600 font-mono">{d.week}</span>
                    ))}
                </div>
            </div>
            {/* Summary stats */}
            <div className="grid grid-cols-3 gap-4 mt-4 pt-4 border-t border-gray-800">
                <div>
                    <div className="text-xs text-gray-500 mb-1">Score Δ (6wk)</div>
                    <div className="text-sm font-bold text-green-400">
                        +{data[data.length - 1].score - data[0].score} pts
                    </div>
                </div>
                <div>
                    <div className="text-xs text-gray-500 mb-1">Gaps Resolved</div>
                    <div className="text-sm font-bold text-amber-400">
                        {data[0].gaps - data[data.length - 1].gaps} closed
                    </div>
                </div>
                <div>
                    <div className="text-xs text-gray-500 mb-1">Events / Week</div>
                    <div className="text-sm font-bold text-blue-400 font-mono">
                        {data[data.length - 1].events_processed.toLocaleString()}
                    </div>
                </div>
            </div>
        </div>
    );
}

function GapAnalysisTable({ data }: { data: { category: string; count: number; severity: string; description: string; regulation: string }[] }) {
    const severityStyles: Record<string, { bg: string; text: string; label: string }> = {
        high: { bg: 'bg-red-500/10', text: 'text-red-400', label: 'High' },
        medium: { bg: 'bg-amber-500/10', text: 'text-amber-400', label: 'Medium' },
        low: { bg: 'bg-blue-500/10', text: 'text-blue-400', label: 'Low' },
    };

    const totalGaps = data.reduce((sum, d) => sum + d.count, 0);

    return (
        <div className="space-y-3">
            {data.map((gap) => {
                const style = severityStyles[gap.severity] || severityStyles.low;
                const pct = (gap.count / totalGaps) * 100;
                return (
                    <div
                        key={gap.category}
                        className="p-4 rounded-lg border border-gray-800 bg-gray-900/50 hover:border-gray-700 transition-colors"
                    >
                        <div className="flex items-start justify-between mb-2">
                            <div className="flex items-center gap-3">
                                <div className="text-lg font-bold font-mono text-gray-200">{gap.count}</div>
                                <div>
                                    <div className="text-sm font-semibold text-gray-200">{gap.category}</div>
                                    <div className="text-xs text-gray-500 mt-0.5">{gap.description}</div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${style.bg} ${style.text}`}>
                                    {style.label}
                                </span>
                            </div>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex-1 mr-4">
                                <div className="h-1.5 rounded-full bg-gray-800 overflow-hidden">
                                    <div
                                        className="h-full rounded-full transition-all duration-700"
                                        style={{
                                            width: `${pct}%`,
                                            background: gap.severity === 'high' ? '#ef4444' : gap.severity === 'medium' ? '#f59e0b' : '#3b82f6',
                                        }}
                                    />
                                </div>
                            </div>
                            <span className="text-[10px] text-gray-600 font-mono whitespace-nowrap">{gap.regulation}</span>
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// ============================================================================
// Main Dashboard Page
// ============================================================================

export default function FoodSafetyDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    const { data: metrics, isLoading: metricsLoading } = useDashboardMetrics();
    const { data: risks, isLoading: risksLoading } = useHighRiskLots();
    const { data: timeline, isLoading: timelineLoading } = useActivityTimeline();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: cteCoverage, isLoading: coverageLoading } = useCTECoverage();
    const { data: trend, isLoading: trendLoading } = useTraceabilityTrend();
    const { data: gapAnalysis, isLoading: gapLoading } = useGapAnalysis();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    return (
        <VerticalDashboardLayout
            title="FSMA 204 Compliance Dashboard"
            subtitle="End-to-End Food Traceability & Safety"
            icon={Shield}
            iconColor="text-green-600 dark:text-green-400"
            iconBgColor="bg-green-100 dark:bg-green-900"
            systemStatus={{ label: 'Traceability Active', variant: 'success', icon: Activity }}
        >
            {/* Metrics Grid */}
            {metricsLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
                    {[...Array(4)].map((_, i) => (
                        <Skeleton key={i} className="h-32 w-full" />
                    ))}
                </div>
            ) : (
                <ComplianceMetricsGrid metrics={metrics || []} columns={4} />
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column (2/3 width) */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Compliance Score */}
                    <Card>
                        <CardHeader>
                            <CardTitle>FSMA 204 Readiness Score</CardTitle>
                            <CardDescription>
                                Based on KDE completeness and 24h recall capability
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="flex items-center justify-center py-8">
                            <ComplianceScoreGauge score={98} label="Readiness Score" size="lg" showTrend trend={1.2} />
                        </CardContent>
                    </Card>

                    {/* ============================================================ */}
                    {/* ANALYSIS SECTION */}
                    {/* ============================================================ */}

                    {/* CTE Coverage Analysis */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-emerald-500/10">
                                        <BarChart3 className="w-5 h-5 text-emerald-400" />
                                    </div>
                                    <div>
                                        <CardTitle>CTE Coverage Analysis</CardTitle>
                                        <CardDescription>Coverage percentage by Critical Tracking Event type across all 430 lots</CardDescription>
                                    </div>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {coverageLoading ? (
                                <div className="space-y-4">
                                    {[...Array(6)].map((_, i) => (
                                        <Skeleton key={i} className="h-8 w-full" />
                                    ))}
                                </div>
                            ) : (
                                <CTECoverageChart data={cteCoverage || []} />
                            )}
                        </CardContent>
                    </Card>

                    {/* Traceability Trend */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-blue-500/10">
                                        <TrendingUp className="w-5 h-5 text-blue-400" />
                                    </div>
                                    <div>
                                        <CardTitle>Compliance Trend</CardTitle>
                                        <CardDescription>Readiness score and open gaps over the last 6 weeks</CardDescription>
                                    </div>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {trendLoading ? (
                                <Skeleton className="h-48 w-full" />
                            ) : (
                                <TrendChart data={trend || []} />
                            )}
                        </CardContent>
                    </Card>

                    {/* Gap Analysis */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2 rounded-lg bg-amber-500/10">
                                        <Target className="w-5 h-5 text-amber-400" />
                                    </div>
                                    <div>
                                        <CardTitle>Gap Analysis</CardTitle>
                                        <CardDescription>Breakdown of {gapAnalysis?.reduce((s, g) => s + g.count, 0) || 12} open gaps by category with CFR references</CardDescription>
                                    </div>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {gapLoading ? (
                                <div className="space-y-3">
                                    {[...Array(4)].map((_, i) => (
                                        <Skeleton key={i} className="h-24 w-full" />
                                    ))}
                                </div>
                            ) : (
                                <GapAnalysisTable data={gapAnalysis || []} />
                            )}
                        </CardContent>
                    </Card>

                    {/* High Risk Lots */}
                    <Card>
                        <CardHeader>
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>High Priority Lots</CardTitle>
                                    <CardDescription>Lots with missing critical tracking events or anomalies</CardDescription>
                                </div>
                                <button
                                    onClick={handleRefresh}
                                    className="text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    <RefreshCw className={`w-5 h-5 ${isRefreshing ? 'animate-spin' : ''}`} />
                                </button>
                            </div>
                        </CardHeader>
                        <CardContent>
                            {risksLoading ? (
                                <div className="space-y-3">
                                    {[...Array(3)].map((_, i) => (
                                        <Skeleton key={i} className="h-20 w-full" />
                                    ))}
                                </div>
                            ) : (
                                <div className="space-y-3">
                                    {risks?.map((lot) => (
                                        <div
                                            key={lot.tlc}
                                            className="p-4 rounded-lg border bg-card hover:shadow-md transition-shadow flex items-center justify-between"
                                        >
                                            <div>
                                                <div className="font-mono text-sm font-bold text-gray-800 dark:text-gray-200">
                                                    {lot.tlc}
                                                </div>
                                                <div className="text-sm text-gray-500">
                                                    {lot.product_description}
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <div className={`text-sm font-semibold ${lot.gap_count > 0 ? 'text-amber-600' : 'text-green-600'}`}>
                                                    {lot.gap_count} Gaps Detected
                                                </div>
                                                <div className="text-xs text-gray-500">
                                                    Last Event: {lot.last_event}
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Activity Timeline */}
                    {timelineLoading ? (
                        <Skeleton className="h-48 w-full" />
                    ) : (
                        <ComplianceTimeline events={timeline || []} title="Recent Traceability Events" maxItems={5} />
                    )}
                </div>

                {/* Right Column (1/3 width) */}
                <div className="space-y-6">
                    {/* System Health Monitor */}
                    {healthLoading ? (
                        <Skeleton className="h-32 w-full" />
                    ) : (
                        <RealTimeMonitor
                            title="Traceability Engine"
                            description="Graph Database Status"
                            health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }}
                            stats={[
                                { label: 'Event Ingestion', value: '45/sec', status: 'ok' },
                                { label: 'Query Latency', value: '12ms', status: 'ok' },
                            ]}
                            onRefresh={handleRefresh}
                            isRefreshing={isRefreshing}
                        />
                    )}

                    {/* Quick Actions */}
                    <QuickActionsPanel actions={quickActions} />

                    {/* Export Button */}
                    <ExportButton
                        data={{
                            title: 'FSMA 204 Compliance Report',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value })) || [],
                            tables: [
                                {
                                    title: 'High Risk Lots',
                                    headers: ['TLC', 'Product', 'Risk Score', 'Gaps'],
                                    rows: risks?.map(r => [r.tlc, r.product_description, r.risk_score.toString(), r.gap_count.toString()]) || [],
                                }
                            ]
                        }}
                        filename="fsma_compliance_report"
                        variant="default"
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
