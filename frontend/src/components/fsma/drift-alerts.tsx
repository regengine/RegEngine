'use client';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useDriftHealth } from '@/hooks/use-fsma';
import { AlertTriangle, CheckCircle, Clock, Activity, XCircle } from 'lucide-react';
import { motion } from 'framer-motion';

export function DriftAlertsWidget() {
    // #2837 This used to destructure only { data, isLoading } and branch on
    // `isLoading || !health`, so ANY failure — 404, 500, network drop — fell
    // into the skeleton branch and the card animated "Monitoring system
    // health..." forever. The skeleton is now reserved for isLoading; every
    // non-success path renders an explicit, honest state.
    const { data: health, isLoading, isError, error } = useDriftHealth();

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Compliance Drift</CardTitle>
                    <CardDescription>Monitoring system health...</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="space-y-4 animate-pulse">
                        <div className="h-4 bg-muted rounded w-3/4" />
                        <div className="h-8 bg-muted rounded" />
                        <div className="h-4 bg-muted rounded w-1/2" />
                    </div>
                </CardContent>
            </Card>
        );
    }

    // #2836 + #2837 This widget's data source (GET /api/fsma/drift/health) has
    // NO backend implementation. There is no drift router anywhere in
    // services/ or server/ — `grep -rn "/drift" services/ server/` returns zero
    // results — so the request cannot succeed in any environment. It is
    // therefore reported as an unavailable capability, not a transient error:
    // a "retry" affordance here would be a lie. Delete this widget or point
    // useDriftHealth() at a real endpoint once a drift backend exists.
    if (isError || !health) {
        return (
            <Card className="h-full">
                <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                        <CardTitle className="flex items-center gap-2">
                            <Activity className="w-5 h-5 text-muted-foreground" />
                            Compliance Drift
                        </CardTitle>
                        <Badge variant="outline" className="text-muted-foreground">
                            Unavailable
                        </Badge>
                    </div>
                    <CardDescription>Real-time FSMA 204 compliance metrics</CardDescription>
                </CardHeader>
                <CardContent>
                    <div
                        role="status"
                        className="flex items-start gap-2 rounded-md border border-re-warning bg-re-warning-muted p-3 text-sm text-re-warning"
                    >
                        <XCircle className="w-4 h-4 mt-0.5 shrink-0" />
                        <div className="space-y-1">
                            <p className="font-medium">Drift monitoring is not available</p>
                            <p>
                                This deployment has no compliance-drift service, so live drift
                                metrics and alerts cannot be shown. Nothing is wrong with your
                                data — the capability simply is not connected yet.
                            </p>
                            {isError && error instanceof Error && error.message ? (
                                <p className="text-xs opacity-80">Details: {error.message}</p>
                            ) : null}
                        </div>
                    </div>
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="h-full">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="w-5 h-5 text-re-info" />
                        Compliance Drift
                    </CardTitle>
                    {health.status === 'HEALTHY' ? (
                        <Badge className="bg-re-success-muted text-re-success hover:bg-re-success-muted">Healthy</Badge>
                    ) : health.status === 'DEGRADED' ? (
                        <Badge className="bg-re-warning-muted text-re-warning hover:bg-re-warning-muted">Degraded</Badge>
                    ) : (
                        <Badge className="bg-re-danger-muted text-re-danger hover:bg-re-danger-muted">Critical</Badge>
                    )}
                </div>
                <CardDescription>Real-time FSMA 204 compliance metrics</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">

                {/* Metrics Grid */}
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1">
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" /> Trace Completeness
                        </span>
                        <p className="text-2xl font-bold">{(health.trace_completeness_rate * 100).toFixed(1)}%</p>
                        <Progress value={health.trace_completeness_rate * 100} className="h-1" />
                    </div>

                    <div className="space-y-1">
                        <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Ingest Latency
                        </span>
                        <p className="text-2xl font-bold">{health.average_ingest_latency_ms.toFixed(0)}ms</p>
                        <Progress value={Math.min(100, (health.average_ingest_latency_ms / 2000) * 100)} className="h-1 bg-secondary" />
                    </div>
                </div>

                {/* Active Alerts List */}
                <div className="space-y-2">
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Active Alerts</h4>
                    {health.alerts.length === 0 ? (
                        <div className="text-sm text-re-success flex items-center gap-2 bg-re-success-muted p-3 rounded-md border border-green-100 dark:bg-re-success/10 dark:border-green-800">
                            <CheckCircle className="w-4 h-4" />
                            No active drift alerts
                        </div>
                    ) : (
                        <div className="space-y-2 max-h-[150px] overflow-y-auto pr-1">
                            {health.alerts.map((alert, idx) => (
                                <motion.div
                                    key={idx}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    className={`flex items-start gap-2 p-2 rounded text-sm border ${alert.severity === 'CRITICAL' ? 'bg-re-danger-muted border-re-danger text-re-danger dark:bg-re-danger/20 dark:border-re-danger dark:text-re-danger' :
                                            alert.severity === 'WARNING' ? 'bg-re-warning-muted border-re-warning text-re-warning dark:bg-re-warning/20 dark:border-re-warning dark:text-re-warning' :
                                                'bg-re-info-muted border-blue-100 text-re-info dark:bg-re-info/20 dark:border-blue-800 dark:text-blue-300'
                                        }`}
                                >
                                    <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
                                    <div>
                                        <p className="font-medium text-xs">{alert.metric.toUpperCase()}</p>
                                        <p>{alert.message}</p>
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    )}
                </div>
            </CardContent>
        </Card>
    );
}
