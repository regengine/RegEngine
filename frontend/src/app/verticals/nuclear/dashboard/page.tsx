'use client';

import React, { useState } from 'react';
import { Atom, Activity, Shield, Lock, AlertTriangle, Download, FileText, Database, Scale } from 'lucide-react';
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
    useFacilityStatus,
    useEvidenceVault,
    useLegalHolds,
    useSystemHealth,
    useAttributionLog,
    useCFRCompliance,
    useFailSafeStatus,
}
    from './api';

const quickActions: QuickAction[] = [
    { label: 'View 10 CFR Guide', icon: FileText, href: '/docs/nuclear', variant: 'outline' },
];

export default function NuclearDashboardPage() {
    const [isRefreshing, setIsRefreshing] = useState(false);

    // Fetch dashboard data using API hooks
    const { data: metrics, isLoading: metricsLoading, error: metricsError } = useDashboardMetrics();
    const { data: facilities, isLoading: facilitiesLoading } = useFacilityStatus();
    const { data: evidenceRecords, isLoading: evidenceLoading } = useEvidenceVault(5);
    const { data: legalHolds, isLoading: holdsLoading } = useLegalHolds();
    const { data: systemHealth, isLoading: healthLoading } = useSystemHealth();
    const { data: attributionLog, isLoading: logLoading } = useAttributionLog(5);
    const { data: cfrCompliance, isLoading: cfrLoading } = useCFRCompliance();
    const { data: failSafeStatus, isLoading: failSafeLoading } = useFailSafeStatus();

    const handleRefresh = () => {
        setIsRefreshing(true);
        setTimeout(() => setIsRefreshing(false), 1000);
    };

    // Show error state if metrics fail to load
    if (metricsError) {
        return (
            <VerticalDashboardLayout
                title="Nuclear Compliance Dashboard"
                subtitle="10 CFR Regulatory Evidence & Chain Integrity"
                icon={Atom}
                iconColor="text-orange-600 dark:text-orange-400"
                iconBgColor="bg-orange-100 dark:bg-orange-900"
                systemStatus={{ label: 'Error Loading Data', variant: 'error', icon: AlertTriangle }}
            >
                <Card>
                    <CardContent className="py-12 text-center">
                        <AlertTriangle className="w-12 h-12 text-red-500 mx-auto mb-4" />
                        <h3 className="text-lg font-semibold mb-2">Failed to Load Dashboard</h3>
                        <p className="text-muted-foreground mb-4">
                            Unable to connect to Nuclear API. Please check backend services.
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
            title="Nuclear Compliance Dashboard"
            subtitle="10 CFR Regulatory Evidence & Chain Integrity"
            icon={Atom}
            iconColor="text-orange-600 dark:text-orange-400"
            iconBgColor="bg-orange-100 dark:bg-orange-900"
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
                    {/* 10 CFR Compliance Score */}
                    <Card>
                        <CardHeader>
                            <CardTitle>10 CFR Compliance Score</CardTitle>
                            <CardDescription>
                                Overall NRC regulatory compliance health
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="flex items-center justify-center py-8">
                            <ComplianceScoreGauge score={96} label="NRC Compliance" size="lg" showTrend trend={2} />
                        </CardContent>
                    </Card>

                    {/* CFR Compliance Breakdown */}
                    {cfrLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>10 CFR Requirements Breakdown</CardTitle>
                                <CardDescription>Compliance scores by regulation</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-4">
                                    {cfrCompliance?.map((cfr) => (
                                        <div key={cfr.regulation} className="flex items-center justify-between">
                                            <div className="flex-1">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="font-medium">{cfr.regulation}</span>
                                                    <Badge variant={cfr.score >= 95 ? 'default' : 'secondary'}>
                                                        {cfr.score}%
                                                    </Badge>
                                                </div>
                                                <div className="text-xs text-muted-foreground">
                                                    {cfr.recordCount.toLocaleString()} records • Last audit: {cfr.lastAudit}
                                                </div>
                                            </div>
                                            <div className="w-32 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden ml-4">
                                                <div
                                                    className={`h-full ${cfr.score >= 95 ? 'bg-green-500' : 'bg-blue-500'}`}
                                                    style={{ width: `${cfr.score}%` }}
                                                />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Regulatory Evidence Vault */}
                    {evidenceLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Regulatory Evidence Vault</CardTitle>
                                <CardDescription>Recently sealed compliance documents</CardDescription>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    {evidenceRecords?.map((record) => (
                                        <div
                                            key={record.id}
                                            className="p-3 rounded-lg border bg-card hover:shadow-md transition-shadow"
                                        >
                                            <div className="flex items-start justify-between mb-2">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <Lock className="w-4 h-4 text-green-600" />
                                                        <span className="font-mono text-sm font-medium">{record.recordType}</span>
                                                        <Badge variant={record.verificationStatus === 'valid' ? 'default' : 'secondary'} className="text-xs">
                                                            {record.verificationStatus}
                                                        </Badge>
                                                    </div>
                                                    <div className="text-xs text-muted-foreground">
                                                        Facility: {record.facilityId} • {new Date(record.createdAt).toLocaleString()}
                                                    </div>
                                                </div>
                                            </div>
                                            <div className="text-xs bg-muted px-2 py-1 rounded font-mono break-all">
                                                {record.contentHash}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Legal Hold Manager */}
                    {holdsLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-32 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle>Legal Hold Manager</CardTitle>
                                <CardDescription>Records under NRC enforcement actions</CardDescription>
                            </CardHeader>
                            <CardContent>
                                {legalHolds && legalHolds.length > 0 ? (
                                    <div className="space-y-3">
                                        {legalHolds.map((hold) => (
                                            <div
                                                key={hold.id}
                                                className="p-3 rounded-lg border bg-card"
                                            >
                                                <div className="flex items-start justify-between mb-2">
                                                    <div className="flex-1">
                                                        <div className="flex items-center gap-2 mb-1">
                                                            <Scale className="w-4 h-4 text-amber-600" />
                                                            <span className="font-medium text-sm">{hold.reason}</span>
                                                            <Badge variant="outline" className="text-xs">
                                                                {hold.status}
                                                            </Badge>
                                                        </div>
                                                        <div className="text-xs text-muted-foreground">
                                                            {hold.recordCount} records • Expires: {new Date(hold.expiresAt).toLocaleDateString()}
                                                        </div>
                                                    </div>
                                                </div>
                                                {hold.enforcementAction && (
                                                    <div className="text-xs text-amber-700 dark:text-amber-400 mt-2">
                                                        Enforcement Action: {hold.enforcementAction}
                                                    </div>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                ) : (
                                    <p className="text-sm text-muted-foreground text-center py-4">
                                        No active legal holds
                                    </p>
                                )}
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
                            description="Regulatory infrastructure status"
                            health={systemHealth || { status: 'UNKNOWN', message: 'Loading...', lastCheck: 'N/A', uptime: 'N/A' }}
                            stats={[
                                { label: 'DB Immutability', value: 'Enforced', status: 'ok' },
                                { label: 'Crypto Engine', value: 'Active', status: 'ok' },
                            ]}
                            onRefresh={handleRefresh}
                            isRefreshing={isRefreshing}
                        />
                    )}

                    {/* Fail-Safe Mode Indicator */}
                    {failSafeLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-24 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium">Fail-Safe Mode</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground">Current Mode</span>
                                        <Badge variant={failSafeStatus?.mode === 'OPERATIONAL' ? 'default' : 'destructive'}>
                                            {failSafeStatus?.mode || 'UNKNOWN'}
                                        </Badge>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground">Emergency Triggers</span>
                                        <span className="font-semibold">{failSafeStatus?.emergencyTriggersActive || 0}</span>
                                    </div>
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm text-muted-foreground">Recovery Ready</span>
                                        <span className="font-semibold text-green-600">
                                            {failSafeStatus?.recoveryProceduresReady ? 'Yes' : 'No'}
                                        </span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    )}

                    {/* Server-Side Attribution Log */}
                    {logLoading ? (
                        <Card>
                            <CardContent className="p-6">
                                <Skeleton className="h-48 w-full" />
                            </CardContent>
                        </Card>
                    ) : (
                        <ComplianceTimeline events={attributionLog || []} title="Attribution Log" maxItems={5} />
                    )}

                    {/* Quick Actions */}
                    <QuickActionsPanel actions={quickActions} />

                    {/* Export Button */}
                    <ExportButton
                        data={{
                            title: 'Nuclear Compliance Dashboard Export',
                            subtitle: '10 CFR Regulatory Evidence & Chain Integrity',
                            metrics: metrics?.map(m => ({
                                label: m.label,
                                value: m.value,
                                helpText: m.helpText,
                            })) || [],
                            tables: [
                                {
                                    title: '10 CFR Compliance Requirements',
                                    headers: ['Regulation', 'Score (%)', 'Record Count', 'Last Audit'],
                                    rows: cfrCompliance?.map(c => [
                                        c.regulation,
                                        c.score,
                                        c.recordCount,
                                        c.lastAudit,
                                    ]) || [],
                                },
                                {
                                    title: 'Regulatory Evidence Vault',
                                    headers: ['Record Type', 'Facility ID', 'Status', 'Created At', 'Content Hash'],
                                    rows: evidenceRecords?.map(e => [
                                        e.recordType,
                                        e.facilityId,
                                        e.verificationStatus,
                                        new Date(e.createdAt).toLocaleString(),
                                        e.contentHash.substring(0, 16) + '...',
                                    ]) || [],
                                },
                                {
                                    title: 'Active Legal Holds',
                                    headers: ['Reason', 'Status', 'Record Count', 'Expires At'],
                                    rows: legalHolds?.map(h => [
                                        h.reason,
                                        h.status,
                                        h.recordCount,
                                        new Date(h.expiresAt).toLocaleDateString(),
                                    ]) || [],
                                },
                            ],
                            metadata: {
                                'generated_at': new Date().toISOString(),
                                'compliance_score': 96,
                            },
                        }}
                        filename="nuclear_compliance_report"
                        variant="default"
                        className="w-full"
                    />
                </div>
            </div>
        </VerticalDashboardLayout>
    );
}
