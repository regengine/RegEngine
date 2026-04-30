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

type InflowHealth = {
    ok?: boolean;
    build?: { version?: string; commit_sha_short?: string };
};

type InflowStatus = {
    running?: boolean;
    config?: {
        source?: string;
        scenario?: string;
        delivery?: { mode?: string; tenant_id?: string | null };
    };
    stats?: {
        total_records?: number;
        unique_lots?: number;
        delivery?: {
            posted?: number;
            failed?: number;
            generated?: number;
            attempts?: number;
            last_attempt_at?: string | null;
            last_success_at?: string | null;
        };
    };
};

type InflowRecord = {
    sequence_no: number;
    destination_mode: string;
    delivery_status: "generated" | "posted" | "failed";
    delivery_attempts?: number;
    event: {
        cte_type: string;
        traceability_lot_code: string;
        product_description: string;
        location_name: string;
        timestamp: string;
    };
};

type InflowLineagePayload = {
    records?: InflowRecord[];
};

const INFLOW_API = "/api/inflow-lab";
const REQUIRED_CTES = ["harvesting", "cooling", "initial_packing", "shipping", "receiving"];

function servicePath(path: string) {
    return `${INFLOW_API}${path}`;
}

async function inflowJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(servicePath(path), {
        cache: "no-store",
        headers: { "content-type": "application/json" },
        ...init,
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || payload.detail || `Inflow Lab request failed: ${response.status}`);
    }
    return response.json();
}

