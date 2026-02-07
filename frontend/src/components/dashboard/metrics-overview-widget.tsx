import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSystemMetrics } from "@/hooks/use-api";
import { Skeleton } from "@/components/ui/skeleton";
import { Users, FileText, Zap, Activity } from "lucide-react";

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

    // Fallback to zeros if error or no data
    const data = metrics || {
        total_tenants: 0,
        total_documents: 0,
        active_jobs: 0,
    };

    return (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Total Tenants</CardTitle>
                    <Users className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{data.total_tenants}</div>
                    <p className="text-xs text-muted-foreground">
                        Active organizations
                    </p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Documents indexed</CardTitle>
                    <FileText className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{data.total_documents}</div>
                    <p className="text-xs text-muted-foreground">
                        Across all jurisdictions
                    </p>
                </CardContent>
            </Card>

            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                    <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
                    <Zap className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                    <div className="text-2xl font-bold">{data.active_jobs}</div>
                    <p className="text-xs text-muted-foreground">
                        Running background tasks
                    </p>
                </CardContent>
            </Card>
        </div>
    );
}
