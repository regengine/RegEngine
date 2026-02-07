"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { AlertCircle, CheckCircle, RefreshCw, Server, Users, FileText, Activity } from "lucide-react"

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { useAuth } from "@/lib/auth-context"

export default function SysAdminDashboard() {
    const { user, accessToken, isHydrated } = useAuth()
    const router = useRouter()
    const [status, setStatus] = useState<any>(null)
    const [metrics, setMetrics] = useState<any>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!user || !user.is_sysadmin) {
            router.push("/login")
        }
    }, [user, router])

    const fetchData = async () => {
        if (!accessToken) return

        setLoading(true)
        setError(null)
        try {
            const headers = {
                "Authorization": `Bearer ${accessToken}`
            }

            // Fetch Status
            const statusRes = await fetch("http://localhost:8400/v1/system/status", { headers })
            if (!statusRes.ok) throw new Error("Failed to fetch system status")
            const statusData = await statusRes.json()
            setStatus(statusData)

            // Fetch Metrics
            const metricsRes = await fetch("http://localhost:8400/v1/system/metrics", { headers })
            if (!metricsRes.ok) throw new Error("Failed to fetch system metrics")
            const metricsData = await metricsRes.json()
            setMetrics(metricsData)

        } catch (err: any) {
            setError(err.message)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        if (user && user.is_sysadmin && accessToken) {
            fetchData()
        }
    }, [user, accessToken])

    if (!user || !user.is_sysadmin) {
        return null // Redirecting
    }

    return (
        <div className="container mx-auto py-10 space-y-8">
            <div className="flex justify-between items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">System Administration</h1>
                    <p className="text-muted-foreground">Real-time system health and operational metrics</p>
                </div>
                <Button onClick={fetchData} disabled={loading}>
                    <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    Refresh
                </Button>
            </div>

            {error && (
                <div className="bg-destructive/15 text-destructive px-4 py-3 rounded-md flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    <div>
                        <p className="font-semibold">Error</p>
                        <p>{error}</p>
                    </div>
                </div>
            )}

            {/* Overview Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Overall Health</CardTitle>
                        <Activity className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold capitalize">
                            {status?.overall_status || "Unknown"}
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {status?.services.filter((s: any) => s.status === 'healthy').length || 0} / {status?.services.length || 0} services healthy
                        </p>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Active Tenants</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{metrics?.total_tenants || "-"}</div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Documents</CardTitle>
                        <FileText className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{metrics?.total_documents || "-"}</div>
                    </CardContent>
                </Card>

                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Active Jobs</CardTitle>
                        <Server className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{metrics?.active_jobs || "-"}</div>
                    </CardContent>
                </Card>
            </div>

            {/* Service Health Table */}
            <Card>
                <CardHeader>
                    <CardTitle>Service Status</CardTitle>
                    <CardDescription>
                        Detailed health check results from internal services.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="rounded-md border">
                        <div className="grid grid-cols-3 p-4 font-medium border-b bg-muted/50">
                            <div>Service Name</div>
                            <div>Status</div>
                            <div>Details</div>
                        </div>
                        {status?.services.map((service: any) => (
                            <div key={service.name} className="grid grid-cols-3 p-4 border-b last:border-0 items-center">
                                <div className="font-semibold capitalize">{service.name}</div>
                                <div className="flex items-center">
                                    {service.status === "healthy" ? (
                                        <span className="flex items-center text-green-600">
                                            <CheckCircle className="mr-2 h-4 w-4" /> Healthy
                                        </span>
                                    ) : (
                                        <span className="flex items-center text-red-600">
                                            <AlertCircle className="mr-2 h-4 w-4" /> {service.status}
                                        </span>
                                    )}
                                </div>
                                <div className="text-sm text-muted-foreground truncate" title={JSON.stringify(service.details)}>
                                    {JSON.stringify(service.details)}
                                </div>
                            </div>
                        ))}
                        {!status && !loading && <div className="p-4 text-center">No service data available</div>}
                    </div>
                </CardContent>
            </Card>
        </div>
    )
}
