"use client"

import { useState, useEffect } from "react"
import { useSearchParams } from "next/navigation"
import { PillarCard } from "@/components/verticals/healthcare/pillar-card"
import { Button } from "@/components/ui/button"
import { WifiOff, RefreshCw, Download } from "lucide-react"
import { ComplianceReportButton } from "@/components/verticals"

type Status = "green" | "yellow" | "red" | "gray"

interface Pillar {
    title: string
    status: Status
    controls: { id: string; name: string; status: Status }[]
}

export default function HealthcareDashboardPage() {
    const searchParams = useSearchParams()
    // Simulate fetching data based on query params (passed from setup wizard)
    const dispensesMeds = searchParams.get("meds") === "true" || localStorage.getItem("mscf_meds") === "true"

    // Offline / Data State
    const [pillars, setPillars] = useState<Pillar[]>([])
    const [overallStatus, setOverallStatus] = useState<Status>("gray")
    const [isOffline, setIsOffline] = useState(false)
    const [lastSynced, setLastSynced] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    const CACHE_KEY = "mscf_dashboard_data"

    // Simulate API Fetch with Caching Strategy
    // REMEDIATION: Using memory state only (Constitution: No Local PII)
    const loadData = async () => {
        setLoading(true)
        try {
            // REAL NETWORK CALL
            // const tenantId = searchParams.get("tenant") || "mock-tenant"

            // Build query params based on local state mock
            const params = new URLSearchParams({
                dispenses_medication: dispensesMeds.toString(),
                state: "CA", // Default for demo
                facility_type: "free_clinic" // Default for demo
            })

            const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY || ""

            const res = await fetch(`/api/admin/verticals/healthcare/status?${params.toString()}`, {
                headers: {
                    "X-RegEngine-API-Key": apiKey
                }
            })

            if (!res.ok) throw new Error("Failed to fetch status")

            const data = await res.json()

            // Update State
            setPillars(data.pillars)
            setOverallStatus(data.overall)
            setLastSynced(new Date().toLocaleTimeString())
            setIsOffline(false)

        } catch (error) {
            console.log("⚠️ Network failed / Auth Failed")
            // REMEDIATION: Do NOT fall back to localStorage PII
            setPillars([])
            setOverallStatus("gray")
            setLastSynced(null)
            setIsOffline(true)
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        loadData()
    }, [dispensesMeds])

    const handleDownloadLifeboat = async () => {
        const projectId = "00000000-0000-0000-0000-000000000000" // Mock project ID
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY || ""

        try {
            const res = await fetch(
                `/api/admin/verticals/healthcare/export/lifeboat?project_id=${projectId}`,
                { headers: { "X-RegEngine-API-Key": apiKey } }
            )

            if (!res.ok) throw new Error(`HTTP ${res.status}`)

            const blob = await res.blob()
            const url = window.URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = `lifeboat_${projectId}.zip`
            document.body.appendChild(a)
            a.click()
            window.URL.revokeObjectURL(url)
        } catch (error) {
            alert(`❌ Failed to export lifeboat: ${error}`)
        }
    }

    const handleExportEvidence = async () => {
        const projectId = "00000000-0000-0000-0000-000000000000"; // Mock project ID
        const apiKey = process.env.NEXT_PUBLIC_ADMIN_API_KEY || "";

        try {
            const res = await fetch(
                `/api/admin/verticals/healthcare/export/evidence?project_id=${projectId}`,
                { headers: { "X-RegEngine-API-Key": apiKey } }
            );

            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }

            const blob = await res.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `evidence_export_${projectId}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);

            alert(`✅ Evidence bundle exported successfully!`);
        } catch (error) {
            alert(`❌ Failed to export evidence: ${error}`);
        }
    }

    return (
        <div className="min-h-screen bg-slate-50 p-8">
            <div className="max-w-6xl mx-auto space-y-8">

                {/* Header Section */}
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div>
                        <div className="flex items-center gap-3">
                            <h1 className="text-3xl font-bold text-slate-900">Clinic Safety Dashboard</h1>
                            {isOffline && (
                                <span className="bg-slate-200 text-slate-700 text-xs px-2 py-1 rounded inline-flex items-center gap-1">
                                    <WifiOff className="h-3 w-3" /> Offline / Auth Error
                                </span>
                            )}
                        </div>
                        <p className="text-slate-500">
                            {loading ? "Syncing..." : `Last synced: ${lastSynced || 'Never'}`}
                        </p>
                    </div>

                    <div className={`px-6 py-4 rounded-lg flex items-center space-x-3 border transition-colors ${overallStatus === "green" ? "bg-green-100 border-green-200" :
                        overallStatus === "red" ? "bg-red-100 border-red-200" :
                            overallStatus === "yellow" ? "bg-yellow-100 border-yellow-200" :
                                "bg-gray-100 border-gray-200"
                        }`}>
                        <div className="text-right">
                            <p className="text-xs uppercase font-semibold tracking-wider text-slate-600">Current Status</p>
                            <h2 className={`text-2xl font-bold ${overallStatus === "green" ? "text-green-800" :
                                overallStatus === "red" ? "text-red-800" :
                                    overallStatus === "yellow" ? "text-yellow-800" :
                                        "text-gray-800"
                                }`}>
                                {overallStatus === "green" ? "SAFE TO OPERATE" :
                                    overallStatus === "red" ? "UNSAFE TO OPERATE" :
                                        overallStatus === "yellow" ? "ATTENTION REQUIRED" : "LOADING..."}
                            </h2>
                        </div>
                    </div>
                </div>

                {/* Main Grid */}
                {loading ? (
                    <div className="text-center py-20 text-slate-500">
                        <RefreshCw className="h-8 w-8 animate-spin mx-auto mb-4 text-slate-400" />
                        Loading safety data...
                    </div>
                ) : pillars.length === 0 ? (
                    <div className="text-center py-16">
                        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-100 mb-4">
                            <WifiOff className="h-8 w-8 text-slate-400" />
                        </div>
                        <h3 className="text-lg font-semibold text-slate-700 mb-2">
                            {isOffline ? "Connection Issue" : "No Data Available"}
                        </h3>
                        <p className="text-slate-500 max-w-md mx-auto mb-6">
                            {isOffline
                                ? "Unable to reach the compliance API. Check your network connection or API key, then try again."
                                : "No compliance pillars configured. Complete the setup wizard to get started."}
                        </p>
                        <div className="flex items-center justify-center gap-3">
                            <Button onClick={loadData} variant="outline">
                                <RefreshCw className="mr-2 h-4 w-4" /> Retry
                            </Button>
                            {!isOffline && (
                                <Button onClick={() => window.location.href = '/verticals/healthcare/setup'} variant="outline">
                                    Open Setup Wizard
                                </Button>
                            )}
                        </div>
                    </div>
                ) : (
                    <div className={"grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 " + (isOffline ? "opacity-75 grayscale-[0.2]" : "")}>
                        {pillars.map((pillar, idx) => (
                            <PillarCard
                                key={idx}
                                title={pillar.title}
                                status={pillar.status}
                                controls={pillar.controls}
                            />
                        ))}
                    </div>
                )}

                {/* Action Footer */}
                <div className="flex justify-end pt-8 gap-4">
                    <Button
                        variant="outline"
                        onClick={handleDownloadLifeboat}
                    >
                        <Download className="mr-2 h-4 w-4" /> Download Lifeboat Archive
                    </Button>
                    <Button
                        variant="outline"
                        onClick={handleExportEvidence}
                    >
                        <Download className="mr-2 h-4 w-4" /> Export Evidence Bundle
                    </Button>
                    <ComplianceReportButton
                        dashboardTitle="HIPAA/MSCF Compliance Report"
                        vertical="Healthcare"
                        reportData={{
                            summary: 'Healthcare compliance covering HIPAA privacy safeguards, MSCF framework pillars, medication safety controls, and evidence vault integrity.',
                            metrics: pillars.flatMap(p => p.controls.map(c => ({ label: `${p.title}: ${c.name}`, value: c.status === 'green' ? 'Compliant' : c.status === 'yellow' ? 'Needs Review' : 'Non-Compliant', status: (c.status === 'green' ? 'pass' : c.status === 'yellow' ? 'warning' : 'fail') as 'pass' | 'warning' | 'fail' }))),
                        }}
                        className=""
                    />
                </div>
            </div>
        </div>
    )
}
