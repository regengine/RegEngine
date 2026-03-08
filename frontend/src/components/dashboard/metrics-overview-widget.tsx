import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSystemMetrics } from "@/hooks/use-api";
import { Skeleton } from "@/components/ui/skeleton";
import { Shield, FileCheck, Link2, AlertTriangle } from "lucide-react";

export function MetricsOverviewWidget() {
    const { data: metrics, isLoading, error } = useSystemMetrics();

    if (isLoading) {
        return (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {[...Array(4)].map((_, i) => (
                    <Card key={i}>
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <Skeleton className="h-4 w-[100px]" />
                            <Skeleton className="h-4 w-4 rounded-full" />
                        </CardHeader>
                        <CardContent>
                            <Skeleton className="h-8 w-[60px] mb-1" />
                            <Skeleton className="h-3 w-[80px]" />
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
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Compliance Score</CardTitle>
                    <Shield className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <span className={`text-2xl font-bold ${gradeColor}`}>
                            {score > 0 ? `${score}%` : '—'}
                        </span>
                        {grade !== '—' && (
                            <span className={`text-lg font-semibold ${gradeColor}`}>
                                ({grade})
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-muted-foreground">FSMA 204 readiness</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">CTE Events</CardTitle>
                    <FileCheck className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">
                        {events > 0 ? events.toLocaleString() : '—'}
                    </div>
                    <p className="text-xs text-muted-foreground">Traceability events tracked</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Hash Chain</CardTitle>
                    <Link2 className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-bold">
                            {chainLen > 0 ? chainLen : '—'}
                        </span>
                        {chainLen > 0 && (
                            <span className={`text-xs font-medium ${chainOk ? 'text-emerald-600' : 'text-red-600'}`}>
                                {chainOk ? '✓ Valid' : '✗ Broken'}
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-muted-foreground">Tamper-evident ledger entries</p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Open Alerts</CardTitle>
                    <AlertTriangle className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{alerts}</div>
                    <p className="text-xs text-muted-foreground">Compliance issues to resolve</p>
                </CardContent>
            </Card>
        </div>
    );
}
