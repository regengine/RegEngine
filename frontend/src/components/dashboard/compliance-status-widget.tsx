"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, XCircle, Clock, Bell } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

export interface ComplianceAlert {
    id: string;
    tenant_id?: string;
    title: string;
    summary?: string;
    severity: string;
    severity_emoji: string;
    source_type?: string;
    source_id?: string;
    countdown_display: string;
    countdown_seconds: number;
    countdown_end?: string;
    is_expired: boolean;
    status: string;
    required_actions: { action: string; completed: boolean }[];
    acknowledged_at?: string;
    acknowledged_by?: string;
    match_reason?: { matched_by: string[] };
    created_at: string;
}

interface ComplianceStatus {
    tenant_id: string;
    status: "COMPLIANT" | "AT_RISK" | "NON_COMPLIANT";
    status_emoji: string;
    status_label: string;
    active_alert_count: number;
    critical_alert_count: number;
    countdown_seconds?: number;
    countdown_display?: string;
    next_deadline_description?: string;
    active_alerts: ComplianceAlert[];
}

interface ComplianceStatusWidgetProps {
    tenantId: string;
    onAlertClick?: (alert: ComplianceAlert) => void;
}

const STATUS_CONFIG = {
    COMPLIANT: {
        bgClass: "bg-re-success-muted dark:bg-re-success/20",
        borderClass: "border-green-200 dark:border-green-800",
        textClass: "text-re-success dark:text-re-success",
        iconClass: "text-re-success",
        Icon: CheckCircle,
    },
    AT_RISK: {
        bgClass: "bg-re-warning-muted dark:bg-re-warning/20",
        borderClass: "border-amber-200 dark:border-amber-800",
        textClass: "text-re-warning dark:text-re-warning",
        iconClass: "text-re-warning",
        Icon: AlertTriangle,
    },
    NON_COMPLIANT: {
        bgClass: "bg-re-danger-muted dark:bg-re-danger/20",
        borderClass: "border-re-danger dark:border-re-danger",
        textClass: "text-re-danger dark:text-re-danger",
        iconClass: "text-re-danger",
        Icon: XCircle,
    },
};

function CountdownTimer({ seconds, display }: { seconds: number; display: string }) {
    const [timeLeft, setTimeLeft] = useState(seconds);

    useEffect(() => {
        if (timeLeft <= 0) return;

        const timer = setInterval(() => {
            setTimeLeft((prev) => Math.max(0, prev - 1));
        }, 1000);

        return () => clearInterval(timer);
    }, [timeLeft]);

    const hours = Math.floor(timeLeft / 3600);
    const minutes = Math.floor((timeLeft % 3600) / 60);
    const secs = timeLeft % 60;

    const urgencyClass = hours < 4
        ? "text-re-danger animate-pulse"
        : hours < 12
            ? "text-re-warning"
            : "text-re-text-disabled";

    return (
        <div className={`font-mono text-2xl font-bold ${urgencyClass}`}>
            {String(hours).padStart(2, "0")}:{String(minutes).padStart(2, "0")}:{String(secs).padStart(2, "0")}
        </div>
    );
}

function AlertCard({ alert, onClick }: { alert: ComplianceAlert; onClick?: () => void }) {
    const severityColors: Record<string, string> = {
        CRITICAL: "bg-re-danger-muted text-re-danger border-re-danger",
        HIGH: "bg-re-warning-muted text-re-warning border-amber-200",
        MEDIUM: "bg-re-info-muted text-re-info border-blue-200",
        LOW: "bg-re-surface-elevated text-re-text-primary border-re-border",
    };

    const completedActions = alert.required_actions.filter(a => a.completed).length;
    const totalActions = alert.required_actions.length;
    const progress = totalActions > 0 ? (completedActions / totalActions) * 100 : 0;

    return (
        <div
            className="p-4 border rounded-lg bg-white dark:bg-re-surface-base hover:shadow-md transition-shadow cursor-pointer"
            onClick={onClick}
        >
            <div className="flex items-start justify-between">
                <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                        <Badge className={severityColors[alert.severity] || severityColors.MEDIUM}>
                            {alert.severity_emoji} {alert.severity}
                        </Badge>
                        {alert.is_expired && (
                            <Badge variant="destructive">EXPIRED</Badge>
                        )}
                    </div>
                    <h4 className="font-semibold text-re-text-primary dark:text-re-text-primary">{alert.title}</h4>
                    {alert.summary && (
                        <p className="text-sm text-re-text-disabled dark:text-re-text-tertiary mt-1 line-clamp-2">
                            {alert.summary}
                        </p>
                    )}
                </div>
                <div className="text-right ml-4">
                    <div className="flex items-center gap-1 text-re-text-muted">
                        <Clock className="h-4 w-4" />
                        <span className="text-sm font-medium">{alert.countdown_display}</span>
                    </div>
                </div>
            </div>

            {totalActions > 0 && (
                <div className="mt-3">
                    <div className="flex justify-between text-xs text-re-text-muted mb-1">
                        <span>Required Actions</span>
                        <span>{completedActions}/{totalActions}</span>
                    </div>
                    <Progress value={progress} className="h-1.5" />
                </div>
            )}
        </div>
    );
}