function formatServiceTime(value: string) {
    return new Date(value).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function toTraceEvent(record: InflowRecord): TraceEvent {
    return {
        id: record.sequence_no,
        cte: record.event.cte_type,
        lotCode: record.event.traceability_lot_code,
        product: record.event.product_description,
        location: record.event.location_name,
        timestamp: formatServiceTime(record.event.timestamp),
        mode: "simulation",
        attempts: record.delivery_attempts || 0,
    };
}

function toLineage(eventsForLot: TraceEvent[]): LineageNode[] {
    const byCte = new Map(eventsForLot.map((event) => [event.cte, event]));
    return REQUIRED_CTES.map((cte) => {
        const event = byCte.get(cte);
        return {
            cte: cte.replaceAll("_", " "),
            location: event?.location || "Not captured",
            time: event?.timestamp || "Missing CTE",
            state: event ? "complete" : "missing",
        };
    });
}

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

type InflowLabClientProps = {
    mode?: "standalone" | "dashboard";
};

export function InflowLabClient({ mode = "standalone" }: InflowLabClientProps) {
    const isStandalone = mode === "standalone";
    const [activeTab, setActiveTab] = useState("Control room");
    const [selectedLot, setSelectedLot] = useState(lotCodes[0]);
    const [traceInput, setTraceInput] = useState(lotCodes[0]);
    const [runStage, setRunStage] = useState<RunStage>("complete");
    const [health, setHealth] = useState<InflowHealth | null>(null);
    const [serviceStatus, setServiceStatus] = useState<InflowStatus | null>(null);
    const [serviceEvents, setServiceEvents] = useState<TraceEvent[]>([]);
    const [serviceLineage, setServiceLineage] = useState<Record<string, LineageNode[]>>({});
    const [serviceError, setServiceError] = useState<string | null>(null);
    const [isBusy, setIsBusy] = useState(false);
    const [tenantId, setTenantId] = useState("local-demo");
    const [scenarioPreset, setScenarioPreset] = useState("leafy_greens_supplier");
    const [fixture, setFixture] = useState("leafy_greens_trace");
    const [deliveryMode, setDeliveryMode] = useState("mock");
    const [source, setSource] = useState("codex-simulator");
    const [exportPreset, setExportPreset] = useState("all_records");
    const [startDate, setStartDate] = useState("2026-04-26");
    const [endDate, setEndDate] = useState("2026-04-27");

    const refreshService = async () => {
        const [healthPayload, statusPayload, eventsPayload] = await Promise.all([
            inflowJson<InflowHealth>("/api/healthz"),
            inflowJson<InflowStatus>("/api/simulate/status"),
            inflowJson<{ events?: InflowRecord[] }>("/api/events?limit=100"),
        ]);
        const nextEvents = (eventsPayload.events || []).map(toTraceEvent);
        setHealth(healthPayload);
        setServiceStatus(statusPayload);
        setServiceEvents(nextEvents);
        setServiceError(null);

        const firstLot = nextEvents[0]?.lotCode;
        if (firstLot && (!traceInput || traceInput === lotCodes[0])) {
            setSelectedLot(firstLot);
            setTraceInput(firstLot);
        }
    };

    const selectedEvents = useMemo(
        () => (serviceEvents.length ? serviceEvents : events).filter((event) => event.lotCode === selectedLot),
        [selectedLot, serviceEvents]
    );

    const activeEvents = serviceEvents.length ? serviceEvents : events;
    const activeLineageByLot = serviceEvents.length ? serviceLineage : lineageByLot;
    const selectedLineage = activeLineageByLot[selectedLot] ?? toLineage(selectedEvents);
    const selectedCompleteCount = selectedLineage.filter((node) => node.state === "complete").length;
    const selectedIsExportReady = selectedCompleteCount === selectedLineage.length;
    const hasGeneratedRecords = runStage !== "loaded";
    const visibleEvents = hasGeneratedRecords ? activeEvents : [];
    const visibleEventStatus = serviceEvents.length ? "posted" : getEventStatus(runStage);
    const deliveredCount = serviceStatus?.stats?.delivery?.posted ?? (stageIndex[runStage] >= 2 ? activeEvents.length : 0);
    const completeLots = Array.from(new Set(activeEvents.map((event) => event.lotCode))).filter((lotCode) => {
        const lineage = activeLineageByLot[lotCode] ?? toLineage(activeEvents.filter((event) => event.lotCode === lotCode));
        return lineage.length > 0 && lineage.every((node) => node.state === "complete");
    }).length;

    useEffect(() => {
        if (isStandalone) {
            document.body.dataset.inflowLab = "true";
        }
        refreshService().catch((error) => setServiceError(error instanceof Error ? error.message : "Inflow Lab service unavailable"));
        return () => {
            if (isStandalone) {
                delete document.body.dataset.inflowLab;
            }
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isStandalone]);

    useEffect(() => {
        if (!serviceEvents.length || !selectedLot || serviceLineage[selectedLot]) return;

        inflowJson<InflowLineagePayload>(`/api/lineage/${encodeURIComponent(selectedLot)}`)
            .then((payload) => {
                const lineageEvents = (payload.records || []).map(toTraceEvent);
                setServiceLineage((current) => ({ ...current, [selectedLot]: toLineage(lineageEvents) }));
            })
            .catch((error) => setServiceError(error instanceof Error ? error.message : "Could not trace lot"));
    }, [selectedLot, serviceEvents.length, serviceLineage]);

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
            Array.from(new Set(activeEvents.map((event) => event.lotCode))).map((lotCode) => {
                const lotEvents = activeEvents.filter((event) => event.lotCode === lotCode);
                const lineage = activeLineageByLot[lotCode] ?? toLineage(lotEvents);
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
        [activeEvents, activeLineageByLot]
    );

    const loadScenario = async () => {
        setIsBusy(true);
        try {
            await inflowJson(`/api/demo-fixtures/${fixture}/load`, {
                method: "POST",
                body: JSON.stringify({
                    reset: true,
                    source,
                    delivery: { mode: deliveryMode, tenant_id: tenantId || null },
                }),
            });
            await refreshService();
            setRunStage("complete");
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : "Could not load Inflow Lab fixture");
            setRunStage("loaded");
        } finally {
            setIsBusy(false);
        }
        setActiveTab("Control room");
    };

    const runPipeline = async () => {
        setIsBusy(true);
        setRunStage("generating");
        setActiveTab("Control room");
        try {
            await inflowJson("/api/simulate/start", {
                method: "POST",
                body: JSON.stringify({
                    config: {
                        source,
                        scenario: scenarioPreset,
                        interval_seconds: 0.1,
                        batch_size: 1,
                        persist_path: "data/events.jsonl",
                        delivery: { mode: deliveryMode, tenant_id: tenantId || null },
                    },
                }),
            });
            setRunStage("delivering");
            await new Promise((resolve) => window.setTimeout(resolve, 700));
            await inflowJson("/api/simulate/stop", { method: "POST" });
            await refreshService();
            setRunStage("complete");
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : "Could not run Inflow Lab pipeline");
            setRunStage("loaded");
        } finally {
            setIsBusy(false);
        }
    };

    const resetServiceState = async () => {
        setIsBusy(true);
        try {
            await inflowJson("/api/simulate/reset", {
                method: "POST",
                body: JSON.stringify({
                    source,
                    scenario: scenarioPreset,
                    delivery: { mode: deliveryMode, tenant_id: tenantId || null },
                }),
            });
            setServiceEvents([]);
            setServiceLineage({});
            await refreshService();
            setRunStage("loaded");
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : "Could not reset Inflow Lab state");
        } finally {
            setIsBusy(false);
        }
    };

    const traceLot = async () => {
        if (traceInput) {
            setSelectedLot(traceInput);
            setActiveTab("Lineage");
        }
        try {
            const payload = await inflowJson<InflowLineagePayload>(`/api/lineage/${encodeURIComponent(traceInput)}`);
            const lineageEvents = (payload.records || []).map(toTraceEvent);
            setServiceLineage((current) => ({ ...current, [traceInput]: toLineage(lineageEvents) }));
            setServiceError(null);
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : "Could not trace lot");
        }
    };

    const traceLatestLot = () => {
        const latestLot = visibleEvents[0]?.lotCode || lotCodes[0];
        setSelectedLot(latestLot);
        setTraceInput(latestLot);
        setActiveTab("Lineage");
    };

    const prepareExport = () => {
        setRunStage("exported");
        setActiveTab("Exports");
    };

    const csvExportHref = `${servicePath(`/api/mock/regengine/export/fda-request?preset=${exportPreset}&traceability_lot_code=${encodeURIComponent(traceInput)}&start_date=${startDate}&end_date=${endDate}`)}`;
    const epcisExportHref = `${servicePath(`/api/mock/regengine/export/epcis?traceability_lot_code=${encodeURIComponent(traceInput)}&start_date=${startDate}&end_date=${endDate}`)}`;
    const engineConnected = Boolean(health?.ok && !serviceError);
    const connectionLabel = engineConnected ? "Engine connected" : serviceError ? "Engine unavailable" : "Checking engine";
    const connectionTone = engineConnected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800";
    const postedCount = serviceStatus?.stats?.delivery?.posted ?? deliveredCount;
    const failedCount = serviceStatus?.stats?.delivery?.failed ?? 0;

    return (
        <main
            data-inflow-lab-app
            data-inflow-lab-mode={mode}
            className={cn("bg-[#f6f8f5] text-slate-950", isStandalone ? "min-h-screen" : "min-h-full")}
        >
            <style jsx global>{`
                body[data-inflow-lab="true"] > a[href="#main-content"],
                body[data-inflow-lab="true"] nav[aria-label="Main navigation"],
                body[data-inflow-lab="true"] footer,
                body[data-inflow-lab="true"] contentinfo,
                body[data-inflow-lab="true"] [role="contentinfo"],
                body[data-inflow-lab="true"] [aria-label="Open accessibility settings"],
                body[data-inflow-lab="true"] [aria-label="Cookie consent"],
                body[data-inflow-lab="true"] [aria-label="Open Next.js Dev Tools"],
                body[data-inflow-lab="true"] nextjs-portal,
                body[data-inflow-lab="true"] > button {
                    display: none !important;
                }

                body[data-inflow-lab="true"] {
                    background: #f6f8f5;
                }

                [data-inflow-lab-app] {
                    min-height: 100vh;
                    background: #f6f8f5;
                    color: #0f172a;
                    font-family: Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                }

                [data-inflow-lab-mode="dashboard"] {
                    min-height: calc(100vh - 44px);
                }

                [data-inflow-lab-app] * {
                    box-sizing: border-box;
                }

                [data-inflow-lab-app] h1,
                [data-inflow-lab-app] h2,
                [data-inflow-lab-app] h3,
                [data-inflow-lab-app] p {
                    margin: 0;
                }

                [data-inflow-lab-app] > div {
                    width: 100%;
                    max-width: 1480px;
                    margin: 0 auto;
                    padding: 20px 32px;
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                }

                [data-inflow-lab-mode="dashboard"] > div {
                    max-width: none;
                    padding: 20px 24px 32px;
                }

                [data-inflow-lab-app] section:first-of-type {
                    overflow: hidden;
                    border-radius: 18px;
                    border: 1px solid rgba(6, 78, 59, 0.22);
                    background: #020617;
                    color: #fff;
                    box-shadow: 0 20px 70px rgba(15, 23, 42, 0.16);
                }

                [data-inflow-lab-app] section:first-of-type > div {
                    display: grid;
                    grid-template-columns: minmax(0, 1fr) 420px;
                }

                [data-inflow-lab-app] section:first-of-type > div > div {
                    padding: 24px;
                }

                [data-inflow-lab-app] section:first-of-type > div > div:last-child {
                    border-left: 1px solid rgba(255, 255, 255, 0.1);
                    background: rgba(255, 255, 255, 0.04);
                }

                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] {
                    border-radius: 10px;
                    border: 1px solid #e2e8f0;
                    background: #fff;
                    color: #0f172a;
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
                }

                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] > div {
                    display: flex;
                    gap: 16px;
                }

                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] > div > div {
                    padding: 0;
                }

                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] > div > div:last-child {
                    border-left: 0;
                    background: transparent;
                }

                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] button:not(.bg-emerald-700) {
                    border-color: #cbd5e1;
                    background: #fff;
                    color: #0f172a;
                }

                [data-inflow-lab-app] section:nth-of-type(2) {
                    display: grid;
                    grid-template-columns: minmax(0, 1fr) 380px;
                    gap: 20px;
                    align-items: start;
                }

                [data-inflow-lab-app] aside,
                [data-inflow-lab-app] .flex.flex-col.gap-4 {
                    display: flex;
                    flex-direction: column;
                    gap: 16px;
                }

                [data-inflow-lab-app] .grid {
                    display: grid;
                }

                [data-inflow-lab-app] .flex {
                    display: flex;
                }

                [data-inflow-lab-app] .inline-flex {
                    display: inline-flex;
                }

                [data-inflow-lab-app] .hidden {
                    display: none;
                }

                [data-inflow-lab-app] .items-center {
                    align-items: center;
                }

                [data-inflow-lab-app] .items-start {
                    align-items: flex-start;
                }

                [data-inflow-lab-app] .justify-between {
                    justify-content: space-between;
                }

                [data-inflow-lab-app] .justify-center {
                    justify-content: center;
                }

                [data-inflow-lab-app] .flex-col {
                    flex-direction: column;
                }

                [data-inflow-lab-app] .flex-wrap {
                    flex-wrap: wrap;
                }

                [data-inflow-lab-app] .gap-1 { gap: 4px; }
                [data-inflow-lab-app] .gap-2 { gap: 8px; }
                [data-inflow-lab-app] .gap-3 { gap: 12px; }
                [data-inflow-lab-app] .gap-4 { gap: 16px; }
                [data-inflow-lab-app] .gap-5 { gap: 20px; }
                [data-inflow-lab-app] .space-y-2 > * + * { margin-top: 8px; }
                [data-inflow-lab-app] .space-y-3 > * + * { margin-top: 12px; }
                [data-inflow-lab-app] .space-y-4 > * + * { margin-top: 16px; }
                [data-inflow-lab-app] .mt-0\\.5 { margin-top: 2px; }
                [data-inflow-lab-app] .mt-1 { margin-top: 4px; }
                [data-inflow-lab-app] .mt-2 { margin-top: 8px; }
                [data-inflow-lab-app] .mt-3 { margin-top: 12px; }
                [data-inflow-lab-app] .mt-4 { margin-top: 16px; }
                [data-inflow-lab-app] .mt-5 { margin-top: 20px; }
                [data-inflow-lab-app] .mb-3 { margin-bottom: 12px; }
                [data-inflow-lab-app] .mr-2 { margin-right: 8px; }
                [data-inflow-lab-app] .p-1 { padding: 4px; }
                [data-inflow-lab-app] .p-2 { padding: 8px; }
                [data-inflow-lab-app] .p-3 { padding: 12px; }
                [data-inflow-lab-app] .p-4 { padding: 16px; }
                [data-inflow-lab-app] .p-5 { padding: 20px; }
                [data-inflow-lab-app] .p-8 { padding: 32px; }
                [data-inflow-lab-app] .px-3 { padding-left: 12px; padding-right: 12px; }
                [data-inflow-lab-app] .px-4 { padding-left: 16px; padding-right: 16px; }
                [data-inflow-lab-app] .py-2 { padding-top: 8px; padding-bottom: 8px; }
                [data-inflow-lab-app] .py-3 { padding-top: 12px; padding-bottom: 12px; }
                [data-inflow-lab-app] .pb-2 { padding-bottom: 8px; }

                [data-inflow-lab-app] .rounded-md { border-radius: 6px; }
                [data-inflow-lab-app] .rounded-lg { border-radius: 10px; }
                [data-inflow-lab-app] .rounded-xl { border-radius: 18px; }
                [data-inflow-lab-app] .rounded-full { border-radius: 9999px; }
                [data-inflow-lab-app] .border { border: 1px solid #e2e8f0; }
                [data-inflow-lab-app] .border-b { border-bottom: 1px solid #e2e8f0; }
                [data-inflow-lab-app] .border-t { border-top: 1px solid #e2e8f0; }
                [data-inflow-lab-app] .border-dashed { border-style: dashed; }
                [data-inflow-lab-app] .border-slate-100 { border-color: #f1f5f9; }
                [data-inflow-lab-app] .border-slate-200 { border-color: #e2e8f0; }
                [data-inflow-lab-app] .border-slate-300 { border-color: #cbd5e1; }
                [data-inflow-lab-app] .border-emerald-200 { border-color: #a7f3d0; }
                [data-inflow-lab-app] .border-emerald-300,
                [data-inflow-lab-app] .border-emerald-400 { border-color: #6ee7b7; }
                [data-inflow-lab-app] .border-amber-200 { border-color: #fde68a; }
                [data-inflow-lab-app] .border-blue-200 { border-color: #bfdbfe; }
                [data-inflow-lab-app] .border-white\\/10 { border-color: rgba(255, 255, 255, 0.1); }
                [data-inflow-lab-app] .border-white\\/20 { border-color: rgba(255, 255, 255, 0.2); }
                [data-inflow-lab-app] .shadow-sm { box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08); }

                [data-inflow-lab-app] .bg-white { background: #fff; }
                [data-inflow-lab-app] .bg-slate-50 { background: #f8fafc; }
                [data-inflow-lab-app] .bg-slate-100 { background: #f1f5f9; }
                [data-inflow-lab-app] .bg-slate-950 { background: #020617; }
                [data-inflow-lab-app] .bg-emerald-50,
                [data-inflow-lab-app] .bg-emerald-50\\/70 { background: rgba(236, 253, 245, 0.78); }
                [data-inflow-lab-app] .bg-emerald-700 { background: #047857; }
                [data-inflow-lab-app] .bg-emerald-600 { background: #059669; }
                [data-inflow-lab-app] .bg-amber-50,
                [data-inflow-lab-app] .bg-amber-50\\/70 { background: rgba(255, 251, 235, 0.86); }
                [data-inflow-lab-app] .bg-blue-50 { background: #eff6ff; }
                [data-inflow-lab-app] .bg-white\\/10 { background: rgba(255, 255, 255, 0.1); }
                [data-inflow-lab-app] .bg-white\\/15 { background: rgba(255, 255, 255, 0.15); }

                [data-inflow-lab-app] .text-white { color: #fff; }
                [data-inflow-lab-app] .text-slate-950 { color: #020617; }
                [data-inflow-lab-app] .text-slate-900 { color: #0f172a; }
                [data-inflow-lab-app] .text-slate-800 { color: #1e293b; }
                [data-inflow-lab-app] .text-slate-700 { color: #334155; }
                [data-inflow-lab-app] .text-slate-600 { color: #475569; }
                [data-inflow-lab-app] .text-slate-500 { color: #64748b; }
                [data-inflow-lab-app] .text-slate-400 { color: #94a3b8; }
                [data-inflow-lab-app] .text-slate-300 { color: #cbd5e1; }
                [data-inflow-lab-app] .text-emerald-700 { color: #047857; }
                [data-inflow-lab-app] .text-emerald-200 { color: #a7f3d0; }
                [data-inflow-lab-app] .text-amber-950 { color: #451a03; }
                [data-inflow-lab-app] .text-amber-800 { color: #92400e; }
                [data-inflow-lab-app] .text-amber-700,
                [data-inflow-lab-app] .text-amber-600 { color: #b45309; }
                [data-inflow-lab-app] .text-blue-700 { color: #1d4ed8; }

                [data-inflow-lab-app] .text-2xl { font-size: 24px; line-height: 32px; }
                [data-inflow-lab-app] .text-sm { font-size: 14px; line-height: 20px; }
                [data-inflow-lab-app] .text-xs { font-size: 12px; line-height: 16px; }
                [data-inflow-lab-app] .text-\\[11px\\] { font-size: 11px; line-height: 14px; }
                [data-inflow-lab-app] .font-semibold { font-weight: 600; }
                [data-inflow-lab-app] .font-medium { font-weight: 500; }
                [data-inflow-lab-app] .font-mono { font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }
                [data-inflow-lab-app] .uppercase { text-transform: uppercase; }
                [data-inflow-lab-app] .leading-5 { line-height: 20px; }
                [data-inflow-lab-app] .leading-6 { line-height: 24px; }
                [data-inflow-lab-app] .tracking-normal { letter-spacing: 0; }

                [data-inflow-lab-app] .h-4 { height: 16px; }
                [data-inflow-lab-app] .w-4 { width: 16px; }
                [data-inflow-lab-app] .h-5 { height: 20px; }
                [data-inflow-lab-app] .w-5 { width: 20px; }
                [data-inflow-lab-app] .h-7 { height: 28px; }
                [data-inflow-lab-app] .w-7 { width: 28px; }
                [data-inflow-lab-app] .h-8 { height: 32px; }
                [data-inflow-lab-app] .w-8 { width: 32px; }
                [data-inflow-lab-app] .h-9 { height: 36px; }
                [data-inflow-lab-app] .h-10 { height: 40px; }
                [data-inflow-lab-app] .w-full { width: 100%; }
                [data-inflow-lab-app] .min-w-0 { min-width: 0; }
                [data-inflow-lab-app] .max-w-2xl { max-width: 672px; }
                [data-inflow-lab-app] .max-w-3xl { max-width: 768px; }
                [data-inflow-lab-app] .shrink-0 { flex-shrink: 0; }

                [data-inflow-lab-app] button,
                [data-inflow-lab-app] input,
                [data-inflow-lab-app] select {
                    font: inherit;
                }

                [data-inflow-lab-app] button {
                    cursor: pointer;
                }

                [data-inflow-lab-app] input,
                [data-inflow-lab-app] select {
                    border: 1px solid #cbd5e1;
                    border-radius: 8px;
                    padding: 0 10px;
                    background: #fff;
                    color: #0f172a;
                }

                [data-inflow-lab-app] button {
                    min-height: 36px;
                    border-radius: 8px;
                    border: 1px solid #cbd5e1;
                    padding: 0 12px;
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    gap: 6px;
                    background: #fff;
                    color: #0f172a;
                    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
                }

                [data-inflow-lab-app] button.bg-emerald-700,
                [data-inflow-lab-app] button.bg-emerald-600,
                [data-inflow-lab-app] button.bg-slate-950 {
                    border-color: transparent;
                    color: #fff;
                }

                [data-inflow-lab-app] button.bg-white\\/10 {
                    border-color: rgba(255, 255, 255, 0.2);
                    background: rgba(255, 255, 255, 0.1);
                    color: #fff;
                }

                [data-inflow-lab-app] button.bg-white\\/10:hover {
                    background: rgba(255, 255, 255, 0.16);
                    border-color: rgba(255, 255, 255, 0.32);
                }

                [data-inflow-lab-app] button:hover {
                    border-color: #10b981;
                }

                [data-inflow-lab-app] button.p-3,
                [data-inflow-lab-app] button.p-4 {
                    display: block;
                    min-height: 0;
                    width: 100%;
                }

                [data-inflow-lab-app] section:first-of-type button:not(.bg-emerald-700),
                [data-inflow-lab-app] .bg-slate-950 button:not(.bg-emerald-600) {
                    border-color: rgba(255, 255, 255, 0.22);
                    background: rgba(255, 255, 255, 0.1);
                    color: #fff;
                }

                [data-inflow-lab-app] section:first-of-type button:not(.bg-emerald-700):hover,
                [data-inflow-lab-app] .bg-slate-950 button:not(.bg-emerald-600):hover {
                    background: rgba(255, 255, 255, 0.16);
                    border-color: rgba(255, 255, 255, 0.34);
                }

                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] button:not(.bg-emerald-700),
                [data-inflow-lab-mode="dashboard"] [data-dashboard-header] button:not(.bg-emerald-700):hover {
                    border-color: #cbd5e1;
                    background: #fff;
                    color: #0f172a;
                }

                [data-inflow-lab-app] .transition { transition: all 0.15s ease; }
                [data-inflow-lab-app] .hover\\:border-emerald-300:hover { border-color: #6ee7b7; }
                [data-inflow-lab-app] .hover\\:bg-emerald-50:hover { background: #ecfdf5; }
                [data-inflow-lab-app] .hover\\:bg-slate-50:hover { background: #f8fafc; }
                [data-inflow-lab-app] .hover\\:bg-slate-800:hover { background: #1e293b; }
                [data-inflow-lab-app] .hover\\:bg-emerald-800:hover { background: #065f46; }
                [data-inflow-lab-app] .hover\\:bg-emerald-700:hover { background: #047857; }
                [data-inflow-lab-app] .break-all { word-break: break-all; }
                [data-inflow-lab-app] .break-words { overflow-wrap: break-word; }
                [data-inflow-lab-app] .text-left { text-align: left; }
                [data-inflow-lab-app] .text-center { text-align: center; }
                [data-inflow-lab-app] .relative { position: relative; }
                [data-inflow-lab-app] .absolute { position: absolute; }
                [data-inflow-lab-app] .overflow-hidden { overflow: hidden; }

                [data-inflow-lab-app] table {
                    width: 100%;
                    border-collapse: collapse;
                }

                [data-inflow-lab-app] th,
                [data-inflow-lab-app] td {
                    border-bottom: 1px solid #e2e8f0;
                    text-align: left;
                }

                [data-inflow-lab-app] aside > div,
                [data-inflow-lab-app] [class*="rounded-lg"][class*="border"] {
                    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
                }

                @media (min-width: 640px) {
                    [data-inflow-lab-app] .sm\\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                    [data-inflow-lab-app] .sm\\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
                    [data-inflow-lab-app] .sm\\:flex-row { flex-direction: row; }
                    [data-inflow-lab-app] .sm\\:items-center { align-items: center; }
                    [data-inflow-lab-app] .sm\\:justify-between { justify-content: space-between; }
                    [data-inflow-lab-app] .sm\\:w-\\[290px\\] { width: 290px; }
                    [data-inflow-lab-app] .sm\\:px-6 { padding-left: 24px; padding-right: 24px; }
                    [data-inflow-lab-app] .sm\\:p-6 { padding: 24px; }
                    [data-inflow-lab-app] .sm\\:text-3xl { font-size: 30px; line-height: 36px; }
                }

                @media (min-width: 768px) {
                    [data-inflow-lab-app] .md\\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                    [data-inflow-lab-app] .md\\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
                    [data-inflow-lab-app] .md\\:grid-cols-5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
                }

                @media (min-width: 1024px) {
                    [data-inflow-lab-app] .lg\\:items-start { align-items: flex-start; }
                    [data-inflow-lab-app] .lg\\:flex-row { flex-direction: row; }
                    [data-inflow-lab-app] .lg\\:items-center { align-items: center; }
                    [data-inflow-lab-app] .lg\\:justify-between { justify-content: space-between; }
                    [data-inflow-lab-app] .lg\\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
                    [data-inflow-lab-app] .lg\\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
                    [data-inflow-lab-app] .lg\\:w-auto { width: auto; }
                    [data-inflow-lab-app] .lg\\:px-8 { padding-left: 32px; padding-right: 32px; }
                    [data-inflow-lab-app] .lg\\:min-w-\\[480px\\] { min-width: 480px; }
                    [data-inflow-lab-app] .lg\\:grid-cols-\\[minmax\\(0\\,1fr\\)_420px\\] {
                        grid-template-columns: minmax(0, 1fr) 420px;
                    }
                }

                @media (min-width: 1280px) {
                    [data-inflow-lab-app] .xl\\:grid-cols-\\[360px_minmax\\(0\\,1fr\\)\\] {
                        grid-template-columns: 360px minmax(0, 1fr);
                    }
                    [data-inflow-lab-app] .xl\\:grid-cols-\\[minmax\\(0\\,1fr\\)_380px\\] {
                        grid-template-columns: minmax(0, 1fr) 380px;
                    }
                }

                @media (max-width: 900px) {
                    [data-inflow-lab-app] > div {
                        padding: 14px;
                    }

                    [data-inflow-lab-app] section:first-of-type > div,
                    [data-inflow-lab-app] section:nth-of-type(2) {
                        grid-template-columns: 1fr;
                    }

                    [data-inflow-lab-app] section:first-of-type > div > div:last-child {
                        border-left: 0;
                        border-top: 1px solid rgba(255, 255, 255, 0.1);
                    }
                }
            `}</style>
            <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
                {isStandalone ? (
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
                                        disabled={isBusy}
                                    >
                                        <RefreshCcw className="mr-2 h-4 w-4" />
                                        Load demo scenario
                                    </Button>
                                    <Button
                                        className="h-10 bg-emerald-700 text-white hover:bg-emerald-800"
                                        onClick={runPipeline}
                                        disabled={isBusy}
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
                                        {fixture === "leafy_greens_trace" ? "Leafy greens trace" : "Fresh-cut transformation"}
                                    </div>
                                    <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2">
                                        <span className="block font-medium text-white">Source</span>
                                        {source}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>
                ) : (
                    <section data-dashboard-header className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                    <h1 className="text-2xl font-semibold tracking-normal text-slate-950">Inflow Lab</h1>
                                    <Badge className={cn("border", connectionTone)}>{connectionLabel}</Badge>
                                    <Badge className="border border-blue-200 bg-blue-50 text-blue-700">Mock records only</Badge>
                                </div>
                                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                                    Test inbound traceability data before it becomes production evidence. Load a demo fixture, verify the API handoff, trace lots, and prepare export filters from the command center.
                                </p>
                                <div className="mt-4 flex flex-wrap gap-2">
                                    <Button className="h-9 bg-emerald-700 text-white hover:bg-emerald-800" onClick={loadScenario} disabled={isBusy}>
                                        <RefreshCcw className="mr-2 h-4 w-4" />
                                        Load demo
                                    </Button>
                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={runPipeline} disabled={isBusy}>
                                        <Play className="mr-2 h-4 w-4" />
                                        Run pipeline
                                    </Button>
                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={traceLatestLot}>
                                        <Search className="mr-2 h-4 w-4" />
                                        Trace latest lot
                                    </Button>
                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={prepareExport} disabled={stageIndex[runStage] < 4}>
                                        <ArrowDownToLine className="mr-2 h-4 w-4" />
                                        Prepare export
                                    </Button>
                                </div>
                            </div>
                            <div className="grid min-w-0 gap-2 sm:grid-cols-3 lg:min-w-[480px]">
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                    <span className="block text-xs font-medium text-slate-500">Proxy route</span>
                                    <strong className="mt-1 block break-words font-mono text-[11px] text-slate-950">/api/inflow-lab</strong>
                                </div>
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                    <span className="block text-xs font-medium text-slate-500">Posted</span>
                                    <strong className="mt-1 block text-sm text-slate-950">{postedCount}</strong>
                                </div>
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                    <span className="block text-xs font-medium text-slate-500">Failed</span>
                                    <strong className="mt-1 block text-sm text-slate-950">{failedCount}</strong>
                                </div>
                            </div>
                        </div>
                    </section>
                )}

                {serviceError && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                        Inflow Lab service connection: {serviceError}
                    </div>
                )}

                <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
                    <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                        <CardHeader className="border-b border-slate-200 p-4">
                            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                <div>
                                    <CardTitle className="text-base font-semibold text-slate-950">Operational workspace</CardTitle>
                                    <p className="mt-1 text-sm text-slate-500">
                                        Review mock-generated records, trace lots, and prepare evidence filters without mixing simulator data into production imports.
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
                                                            <option value="leafy_greens_supplier">Leafy greens supplier</option>
                                                            <option value="fresh_cut_processor">Fresh-cut processor</option>
                                                            <option value="retailer_readiness_demo">Retailer readiness demo</option>
                                                        </select>
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Fixture
                                                        <select value={fixture} onChange={(event) => setFixture(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900">
                                                            <option value="leafy_greens_trace">Leafy greens trace</option>
                                                            <option value="fresh_cut_transformation">Fresh-cut transformation</option>
                                                            <option value="retailer_handoff">Retailer handoff</option>
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
                                                        <p className="mt-1 text-xs leading-5 text-slate-600">Harvest, cool, pack, ship, receive, validate, and export one safe demo scenario through the same API path.</p>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        <Button className="h-9 bg-emerald-700 text-white hover:bg-emerald-800" onClick={runPipeline}>
                                                            <Play className="mr-2 h-4 w-4" />
                                                            Start loop
                                                        </Button>
                                                        <Button variant="outline" className="h-9 border-slate-300 bg-white" disabled={isBusy}>
                                                            Stop
                                                        </Button>
                                                        <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={resetServiceState} disabled={isBusy}>
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
                                                            <div className="flex flex-col items-start gap-2">
                                                                <span className="text-xs font-medium text-slate-500">{lot.product}</span>
                                                                <LotReadinessPill ready={lot.complete} />
                                                            </div>
                                                            <p className="mt-3 break-words font-mono text-[11px] font-semibold leading-5 text-slate-950">{lot.lotCode}</p>
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
                                                                <option value="all_records">All records</option>
                                                                <option value="lot_trace">Lot trace</option>
                                                                <option value="shipment_handoff">Shipment handoff</option>
                                                                <option value="receiving_log">Receiving log</option>
                                                                <option value="transformation_batches">Transformation batches</option>
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
                                                        <Button asChild className="h-9 bg-emerald-600 text-white hover:bg-emerald-700">
                                                            <a href={csvExportHref}>Download CSV</a>
                                                        </Button>
                                                        <Button asChild variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                            <a href={epcisExportHref}>EPCIS JSON</a>
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
                                                <Button asChild className="mt-4 h-9 bg-emerald-700 text-white hover:bg-emerald-800">
                                                    <a href={csvExportHref}>Download CSV</a>
                                                </Button>
                                            </div>
                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <FileJson className="h-5 w-5 text-blue-700" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">GS1 EPCIS 2.0 JSON-LD</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Uses the same lot and date filters as the FDA package for interoperability testing.
                                                </p>
                                                <Button asChild variant="outline" className="mt-4 h-9 border-slate-300 bg-white">
                                                    <a href={epcisExportHref}>Download EPCIS</a>
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
                                                ["Source", source],
                                                ["Service build", health?.build?.commit_sha_short || health?.build?.version || "Not connected"],
                                                ["Retry queue", `${serviceStatus?.stats?.delivery?.failed || 0} failed deliveries`],
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
                                    ["Failed", String(serviceStatus?.stats?.delivery?.failed || 0)],
                                    ["Generated only", String(serviceStatus?.stats?.delivery?.generated || 0)],
                                    ["Attempts", String(serviceStatus?.stats?.delivery?.attempts || deliveredCount)],
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
