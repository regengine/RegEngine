"use client"

import { useState, useEffect, useCallback } from "react"
import { useRouter } from "next/navigation"
import { RefreshCw } from "lucide-react"

import { PageContainer } from "@/components/layout/page-container"
import { PageHeader } from "@/components/layout/page-header"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Callout } from "@/components/ui/callout"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { StatTile } from "@/components/ui/stat-tile"
import { StatusBadge } from "@/components/ui/status-badge"
import { useAuth } from "@/lib/auth-context"
import { getServiceURL } from "@/lib/api-config"

interface ServiceInfo {
    name: string;
    status: string;
    details?: Record<string, unknown>;
}

interface SystemStatus {
    overall_status: string;
    services: ServiceInfo[];
}

interface SystemMetrics {
    total_tenants: number;
    total_documents: number;
    active_jobs: number;
}

const SERVICE_COLUMNS: DataTableColumn<ServiceInfo>[] = [
    {
        key: "name",
        header: "Service Name",
        width: "14rem",
        cell: (service) => <span className="capitalize">{service.name}</span>,
    },
    {
        key: "status",
        header: "Status",
        width: "12rem",
        cell: (service) =>
            service.status === "healthy" ? (
                <StatusBadge state="compliant" label="Healthy" size="sm" />
            ) : (
                <StatusBadge state="non-compliant" label={service.status} size="sm" />
            ),
    },
    {
        key: "details",
        header: "Details",
        mono: true,
        cell: (service) => (
            <span className="block truncate" title={JSON.stringify(service.details)}>
                {JSON.stringify(service.details)}
            </span>
        ),
    },
];

export default function SysAdminDashboard() {
    const { user, accessToken, isHydrated } = useAuth()
    const router = useRouter()
    const [status, setStatus] = useState<SystemStatus | null>(null)
    const [metrics, setMetrics] = useState<SystemMetrics | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!user || !user.is_sysadmin) {
            router.push("/login")
        }
    }, [user, router])

    const fetchData = useCallback(async () => {
        if (!accessToken) return

        setLoading(true)
        setError(null)
        try {
            // Same-origin admin proxy call: the proxy injects the real
            // credential from HTTP-only cookies server-side. No explicit
            // Authorization header here — accessToken is routinely the
            // "cookie-managed" placeholder, which must never be sent.
            const adminBase = getServiceURL('admin')

            // Fetch Status
            const statusRes = await fetch(`${adminBase}/v1/system/status`)
            if (!statusRes.ok) throw new Error("Failed to fetch system status")
            const statusData = await statusRes.json()
            setStatus(statusData)

            // Fetch Metrics
            const metricsRes = await fetch(`${adminBase}/v1/system/metrics`)
            if (!metricsRes.ok) throw new Error("Failed to fetch system metrics")
            const metricsData = await metricsRes.json()
            setMetrics(metricsData)

        } catch (err: unknown) {
            setError(err instanceof Error ? err.message : 'An unknown error occurred')
        } finally {
            setLoading(false)
        }
    }, [accessToken])

    useEffect(() => {
        if (user && user.is_sysadmin && accessToken) {
            fetchData()
        }
    }, [user, accessToken, fetchData])

    if (!user || !user.is_sysadmin) {
        return null // Redirecting
    }

    const healthyCount = status?.services.filter((s: ServiceInfo) => s.status === 'healthy').length || 0
    const serviceCount = status?.services.length || 0

    return (
        <PageContainer>
            {/* The dashboard shell owns the breadcrumb, the service-health badge
                and the Dashboard / Sign Out links — this page only keeps its own
                Refresh action. */}
            <PageHeader
                title="System Administration"
                description="Real-time system health and operational metrics"
                primaryAction={
                    <Button
                        onClick={fetchData}
                        disabled={loading}
                        leadingIcon={
                            <RefreshCw
                                className={loading ? "animate-spin motion-reduce:animate-none" : undefined}
                                strokeWidth={1.75}
                                aria-hidden="true"
                            />
                        }
                    >
                        Refresh
                    </Button>
                }
            />

            <div className="space-y-6">
                {error && (
                    <Callout tone="danger" role="alert" title="Error">
                        {error}
                    </Callout>
                )}

                {/* Overview Cards */}
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                    <StatTile
                        label="Overall Health"
                        value={<span className="capitalize">{status?.overall_status || "Unknown"}</span>}
                    >
                        <p className="text-small text-re-text-tertiary">
                            {healthyCount} / {serviceCount} services healthy
                        </p>
                    </StatTile>
                    <StatTile label="Active Tenants" value={metrics?.total_tenants || "-"} />
                    <StatTile label="Total Documents" value={metrics?.total_documents || "-"} />
                    <StatTile label="Active Jobs" value={metrics?.active_jobs || "-"} />
                </div>

                {/* Service Health Table */}
                <Card>
                    <CardHeader>
                        <div className="min-w-0">
                            <CardTitle>Service Status</CardTitle>
                            <CardDescription>
                                Detailed health check results from internal services.
                            </CardDescription>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">
                        <DataTable
                            caption="Detailed health check results from internal services"
                            columns={SERVICE_COLUMNS}
                            data={status?.services ?? []}
                            rowKey={(service) => service.name}
                            status={loading && !status ? 'loading' : 'idle'}
                            empty={{ title: 'No service data available' }}
                            minWidth="560px"
                            stickyFirstColumn
                            className="rounded-none border-0"
                        />
                    </CardContent>
                </Card>
            </div>
        </PageContainer>
    )
}
