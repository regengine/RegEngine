'use client';

import React, { useState, useMemo } from 'react';
import { Cpu, Activity, Shield, AlertTriangle, Download, Settings, Users, BarChart3, FileText } from 'lucide-react';
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
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';

// Import dashboard API hooks
import {
    useDashboardMetrics,
    useSecurityControls,
    useConfigurationDrift,
    useAccessReviews,
    useISOGapAnalysis,
    useMonitoringFeed,
    useSystemHealth,
    useAutomationStatus,
} from './api';

const quickActions: QuickAction[] = [
    { label: 'View SOC 2 Guide', icon: FileText, href: '/docs/technology', variant: 'outline' },
];

export default function TechnologyDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    // Fetch dashboard data using API hooks
    const { data: metrics, isLoading: metricsLoading, error: metricsError } = useDashboardMetrics();
    const { data: securityControls, isLoading: controlsLoading } = useSecurityControls();
    const { data: configDrift, isLoading: driftLoading } = useConfigurationDrift(5);
    const { data: accessReviews, isLoading: reviewsLoading } = useAccessReviews(3);
    const { data: isoGaps, isLoading: gapsLoading } = useISOGapAnalysis();
    const { data: monitoringFeed, isLoading: feedLoading } = useMonitoringFeed(5);
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: automationStatus, isLoading: automationLoading } = useAutomationStatus();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    // Show error state if metrics fail to load
    if (metricsError) {
        return (
            <VerticalDashboardLayout
                title="Technology Compliance Dashboard"
                subtitle="SOC 2 & ISO 27001 Security Monitoring"
                icon={Cpu}
                iconColor="text-purple-600 dark:text-purple-400"
                iconBgColor="bg-purple-100 dark:bg-purple-900"
                systemStatus={{ label: 'Error Loading Data', variant: 'error', icon: AlertTriangle }}
            >
                <Card>
                    <CardContent className="py-12 text-center">
                        <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
                        <h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3>
                        <p className="text-muted-foreground mb-4">
                            Unable to connect to Technology API. Please check backend services.
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
            title="Technology Compliance Dashboard"
            subtitle="SOC 2 & ISO 27001 Security Monitoring"
            icon={Cpu}
            iconColor="text-purple-600 dark:text-purple-400"
            iconBgColor="bg-purple-100 dark:bg-purple-900"
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
                    {/* Overall Security Score */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Security Compliance Score</CardTitle>
                            <CardDescription>
                                Overall SOC 2 & ISO 27001 compliance health
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="flex items-center justify-center py-8">
                            <ComplianceScoreGauge score={94} label="Security" size="lg" showTrend trend={3} />
                        </CardContent>
                    </Card>

                    {/* Security Control Matrix */}
                    {controlsLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Security Control Matrix</CardTitle>
                                <CardDescription>Multi-framework control implementation status</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {securityControls?.map((control) => (
                                        <div
                                            key={control.id}
                                            className="p-3 rounded-lg border bg-card"
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <Shield className="w-4 h-4 text-purple-600" />
                                                        <span className="font-mono text-sm font-medium">{control.controlId}</span>
                                                        <Badge variant="outline" className="text-xs">
                                                            {control.framework}
                                                        </Badge>
                                                        <Badge
                                                            variant={
                                                                control.status === 'implemented'
                                                                    ? 'default'
                                                                    : control.status === 'in_progress'
                                                                        ? 'secondary'
                                                                        : 'outline'
                                                            }
                                                            className="text-xs"
                                                        >
                                                            {control.status.replace('_', ' ')}
                                                        </Badge>
                                                    </div>
                                                    <div className="text-sm">{control.description}</div>
                                                    <div className="text-xs text-muted-foreground mt-1">
                                                        {control.domain} • Owner: {control.owner} • Last audited: {control.lastAudited}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Configuration Drift Monitor */}
                    {driftLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Configuration Drift Monitor</CardTitle>
                                <CardDescription>Infrastructure deviations from baseline</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {configDrift && configDrift.length > 0 ? (
                                        configDrift.map((drift) => (
                                            <div
                                                key={drift.id}
                                                className="p-3 rounded-lg border bg-card"
                                            >
                                                <div className="flex items-start justify-between mb-2">
                                                    <div className="flex-1">
                                                        <div className="flex items-center gap-2 mb-1">
                                                            <AlertTriangle className={`w-4 h-4 ${drift.severity === 'critical' || drift.severity === 'high'
                                                                ? 'text-red-600'
                                                                : 'text-amber-600'
                                                                }`} />
                                                            <span className="font-medium text-sm">{drift.resource}</span>
                                                            <Badge variant="outline" className="text-xs">
                                                                {drift.resourceType}
                                                            </Badge>
                                                            <Badge
                                                                variant={drift.severity === 'high' || drift.severity === 'critical' ? 'destructive' : 'secondary'}
                                                                className="text-xs"
                                                            >
                                                                {drift.severity}
                                                            </Badge>
                                                        </div>
                                                        <div className="text-xs text-muted-foreground mb-1">
                                                            <strong>Current:</strong> {drift.currentState}
                                                        </div>
                                                        <div className="text-xs text-muted-foreground">
                                                            <strong>Expected:</strong> {drift.baseline}
                                                        </div>
                                                        <div className="text-xs text-muted-foreground mt-1">
                                                            Detected: {new Date(drift.detectedAt).toLocaleString()}
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        ))
                                    ) : (
                                        <p className="text-sm text-muted-foreground text-center py-4">
                                            No configuration drift detected
                                        </p>
                                    )}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* ISO 27001 Gap Analysis */}
                    {gapsLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>ISO 27001 Gap Analysis</CardTitle>
                                <CardDescription>Annex A control compliance status</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {isoGaps?.map((gap) => (
                                        <div key={gap.controlId} className="p-2 rounded border">
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="text-xs font-mono">{gap.controlId}</span>
                                                <Badge
                                                    variant={
                                                        gap.status === 'compliant'
                                                            ? 'default'
                                                            : gap.status === 'non_compliant'
                                                                ? 'destructive'
                                                                : 'outline'
                                                    }
                                                    className="text-xs"
                                                >
                                                    {gap.status.replace('_', ' ')}
                                                </Badge>
                                            </div>
                                            <div className="text-xs font-medium">{gap.controlName}</div>
                                            <div className="text-xs text-muted-foreground">{gap.annexReference}</div>
                                            {gap.gapDescription && (
                                                <div className="text-xs text-amber-700 dark:text-amber-400 mt-1">
                                                    Gap: {gap.gapDescription}
                                                </div>
                                            )}
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
                            description="Security infrastructure status"
                            health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }}
                            stats={[
                                { label: 'Vuln Scanner', value: 'Active', status: 'ok' },
                                { label: 'Config Monitor', value: 'Running', status: 'ok' },
                            ]}
                            onRefresh={handleRefresh}
                            isRefreshing={isRefreshing}
                        />
                    )}

                    {/* Compliance Automation Status */}
                    {automationLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Automation Status</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {automationStatus?.map((item) => (
                                        <div key={item.category}>
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="text-xs font-medium">{item.category}</span>
                                                <span className="text-xs font-semibold">{item.automationLevel}%</span>
                                            </div>
                                            <div className="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full ${item.automationLevel >= 85 ? 'bg-green-500' : 'bg-blue-500'}`}
                                                    style={{ width: `${item.automationLevel}%` }}
                                                />
                                            </div>
                                            <div className="text-xs text-muted-foreground mt-1">
                                                {item.automatedControls}/{item.totalControls} controls automated
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Access Review Dashboard */}
                    {reviewsLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Pending Access Reviews</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-2">
                                    {accessReviews?.map((review) => (
                                        <div key={review.id} className="p-2 rounded border">
                                            <div className="flex items-center justify-between mb-1">
                                                <span className="text-xs font-medium">{review.userName}</span>
                                                <Badge
                                                    variant={review.reviewStatus === 'approved' ? 'default' : 'outline'}
                                                    className="text-xs"
                                                >
                                                    {review.reviewStatus}
                                                </Badge>
                                            </div>
                                            <div className="text-xs text-muted-foreground">{review.accessLevel}</div>
                                            <div className="text-xs text-muted-foreground">
                                                Last review: {review.lastReviewDate}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Continuous Monitoring Feed */}
                    {feedLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <ComplianceTimeline events={monitoringFeed || []} title="Monitoring Feed" maxItems={5} />
                    )}

                    {/* Quick Actions */}
                    <QuickActionsPanel actions={quickActions} />

                    {/* Export Button */}
                    <ExportButton
                        data={{
                            title: 'Technology Compliance Dashboard Export',
                            subtitle: 'SOC 2 & ISO 27001 Security Monitoring',
                            metrics: metrics?.map(m => ({
                                label: m.label,
                                value: m.value,
                                helpText: m.helpText,
                            })) || [],
                            tables: [
                                {
                                    title: 'Security Controls',
                                    headers: ['Control ID', 'Framework', 'Status', 'Owner', 'Last Audited'],
                                    rows: securityControls?.slice(0, 10).map(c => [
                                        c.controlId,
                                        c.framework,
                                        c.status,
                                        c.owner,
                                        c.lastAudited,
                                    ]) || [],
                                },
                                {
                                    title: 'Configuration Drift',
                                    headers: ['Resource', 'Type', 'Severity', 'Current State', 'Baseline'],
                                    rows: configDrift?.map(d => [
                                        d.resource,
                                        d.resourceType,
                                        d.severity,
                                        d.currentState,
                                        d.baseline,
                                    ]) || [],
                                },
                            ],
                            metadata: {
                                'generated_at': new Date().toISOString(),
                                'compliance_score': 94,
                            },
                        }}
                        filename="technology_compliance_report"
                        variant="default"
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
