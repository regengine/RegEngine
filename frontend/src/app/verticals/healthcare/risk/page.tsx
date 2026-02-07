"use client"

import { useState, useEffect } from "react"
import { useSearchParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { DepartmentRisk, AccessLog, EnterpriseRiskStatus } from "../crm-types"
import { AlertTriangle, ShieldCheck, Users, FileText, Activity, Lock } from "lucide-react"

export default function ClinicalRiskMonitorPage() {
    const searchParams = useSearchParams()
    // In prod, tenantId comes from Auth context or URL
    const tenantId = searchParams.get("tenant") || "40e74bc9-4087-4612-8d94-215347138a68"
    const projectId = "00000000-0000-0000-0000-000000000000"

    const [loading, setLoading] = useState(true)
    const [heatmap, setHeatmap] = useState<DepartmentRisk[]>([])
    const [logs, setLogs] = useState<AccessLog[]>([])
    const [metrics, setMetrics] = useState<EnterpriseRiskStatus | null>(null)
    const [lastUpdated, setLastUpdated] = useState<string>("")

    const fetchData = async () => {
        try {
            const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY || ""
            const headers = { "X-RegEngine-API-Key": apiKey }

            // 1. Get Heatmap
            const heatRes = await fetch(`/api/admin/verticals/healthcare-enterprise/${projectId}/heatmap?tenant_id=${tenantId}`, { headers })
            if (heatRes.ok) setHeatmap(await heatRes.json())

            // 2. Get Logs
            const logRes = await fetch(`/api/admin/verticals/healthcare-enterprise/${projectId}/logs?tenant_id=${tenantId}`, { headers })
            if (logRes.ok) setLogs(await logRes.json())

            // 3. Get Overall Metrics
            const metricRes = await fetch(`/api/admin/verticals/healthcare-enterprise/${projectId}/risk?tenant_id=${tenantId}`, { headers })
            if (metricRes.ok) setMetrics(await metricRes.json())

            setLastUpdated(new Date().toLocaleTimeString())
        } catch (e) {
            console.error("Failed to fetch CRM data", e)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        fetchData()
        // Auto-refresh every 5s for "Live Stream" effect
        const interval = setInterval(fetchData, 5000)
        return () => clearInterval(interval)
    }, [])

    const getRiskColor = (risk: number) => {
        if (risk >= 80) return "bg-red-50 border-red-200 text-red-900"
        if (risk >= 40) return "bg-yellow-50 border-yellow-200 text-yellow-900"
        return "bg-green-50 border-green-200 text-green-900"
    }

    return (
        <div className="min-h-screen bg-slate-100 p-6 font-sans">
            {/* Top Navigation / Breadcrumbs (Mock) */}
            <div className="max-w-7xl mx-auto mb-6 flex justify-between items-center text-sm text-slate-500">
                <div>Healthcare / General Hospital Q1 Audit / <span className="font-bold text-slate-900">Clinical Risk Monitor</span></div>
                <div>{lastUpdated && `Live Stream: ${lastUpdated}`}</div>
            </div>

            <div className="max-w-7xl mx-auto space-y-6">

                {/* Controls Header */}
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-white p-4 rounded-lg shadow-sm border border-slate-200">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900">General Hospital Q1 Audit</h1>
                        <p className="text-slate-500">Real-time heuristic analysis of behavioral anomalies.</p>
                    </div>
                    <div className="flex gap-2">
                        <Button variant="outline"><FileText className="mr-2 h-4 w-4" /> Audit Report</Button>
                        <Button variant="destructive"><Lock className="mr-2 h-4 w-4" /> Lockdown Mode</Button>
                    </div>
                </div>

                {/* Metrics Row */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    <Card>
                        <CardContent className="pt-6 flex items-center justify-between">
                            <div>
                                <p className="text-sm font-medium text-slate-500">Active Staff</p>
                                <h3 className="text-3xl font-bold text-slate-900">{metrics?.monitored_users || 0}</h3>
                            </div>
                            <Users className="h-8 w-8 text-blue-500 opacity-20" />
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="pt-6 flex items-center justify-between">
                            <div>
                                <p className="text-sm font-medium text-slate-500">ePHI Records Open</p>
                                <h3 className="text-3xl font-bold text-slate-900">892</h3>
                            </div>
                            <FileText className="h-8 w-8 text-indigo-500 opacity-20" />
                        </CardContent>
                    </Card>
                    <Card className={metrics?.active_alerts ? "border-red-500 bg-red-50" : ""}>
                        <CardContent className="pt-6 flex items-center justify-between">
                            <div>
                                <p className="text-sm font-medium text-red-600">Breach Attempts (24h)</p>
                                <h3 className="text-3xl font-bold text-red-900">{metrics?.active_alerts || 0}</h3>
                            </div>
                            <AlertTriangle className="h-8 w-8 text-red-600" />
                        </CardContent>
                    </Card>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    {/* Heatmap Section (2 Columns) */}
                    <div className="lg:col-span-2 space-y-4">
                        <h2 className="text-lg font-semibold text-slate-900">Departmental Risk Heatmap</h2>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            {heatmap.map((dept, idx) => (
                                <Card key={idx} className={`border-l-4 shadow-sm ${getRiskColor(dept.risk)}`}>
                                    <CardHeader className="pb-2">
                                        <div className="flex justify-between items-start">
                                            <CardTitle className="text-lg">{dept.dept}</CardTitle>
                                            <span className="text-2xl font-bold">{dept.risk}%</span>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <p className="text-sm font-medium opacity-90">{dept.detail}</p>
                                        {/* Progress Bar Visual */}
                                        <div className="mt-3 h-2 w-full bg-slate-200/50 rounded-full overflow-hidden">
                                            <div
                                                className={`h-full ${dept.risk > 50 ? 'bg-red-500' : dept.risk > 25 ? 'bg-yellow-500' : 'bg-green-500'}`}
                                                style={{ width: `${dept.risk}%` }}
                                            />
                                        </div>
                                    </CardContent>
                                </Card>
                            ))}
                        </div>
                    </div>

                    {/* Live Stream Section (1 Column) */}
                    <div className="space-y-4">
                        <div className="flex justify-between items-center">
                            <h2 className="text-lg font-semibold text-slate-900 flex items-center gap-2">
                                <Activity className="h-4 w-4 text-green-600 animate-pulse" /> Live Access Stream
                            </h2>
                            <Button variant="ghost" size="sm" className="text-xs">View Full Log</Button>
                        </div>

                        <div className="bg-white rounded-lg border border-slate-200 shadow-sm divide-y divide-slate-100 max-h-[500px] overflow-y-auto">
                            {logs.map((log, idx) => (
                                <div key={idx} className="p-4 hover:bg-slate-50 transition-colors">
                                    <div className="flex justify-between items-start mb-1">
                                        <span className="font-mono text-xs text-slate-400">{log.time}</span>
                                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${log.status === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                                                log.status === 'FLAGGED' ? 'bg-yellow-100 text-yellow-700' :
                                                    'bg-slate-100 text-slate-600'
                                            }`}>
                                            {log.status}
                                        </span>
                                    </div>
                                    <div className="font-medium text-sm text-slate-900">{log.user}</div>
                                    <div className="text-xs text-slate-500 mt-1 font-mono">{log.action}</div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

            </div>
        </div>
    )
}
