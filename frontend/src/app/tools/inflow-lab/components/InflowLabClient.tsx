"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { fetchWithCsrf } from "@/lib/fetch-with-csrf";
import { cn } from "@/lib/utils";

type RunStage = "loaded" | "generating" | "delivering" | "validating" | "complete" | "exported";
type EventStatus = "posted" | "validated" | "queued" | "generated" | "failed";
type CteState = "complete" | "missing";
type DeliveryState = "posted" | "generated" | "failed";
type LotReadinessState = "ready" | "warning" | "blocked";

type TraceEvent = {
    id: number;
    cte: string;
    lotCode: string;
    product: string;
    location: string;
    timestamp: string;
    mode: "simulation" | "uploaded";
    attempts: number;
    deliveryStatus: DeliveryState;
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

type SandboxEventEvaluation = {
    event_index: number;
    cte_type: string;
    traceability_lot_code: string;
    product_description: string;
    kde_errors: string[];
    rules_failed: number;
    rules_warned: number;
    compliant: boolean;
    blocking_defects?: {
        rule_title: string;
        severity: string;
        result: string;
        why_failed: string | null;
        remediation: string | null;
        category: string;
    }[];
    all_results?: {
        rule_title: string;
        severity: string;
        result: string;
        why_failed: string | null;
        remediation: string | null;
        category: string;
    }[];
};

type SandboxEvaluationResult = {
    total_events: number;
    compliant_events: number;
    non_compliant_events: number;
    total_kde_errors: number;
    total_rule_failures: number;
    submission_blocked: boolean;
    blocking_reasons: string[];
    duplicate_warnings?: string[];
    entity_warnings?: string[];
    normalizations?: { field: string; original: string; normalized: string; action_type: string }[];
    events: SandboxEventEvaluation[];
};

type FeederDiagnosis = {
    status: "clear" | "needs_work" | "blocked";
    headline: string;
    impact: string;
    buckets: { id: string; label: string; count: number; tone: "danger" | "warning" | "success" | "info" }[];
};

type FeederRemediationStep = {
    title: string;
    detail: string;
};

const INFLOW_API = "/api/inflow-lab";
const REQUIRED_CTES = ["harvesting", "cooling", "initial_packing", "shipping", "receiving"];
const SANDBOX_CTE_TYPES = [
    "harvesting",
    "cooling",
    "initial_packing",
    "first_land_based_receiving",
    "shipping",
    "receiving",
    "transformation",
];
const FEEDER_SAMPLE_CSV = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-FEED-001,Romaine Lettuce,120,cases,Valley Fresh Farms,2026-04-26T15:20:00Z,,,HARV-001
cooling,TLC-FEED-001,Romaine Lettuce,120,cases,Salinas Cooling Hub,2026-04-26T18:12:00Z,,,COOL-001
initial_packing,TLC-FEED-001,Romaine Lettuce,118,cases,Salinas Packhouse,2026-04-26T20:12:00Z,,,PACK-001
shipping,TLC-FEED-001,Romaine Lettuce,118,cases,Salinas Packout Dock,2026-04-26T22:41:00Z,Salinas Packhouse,Bay Area DC,BOL-001
receiving,TLC-FEED-001,Romaine Lettuce,118,cases,Bay Area DC,2026-04-27T02:04:00Z,Salinas Packout Dock,Bay Area DC,REC-001`;
const FEEDER_SAVED_RUN_KEY = "regengine:inflow-lab:last-feeder-run";

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
        deliveryStatus: record.delivery_status,
    };
}

function sandboxEventToTraceEvent(event: SandboxEventEvaluation): TraceEvent {
    return {
        id: event.event_index + 1,
        cte: event.cte_type,
        lotCode: event.traceability_lot_code || `row-${event.event_index + 1}`,
        product: event.product_description || "Uploaded traceability record",
        location: `Uploaded row ${event.event_index + 1}`,
        timestamp: formatServiceTime(new Date().toISOString()),
        mode: "uploaded",
        attempts: 1,
        deliveryStatus: event.compliant ? "posted" : "generated",
    };
}

function lineageByLotFromEvents(traceEvents: TraceEvent[]) {
    return traceEvents.reduce<Record<string, LineageNode[]>>((current, event) => {
        const lotEvents = traceEvents.filter((candidate) => candidate.lotCode === event.lotCode);
        current[event.lotCode] = toLineage(lotEvents);
        return current;
    }, {});
}

function formatCteLabel(cte: string) {
    if (cte === "receiving") return "DC receiving";
    return cte.replaceAll("_", " ");
}

function toLineage(eventsForLot: TraceEvent[]): LineageNode[] {
    const byCte = new Map(eventsForLot.map((event) => [event.cte, event]));
    return REQUIRED_CTES.map((cte) => {
        const event = byCte.get(cte);
        return {
            cte: formatCteLabel(cte),
            location: event?.location || "Not captured",
            time: event?.timestamp || "Missing CTE",
            state: event ? "complete" : "missing",
        };
    });
}

function getLotReadiness(lineage: LineageNode[], lotEvents: TraceEvent[]) {
    const completeCount = lineage.filter((node) => node.state === "complete").length;
    const totalCount = lineage.length;
    const failedDeliveries = lotEvents.filter((event) => event.deliveryStatus === "failed").length;
    const generatedOnly = lotEvents.filter((event) => event.deliveryStatus === "generated").length;
    const missingCtes = lineage.filter((node) => node.state === "missing").map((node) => node.cte);
    const hasCompleteLineage = totalCount > 0 && completeCount === totalCount;

    if (failedDeliveries > 0 || lotEvents.length === 0) {
        return {
            state: "blocked" as LotReadinessState,
            label: "blocked",
            completeCount,
            totalCount,
            missingCtes,
            deliveryLabel: failedDeliveries > 0 ? "delivery failed" : "no events",
            exportReady: false,
        };
    }

    if (!hasCompleteLineage || generatedOnly > 0) {
        return {
            state: "warning" as LotReadinessState,
            label: "exception",
            completeCount,
            totalCount,
            missingCtes,
            deliveryLabel: generatedOnly > 0 ? "generated only" : "posted",
            exportReady: false,
        };
    }

    return {
        state: "ready" as LotReadinessState,
        label: "test complete",
        completeCount,
        totalCount,
        missingCtes,
        deliveryLabel: "posted",
        exportReady: true,
    };
}

function summarizeFeederDiagnosis(result: SandboxEvaluationResult): FeederDiagnosis {
    const issueCount = result.total_kde_errors + result.total_rule_failures;
    const status: FeederDiagnosis["status"] = result.submission_blocked
        ? "blocked"
        : issueCount > 0 || result.non_compliant_events > 0
        ? "needs_work"
        : "clear";

    return {
        status,
        headline:
            status === "clear"
                ? "Sandbox diagnosis found no blocking fixes"
                : status === "blocked"
                ? "Sandbox diagnosis found blockers before mapping"
                : "Sandbox diagnosis found corrections before mapping",
        impact:
            status === "clear"
                ? "This test run can move into import mapping, but it is still not authenticated evidence."
                : "Correct the highlighted rows and fields before treating this source as a monitored authenticated feed.",
        buckets: [
            { id: "events", label: "Rows checked", count: result.total_events, tone: "info" },
            { id: "passed", label: "Rows passing", count: result.compliant_events, tone: "success" },
            { id: "kde", label: "KDE fixes", count: result.total_kde_errors, tone: result.total_kde_errors ? "warning" : "success" },
            { id: "rules", label: "Rule failures", count: result.total_rule_failures, tone: result.total_rule_failures ? "danger" : "success" },
        ],
    };
}

function buildFeederRemediationPlan(result: SandboxEvaluationResult): FeederRemediationStep[] {
    const steps: FeederRemediationStep[] = [];
    if (result.total_kde_errors > 0) {
        steps.push({
            title: "Correct missing KDE fields",
            detail: "Fill required lot, location, quantity, timestamp, and handoff fields in the source CSV before mapping.",
        });
    }
    if (result.total_rule_failures > 0) {
        steps.push({
            title: "Resolve failed FSMA checks",
            detail: "Review the failed row-level rules, fix source data, and rerun the sandbox diagnosis.",
        });
    }
    if (result.duplicate_warnings?.length || result.entity_warnings?.length) {
        steps.push({
            title: "Review duplicate and entity warnings",
            detail: "Confirm aliases, facility names, and duplicate rows before connecting an authenticated feed.",
        });
    }
    steps.push({
        title: "Map only after diagnosis",
        detail: "Use the test run to configure import mapping; production evidence still requires authenticated persisted records.",
    });
    return steps;
}

const standaloneTabs = ["Control room", "Data feeder", "Lots", "Lineage", "Exports", "Event log", "Diagnostics"];
const dashboardTabs = ["Overview", "Data feeder", "Lots", "Lineage", "Exports", "Record log", "Diagnostics"];

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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        deliveryStatus: "posted",
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
        generated: "border-amber-200 bg-amber-50 text-amber-700",
        failed: "border-amber-200 bg-amber-50 text-amber-800",
    };

    return (
        <span className={cn("inline-flex rounded-full border px-2 py-0.5 text-xs font-medium", styles[status])}>
            {status}
        </span>
    );
}

function LotReadinessPill({ state, label }: { state: LotReadinessState; label: string }) {
    const styles = {
        ready: "border-emerald-200 bg-emerald-50 text-emerald-700",
        warning: "border-amber-200 bg-amber-50 text-amber-700",
        blocked: "border-amber-200 bg-amber-50 text-amber-800",
    };

    return (
        <span className={cn("inline-flex rounded-full border px-2 py-0.5 text-xs font-medium", styles[state])}>
            {label}
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
    const primaryTab = isStandalone ? "Control room" : "Overview";
    const tabs = isStandalone ? standaloneTabs : dashboardTabs;
    const [activeTab, setActiveTab] = useState(primaryTab);
    const [selectedLot, setSelectedLot] = useState(lotCodes[0]);
    const [traceInput, setTraceInput] = useState(lotCodes[0]);
    const [runStage, setRunStage] = useState<RunStage>("complete");
    const [health, setHealth] = useState<InflowHealth | null>(null);
    const [serviceStatus, setServiceStatus] = useState<InflowStatus | null>(null);
    const [serviceEvents, setServiceEvents] = useState<TraceEvent[]>([]);
    const [serviceLineage, setServiceLineage] = useState<Record<string, LineageNode[]>>({});
    const [serviceError, setServiceError] = useState<string | null>(null);
    const [isBusy, setIsBusy] = useState(false);
    const [tenantId, setTenantId] = useState("mock-tenant");
    const [scenarioPreset, setScenarioPreset] = useState("leafy_greens_supplier");
    const [fixture, setFixture] = useState("leafy_greens_trace");
    const [deliveryMode, setDeliveryMode] = useState("mock");
    const [source, setSource] = useState("codex-simulator");
    const [exportPreset, setExportPreset] = useState("all_records");
    const [startDate, setStartDate] = useState("2026-04-26");
    const [endDate, setEndDate] = useState("2026-04-27");
    const [feederCsv, setFeederCsv] = useState(FEEDER_SAMPLE_CSV);
    const [feederResult, setFeederResult] = useState<SandboxEvaluationResult | null>(null);
    const [feederError, setFeederError] = useState<string | null>(null);
    const [feederSavedAt, setFeederSavedAt] = useState<string | null>(null);
    const [isFeederEvaluating, setIsFeederEvaluating] = useState(false);
    const feederFileInputRef = useRef<HTMLInputElement>(null);

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
    const selectedReadiness = getLotReadiness(selectedLineage, selectedEvents);
    const selectedCompleteCount = selectedReadiness.completeCount;
    const selectedIsExportReady = selectedReadiness.exportReady;
    const hasGeneratedRecords = runStage !== "loaded";
    const visibleEvents = hasGeneratedRecords ? activeEvents : [];
    const visibleEventStatus = serviceEvents.length ? "posted" : getEventStatus(runStage);
    const localDeliveryCounts = useMemo(
        () =>
            activeEvents.reduce(
                (counts, event) => {
                    counts.attempts += event.attempts;
                    if (event.deliveryStatus === "posted") counts.posted += 1;
                    if (event.deliveryStatus === "failed") counts.failed += 1;
                    if (event.deliveryStatus === "generated") counts.generated += 1;
                    return counts;
                },
                { posted: 0, failed: 0, generated: 0, attempts: 0 }
            ),
        [activeEvents]
    );
    const deliveredCount = serviceStatus?.stats?.delivery?.posted ?? localDeliveryCounts.posted;

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
            ? "Mock export filters prepared"
            : runStage === "complete"
                ? "Mock run complete"
                : runStage === "loaded"
                    ? "Mock scenario loaded"
                    : "Mock run in progress";

    const uniqueLots = useMemo(
        () =>
            Array.from(new Set(activeEvents.map((event) => event.lotCode))).map((lotCode) => {
                const lotEvents = activeEvents.filter((event) => event.lotCode === lotCode);
                const lineage = activeLineageByLot[lotCode] ?? toLineage(lotEvents);
                const product = lotEvents[0]?.product ?? "Unknown product";
                const readiness = getLotReadiness(lineage, lotEvents);
                return {
                    lotCode,
                    product,
                    events: lotEvents.length,
                    readiness,
                    missingCtes: readiness.missingCtes,
                    completeCount: readiness.completeCount,
                    totalCount: readiness.totalCount,
                    lastLocation: lotEvents[0]?.location ?? "No location",
                };
            }),
        [activeEvents, activeLineageByLot]
    );
    const exportReadyLots = uniqueLots.filter((lot) => lot.readiness.exportReady);
    const exceptionLots = uniqueLots.filter((lot) => !lot.readiness.exportReady);
    const warningLots = uniqueLots.filter((lot) => lot.readiness.state === "warning");
    const blockedLots = uniqueLots.filter((lot) => lot.readiness.state === "blocked");

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
        setActiveTab(primaryTab);
    };

    const runPipeline = async () => {
        setIsBusy(true);
        setRunStage("generating");
        setActiveTab(primaryTab);
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

    const evaluateFeederData = async () => {
        if (!feederCsv.trim()) {
            setFeederError("Paste CSV text or upload a CSV file before evaluating.");
            return;
        }

        setIsFeederEvaluating(true);
        setFeederError(null);
        try {
            const response = await fetchWithCsrf("/api/ingestion/api/v1/sandbox/evaluate", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ csv: feederCsv }),
            });

            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                const detail = typeof payload.detail === "string" ? payload.detail : `Sandbox evaluation failed: ${response.status}`;
                throw new Error(detail);
            }

            const result = (await response.json()) as SandboxEvaluationResult;
            const evaluatedEvents = result.events.map(sandboxEventToTraceEvent);
            setFeederResult(result);
            setFeederSavedAt(null);
            setServiceEvents(evaluatedEvents);
            setServiceLineage(lineageByLotFromEvents(evaluatedEvents));
            setServiceStatus(null);
            setRunStage("complete");
            setSource("sandbox-data-feeder");

            const firstLot = evaluatedEvents[0]?.lotCode;
            if (firstLot) {
                setSelectedLot(firstLot);
                setTraceInput(firstLot);
            }
        } catch (error) {
            setFeederError(error instanceof Error ? error.message : "Could not evaluate pasted data");
        } finally {
            setIsFeederEvaluating(false);
        }
    };

    const handleFeederFile = (file: File | null) => {
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            setFeederCsv(String(reader.result || ""));
            setFeederResult(null);
            setFeederSavedAt(null);
            setFeederError(null);
        };
        reader.onerror = () => setFeederError("Could not read the selected CSV file.");
        reader.readAsText(file);
    };

    const saveFeederRun = () => {
        if (!feederResult) return;
        const savedAt = new Date().toISOString();
        window.localStorage.setItem(
            FEEDER_SAVED_RUN_KEY,
            JSON.stringify({
                saved_at: savedAt,
                csv: feederCsv,
                result: feederResult,
                source: "inflow-lab-data-feeder",
            })
        );
        setFeederSavedAt(savedAt);
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
    const connectionLabel = engineConnected ? "Connection ready" : serviceError ? "Connection needs attention" : "Checking connection";
    const connectionTone = engineConnected ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-amber-200 bg-amber-50 text-amber-800";
    const postedCount = serviceStatus?.stats?.delivery?.posted ?? deliveredCount;
    const failedCount = serviceStatus?.stats?.delivery?.failed ?? localDeliveryCounts.failed;
    const generatedOnlyCount = serviceStatus?.stats?.delivery?.generated ?? localDeliveryCounts.generated;
    const attemptCount = serviceStatus?.stats?.delivery?.attempts ?? localDeliveryCounts.attempts;
    const totalLotCount = uniqueLots.length;
    const exceptionCount = exceptionLots.length + failedCount;
    const feederDefectCount = feederResult ? feederResult.total_kde_errors + feederResult.total_rule_failures : 0;
    const validationOutcome = feederResult
        ? feederDefectCount
            ? `${feederDefectCount} validation issue${feederDefectCount === 1 ? "" : "s"} found`
            : "No sandbox validation issues"
        : exceptionCount
        ? `${exceptionCount} exception${exceptionCount === 1 ? "" : "s"} to review`
        : "No blocking exceptions";
    const exportReadyCount = exportReadyLots.length;
    const exportReadinessLabel =
        totalLotCount > 0 ? `${exportReadyCount} of ${totalLotCount} lots test complete` : "No test records loaded";
    const lastReceivedLabel = serviceStatus?.stats?.delivery?.last_success_at
        ? formatServiceTime(serviceStatus.stats.delivery.last_success_at)
        : visibleEvents[0]?.timestamp || "No inbound records yet";
    const feederCteCoverage = useMemo(() => {
        const covered = new Set((feederResult?.events || []).map((event) => event.cte_type).filter(Boolean));
        return {
            covered: SANDBOX_CTE_TYPES.filter((cte) => covered.has(cte)),
            missing: SANDBOX_CTE_TYPES.filter((cte) => !covered.has(cte)),
        };
    }, [feederResult]);
    const feederDiagnosis = useMemo(() => (feederResult ? summarizeFeederDiagnosis(feederResult) : null), [feederResult]);
    const feederRemediationPlan = useMemo(() => (feederResult ? buildFeederRemediationPlan(feederResult) : []), [feederResult]);
    const activeDataBoundary = feederResult ? "Public sandbox diagnosis" : serviceEvents.length ? "Mock Inflow Lab feed" : "Bundled mock fixture";
    const boundarySteps = [
        {
            label: "Sandbox diagnosis",
            value: feederResult ? "CSV evaluated in this browser session" : "No sandbox run loaded",
            tone: "border-blue-200 bg-blue-50 text-blue-900",
        },
        {
            label: "Mock Inflow Lab",
            value: "Simulator and fixture data only; not production ingestion",
            tone: "border-amber-200 bg-amber-50 text-amber-950",
        },
        {
            label: "Authenticated feed",
            value: "Production monitoring starts after signed-in import mapping",
            tone: "border-slate-200 bg-white text-slate-900",
        },
        {
            label: "Production evidence",
            value: "Authenticated persisted records only",
            tone: "border-emerald-200 bg-emerald-50 text-emerald-950",
        },
    ];

    return (
        <main
            data-inflow-lab-app
            data-inflow-lab-mode={mode}
            className={cn("text-slate-950", isStandalone ? "min-h-screen bg-[#f6f8f5]" : "min-h-full bg-slate-50")}
        >
            <div
                data-dashboard-shell={!isStandalone ? true : undefined}
                className={cn(
                    "mx-auto flex w-full flex-col px-4 sm:px-6 lg:px-8",
                    isStandalone ? "max-w-[1480px] gap-5 py-5" : "max-w-none gap-4 py-4"
                )}
            >
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
                                        Diagnose CSV data, run a mock FSMA 204 feed, and keep test data separate from authenticated persisted records.
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
                                        Load mock scenario
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
                                        Preview export filters
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
                                        {deliveryMode === "mock" ? "Mock only" : "Live adapter disabled"}
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
                    <section data-dashboard-header className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm sm:p-4">
                        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                            <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                    <h1 className="text-xl font-semibold tracking-normal text-slate-950">Inflow Lab</h1>
                                    <Badge className={cn("border", connectionTone)}>{connectionLabel}</Badge>
                                    <Badge className="border border-amber-200 bg-amber-50 text-amber-800">Mock environment</Badge>
                                </div>
                                <p className="mt-1.5 max-w-3xl text-sm leading-6 text-slate-600">
                                    Validate sandbox and mock inbound data before production ingestion. Evidence is generated only from authenticated, persisted records outside this mock lab.
                                </p>
                                <div data-dashboard-actions className="mt-3 flex flex-wrap gap-2">
                                    <Button className="h-9 bg-emerald-700 text-white hover:bg-emerald-800" onClick={loadScenario} disabled={isBusy}>
                                        <RefreshCcw className="mr-2 h-4 w-4" />
                                        Load test data
                                    </Button>
                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={runPipeline} disabled={isBusy}>
                                        <Play className="mr-2 h-4 w-4" />
                                        Validate inbound data
                                    </Button>
                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={traceLatestLot}>
                                        <Search className="mr-2 h-4 w-4" />
                                        Trace latest lot
                                    </Button>
                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={prepareExport} disabled={stageIndex[runStage] < 4}>
                                        <ArrowDownToLine className="mr-2 h-4 w-4" />
                                        Preview export filters
                                    </Button>
                                </div>
                            </div>
                            <div className="grid min-w-0 gap-2 sm:grid-cols-3 lg:min-w-[480px]">
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                    <span className="block text-xs font-medium text-slate-500">Last inbound record</span>
                                    <strong className="mt-1 block text-sm text-slate-950">{lastReceivedLabel}</strong>
                                </div>
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                    <span className="block text-xs font-medium text-slate-500">Validation outcome</span>
                                    <strong className="mt-1 block text-sm text-slate-950">{validationOutcome}</strong>
                                </div>
                                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
                                    <span className="block text-xs font-medium text-slate-500">Test completeness</span>
                                    <strong className="mt-1 block text-sm text-slate-950">{exportReadinessLabel}</strong>
                                </div>
                            </div>
                        </div>
                    </section>
                )}

                <section
                    aria-label="Inflow Lab environment boundary"
                    className="rounded-lg border border-slate-300 bg-white p-3 shadow-sm sm:p-4"
                >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                                <Badge className="border border-slate-300 bg-slate-100 text-slate-900">Boundary active</Badge>
                                <span className="text-sm font-semibold text-slate-950">{activeDataBoundary}</span>
                            </div>
                            <p className="mt-1 text-xs leading-5 text-slate-600">
                                Sandbox rows and mock simulator events may diagnose, map, and monitor a source. They do not become production evidence. Evidence exports require an authenticated session and persisted tenant records.
                            </p>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2 lg:min-w-[620px] xl:grid-cols-4">
                            {boundarySteps.map((step) => (
                                <div key={step.label} className={cn("rounded-md border px-3 py-2", step.tone)}>
                                    <p className="text-[11px] font-semibold uppercase tracking-wide">{step.label}</p>
                                    <p className="mt-1 text-xs leading-4">{step.value}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>

                {serviceError && (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                        Inflow Lab service connection: {serviceError}
                    </div>
                )}

                <section className={cn("grid xl:grid-cols-[minmax(0,1fr)_380px]", isStandalone ? "gap-5" : "gap-4")}>
                    <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                        <CardHeader className={cn("border-b border-slate-200", isStandalone ? "p-4" : "p-3 sm:p-4")}>
                            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                                <div>
                                    <CardTitle className="text-base font-semibold text-slate-950">
                                        {isStandalone ? "Operational workspace" : "Inbound data readiness"}
                                    </CardTitle>
                                    <p className="mt-1 text-sm leading-5 text-slate-500">
                                        {isStandalone
                                            ? "Review mock-generated records, trace lots, and preview export filters without mixing simulator data into production imports."
                                            : "Validate FSMA 204 records, resolve exceptions, prove traceability, and keep production evidence limited to authenticated persisted records."}
                                    </p>
                                </div>
                                <div className="flex w-full flex-col gap-2 sm:flex-row lg:w-auto">
                                    <Input
                                        value={traceInput}
                                        onChange={(event) => setTraceInput(event.target.value)}
                                        className={cn("min-w-0 border-slate-300 text-xs sm:w-[290px]", isStandalone ? "h-10" : "h-9")}
                                        aria-label="Traceability lot code"
                                    />
                                    <Button onClick={traceLot} className={cn("bg-slate-950 text-white hover:bg-slate-800", isStandalone ? "h-10" : "h-9")}>
                                        <GitBranch className="mr-2 h-4 w-4" />
                                        Trace lot
                                    </Button>
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className={cn(isStandalone ? "p-4" : "p-3 sm:p-4")}>
                            <div>
                                <div className={cn("flex h-auto justify-start gap-1 rounded-md bg-slate-100 p-1", isStandalone ? "flex-wrap" : "overflow-x-auto")}>
                                    {tabs.map((tab) => (
                                        <button
                                            key={tab}
                                            type="button"
                                            onClick={() => setActiveTab(tab)}
                                            className={cn(
                                                "shrink-0 rounded-md px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-white/70 hover:text-slate-950",
                                                activeTab === tab && "bg-white text-slate-950 shadow-sm"
                                            )}
                                            aria-pressed={activeTab === tab}
                                        >
                                            {tab}
                                        </button>
                                    ))}
                                </div>

                                {activeTab === "Overview" && (
                                    <div className={cn("mt-4", isStandalone ? "space-y-4" : "space-y-3")}>
                                        <div className={cn("grid lg:grid-cols-3", isStandalone ? "gap-4" : "gap-3")}>
                                            <div className={cn("rounded-lg border border-slate-200 bg-white", isStandalone ? "p-4" : "p-3")}>
                                                <div className="flex items-center gap-2">
                                                    <CheckCircle2 className={cn("h-4 w-4", engineConnected ? "text-emerald-700" : "text-amber-600")} />
                                                    <p className="text-sm font-semibold text-slate-950">Connection status</p>
                                                </div>
                                                <p className="mt-2 text-sm text-slate-700">{connectionLabel}</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Test submissions are routed through the Inflow Lab gateway and remain outside production ingestion.
                                                </p>
                                            </div>

                                            <div className={cn("rounded-lg border", isStandalone ? "p-4" : "p-3", exceptionCount ? "border-amber-200 bg-amber-50/70" : "border-emerald-200 bg-emerald-50/70")}>
                                                <div className="flex items-center gap-2">
                                                    {exceptionCount ? (
                                                        <AlertTriangle className="h-4 w-4 text-amber-700" />
                                                    ) : (
                                                        <PackageCheck className="h-4 w-4 text-emerald-700" />
                                                    )}
                                                    <p className="text-sm font-semibold text-slate-950">Validation outcome</p>
                                                </div>
                                                <p className="mt-2 text-sm text-slate-700">{validationOutcome}</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Ready: {exportReadyCount}. Warning: {warningLots.length}. Blocked: {blockedLots.length}. Records need CTE coverage, KDE completeness, lineage, and posted delivery before export.
                                                </p>
                                            </div>

                                            <div className={cn("rounded-lg border border-slate-200 bg-white", isStandalone ? "p-4" : "p-3")}>
                                                <div className="flex items-center gap-2">
                                                    <FileSpreadsheet className="h-4 w-4 text-blue-700" />
                                                    <p className="text-sm font-semibold text-slate-950">Test completeness</p>
                                                </div>
                                                <p className="mt-2 text-sm text-slate-700">{exportReadinessLabel}</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Mock export previews use the selected lot and date window. Production evidence exports require authenticated persisted records.
                                                </p>
                                            </div>
                                        </div>

                                        <div className={cn("grid lg:grid-cols-2", isStandalone ? "gap-4" : "gap-3")}>
                                            <div className={cn("rounded-lg border border-slate-200 bg-white", isStandalone ? "p-4" : "p-3")}>
                                                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                                    <div>
                                                        <p className="text-sm font-semibold text-slate-950">Lot readiness</p>
                                                        <p className="mt-1 text-xs leading-5 text-slate-500">Select a lot to inspect the traceability path and required FSMA 204 events.</p>
                                                    </div>
                                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={() => setActiveTab("Lots")}>
                                                        Review lots
                                                    </Button>
                                                </div>
                                                <div className={cn("grid gap-3", isStandalone ? "mt-4" : "mt-3")}>
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
                                                                "rounded-lg border bg-white p-3 text-left transition hover:border-emerald-300",
                                                                lot.lotCode === selectedLot ? "border-emerald-400 shadow-sm" : "border-slate-200"
                                                            )}
                                                        >
                                                            <div className="flex items-start justify-between gap-3">
                                                                <div className="min-w-0">
                                                                    <p className="text-sm font-semibold text-slate-950">{lot.product}</p>
                                                                    <p className="mt-1 break-words font-mono text-[11px] text-slate-500">{lot.lotCode}</p>
                                                                </div>
                                                                <LotReadinessPill state={lot.readiness.state} label={lot.readiness.label} />
                                                            </div>
                                                            <p className="mt-2 text-xs text-slate-500">
                                                                CTE coverage {lot.completeCount} of {lot.totalCount}; delivery {lot.readiness.deliveryLabel}
                                                            </p>
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>

                                            <div className={cn(isStandalone ? "space-y-4" : "space-y-3")}>
                                                <div className={cn("rounded-lg border", isStandalone ? "p-4" : "p-3", exceptionLots.length ? "border-amber-200 bg-amber-50/70" : "border-slate-200 bg-white")}>
                                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                                                        <div>
                                                            <p className="text-sm font-semibold text-slate-950">Exceptions</p>
                                                            <p className="mt-1 text-xs leading-5 text-slate-500">
                                                                Partial lots remain visible for remediation instead of being hidden from the mock preview.
                                                            </p>
                                                        </div>
                                                        <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={() => setActiveTab("Lineage")}>
                                                            Trace selected lot
                                                        </Button>
                                                    </div>
                                                    <div className={cn("space-y-3", isStandalone ? "mt-4" : "mt-3")}>
                                                        {exceptionLots.length === 0 && failedCount === 0 ? (
                                                            <div className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                                                                No blocking exceptions found in the current test data.
                                                            </div>
                                                        ) : (
                                                            <>
                                                                {exceptionLots.map((lot) => (
                                                                    <div key={lot.lotCode} className="rounded-md border border-amber-200 bg-white px-3 py-2">
                                                                        <p className="text-xs font-semibold text-amber-950">{lot.product}</p>
                                                                        <p className="mt-1 break-words font-mono text-[11px] text-amber-800">{lot.lotCode}</p>
                                                                        <p className="mt-1 text-xs text-amber-800">
                                                                            {lot.missingCtes.length > 0
                                                                                ? `Missing KDE evidence for ${lot.missingCtes.join(", ")}.`
                                                                                : `Delivery ${lot.readiness.deliveryLabel}; not test complete.`}
                                                                        </p>
                                                                    </div>
                                                                ))}
                                                                {failedCount > 0 && (
                                                                    <div className="rounded-md border border-amber-200 bg-white px-3 py-2 text-xs text-amber-800">
                                                                        {failedCount} inbound delivery {failedCount === 1 ? "attempt needs" : "attempts need"} review.
                                                                    </div>
                                                                )}
                                                            </>
                                                        )}
                                                    </div>
                                                </div>

                                                <div className={cn("rounded-lg border border-slate-200 bg-slate-950 text-white", isStandalone ? "p-4" : "p-3")}>
                                                    <p className="text-sm font-semibold">Mock export preview</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-300">
                                                        Preview CSV or EPCIS JSON-LD filters for test data. Generate production evidence only from authenticated persisted records.
                                                    </p>
                                                    <div className={cn("grid grid-cols-1 gap-2 sm:grid-cols-2", isStandalone ? "mt-4" : "mt-3")}>
                                                        <Button asChild className="h-9 bg-emerald-600 text-white hover:bg-emerald-700">
                                                            <a href={csvExportHref}>Preview CSV</a>
                                                        </Button>
                                                        <Button asChild variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                            <a href={epcisExportHref}>Preview EPCIS</a>
                                                        </Button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Data feeder" && (
                                    <div className={cn("mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]", !isStandalone && "xl:grid-cols-[minmax(0,1fr)_340px]")}>
                                        <div className="rounded-lg border border-slate-200 bg-white p-4">
                                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                                <div>
                                                    <p className="text-sm font-semibold text-slate-950">Paste or upload inbound CSV</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-500">
                                                        Uses the public stateless sandbox evaluator. Data is parsed, normalized, and checked against FSMA 204 rules without being stored or promoted to production ingestion.
                                                    </p>
                                                </div>
                                                <div className="flex shrink-0 gap-2">
                                                    <input
                                                        ref={feederFileInputRef}
                                                        type="file"
                                                        accept=".csv,text/csv"
                                                        className="hidden"
                                                        aria-label="Upload feeder CSV"
                                                        onChange={(event) => handleFeederFile(event.target.files?.[0] ?? null)}
                                                    />
                                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={() => feederFileInputRef.current?.click()}>
                                                        <Upload className="mr-2 h-4 w-4" />
                                                        Upload CSV
                                                    </Button>
                                                </div>
                                            </div>
                                            <Textarea
                                                value={feederCsv}
                                                onChange={(event) => {
                                                    setFeederCsv(event.target.value);
                                                    setFeederResult(null);
                                                    setFeederSavedAt(null);
                                                    setFeederError(null);
                                                }}
                                                className="mt-4 min-h-[260px] resize-y border-slate-300 bg-slate-50 font-mono text-xs leading-5 text-slate-900"
                                                spellCheck={false}
                                                aria-label="Inbound CSV data"
                                            />
                                            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                                                <p className="text-xs leading-5 text-slate-500">
                                                    Best for ERP exports, supplier CSVs, and messy column names. The evaluator accepts up to 500 events per run.
                                                </p>
                                                <Button className="h-9 bg-emerald-700 text-white hover:bg-emerald-800" onClick={evaluateFeederData} disabled={isFeederEvaluating}>
                                                    {isFeederEvaluating ? (
                                                        <>
                                                            <RefreshCcw className="mr-2 h-4 w-4 animate-spin" />
                                                            Evaluating
                                                        </>
                                                    ) : (
                                                        <>
                                                            <Play className="mr-2 h-4 w-4" />
                                                            Evaluate data
                                                        </>
                                                    )}
                                                </Button>
                                            </div>
                                            {feederError && (
                                                <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                                                    {feederError}
                                                </div>
                                            )}
                                        </div>

                                        <div className="space-y-4">
                                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                                                <div className="flex items-center gap-2">
                                                    <ClipboardList className="h-4 w-4 text-blue-700" />
                                                    <p className="text-sm font-semibold text-slate-950">Feeder validation</p>
                                                </div>
                                                {feederResult ? (
                                                    <div className="mt-4 grid gap-3">
                                                        {[
                                                            ["Events evaluated", `${feederResult.total_events}`],
                                                            ["Compliant events", `${feederResult.compliant_events}`],
                                                            ["KDE errors", `${feederResult.total_kde_errors}`],
                                                            ["Rule failures", `${feederResult.total_rule_failures}`],
                                                        ].map(([label, value]) => (
                                                            <div key={label} className="flex items-center justify-between rounded-md border border-slate-200 bg-white px-3 py-2">
                                                                <span className="text-xs text-slate-500">{label}</span>
                                                                <strong className="text-sm text-slate-950">{value}</strong>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p className="mt-3 text-xs leading-5 text-slate-500">
                                                        Run the feeder to replace the predetermined mock records with evaluated CSV data in the lot, lineage, exception, and record log views.
                                                    </p>
                                                )}
                                            </div>

                                            {feederDiagnosis && (
                                                <div className={cn(
                                                    "rounded-lg border p-4",
                                                    feederDiagnosis.status === "blocked"
                                                        ? "border-amber-200 bg-amber-50"
                                                        : feederDiagnosis.status === "needs_work"
                                                        ? "border-blue-200 bg-blue-50"
                                                        : "border-emerald-200 bg-emerald-50"
                                                )}>
                                                    <div className="flex items-center gap-2">
                                                        {feederDiagnosis.status === "clear" ? (
                                                            <CheckCircle2 className="h-4 w-4 text-emerald-700" />
                                                        ) : (
                                                            <AlertTriangle className="h-4 w-4 text-amber-700" />
                                                        )}
                                                        <p className="text-sm font-semibold text-slate-950">What the feeder uncovered</p>
                                                    </div>
                                                    <p className="mt-2 text-sm font-semibold text-slate-900">{feederDiagnosis.headline}</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-600">{feederDiagnosis.impact}</p>
                                                    <div className="mt-3 grid grid-cols-2 gap-2">
                                                        {feederDiagnosis.buckets.map((bucket) => (
                                                            <div key={bucket.id} className="rounded-md border border-white/70 bg-white px-3 py-2">
                                                                <div className={cn(
                                                                    "font-mono text-base font-semibold",
                                                                    bucket.tone === "danger" ? "text-red-700" :
                                                                        bucket.tone === "warning" ? "text-amber-700" :
                                                                        bucket.tone === "success" ? "text-emerald-700" : "text-blue-700"
                                                                )}>
                                                                    {bucket.count}
                                                                </div>
                                                                <p className="text-[11px] font-semibold text-slate-700">{bucket.label}</p>
                                                            </div>
                                                        ))}
                                                    </div>
                                                    <div className="mt-3">
                                                        <p className="text-xs font-semibold text-slate-900">Correction plan</p>
                                                    </div>
                                                    <div className="mt-2 space-y-2">
                                                        {feederRemediationPlan.map((step, index) => (
                                                            <div key={step.title} className="grid grid-cols-[22px_minmax(0,1fr)] gap-2 rounded-md bg-white px-3 py-2">
                                                                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-100 text-[10px] font-semibold text-emerald-800">
                                                                    {index + 1}
                                                                </span>
                                                                <div>
                                                                    <p className="text-xs font-semibold text-slate-900">{step.title}</p>
                                                                    <p className="mt-0.5 text-[11px] leading-4 text-slate-600">{step.detail}</p>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}

                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <div className="flex items-center gap-2">
                                                    <PackageCheck className="h-4 w-4 text-emerald-700" />
                                                    <p className="text-sm font-semibold text-slate-950">7 CTE type coverage</p>
                                                </div>
                                                <p className="mt-2 text-sm text-slate-700">
                                                    {feederResult ? `${feederCteCoverage.covered.length} of ${SANDBOX_CTE_TYPES.length} CTE types present` : "Awaiting feeder run"}
                                                </p>
                                                <div className="mt-3 flex flex-wrap gap-2">
                                                    {SANDBOX_CTE_TYPES.map((cte) => {
                                                        const covered = feederCteCoverage.covered.includes(cte);
                                                        return (
                                                            <Badge
                                                                key={cte}
                                                                variant="outline"
                                                                className={cn(
                                                                    "border text-[10px] uppercase tracking-wide",
                                                                    covered ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-slate-200 bg-slate-50 text-slate-500"
                                                                )}
                                                            >
                                                                {formatCteLabel(cte)}
                                                            </Badge>
                                                        );
                                                    })}
                                                </div>
                                            </div>

                                            {feederResult?.blocking_reasons.length ? (
                                                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                                                    <div className="flex items-center gap-2">
                                                        <AlertTriangle className="h-4 w-4 text-amber-700" />
                                                        <p className="text-sm font-semibold text-amber-950">Blocking reasons</p>
                                                    </div>
                                                    <ul className="mt-3 space-y-2 text-xs leading-5 text-amber-900">
                                                        {feederResult.blocking_reasons.slice(0, 4).map((reason) => (
                                                            <li key={reason}>{reason}</li>
                                                        ))}
                                                    </ul>
                                                </div>
                                            ) : null}

                                            <div className="rounded-lg border border-slate-200 bg-slate-950 p-4 text-white">
                                                <div className="flex items-center gap-2">
                                                    <Truck className="h-4 w-4 text-emerald-300" />
                                                    <p className="text-sm font-semibold">Path to production</p>
                                                </div>
                                                <p className="mt-1 text-xs leading-5 text-slate-300">
                                                    Move from free diagnosis to a monitored feed without treating sandbox rows as production evidence.
                                                </p>
                                                <div className="mt-4 space-y-3">
                                                    {[
                                                        ["1", "Diagnose free", feederResult ? `${feederResult.total_events} events evaluated` : "Evaluate CSV first"],
                                                        ["2", "Save as test run", feederSavedAt ? `Saved ${formatServiceTime(feederSavedAt)}` : "Keep the sandbox result for handoff"],
                                                        ["3", "Convert to import mapping", "Turn headers and CTE aliases into an import setup"],
                                                        ["4", "Monitor live feed", "Watch connector health, failures, and exceptions"],
                                                        ["5", "Generate production evidence", "Use authenticated persisted records only"],
                                                    ].map(([step, title, detail]) => (
                                                        <div key={step} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
                                                            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-emerald-200">
                                                                {step}
                                                            </span>
                                                            <div>
                                                                <p className="text-xs font-semibold text-white">{title}</p>
                                                                <p className="mt-0.5 text-xs leading-5 text-slate-300">{detail}</p>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                                <div className="mt-4 grid gap-2">
                                                    <Button
                                                        className="h-9 bg-emerald-600 text-white hover:bg-emerald-700"
                                                        onClick={saveFeederRun}
                                                        disabled={!feederResult}
                                                    >
                                                        <ClipboardList className="mr-2 h-4 w-4" />
                                                        Save test run
                                                    </Button>
                                                    <Button asChild variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                        <Link href="/ingest">Convert to import mapping</Link>
                                                    </Button>
                                                    <Button asChild variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                        <Link href="/dashboard/integrations">Monitor live feed</Link>
                                                    </Button>
                                                    <Button asChild variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                        <Link href="/dashboard/export-jobs">Generate production evidence</Link>
                                                    </Button>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Control room" && isStandalone && (
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
                                                            <option value="retailer_readiness_demo">Retailer handoff test</option>
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
                                                            <option value="mock">Mock only</option>
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
                                                <p className="mt-1 text-xs leading-5 text-slate-500">Stage scheduled events or replace the mock fixture during local testing.</p>
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
                                                        <p className="mt-1 text-xs leading-5 text-slate-600">Harvest, cool, pack, ship, and receive one mock scenario through the test gateway. Production evidence stays in authenticated export jobs.</p>
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
                                                                <LotReadinessPill state={lot.readiness.state} label={lot.readiness.label} />
                                                            </div>
                                                            <p className="mt-3 break-words font-mono text-[11px] font-semibold leading-5 text-slate-950">{lot.lotCode}</p>
                                                            <p className="mt-2 text-xs text-slate-500">
                                                                {lot.completeCount}/{lot.totalCount} CTEs captured - delivery {lot.readiness.deliveryLabel}
                                                            </p>
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
                                                    <p className="text-sm font-semibold">Mock export preview</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-300">
                                                        {exportReadyCount} lots are test complete. {exceptionLots.length} exception lots remain visible. Production evidence requires authenticated persisted records.
                                                    </p>
                                                    <div className="mt-4 grid grid-cols-2 gap-2">
                                                        <Button asChild className="h-9 bg-emerald-600 text-white hover:bg-emerald-700">
                                                            <a href={csvExportHref}>Preview CSV</a>
                                                        </Button>
                                                        <Button asChild variant="outline" className="h-9 border-white/20 bg-white/10 text-white hover:bg-white/15">
                                                            <a href={epcisExportHref}>Preview EPCIS</a>
                                                        </Button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {(activeTab === "Event log" || activeTab === "Record log") && (
                                    <div className="mt-4">
                                        {visibleEvents.length === 0 ? (
                                            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
                                                <ClipboardList className="mx-auto h-8 w-8 text-slate-400" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">
                                                    {isStandalone ? "Mock scenario loaded" : "No inbound records loaded"}
                                                </p>
                                                <p className="mt-1 text-sm text-slate-500">
                                                    {isStandalone
                                                        ? "Run the pipeline to generate FSMA 204 traceability records."
                                                        : "Load test data to validate FSMA 204 records before production ingestion."}
                                                </p>
                                            </div>
                                        ) : (
                                            <Table data-inflow-table>
                                                <TableHeader>
                                                    <TableRow className="border-slate-200 bg-slate-50 hover:bg-slate-50">
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>#</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>CTE</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>Lot code</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>Product</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>Location</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>Timestamp</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>{isStandalone ? "Mode" : "Source type"}</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>Attempts</TableHead>
                                                        <TableHead className={cn("px-3 text-xs", isStandalone ? "h-10" : "h-9")}>Status</TableHead>
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
                                                            <TableCell className={cn("px-3 text-xs text-slate-500", isStandalone ? "py-3" : "py-2")}>{event.id}</TableCell>
                                                            <TableCell className={cn("px-3 text-xs font-medium text-slate-900", isStandalone ? "py-3" : "py-2")}>{event.cte}</TableCell>
                                                            <TableCell className={cn("px-3", isStandalone ? "py-3" : "py-2")}>
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
                                                            <TableCell className={cn("px-3 text-xs text-slate-700", isStandalone ? "py-3" : "py-2")}>{event.product}</TableCell>
                                                            <TableCell className={cn("px-3 text-xs text-slate-700", isStandalone ? "py-3" : "py-2")}>{event.location}</TableCell>
                                                            <TableCell className={cn("px-3 text-xs text-slate-600", isStandalone ? "py-3" : "py-2")}>{event.timestamp}</TableCell>
                                                            <TableCell className={cn("px-3 text-xs text-slate-600", isStandalone ? "py-3" : "py-2")}>
                                                                {isStandalone ? event.mode : "Test data"}
                                                            </TableCell>
                                                            <TableCell className={cn("px-3 text-xs text-slate-600", isStandalone ? "py-3" : "py-2")}>{event.attempts}</TableCell>
                                                            <TableCell className={cn("px-3", isStandalone ? "py-3" : "py-2")}>
                                                                <StatusPill status={serviceEvents.length ? event.deliveryStatus : visibleEventStatus} />
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
                                        <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 p-4">
                                            <p className="text-sm font-semibold text-slate-950">Lot acceptance criteria</p>
                                            <div className="mt-3 grid gap-3 md:grid-cols-3">
                                                <div className="rounded-md border border-emerald-200 bg-white px-3 py-2">
                                                    <p className="text-xs font-semibold text-emerald-700">Ready</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-600">
                                                        Required CTEs captured, KDE-bearing events posted, lineage complete, included in test-complete counts.
                                                    </p>
                                                </div>
                                                <div className="rounded-md border border-amber-200 bg-white px-3 py-2">
                                                    <p className="text-xs font-semibold text-amber-700">Warning</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-600">
                                                        Partial CTE/KDE coverage or generated-only delivery; visible as an exception and excluded from ready counts.
                                                    </p>
                                                </div>
                                                <div className="rounded-md border border-amber-200 bg-white px-3 py-2">
                                                    <p className="text-xs font-semibold text-amber-800">Blocked</p>
                                                    <p className="mt-1 text-xs leading-5 text-slate-600">
                                                        Failed delivery or no traceability events; cannot be exported until delivery and lineage are corrected.
                                                    </p>
                                                </div>
                                            </div>
                                        </div>
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
                                                        <PackageCheck
                                                            className={cn(
                                                                "h-5 w-5",
                                                                lot.readiness.exportReady ? "text-emerald-700" : "text-amber-600"
                                                            )}
                                                        />
                                                        <LotReadinessPill state={lot.readiness.state} label={lot.readiness.label} />
                                                    </div>
                                                    <p className="mt-3 font-mono text-xs font-semibold text-slate-950">{lot.lotCode}</p>
                                                    <p className="mt-2 text-sm font-medium text-slate-800">{lot.product}</p>
                                                    <p className="mt-1 text-xs text-slate-500">
                                                        CTE coverage {lot.completeCount} of {lot.totalCount}; delivery {lot.readiness.deliveryLabel}; last seen at {lot.lastLocation}
                                                    </p>
                                                    {lot.missingCtes.length > 0 && (
                                                        <p className="mt-2 text-xs text-amber-700">Missing KDE evidence: {lot.missingCtes.join(", ")}</p>
                                                    )}
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
                                                        CTE coverage {selectedCompleteCount} of {selectedLineage.length}; delivery {selectedReadiness.deliveryLabel}.
                                                    </p>
                                                </div>
                                                <LotReadinessPill state={selectedReadiness.state} label={selectedReadiness.label} />
                                            </div>
                                            {!selectedIsExportReady && (
                                                <div className="mt-4 rounded-md border border-amber-200 bg-white px-3 py-2 text-xs text-amber-800">
                                                    {selectedReadiness.missingCtes.length > 0
                                                        ? `Capture missing KDE evidence for ${selectedReadiness.missingCtes.join(", ")} before this lot is counted as test complete.`
                                                        : "Resolve delivery status before this lot is counted as test complete."}
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
                                                Selected lot is an exception. Test-complete counts include only complete mock lots; this lot stays visible until missing CTE/KDE evidence or delivery issues are resolved.
                                            </div>
                                        )}
                                        <div className="grid gap-3 md:grid-cols-2">
                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <FileSpreadsheet className="h-5 w-5 text-emerald-700" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">CSV filter preview</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Includes {exportReadyCount} test-complete lots. {exceptionLots.length} exception lots are flagged for review. Production evidence is generated only from authenticated persisted records.
                                                </p>
                                                <Button asChild className="mt-4 h-9 bg-emerald-700 text-white hover:bg-emerald-800">
                                                    <a href={csvExportHref}>Preview CSV</a>
                                                </Button>
                                            </div>
                                            <div className="rounded-lg border border-slate-200 bg-white p-4">
                                                <FileJson className="h-5 w-5 text-blue-700" />
                                                <p className="mt-3 text-sm font-semibold text-slate-950">EPCIS JSON-LD filter preview</p>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Uses the same lot and date filters for interoperability testing. It is not production evidence.
                                                </p>
                                                <Button asChild variant="outline" className="mt-4 h-9 border-slate-300 bg-white">
                                                    <a href={epcisExportHref}>Preview EPCIS</a>
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                )}

                                {activeTab === "Diagnostics" && (
                                    <div className="mt-4">
                                        {!isStandalone && (
                                            <div className="mb-3 rounded-lg border border-slate-200 bg-white p-4">
                                                <div className="flex items-center gap-2">
                                                    <SlidersHorizontal className="h-4 w-4 text-slate-700" />
                                                    <p className="text-sm font-semibold text-slate-950">Test data controls</p>
                                                </div>
                                                <p className="mt-1 text-xs leading-5 text-slate-500">
                                                    Fixture and source settings are kept here for implementation review; the main workflow stays focused on validation and evidence.
                                                </p>
                                                <div className="mt-4 grid gap-3 md:grid-cols-2">
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Tenant
                                                        <Input value={tenantId} onChange={(event) => setTenantId(event.target.value)} className="mt-1 h-9 bg-white" />
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Source
                                                        <Input value={source} onChange={(event) => setSource(event.target.value)} className="mt-1 h-9 bg-white" />
                                                    </label>
                                                    <label className="block text-xs font-medium text-slate-600">
                                                        Test scenario
                                                        <select value={scenarioPreset} onChange={(event) => setScenarioPreset(event.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900">
                                                            <option value="leafy_greens_supplier">Leafy greens supplier</option>
                                                            <option value="fresh_cut_processor">Fresh-cut processor</option>
                                                            <option value="retailer_readiness_demo">Retailer handoff test</option>
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
                                                            <option value="mock">Test gateway</option>
                                                            <option value="live">Live adapter disabled</option>
                                                        </select>
                                                    </label>
                                                </div>
                                                <div className="mt-4 flex flex-wrap gap-2">
                                                    <Button className="h-9 bg-emerald-700 text-white hover:bg-emerald-800" onClick={loadScenario} disabled={isBusy}>
                                                        <RefreshCcw className="mr-2 h-4 w-4" />
                                                        Load test data
                                                    </Button>
                                                    <Button variant="outline" className="h-9 border-slate-300 bg-white" onClick={resetServiceState} disabled={isBusy}>
                                                        Reset test state
                                                    </Button>
                                                </div>
                                            </div>
                                        )}
                                        <div className="grid gap-3 md:grid-cols-2">
                                            {[
                                                ["Auth", isStandalone ? "Off for local simulation" : "Dashboard session"],
                                                ["Storage", isStandalone ? "Local JSONL" : "Test data store"],
                                                ["Persist path", "data/events.jsonl"],
                                                ["Source", source],
                                                ["Service build", health?.build?.commit_sha_short || health?.build?.version || "Not connected"],
                                                ["Exception queue", `${serviceStatus?.stats?.delivery?.failed || 0} failed deliveries`],
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
                                    <LotReadinessPill state={selectedReadiness.state} label={selectedReadiness.label} />
                                </div>
                                <p className="mt-2 text-xs text-slate-500">
                                    CTE coverage {selectedCompleteCount} of {selectedLineage.length}; delivery {selectedReadiness.deliveryLabel}
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
                                    {isStandalone ? "Delivery monitor" : "Inbound validation"}
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-3 p-4">
                                {(isStandalone
                                    ? [
                                          ["Posted", String(deliveredCount)],
                                          ["Failed", String(failedCount)],
                                          ["Generated only", String(generatedOnlyCount)],
                                          ["Attempts", String(attemptCount)],
                                      ]
                                    : [
                                          ["Accepted records", String(postedCount)],
                                          ["Exceptions", String(exceptionCount)],
                                          ["Lots reviewed", String(totalLotCount)],
                                          ["Export-ready lots", String(exportReadyCount)],
                                      ]
                                ).map(([label, value]) => (
                                    <div key={label} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2">
                                        <span className="text-xs text-slate-500">{label}</span>
                                        <span className="text-sm font-semibold text-slate-950">{value}</span>
                                    </div>
                                ))}
                                {isStandalone ? (
                                    <Button variant="outline" className="mt-1 h-9 w-full border-slate-300 bg-white">
                                        <RotateCcw className="mr-2 h-4 w-4" />
                                        Retry failed deliveries
                                    </Button>
                                ) : (
                                    <Button variant="outline" className="mt-1 h-9 w-full border-slate-300 bg-white" onClick={() => setActiveTab("Diagnostics")}>
                                        <SlidersHorizontal className="mr-2 h-4 w-4" />
                                        Test data settings
                                    </Button>
                                )}
                            </CardContent>
                        </Card>

                        {isStandalone ? (
                            <>
                                <Card className="rounded-lg border-amber-200 bg-amber-50/70 shadow-sm">
                                    <CardContent className="flex gap-3 p-4">
                                        <Info className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                                        <div>
                                            <p className="text-sm font-semibold text-amber-950">Local simulation</p>
                                            <p className="mt-1 text-xs leading-5 text-amber-800">
                                                This mock lab writes local events and validates the FSMA record shape before an authenticated feed is enabled.
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
                            </>
                        ) : (
                            <Card className="rounded-lg border-slate-200 bg-white shadow-sm">
                                <CardHeader className="border-b border-slate-200 p-4">
                                    <CardTitle className="flex items-center gap-2 text-base font-semibold text-slate-950">
                                        <CalendarDays className="h-4 w-4 text-slate-700" />
                                        Evidence filters
                                    </CardTitle>
                                </CardHeader>
                                <CardContent className="space-y-3 p-4">
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
                                        Start date
                                        <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="mt-1 h-9 bg-white" />
                                    </label>
                                    <label className="block text-xs font-medium text-slate-600">
                                        End date
                                        <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="mt-1 h-9 bg-white" />
                                    </label>
                                </CardContent>
                            </Card>
                        )}
                    </aside>
                </section>
            </div>
        </main>
    );
}
