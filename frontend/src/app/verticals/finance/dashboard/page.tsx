'use client';

import React, { useState } from 'react';
import { TrendingUp, Activity, FileText, Shield, AlertTriangle, Download, Scale, BarChart3 } from 'lucide-react';
import {
    VerticalDashboardLayout,
    ComplianceMetricsGrid,
    RealTimeMonitor,
    ComplianceTimeline,
    AlertsWidget,
    QuickActionsPanel,
    ComplianceScoreGauge,
    ExportButton,
    ComplianceReportButton,
    type QuickAction,
} from '@/components/verticals';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';

// Import dashboard API hooks
import {
    useDashboardMetrics,
    useSECFilings,
    useSOXControls,
    useRegulationChanges,
    useAuditTrail,
    useRiskHeatMap,
    useSystemHealth,
    useComplianceTrend,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View SEC Compliance Guide', icon: FileText, href: '/docs/finance', variant: 'outline' },
];

export default function FinanceDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    // Fetch dashboard data using API hooks
    const { data: metrics, isLoading: metricsLoading, error: metricsError } = useDashboardMetrics();
    const { data: secFilings, isLoading: filingsLoading } = useSECFilings(5);
    const { data: soxControls, isLoading: controlsLoading } = useSOXControls();
    const { data: regulationChanges, isLoading: changesLoading } = useRegulationChanges(3);
    const { data: auditTrail, isLoading: trailLoading } = useAuditTrail(5);
    const { data: riskHeatMap, isLoading: riskLoading } = useRiskHeatMap();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: complianceTrend, isLoading: trendLoading } = useComplianceTrend();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    // Show error state if metrics fail to load
    if (metricsError) {
        return (
            <VerticalDashboardLayout
                title="Finance Compliance Dashboard"
                subtitle="SEC & SOX 404 Regulatory Monitoring"
                icon={TrendingUp}
                iconColor="text-blue-600 dark:text-blue-400"
                iconBgColor="bg-blue-100 dark:bg-blue-900"
                systemStatus={{ label: 'Error Loading Data', variant: 'error', icon: AlertTriangle }}
            >
                <Card>
                    <CardContent className="py-12 text-center">
                        <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
                        <h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3>
                        <p className="text-muted-foreground mb-4">
                            Unable to connect to Finance API. Please check backend services.
                        </p>
                        <button
                            onClick={() => window.location.reload()}
                            className="px-4 py-2 bg-primary text-primary-foreground rounded-md hover:bg-primary/90"
                        >
                            Retry
                        </button>
                    </CardContent>
                </Card>
            </VerticalDashboardLayout>
        );
    }

    return (
        <VerticalDashboardLayout
            title="Finance Compliance Dashboard"
            subtitle="SEC & SOX 404 Regulatory Monitoring"
            icon={TrendingUp}
            iconColor="text-blue-600 dark:text-blue-400"
            iconBgColor="bg-blue-100 dark:bg-blue-900"
            systemStatus={{ label: 'All Systems Operational', variant: 'success', icon: Activity }}
        >
            {/* Metrics Grid */}
            {metricsLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
                    {[...Array(4)].map((_, i) => (
                        <Card key={i}>
                            <CardContent className="p-6">
                                <Skeleton className="h-20 w-full" />
                            </CardContent>
                        </Card>
                    ))}
                </div>
            ) : (
                <ComplianceMetricsGrid metrics={metrics || []} columns={4} />
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Left Column (2/3 width) */}
                <div className="lg:col-span-2 space-y-6">
                    {/* Overall Compliance Score */}
                    <Card>
                        <CardHeader>
                            <CardTitle>SEC/SOX Compliance Score</CardTitle>
                            <CardDescription>
                                Overall financial regulatory compliance health
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="flex items-center justify-center py-8">
                            <ComplianceScoreGauge score={98} label="Compliance" size="lg" showTrend trend={4} />
                        </CardContent>
                    </Card>

                    {/* Compliance Score Trend */}
                    {trendLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Compliance Score Trend</CardTitle>
                                <CardDescription>Quarterly compliance performance</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-4">
                                    {complianceTrend?.map((trend, idx) => (
                                        <div key={trend.period} className="flex items-center justify-between">
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="font-medium">{trend.period}</span>
                                                    <Badge variant={trend.score >= 95 ? 'default' : 'secondary'}>
                                                        {trend.score}/100
                                                    </Badge>
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {trend.filingCount} filings submitted
                                                </div>
                                            </div>
                                            <div className="w-32 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden ml-4">
                                                <div
                                                    className={`h-full ${trend.score >= 95 ? 'bg-green-500' : 'bg-blue-500'}`}
                                                    style={{ width: `${trend.score}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* SEC Filing Verification Status */}
                    {filingsLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Recent SEC Filings</CardTitle>
                                <CardDescription>Filing status and verification</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {secFilings?.map((filing) => (
                                        <div
                                            key={filing.id}
                                            className="p-3 rounded-lg border bg-card hover:shadow-md transition-shadow"
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <FileText className="w-4 h-4 text-blue-600" />
                                                        <span className="font-semibold text-sm">{filing.filingType}</span>
                                                        <Badge
                                                            variant={
                                                                filing.status === 'verified'
                                                                    ? 'default'
                                                                    : filing.status === 'deficient'
                                                                        ? 'destructive'
                                                                        : 'secondary'
                                                            }
                                                            className="text-xs"
                                                        >
                                                            {filing.status}
                                                        </Badge>
                                                    </div>
                                                    <div className="text-sm font-medium">{filing.entity}</div>
                                                    <div className="text-xs text-muted-foreground">
                                                        {filing.periodEnding} • Filed: {new Date(filing.filedDate).toLocaleDateString()}
                                                    </div>
                                                </div>
                                            </div>
                                            {filing.accessionNumber && (
                                                <div className="text-xs bg-muted px-2 py-1 rounded font-mono">
                                                    {filing.accessionNumber}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* SOX 404 Control Health Matrix */}
                    {controlsLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>SOX 404 Control Health</CardTitle>
                                <CardDescription>Internal control effectiveness</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {soxControls?.map((control) => (
                                        <div
                                            key={control.id}
                                            className="p-3 rounded-lg border bg-card"
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <Shield className="w-4 h-4 text-purple-600" />
                                                        <span className="font-mono text-sm font-medium">{control.controlId}</span>
                                                        <Badge
                                                            variant={
                                                                control.effectiveness === 'effective'
                                                                    ? 'default'
                                                                    : control.effectiveness === 'material_weakness'
                                                                        ? 'destructive'
                                                                        : 'outline'
                                                            }
                                                            className="text-xs"
                                                        >
                                                            {control.effectiveness.replace('_', ' ')}
                                                        </Badge>
                                                    </div>
                                                    <div className="text-sm">{control.description}</div>
                                                    <div className="text-xs text-muted-foreground mt-1">
                                                        {control.category} • Owner: {control.owner} • Last tested: {control.lastTested}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </div>

                {/* Right Column (1/3 width) */}
                <div className="space-y-6">
                    {/* System Health Monitor */}
                    {healthLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <RealTimeMonitor
                            title="System Health"
                            description="Compliance infrastructure status"
                            health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }}
                            stats={[
                                { label: 'Filing API', value: 'Connected', status: 'ok' },
                                { label: 'Control Tests', value: 'Active', status: 'ok' },
                            ]}
                            onRefresh={handleRefresh}
                            isRefreshing={isRefreshing}
                        />
                    )}

                    {/* Risk Heat Map */}
                    {riskLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Risk Heat Map</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {riskHeatMap?.map((risk) => (
                                        <div key={risk.category} className="p-2 rounded border">
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="text-xs font-medium">{risk.category}</span>
                                                <Badge
                                                    variant={
                                                        risk.riskLevel === 'low'
                                                            ? 'default'
                                                            : risk.riskLevel === 'high' || risk.riskLevel === 'critical'
                                                                ? 'destructive'
                                                                : 'outline'
                                                    }
                                                    className="text-xs"
                                                >
                                                    {risk.riskLevel}
                                                </Badge>
                                            </div>
                                            <div className="text-xs text-muted-foreground">
                                                {risk.controlCount} controls • {risk.deficiencyCount} deficiencies
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Regulation Change Feed */}
                    {changesLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Regulation Updates</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {regulationChanges?.map((change) => (
                                        <div key={change.id} className="p-2 rounded border">
                                            <div className="flex items-center gap-2 mb-1">
                                                <Badge variant="outline" className="text-xs">
                                                    {change.source}
                                                </Badge>
                                                <Badge
                                                    variant={change.impact === 'high' ? 'destructive' : 'secondary'}
                                                    className="text-xs"
                                                >
                                                    {change.impact}
                                                </Badge>
                                            </div>
                                            <div className="text-xs font-medium mb-1">{change.title}</div>
                                            <div className="text-xs text-muted-foreground">
                                                Effective: {new Date(change.effectiveDate).toLocaleDateString()}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Audit Trail */}
                    {trailLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <ComplianceTimeline events={auditTrail || []} title="Audit Trail" maxItems={5} />
                    )}

                    {/* Quick Actions */}
                    <QuickActionsPanel actions={quickActions} />

                    {/* Export Button */}
                    <ExportButton
                        data={{
                            title: 'Finance Compliance Dashboard Export',
                            subtitle: 'SEC & SOX 404 Regulatory Monitoring',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value, helpText: m.helpText })) || [],
                            tables: [
                                {
                                    title: 'Recent SEC Filings',
                                    headers: ['Filing Type', 'Entity', 'Status', 'Period Ending', 'Filed Date'],
                                    rows: secFilings?.map(f => [f.filingType, f.entity, f.status, f.periodEnding, new Date(f.filedDate).toLocaleDateString()]) || [],
                                },
                                {
                                    title: 'SOX 404 Controls',
                                    headers: ['Control ID', 'Description', 'Category', 'Effectiveness', 'Owner'],
                                    rows: soxControls?.slice(0, 10).map(c => [c.controlId, c.description, c.category, c.effectiveness, c.owner]) || [],
                                },
                            ],
                            metadata: { 'generated_at': new Date().toISOString(), 'compliance_score': 98 },
                        }}
                        filename="finance_compliance_report"
                        variant="default"
                        className="w-full"
                    />
                    <ComplianceReportButton
                        dashboardTitle="SEC & SOX 404 Compliance Report"
                        vertical="Finance"
                        reportData={{
                            summary: 'Financial regulatory compliance covering SEC filing verification, SOX 404 internal control effectiveness, risk heat map analysis, and regulation change tracking.',
                            metrics: metrics?.map(m => ({ label: m.label, value: m.value, status: 'pass' as const })) || [],
                        }}
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
