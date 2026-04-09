import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, CheckCircle, AlertTriangle, XCircle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { POLL_HEALTH_MS } from "@/lib/polling-config";
import { Skeleton } from "@/components/ui/skeleton";

interface ServiceCheck {
    name: string;
    status: 'healthy' | 'unhealthy' | 'unreachable' | 'not_configured';
    code?: number;
    latencyMs?: number;
}

interface HealthResponse {
    status: 'healthy' | 'degraded';
    services: ServiceCheck[];
    summary: { healthy: number; total: number };
}

/** Fetch from /api/health — unauthenticated, server-side health checks */
function useHealthCheck() {
    return useQuery<HealthResponse>({
        queryKey: ['health-check'],
        queryFn: async () => {
            const res = await fetch('/api/health');
            if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
            return res.json();
        },
        refetchInterval: POLL_HEALTH_MS,
        retry: 1,
    });
}

interface ServiceStatusProps {
    name: string;
    status: 'healthy' | 'unhealthy' | 'degraded' | 'unreachable' | 'not_configured';
    details?: Record<string, unknown>;
}

const ServiceStatus = ({ name, status, details }: ServiceStatusProps) => {
    const getIcon = () => {
        switch (status) {
            case 'healthy':
                return <CheckCircle className="h-5 w-5 text-green-500" />;
            case 'degraded':
                return <AlertTriangle className="h-5 w-5 text-yellow-500" />;
            case 'unhealthy':
            case 'unreachable':
                return <XCircle className="h-5 w-5 text-red-500" />;
            case 'not_configured':
                return <Activity className="h-5 w-5 text-muted-foreground" />;
            default:
                return <Activity className="h-5 w-5 text-muted-foreground" />;
        }
    };

    const getBadgeVariant = () => {
        switch (status) {
            case 'healthy':
                return 'default';
            case 'degraded':
                return 'secondary';
            case 'unhealthy':
            case 'unreachable':
                return 'destructive';
            default:
                return 'outline';
        }
    };

    return (
        <div className="flex items-center justify-between p-3 border rounded-lg bg-card/50 min-h-[48px] gap-2">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
                <div className="flex-shrink-0">{getIcon()}</div>
                <div className="min-w-0">
                    <p className="font-medium capitalize text-sm sm:text-base truncate">{name}</p>
                    {status !== 'healthy' && details?.error != null && (
                        <p className="text-[11px] sm:text-xs text-muted-foreground truncate">
                            {String(details.error)}
                        </p>
                    )}
                </div>
            </div>
            <Badge variant={getBadgeVariant()} className="capitalize flex-shrink-0 text-[11px] sm:text-xs">
                {status}
            </Badge>
        </div>
    );
};

export function SystemHealthWidget() {
    const { data: health, isLoading, error } = useHealthCheck();

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-sm font-medium">System Health</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                    <Skeleton className="h-12 w-full" />
                </CardContent>
            </Card>
        );
    }

    if (error && !health) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle className="text-sm font-medium">System Health</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="flex items-center gap-2 p-3 text-red-600 bg-red-50 dark:bg-red-900/10 rounded-lg">
                        <XCircle className="h-5 w-5" />
                        <span className="text-sm">Failed to load system status</span>
                    </div>
                </CardContent>
            </Card>
        );
    }

    const services = health?.services || [];
    const overallStatus = health?.status || 'unknown';

    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">System Health</CardTitle>
                <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${overallStatus === 'healthy' ? 'bg-green-500' :
                        overallStatus === 'degraded' ? 'bg-yellow-500' : 'bg-red-500'
                        }`} />
                    <span className="text-xs text-muted-foreground capitalize">{overallStatus}</span>
                </div>
            </CardHeader>
            <CardContent className="space-y-3 pt-4">
                {services.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No services monitored.</p>
                ) : (
                    services.map((service) => (
                        <ServiceStatus
                            key={service.name}
                            name={service.name}
                            status={service.status}
                        />
                    ))
                )}
            </CardContent>
        </Card>
    );
}
