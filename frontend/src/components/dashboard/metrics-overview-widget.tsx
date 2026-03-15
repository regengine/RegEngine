import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSystemMetrics } from "@/hooks/use-api";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, FileCheck, Link2, AlertTriangle } from "lucide-react";

export function MetricsOverviewWidget() {
    const { data: metrics, isLoading, error } = useSystemMetrics();

    if (isLoading) {
        return (
            <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
                {[...Array(4)].map((_, i) => (
                    <Card key={i}>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 p-3 sm:p-6 sm:pb-2">
                            <Skeleton className="h-4 w-[80px] sm:w-[100px]" />
                            <Skeleton className="h-4 w-4 rounded-full" />
                        </CardHeader>
                        <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
                            <Skeleton className="h-7 sm:h-8 w-[50px] sm:w-[60px] mb-1" />
                            <Skeleton className="h-3 w-[70px] sm:w-[80px]" />
                        </CardContent>
                    </Card>
                ))}
            </div>
        );
    }

    const score = metrics?.compliance_score ?? 0;
    const grade = metrics?.compliance_grade ?? '—';
    const events = metrics?.events_ingested ?? 0;
    const chainLen = metrics?.chain_length ?? 0;
    const chainOk = metrics?.chain_valid ?? false;
    const alerts = metrics?.open_alerts ?? 0;

    // Color grade badge
    const gradeColor = score >= 90
        ? 'text-emerald-600'
        : score >= 70
            ? 'text-amber-600'
            : 'text-red-600';

    return (
        <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1 sm:pb-2 p-3 sm:p-6 sm:pb-2">
                    <CardTitle className="text-xs sm:text-sm font-medium">Compliance Score</CardTitle>
                    <Shield className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-muted-foreground flex-shrink-0" />
                </CardHeader>
                <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
                    <div className="flex items-baseline gap-1 sm:gap-2 flex-wrap">
                        <span className={`text-xl sm:text-2xl font-bold ${gradeColor}`}>
                            {score > 0 ? `${score}%` : '—'}
                        </span>
                        {grade !== '—' && (
                            <span className={`text-sm sm:text-lg font-semibold ${gradeColor}`}>
                                ({grade})
                            </span>
                        )}
                    </div>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">FSMA 204 readiness</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1 sm:pb-2 p-3 sm:p-6 sm:pb-2">
                    <CardTitle className="text-xs sm:text-sm font-medium">CTE Events</CardTitle>
                    <FileCheck className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-muted-foreground flex-shrink-0" />
                </CardHeader>
                <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
                    <div className="text-xl sm:text-2xl font-bold truncate">
                        {events > 0 ? events.toLocaleString() : '—'}
                    </div>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">Traceability events tracked</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1 sm:pb-2 p-3 sm:p-6 sm:pb-2">
                    <CardTitle className="text-xs sm:text-sm font-medium">Hash Chain</CardTitle>
                    <Link2 className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-muted-foreground flex-shrink-0" />
                </CardHeader>
                <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
                    <div className="flex items-baseline gap-1 sm:gap-2 flex-wrap">
                        <span className="text-xl sm:text-2xl font-bold">
                            {chainLen > 0 ? chainLen : '—'}
                        </span>
                        {chainLen > 0 && (
                            <span className={`text-[10px] sm:text-xs font-medium ${chainOk ? 'text-emerald-600' : 'text-red-600'}`}>
                                {chainOk ? '✓ Valid' : '✗ Broken'}
                            </span>
                        )}
                    </div>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">Tamper-evident ledger entries</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1 sm:pb-2 p-3 sm:p-6 sm:pb-2">
                    <CardTitle className="text-xs sm:text-sm font-medium">Open Alerts</CardTitle>
                    <AlertTriangle className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-muted-foreground flex-shrink-0" />
                </CardHeader>
                <CardContent className="p-3 pt-0 sm:p-6 sm:pt-0">
                    <div className="text-xl sm:text-2xl font-bold">{alerts}</div>
                    <p className="text-[11px] sm:text-xs text-muted-foreground">Compliance issues to resolve</p>
                </CardContent>
            </Card>
        </div>
    );
}
