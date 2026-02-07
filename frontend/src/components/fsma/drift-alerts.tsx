'use client';

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useDriftHealth } from '@/hooks/use-fsma';
import { useAuth } from '@/lib/auth-context';
import { AlertTriangle, CheckCircle, Clock, Activity, XCircle } from 'lucide-react';
import { motion } from 'framer-motion';

export function DriftAlertsWidget() {
    const { apiKey } = useAuth();
    const { data: health, isLoading } = useDriftHealth(apiKey || '');

    if (isLoading || !health) {
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

    return (
        <Card className="h-full">
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2">
                        <Activity className="w-5 h-5 text-blue-500" />
                        Compliance Drift
                    </CardTitle>
                    {health.status === 'HEALTHY' ? (
                        <Badge className="bg-green-100 text-green-700 hover:bg-green-100">Healthy</Badge>
                    ) : health.status === 'DEGRADED' ? (
                        <Badge className="bg-amber-100 text-amber-700 hover:bg-amber-100">Degraded</Badge>
                    ) : (
                        <Badge className="bg-red-100 text-red-700 hover:bg-red-100">Critical</Badge>
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
                        <div className="text-sm text-green-600 flex items-center gap-2 bg-green-50 p-3 rounded-md border border-green-100 dark:bg-green-900/10 dark:border-green-800">
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
                                    className={`flex items-start gap-2 p-2 rounded text-sm border ${alert.severity === 'CRITICAL' ? 'bg-red-50 border-red-100 text-red-800 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300' :
                                            alert.severity === 'WARNING' ? 'bg-amber-50 border-amber-100 text-amber-800 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-300' :
                                                'bg-blue-50 border-blue-100 text-blue-800 dark:bg-blue-900/20 dark:border-blue-800 dark:text-blue-300'
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