export function ComplianceStatusWidget({ tenantId, onAlertClick }: ComplianceStatusWidgetProps) {
    const [status, setStatus] = useState<ComplianceStatus | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchStatus() {
            try {
                const response = await fetch(`/api/v1/compliance/status/${tenantId}`);
                if (!response.ok) throw new Error("API unavailable");
                const data = await response.json();
                setStatus(data);
                setError(null);
            } catch (e) {
                // Show error - no mock fallback for production FSMA
                if (process.env.NODE_ENV !== 'production') { console.error('Compliance API unavailable:', e); }
                setError(e instanceof Error ? e.message : "Compliance service unavailable");
            } finally {
                setLoading(false);
            }
        }

        fetchStatus();

        // Refresh every 30 seconds
        const interval = setInterval(fetchStatus, 30000);
        return () => clearInterval(interval);
    }, [tenantId]);

    if (loading) {
        return (
            <Card className="animate-pulse">
                <CardContent className="h-32 flex items-center justify-center">
                    <div className="h-8 w-48 bg-re-surface-elevated rounded" />
                </CardContent>
            </Card>
        );
    }

    if (error) {
        return (
            <Card className="border-re-danger bg-re-danger-muted">
                <CardContent className="p-4">
                    <p className="text-re-danger">Error loading compliance status: {error}</p>
                </CardContent>
            </Card>
        );
    }

    if (!status) return null;

    const config = STATUS_CONFIG[status.status];
    const StatusIcon = config.Icon;

    return (
        <div className="space-y-4">
            {/* Main Status Card */}
            <Card className={`${config.bgClass} ${config.borderClass} border-2`}>
                <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-4">
                            <StatusIcon className={`h-12 w-12 ${config.iconClass}`} />
                            <div>
                                <h2 className={`text-3xl font-bold ${config.textClass}`}>
                                    {status.status_emoji} {status.status_label}
                                </h2>
                                <p className="text-sm text-re-text-disabled dark:text-re-text-tertiary">
                                    {status.active_alert_count > 0
                                        ? `${status.active_alert_count} active alert${status.active_alert_count > 1 ? 's' : ''}`
                                        : 'No active alerts'
                                    }
                                    {status.critical_alert_count > 0 && (
                                        <span className="text-re-danger font-semibold ml-2">
                                            ({status.critical_alert_count} critical)
                                        </span>
                                    )}
                                </p>
                            </div>
                        </div>

                        {/* Countdown Timer */}
                        {status.countdown_seconds && status.countdown_seconds > 0 && (
                            <div className="text-right">
                                <p className="text-xs text-re-text-muted uppercase tracking-wide mb-1">
                                    Action Required In
                                </p>
                                <CountdownTimer
                                    seconds={status.countdown_seconds}
                                    display={status.countdown_display || ""}
                                />
                                <p className="text-xs text-re-text-muted mt-1 max-w-48 truncate">
                                    {status.next_deadline_description}
                                </p>
                            </div>
                        )}
                    </div>
                </CardContent>
            </Card>

            {/* Active Alerts */}
            {status.active_alerts.length > 0 && (
                <Card>
                    <CardHeader className="pb-3">
                        <CardTitle className="flex items-center gap-2 text-lg">
                            <Bell className="h-5 w-5" />
                            Active Alerts
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        {status.active_alerts.map((alert) => (
                            <AlertCard
                                key={alert.id}
                                alert={alert}
                                onClick={() => onAlertClick?.(alert)}
                            />
                        ))}
                    </CardContent>
                </Card>
            )}

            {/* Compliant State - Show last check */}
            {status.status === "COMPLIANT" && status.active_alerts.length === 0 && (
                <Card className="border-dashed">
                    <CardContent className="p-6 text-center text-re-text-muted">
                        <CheckCircle className="h-8 w-8 mx-auto mb-2 text-re-success" />
                        <p>All compliance requirements met</p>
                        <p className="text-xs mt-1">Last checked: just now</p>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
