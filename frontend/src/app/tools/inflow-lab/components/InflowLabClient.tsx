"use client";

import { useEffect, useMemo, useState } from "react";
import {
    AlertTriangle,
    ArrowDownToLine,
    CalendarDays,
    CheckCircle2,
    ClipboardList,
    Database,
    FileJson,
    FileSpreadsheet,
    GitBranch,
    Info,
    PackageCheck,
    Play,
    RefreshCcw,
    RotateCcw,
    Search,
    SlidersHorizontal,
    Truck,
    Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

type RunStage = "loaded" | "generating" | "delivering" | "validating" | "complete" | "exported";
type EventStatus = "posted" | "validated" | "queued";
type CteState = "complete" | "missing";

type TraceEvent = {
    id: number;
    cte: string;
    lotCode: string;
    product: string;
    location: string;
    timestamp: string;
    mode: "simulation";
    attempts: number;
};

type LineageNode = {
    cte: string;
    location: string;
    time: string;
    state: CteState;
};

const tabs = ["Control room", "Lots", "Lineage", "Exports", "Event log", "Diagnostics"];

const lotCodes = [
    "00614141000012-20260426-000001",
    "00614141000012-20260426-000002",
    "00614141000012-20260426-000003",
];

const events: TraceEvent[] = [
    {
        id: 15,
        cte: "receiving",
        lotCode: lotCodes[0],
        product: "Green Leaf Lettuce",
        location: "Bay Area DC",
        timestamp: "Apr 27, 2026, 2:04 AM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 14,
        cte: "shipping",
        lotCode: lotCodes[0],
        product: "Green Leaf Lettuce",
        location: "Salinas Packout Dock",
        timestamp: "Apr 26, 2026, 10:41 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 13,
        cte: "initial_packing",
        lotCode: lotCodes[0],
        product: "Green Leaf Lettuce",
        location: "Salinas Packhouse",
        timestamp: "Apr 26, 2026, 8:12 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 12,
        cte: "cooling",
        lotCode: lotCodes[0],
        product: "Green Leaf Lettuce",
        location: "Salinas Cooling Hub",
        timestamp: "Apr 26, 2026, 6:12 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 11,
        cte: "harvesting",
        lotCode: lotCodes[0],
        product: "Green Leaf Lettuce",
        location: "Valley Fresh Farms",
        timestamp: "Apr 26, 2026, 3:20 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 10,
        cte: "receiving",
        lotCode: lotCodes[1],
        product: "Spring Mix",
        location: "Los Angeles DC",
        timestamp: "Apr 27, 2026, 1:24 AM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 9,
        cte: "shipping",
        lotCode: lotCodes[1],
        product: "Spring Mix",
        location: "Imperial Packout Dock",
        timestamp: "Apr 26, 2026, 10:03 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 8,
        cte: "initial_packing",
        lotCode: lotCodes[1],
        product: "Spring Mix",
        location: "Imperial Packhouse",
        timestamp: "Apr 26, 2026, 7:18 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 7,
        cte: "cooling",
        lotCode: lotCodes[1],
        product: "Spring Mix",
        location: "Imperial Pre-Cool Facility",
        timestamp: "Apr 26, 2026, 4:51 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 6,
        cte: "harvesting",
        lotCode: lotCodes[1],
        product: "Spring Mix",
        location: "Desert Bloom Farm",
        timestamp: "Apr 26, 2026, 3:43 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 5,
        cte: "cooling",
        lotCode: lotCodes[2],
        product: "Green Leaf Lettuce",
        location: "Salinas Cooling Hub",
        timestamp: "Apr 26, 2026, 5:26 PM",
        mode: "simulation",
        attempts: 1,
    },
    {
        id: 4,
        cte: "harvesting",
        lotCode: lotCodes[2],
        product: "Green Leaf Lettuce",
        location: "Valley Fresh Farms",
        timestamp: "Apr 26, 2026, 4:28 PM",
        mode: "simulation",
        attempts: 1,
    },
];

const lineageByLot: Record<string, LineageNode[]> = {
    [lotCodes[0]]: [
        { cte: "Harvesting", location: "Valley Fresh Farms", time: "Apr 26, 3:20 PM", state: "complete" },
        { cte: "Cooling", location: "Salinas Cooling Hub", time: "Apr 26, 6:12 PM", state: "complete" },
        { cte: "Initial packing", location: "Salinas Packhouse", time: "Apr 26, 8:12 PM", state: "complete" },
        { cte: "Shipping", location: "Salinas Packout Dock", time: "Apr 26, 10:41 PM", state: "complete" },
        { cte: "DC receiving", location: "Bay Area DC", time: "Apr 27, 2:04 AM", state: "complete" },
    ],
    [lotCodes[1]]: [
        { cte: "Harvesting", location: "Desert Bloom Farm", time: "Apr 26, 3:43 PM", state: "complete" },
        { cte: "Cooling", location: "Imperial Pre-Cool Facility", time: "Apr 26, 4:51 PM", state: "complete" },
        { cte: "Initial packing", location: "Imperial Packhouse", time: "Apr 26, 7:18 PM", state: "complete" },
        { cte: "Shipping", location: "Imperial Packout Dock", time: "Apr 26, 10:03 PM", state: "complete" },
        { cte: "DC receiving", location: "Los Angeles DC", time: "Apr 27, 1:24 AM", state: "complete" },
    ],
    [lotCodes[2]]: [
        { cte: "Harvesting", location: "Valley Fresh Farms", time: "Apr 26, 4:28 PM", state: "complete" },
        { cte: "Cooling", location: "Salinas Cooling Hub", time: "Apr 26, 5:26 PM", state: "complete" },
        { cte: "Initial packing", location: "Not captured", time: "Missing KDEs", state: "missing" },
        { cte: "Shipping", location: "Not captured", time: "Missing CTE", state: "missing" },
        { cte: "DC receiving", location: "Not captured", time: "Missing CTE", state: "missing" },
    ],
};

const stageIndex: Record<RunStage, number> = {
    loaded: 0,
    generating: 1,
    delivering: 2,
    validating: 3,
    complete: 4,
    exported: 5,
};

function getEventStatus(stage: RunStage): EventStatus {
    if (stage === "generating") return "queued";
    if (stage === "validating") return "validated";
    return "posted";
}

function StatusPill({ status }: { status: EventStatus }) {
    const styles = {
        posted: "border-emerald-200 bg-emerald-50 text-emerald-700",
        validated: "border-blue-200 bg-blue-50 text-blue-700",
        queued: "border-amber-200 bg-amber-50 text-amber-700",
    };

    return (
        <span className={cn("inline-flex rounded-full border px-2 py-0.5 text-xs font-medium", styles[status])}>
            {status}
        </span>
    );
}

function LotReadinessPill({ ready }: { ready: boolean }) {
    return (
        <span
            className={cn(
                "inline-flex rounded-full border px-2 py-0.5 text-xs font-medium",
                ready
                    ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                    : "border-amber-200 bg-amber-50 text-amber-700"
            )}
        >
            {ready ? "export ready" : "partial"}
        </span>
    );
}

function LineageStatusIcon({ state }: { state: CteState }) {
    if (state === "complete") return <CheckCircle2 className="h-4 w-4" />;
    return <AlertTriangle className="h-4 w-4" />;
}

export function InflowLabClient() {
    const [activeTab, setActiveTab] = useState("Control room");
    const [selectedLot, setSelectedLot] = useState(lotCodes[0]);
    const [traceInput, setTraceInput] = useState(lotCodes[0]);
    const [runStage, setRunStage] = useState<RunStage>("complete");
    const [tenantId, setTenantId] = useState("local-demo");
    const [scenarioPreset, setScenarioPreset] = useState("leafy-greens");
    const [fixture, setFixture] = useState("leafy-greens-trace");
    const [deliveryMode, setDeliveryMode] = useState("mock");
    const [source, setSource] = useState("codex-simulator");
    const [exportPreset, setExportPreset] = useState("all-records");
    const [startDate, setStartDate] = useState("2026-04-26");
    const [endDate, setEndDate] = useState("2026-04-27");

    const selectedEvents = useMemo(
        () => events.filter((event) => event.lotCode === selectedLot),
        [selectedLot]
    );

    const selectedLineage = lineageByLot[selectedLot] ?? [];
    const selectedCompleteCount = selectedLineage.filter((node) => node.state === "complete").length;
    const selectedIsExportReady = selectedCompleteCount === selectedLineage.length;
    const hasGeneratedRecords = runStage !== "loaded";
    const visibleEvents = hasGeneratedRecords ? events : [];
    const visibleEventStatus = getEventStatus(runStage);
    const deliveredCount = stageIndex[runStage] >= 2 ? events.length : 0;
    const completeLots = lotCodes.filter((lotCode) => {
        const lineage = lineageByLot[lotCode] ?? [];
        return lineage.length > 0 && lineage.every((node) => node.state === "complete");
    }).length;

    useEffect(() => {
        document.body.dataset.inflowLab = "true";
        return () => {
            delete document.body.dataset.inflowLab;
        };
    }, []);

    const runStatusLabel =
        runStage === "exported"
            ? "FDA package prepared"
            : runStage === "complete"
                ? "Demo run complete"
                : runStage === "loaded"
                    ? "Demo scenario loaded"
                    : "Demo run in progress";

    const uniqueLots = useMemo(
        () =>
            lotCodes.map((lotCode) => {
                const lotEvents = events.filter((event) => event.lotCode === lotCode);
                const lineage = lineageByLot[lotCode] ?? [];
                const product = lotEvents[0]?.product ?? "Unknown product";
                const completeCount = lineage.filter((node) => node.state === "complete").length;
                const complete = completeCount === lineage.length;
                return {
                    lotCode,
                    product,
                    events: lotEvents.length,
                    complete,
                    completeCount,
                    totalCount: lineage.length,
                    lastLocation: lotEvents[0]?.location ?? "No location",
                };
            }),
        []
    );

    const loadScenario = () => {
        setRunStage("loaded");
        setSelectedLot(lotCodes[0]);
        setTraceInput(lotCodes[0]);
        setActiveTab("Control room");
    };

    const runPipeline = () => {
        setRunStage("generating");
        setActiveTab("Control room");
        window.setTimeout(() => setRunStage("delivering"), 450);
        window.setTimeout(() => setRunStage("validating"), 900);
        window.setTimeout(() => setRunStage("complete"), 1350);
    };

    const traceLot = () => {
        if (lotCodes.includes(traceInput)) {
            setSelectedLot(traceInput);
            setActiveTab("Lineage");
        }
    };

    const traceLatestLot = () => {
        setSelectedLot(lotCodes[0]);
        setTraceInput(lotCodes[0]);
        setActiveTab("Lineage");
    };

    const prepareExport = () => {
        setRunStage("exported");
        setActiveTab("Exports");
    };

    return (
        <main data-inflow-lab-app className="min-h-screen bg-[#f6f8f5] text-slate-950">
            <style jsx global>{`
                body[data-inflow-lab="true"] > a[href="#main-content"],
                body[data-inflow-lab="true"] nav[aria-label="Main navigation"],
                body[data-inflow-lab="true"] footer,
                body[data-inflow-lab="true"] contentinfo,
                body[data-inflow-lab="true"] [role="contentinfo"] {
                    display: none !important;
                }

                body[data-inflow-lab="true"] {
                    background: #f6f8f5;
                }
            `}</style>
            <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
                <section className="overflow-hidden rounded-xl border border-emerald-900/15 bg-slate-950 text-white shadow-sm">
                    <div className="grid gap-0 lg:grid-cols-[minmax(0,1fr)_420px]">
                        <div className="p-5 sm:p-6">
                        <div className="max-w-3xl">
                            <div className="flex flex-wrap items-center gap-2">
                                <h1 className="text-2xl font-semibold tracking-normal text-white sm:text-3xl">
                                    RegEngine Inflow Lab
                                </h1>
                                <Badge className="border-emerald-300/25 bg-emerald-400/10 text-emerald-200 hover:bg-emerald-400/10">
                                    {runStatusLabel}
                                </Badge>
                            </div>
                            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                                Configure an inflow source, run a mock FSMA 204 delivery, resolve lot warnings, and package export-ready evidence.
                            </p>
                        </div>
                        <div className="mt-5 flex flex-wrap gap-2">
                            <Button
                                variant="outline"
                                className="h-10 border-white/20 bg-white/10 text-white hover:bg-white/15"
                                onClick={loadScenario}
                            >
                                <RefreshCcw className="mr-2 h-4 w-4" />
                                Load demo scenario
                            </Button>
                            <Button
                                className="h-10 bg-emerald-700 text-white hover:bg-emerald-800"
                                onClick={runPipeline}
                            >
                                <Play className="mr-2 h-4 w-4" />
                                Run pipeline
                            </Button>
                            <Button
                                variant="outline"
                                className="h-10 border-white/20 bg-white/10 text-white hover:bg-white/15"
                                onClick={traceLatestLot}
                            >
                                <Search className="mr-2 h-4 w-4" />
                                Trace latest lot
                            </Button>
                            <Button
                                variant="outline"
                                className="h-10 border-white/20 bg-white/10 text-white hover:bg-white/15"
                                onClick={prepareExport}
                                disabled={stageIndex[runStage] < 4}
                            >
                                <ArrowDownToLine className="mr-2 h-4 w-4" />
                                Prepare FDA package
                            </Button>
                        </div>
                        </div>

                        <div className="border-t border-white/10 bg-white/[0.04] p-5 lg:border-l lg:border-t-0">
                            <div className="grid grid-cols-2 gap-2 text-xs text-slate-300">
                                <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                                    <span className="block font-medium text-white">Tenant</span>
                                    {tenantId}
                        </div>
                                <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                                    <span className="block font-medium text-white">Delivery</span>
                                    {deliveryMode === "mock" ? "Mock RegEngine" : "Live adapter"}
                        </div>
                                <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                                    <span className="block font-medium text-white">Fixture</span>
                                    {fixture === "leafy-greens-trace" ? "Leafy greens trace" : "Single batch"}
                        </div>
                                <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                                    <span className="block font-medium text-white">Source</span>
                                    {source}
                        </div>
                            </div>
                        </div>
                    </div>
                </section>

                <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
                    <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                        <CardHeader className="border-b border-slate-200 p-4">
                            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                <div>
                                    <CardTitle className="text-base font-semibold text-slate-950">Operational workspace</CardTitle>
                                    <p className="mt-1 text-sm text-slate-500">
                                        Review generated records, trace lots, and prepare evidence exports from the active demo scenario.
                                    </p>
                                </div>
                                <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
                                    <Input
                                        value={traceInput}
                                        onChange={(event) => setTraceInput(event.target.value)}
                                        className="h-10 min-w-0 border-slate-300 text-xs sm:w-[290px]"
                                        aria-label="Traceability lot code"
                                    />
                                    <Button onClick={traceLot} className="h-10 bg-slate-950 text-white hover:bg-slate-800">
                                        <GitBranch className="mr-2 h-4 w-4" />
                                        Trace lot
                                    </Button>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="p-4">
                            <div>
                                <div className="flex h-auto flex-wrap justify-start gap-1 rounded-lg bg-slate-100 p-1">
                                    {tabs.map((tab) => (
                                        <button
                                            key={tab}
                                            type="button"
                                            onClick={() => setActiveTab(tab)}
                                            className={cn(
                                                "rounded-md px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-white/70 hover:text-slate-950",
                                                activeTab === tab && "bg-white text-slate-950 shadow-sm"
                                            )}
                                            aria-pressed={activeTab === tab}
                                        >
                                            {tab}
                                        </button>
                                    ))}
                                </div>

                                {activeTab === "Control room" && (
                                    <div className="mt-4 grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)]">
                                        <div className="space-y-4">
                                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                                                <div className="flex items-center gap-2">
                                                    <SlidersHorizontal className="h-4 w-4 text-emerald-700" />
                                                    <p className="text-sm font-semibold text-slate-950">Scenario setup</p>
                                                </div>
                                                <div className="mt-4 space-y-3">
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Tenant
                                                        <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} className="mt-1 h-9 bg-white" />
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Scenario preset
                                                        <select value={scenarioPreset} onChange={(event) => setScenarioPreset(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900">
                                                            <option value="leafy-greens">Leafy greens supplier</option>
                                                            <option value="single-batch">Single batch receiving</option>
                                                        </select>
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Fixture
                                                        <select value={fixture} onChange={(event) => setFixture(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900">
                                                            <option value="leafy-greens-trace">Leafy greens trace</option>
                                                            <option value="single-batch">Single batch</option>
                                                        </select>
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Delivery mode
                                                        <select value={deliveryMode} onChange={(event) => setDeliveryMode(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900">
                                                            <option value="mock">Mock RegEngine</option>
                                                            <option value="live">Live adapter disabled</option>
                                                        </select>
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Source
                                                        <Input value={source} onChange={(event) => setSource(event.target.value)} className="mt-1 h-9 bg-white" />
                                                    </label>
                                                </div>
                                            </div>

                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <div className="flex items-center gap-2">
                                                    <Upload className="h-4 w-4 text-blue-700" />
                                                    <p className="text-sm font-semibold text-slate-950">CSV import</p>
                                                </div>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">Stage scheduled events or replace the demo fixture during local testing.</p>
                                                <div className="mt-3 rounded-md border border-dashed border-slate-300 bg-slate-50 px-3 py-4 text-center text-xs text-slate-500">
                                                    CSV file input disabled in mock preview
                                                </div>
                                                <Button variant="outline" className="mt-3 h-9 w-full border-slate-300 bg-white">
                                                    Import CSV
                                                </Button>
                                            </div>
                                        </div>

                                        <div className="space-y-4">
                                            <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4">
                                                <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                                    <div>
                                                        <p className="text-sm font-semibold text-slate-950">Run command center</p>
                                                        <p className="mt-1 text-xs leading-5 text-slate-600">Harvest, cool, pack, ship, receive, validate, and export one leafy greens scenario.</p>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        <Button className="h-9 bg-emerald-700 text-white hover:bg-emerald-800" onClick={runPipeline}>
                                                            <Play className="mr-2 h-4 w-4" />
                                                            Start loop
                                                        </Button>
                                                        <Button variant="outline" className="h-9 border-slate-300 bg-white">
                                                            Stop
                                                        </Button>
                                                        <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={loadScenario}>
                                                            Reset state
                                                        </Button>
                                                    </div>
                                                </div>
                                                <div className="mt-4 grid gap-3 md:grid-cols-3">
                                                    {uniqueLots.map((lot) => (
                                                        <button
                                                            key={lot.lotCode}
                                                            type="button"
                                                            onClick={() => {
                                                                setSelectedLot(lot.lotCode);
                                                                setTraceInput(lot.lotCode);
                                                            }}
                                                            className={cn(
                                                                "rounded-lg border bg-white p-3 text-left transition hover:border-emerald-300",
                                                                lot.lotCode === selectedLot ? "border-emerald-400 shadow-sm" : "border-slate-200"
                                                            )}
                                                        >
                                                            <div className="flex items-center justify-between gap-2">
                                                                <span className="text-xs font-medium text-slate-500">{lot.product}</span>
                                                                <LotReadinessPill ready={lot.complete} />
                                                            </div>
                                                            <p className="mt-2 break-all font-mono text-[11px] font-semibold text-slate-950">{lot.lotCode}</p>
                                                            <p className="mt-2 text-xs text-slate-500">{lot.completeCount}/{lot.totalCount} CTEs captured</p>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className="grid gap-4 lg:grid-cols-2">
                                                <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                    <div className="flex items-center gap-2">
                                                        <CalendarDays className="h-4 w-4 text-slate-700" />
                                                        <p className="text-sm font-semibold text-slate-950">Export filters</p>
                                                    </div>
                                                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                                                        <label className="block text-xs font-medium text-slate-600">
                                                            Preset
                                                            <select value={exportPreset} onChange={(event) => setExportPreset(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900">
                                                                <option value="all-records">All records</option>
                                                                <option value="selected-lot">Selected lot</option>
                                                                <option value="export-ready">Export-ready only</option>
                                                            </select>
                                                        </label>
                                                        <label className="block text-xs font-medium text-slate-600">
                                                            Traceability Lot Code
                                                            <Input value={traceInput} onChange={(event) => setTraceInput(event.target.value)} className="mt-1 h-9 bg-white text-xs" />
                                                        </label>
                                                        <label className="block text-xs font-medium text-slate-600">
                                                            Start date
                                                            <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 h-9 bg-white" />
                                                        </label>
                                                        <label className="block text-xs font-medium text-slate-600">
                                                            End date
                                                            <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 h-9 bg-white" />
                                                        </label>
                                                    </div>
                                                </div>

                                                <div className="rounded-lg border border-slate-200 bg-slate-950 p-4 text-white">
                                                    <p className="text-sm font-semibold">Evidence package</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-300">2 lots are export-ready. 1 partial lot remains visible as an exception, not silently included.</p>
                                                    <div className="mt-4 grid grid-cols-2 gap-2">
                                                        <Button className="h-9 bg-emerald-600 text-white hover:bg-emerald-700" onClick={prepareExport}>
                                                            Download CSV
                                                        </Button>
                                                        <Button variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                            EPCIS JSON
                                                        </Button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Event log" && (
                                    <div className="mt-4">
                                        {visibleEvents.length === 0 ? (
                                            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
                                                <ClipboardList className="mx-auto h-8 w-8 text-slate-400" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">Demo scenario loaded</p>
                                                <p className="mt-1 text-sm text-slate-500">Run the pipeline to generate FSMA 204 traceability records.</p>
                                            </div>
                                        ) : (
                                            <Table>
                                                <TableHeader>
                                                    <TableRow className="border-slate-200 bg-slate-50 hover:bg-slate-50">
                                                        <TableHead className="h-10 px-3 text-xs">#</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">CTE</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Lot code</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Product</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Location</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Timestamp</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Mode</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Attempts</TableHead>
                                                        <TableHead className="h-10 px-3 text-xs">Status</TableHead>
                                                    </TableRow>
                                                </TableHeader>
                                                <TableBody>
                                                    {visibleEvents.map((event) => (
                                                        <TableRow
                                                            key={event.id}
                                                            className={cn(
                                                                "border-slate-100 hover:bg-emerald-50/40",
                                                                event.lotCode === selectedLot && "bg-emerald-50/35"
                                                            )}
                                                        >
                                                            <TableCell className="px-3 py-3 text-xs text-slate-500">{event.id}</TableCell>
                                                            <TableCell className="px-3 py-3 text-xs font-medium text-slate-900">{event.cte}</TableCell>
                                                            <TableCell className="px-3 py-3">
                                                                <button
                                                                    type="button"
                                                                    onClick={() => {
                                                                        setSelectedLot(event.lotCode);
                                                                        setTraceInput(event.lotCode);
                                                                        setActiveTab("Lineage");
                                                                    }}
                                                                    className="text-left font-mono text-xs font-medium text-emerald-700 underline-offset-4 hover:underline"
                                                                >
                                                                    {event.lotCode}
                                                                </button>
                                                            </TableCell>
                                                            <TableCell className="px-3 py-3 text-xs text-slate-700">{event.product}</TableCell>
                                                            <TableCell className="px-3 py-3 text-xs text-slate-700">{event.location}</TableCell>
                                                            <TableCell className="px-3 py-3 text-xs text-slate-600">{event.timestamp}</TableCell>
                                                            <TableCell className="px-3 py-3 text-xs text-slate-600">{event.mode}</TableCell>
                                                            <TableCell className="px-3 py-3 text-xs text-slate-600">{event.attempts}</TableCell>
                                                            <TableCell className="px-3 py-3">
                                                                <StatusPill status={visibleEventStatus} />
                                                            </TableCell>
                                                        </TableRow>
                                                    ))}
                                                </TableBody>
                                            </Table>
                                        )}
                                    </div>
                                )}

                                {activeTab === "Lots" && (
                                    <div className="mt-4">
                                        <div className="grid gap-3 lg:grid-cols-3">
                                            {uniqueLots.map((lot) => (
                                                <button
                                                    key={lot.lotCode}
                                                    type="button"
                                                    onClick={() => {
                                                        setSelectedLot(lot.lotCode);
                                                        setTraceInput(lot.lotCode);
                                                        setActiveTab("Lineage");
                                                    }}
                                                    className={cn(
                                                        "rounded-lg border p-4 text-left transition hover:border-emerald-300 hover:bg-emerald-50",
                                                        lot.lotCode === selectedLot ? "border-emerald-300 bg-emerald-50" : "border-slate-200 bg-white"
                                                    )}
                                                >
                                                    <div className="flex items-start justify-between gap-3">
                                                        <PackageCheck className={cn("h-5 w-5", lot.complete ? "text-emerald-700" : "text-amber-600")} />
                                                        <LotReadinessPill ready={lot.complete} />
                                                    </div>
                                                    <p className="mt-3 font-mono text-xs font-semibold text-slate-950">{lot.lotCode}</p>
                                                    <p className="mt-2 text-sm font-medium text-slate-800">{lot.product}</p>
                                                    <p className="mt-1 text-xs text-slate-500">
                                                        {lot.completeCount} of {lot.totalCount} CTEs captured - last seen at {lot.lastLocation}
                                                    </p>
                                                </button>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Lineage" && (
                                    <div className="mt-4">
                                        <div
                                            className={cn(
                                                "rounded-lg border p-4",
                                                selectedIsExportReady ? "border-slate-200 bg-slate-50" : "border-amber-200 bg-amber-50/70"
                                            )}
                                        >
                                            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                                <div>
                                                    <p className="text-sm font-semibold text-slate-950">Lineage for {selectedLot}</p>
                                                    <p className="mt-1 text-xs text-slate-500">
                                                        {selectedCompleteCount} of {selectedLineage.length} required CTEs captured.
                                                    </p>
                                                </div>
                                                <LotReadinessPill ready={selectedIsExportReady} />
                                            </div>
                                            {!selectedIsExportReady && (
                                                <div className="mt-4 rounded-md border border-amber-200 bg-white px-3 py-2 text-xs text-amber-800">
                                                    Capture initial packing, shipping, and DC receiving before this lot is included in the FDA-ready export package.
                                                </div>
                                            )}
                                            <div className="mt-5 grid gap-3 md:grid-cols-5">
                                                {selectedLineage.map((node, index) => (
                                                    <div
                                                        key={node.cte}
                                                        className={cn(
                                                            "relative rounded-lg border bg-white p-3",
                                                            node.state === "complete" ? "border-slate-200" : "border-amber-200"
                                                        )}
                                                    >
                                                        {index < selectedLineage.length - 1 && (
                                                            <div className="absolute -right-2 top-1/2 hidden h-px w-4 bg-slate-300 md:block" />
                                                        )}
                                                        <p className="text-xs font-semibold text-slate-950">{node.cte}</p>
                                                        <p className="mt-2 text-xs text-slate-600">{node.location}</p>
                                                        <p className="mt-1 text-[11px] text-slate-500">{node.time}</p>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Exports" && (
                                    <div className="mt-4">
                                        {!selectedIsExportReady && (
                                            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                                                Selected lot is partial. The package can be prepared for export-ready lots, but this lot will be flagged until missing CTEs are captured.
                                            </div>
                                        )}
                                        <div className="grid gap-3 md:grid-cols-2">
                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <FileSpreadsheet className="h-5 w-5 text-emerald-700" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">FDA sortable spreadsheet</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Includes the two complete lots and flags the partial lot for review.
                                                </p>
                                                <Button className="mt-4 h-9 bg-emerald-700 text-white hover:bg-emerald-800">
                                                    Download CSV
                                                </Button>
                                            </div>
                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <FileJson className="h-5 w-5 text-blue-700" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">GS1 EPCIS 2.0 JSON-LD</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Uses the same lot and date filters as the FDA package for interoperability testing.
                                                </p>
                                                <Button variant="outline" className="mt-4 h-9 border-slate-300 bg-white">
                                                    Download EPCIS
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Diagnostics" && (
                                    <div className="mt-4">
                                        <div className="grid gap-3 md:grid-cols-2">
                                            {[
                                                ["Auth", "Off for local simulation"],
                                                ["Storage", "Local JSONL"],
                                                ["Persist path", "data/events.jsonl"],
                                                ["Source", "Demo generator"],
                                                ["Last success", runStage === "loaded" ? "Not run yet" : "Apr 27, 2026, 2:04 AM"],
                                                ["Retry queue", "0 failed deliveries"],
                                            ].map(([label, value]) => (
                                                <div key={label} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                                                    <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
                                                    <p className="mt-1 text-sm text-slate-900">{value}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </CardContent>
                    </Card>

                    <aside className="flex flex-col gap-4">
                        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                            <CardHeader className="border-b border-slate-200 p-4">
                                <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-950">
                                    <GitBranch className="h-4 w-4 text-emerald-700" />
                                    Selected lot lineage
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="p-4">
                                <div className="flex items-start justify-between gap-3">
                                    <p className="font-mono text-xs font-semibold text-slate-950">{selectedLot}</p>
                                    <LotReadinessPill ready={selectedIsExportReady} />
                                </div>
                                <p className="mt-2 text-xs text-slate-500">
                                    {selectedCompleteCount} of {selectedLineage.length} CTEs captured
                                </p>
                                <div className="mt-4 space-y-3">
                                    {selectedLineage.map((node, index) => (
                                        <div key={node.cte} className="flex gap-3">
                                            <div className="flex flex-col items-center">
                                                <span
                                                    className={cn(
                                                        "flex h-7 w-7 items-center justify-center rounded-full border",
                                                        node.state === "complete"
                                                            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                                            : "border-amber-200 bg-amber-50 text-amber-700"
                                                    )}
                                                >
                                                    <LineageStatusIcon state={node.state} />
                                                </span>
                                                {index < selectedLineage.length - 1 && <span className="h-9 w-px bg-slate-200" />}
                                            </div>
                                            <div className="pb-2">
                                                <p className="text-sm font-semibold text-slate-950">{node.cte}</p>
                                                <p className="mt-0.5 text-xs text-slate-600">{node.location}</p>
                                                <p className="mt-0.5 text-[11px] text-slate-500">{node.time}</p>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                            <CardHeader className="border-b border-slate-200 p-4">
                                <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-950">
                                    <Truck className="h-4 w-4 text-blue-700" />
                                    Delivery monitor
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3 p-4">
                                {[
                                    ["Posted", String(deliveredCount)],
                                    ["Failed", "0"],
                                    ["Generated only", hasGeneratedRecords && deliveredCount === 0 ? String(events.length) : "0"],
                                    ["Attempts", String(deliveredCount)],
                                ].map(([label, value]) => (
                                    <div key={label} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2">
                                        <span className="text-xs text-slate-500">{label}</span>
                                        <span className="text-sm font-semibold text-slate-950">{value}</span>
                                    </div>
                                ))}
                                <Button variant="outline" className="mt-1 h-9 w-full border-slate-300 bg-white">
                                    <RotateCcw className="mr-2 h-4 w-4" />
                                    Retry failed deliveries
                                </Button>
                            </CardContent>
                        </Card>

                        <Card className="rounded-lg border-amber-200 bg-amber-50/70 shadow-sm">
                            <CardContent className="flex gap-3 p-4">
                                <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                                <div>
                                    <p className="text-sm font-semibold text-amber-950">Local simulation</p>
                                    <p className="mt-1 text-xs leading-5 text-amber-800">
                                        This demo writes local events and validates the FSMA record shape before a live delivery adapter is enabled.
                                    </p>
                                </div>
                            </CardContent>
                        </Card>

                        <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                            <CardContent className="flex items-center gap-3 p-4">
                                <Database className="h-5 w-5 text-slate-500" />
                                <div>
                                    <p className="text-sm font-semibold text-slate-950">Local state</p>
                                    <p className="text-xs text-slate-500">data/events.jsonl</p>
                                </div>
                            </CardContent>
                        </Card>
                    </aside>
                </section>
            </div>
        </main>
    );
}
