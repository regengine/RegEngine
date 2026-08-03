"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
    AlertTriangle,
    CheckCircle2,
    ChevronRight,
    ClipboardList,
    Lightbulb,
    Lock,
    Mail,
    Package,
    Play,
    RefreshCcw,
    Settings2,
    Upload,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { fetchWithCsrf } from "@/lib/fetch-with-csrf";
import { useAuth } from "@/lib/auth-context";
import { hasPermission } from "@/lib/permissions";
import { useTenant } from "@/lib/tenant-context";
import { cn } from "@/lib/utils";

import {
    classifyExceptionLot,
    groupExceptionsByPattern,
    summarizeSourceSuppliers,
    type ExceptionPatternId,
} from "../lib/exception-grouping";

type CteState = "complete" | "missing";
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
    deliveryStatus: "posted" | "generated" | "failed";
    supplier?: string;
    cases?: number;
};

type LineageNode = {
    cte: string;
    location: string;
    time: string;
    state: CteState;
};

type OptionalOfflinePayload = {
    available?: boolean;
    offline?: boolean;
    detail?: string;
};

type InflowHealth = OptionalOfflinePayload & { ok?: boolean; build?: { version?: string; commit_sha_short?: string } };

type InflowStatus = OptionalOfflinePayload & {
    running?: boolean;
    config?: { source?: string; scenario?: string; delivery?: { mode?: string; tenant_id?: string | null } };
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

function optionalOfflineDetail(...payloads: OptionalOfflinePayload[]) {
    const offline = payloads.find((payload) => payload.offline || payload.available === false);
    return offline ? offline.detail || "Inflow Lab service unavailable" : null;
}

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
    events: SandboxEventEvaluation[];
};

type ReadinessSummary = {
    score: number;
    label: string;
    components: { id: string; label: string; score: number; detail: string }[];
};

type WorkbenchFixQueueItem = {
    id: string;
    status: "open" | "waiting" | "corrected" | "accepted";
};

type WorkbenchCommitGate = {
    mode: "simulation" | "preflight" | "staging" | "production_evidence";
    allowed: boolean;
    export_eligible: boolean;
    reasons: string[];
    next_state: string;
};

type WorkbenchRun = {
    run_id: string;
    tenant_id: string;
    source: string;
    readiness: ReadinessSummary;
    fix_queue: WorkbenchFixQueueItem[];
    commit_gate: WorkbenchCommitGate;
    saved_at: string;
};

type WorkbenchRequestError = Error & { status?: number };

const INFLOW_API = "/api/inflow-lab";
const WORKBENCH_API = "/api/ingestion/api/v1/inflow-workbench";
const REQUIRED_CTES = ["harvesting", "cooling", "initial_packing", "shipping", "receiving"];
const REALISTIC_SAMPLE_CSV = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,ship_from_location,ship_to_location,reference_document
harvesting,TLC-SBX-20260506-021,Spring Mix,184,cases,Riverbend Organics,2026-05-06T11:52:00Z,,,HARV-021
cooling,TLC-SBX-20260506-021,Spring Mix,184,cases,Salinas Cooling Hub,2026-05-06T12:49:00Z,,,COOL-021
initial_packing,TLC-SBX-20260506-021,Spring Mix,182,cases,GreenLeaf Packing House,2026-05-06T14:31:00Z,,,PACK-021
shipping,TLC-SBX-20260506-021,Spring Mix,182,cases,GreenLeaf Shipping Dock,2026-05-06T18:06:00Z,GreenLeaf Packing House,North Bay DC,BOL-021
receiving,TLC-SBX-20260506-021,Spring Mix,182,cases,North Bay DC,2026-05-07T01:14:00Z,GreenLeaf Shipping Dock,North Bay DC,REC-021`;
const EXPLAINER_STEPS = [
    {
        title: "What goes in",
        detail: "Supplier CSV rows with lot codes, CTE timestamps, facilities, and shipping references.",
    },
    {
        title: "What the machine does",
        detail: "Normalizes row formats, reconstructs each lot lifecycle, and groups the missing KDE or handoff defects.",
    },
    {
        title: "What comes out",
        detail: "A readiness score, a fix queue by pattern, and a lot-by-lot trace that shows where evidence dropped.",
    },
] as const;
const DEFAULT_PROOF_INPUTS = [
    "Harvest timestamp from supplier field team",
    "Cooling confirmation from pre-cool facility",
    "Packing and shipping handoff from pack house",
    "DC receiving confirmation before export staging",
] as const;
const FILTER_CHIPS: { id: "all" | ExceptionPatternId; label: string }[] = [
    { id: "all", label: "all" },
    { id: "handoff", label: "handoff" },
    { id: "source", label: "source" },
    { id: "mixed", label: "mixed" },
];

function buildPreviewTraceEvent({
    id,
    cte,
    lotCode,
    product,
    location,
    timestamp,
    supplier,
    cases,
}: {
    id: number;
    cte: string;
    lotCode: string;
    product: string;
    location: string;
    timestamp: string;
    supplier: string;
    cases: number;
}): TraceEvent {
    return {
        id,
        cte,
        lotCode,
        product,
        location,
        timestamp: formatServiceTime(timestamp),
        mode: "simulation",
        attempts: 1,
        deliveryStatus: "posted",
        supplier,
        cases,
    };
}

const PREVIEW_TRACE_EVENTS: TraceEvent[] = [
    buildPreviewTraceEvent({
        id: 25,
        cte: "harvesting",
        lotCode: "TLC-20260508-000021",
        product: "Spring Mix",
        location: "Riverbend Organics",
        timestamp: "2026-05-06T11:52:00.000Z",
        supplier: "Riverbend Organics",
        cases: 182,
    }),
    buildPreviewTraceEvent({
        id: 24,
        cte: "cooling",
        lotCode: "TLC-20260508-000021",
        product: "Spring Mix",
        location: "Salinas Cooling Hub",
        timestamp: "2026-05-06T12:49:00.000Z",
        supplier: "Riverbend Organics",
        cases: 182,
    }),
    buildPreviewTraceEvent({
        id: 23,
        cte: "initial_packing",
        lotCode: "TLC-20260508-000021",
        product: "Spring Mix",
        location: "GreenLeaf Packing House",
        timestamp: "2026-05-06T14:31:00.000Z",
        supplier: "Riverbend Organics",
        cases: 182,
    }),
    buildPreviewTraceEvent({
        id: 22,
        cte: "shipping",
        lotCode: "TLC-20260508-000021",
        product: "Spring Mix",
        location: "GreenLeaf Shipping Dock",
        timestamp: "2026-05-06T18:06:00.000Z",
        supplier: "Riverbend Organics",
        cases: 182,
    }),
    buildPreviewTraceEvent({
        id: 21,
        cte: "receiving",
        lotCode: "TLC-20260508-000021",
        product: "Spring Mix",
        location: "North Bay DC",
        timestamp: "2026-05-07T01:14:00.000Z",
        supplier: "Riverbend Organics",
        cases: 182,
    }),
    buildPreviewTraceEvent({
        id: 18,
        cte: "harvesting",
        lotCode: "TLC-20260508-000022",
        product: "Green Leaf Lettuce",
        location: "Valley Fresh Farms",
        timestamp: "2026-05-07T10:18:00.000Z",
        supplier: "Valley Fresh Farms",
        cases: 156,
    }),
    buildPreviewTraceEvent({
        id: 17,
        cte: "cooling",
        lotCode: "TLC-20260508-000022",
        product: "Green Leaf Lettuce",
        location: "Salinas Cooling Hub",
        timestamp: "2026-05-07T11:02:00.000Z",
        supplier: "Valley Fresh Farms",
        cases: 156,
    }),
    buildPreviewTraceEvent({
        id: 16,
        cte: "initial_packing",
        lotCode: "TLC-20260508-000022",
        product: "Green Leaf Lettuce",
        location: "GreenLeaf Packing House",
        timestamp: "2026-05-07T13:20:00.000Z",
        supplier: "Valley Fresh Farms",
        cases: 154,
    }),
    buildPreviewTraceEvent({
        id: 13,
        cte: "initial_packing",
        lotCode: "TLC-20260508-000023",
        product: "Romaine Lettuce",
        location: "GreenLeaf Packing House",
        timestamp: "2026-05-07T08:42:00.000Z",
        supplier: "Desert Bloom Farms",
        cases: 204,
    }),
    buildPreviewTraceEvent({
        id: 12,
        cte: "shipping",
        lotCode: "TLC-20260508-000023",
        product: "Romaine Lettuce",
        location: "GreenLeaf Shipping Dock",
        timestamp: "2026-05-07T12:11:00.000Z",
        supplier: "Desert Bloom Farms",
        cases: 204,
    }),
    buildPreviewTraceEvent({
        id: 11,
        cte: "receiving",
        lotCode: "TLC-20260508-000023",
        product: "Romaine Lettuce",
        location: "Sacramento DC",
        timestamp: "2026-05-07T19:08:00.000Z",
        supplier: "Desert Bloom Farms",
        cases: 204,
    }),
];

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

async function workbenchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    if (!headers.has("content-type")) {
        headers.set("content-type", "application/json");
    }
    const response = await fetchWithCsrf(`${WORKBENCH_API}${path}`, {
        cache: "no-store",
        ...init,
        headers,
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        const error = new Error(
            payload.error || payload.detail || `Inflow Workbench request failed: ${response.status}`,
        ) as WorkbenchRequestError;
        error.status = response.status;
        throw error;
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

function formatCteLabel(cte: string) {
    if (cte === "receiving") return "DC receiving";
    return cte.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
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

function toLineage(eventsForLot: TraceEvent[]): LineageNode[] {
    const byCte = new Map(eventsForLot.map((event) => [event.cte, event]));
    return REQUIRED_CTES.map((cte) => {
        const event = byCte.get(cte);
        return {
            cte: formatCteLabel(cte),
            location: event?.location || "Not captured",
            time: event?.timestamp || "Missing CTE",
            state: event ? ("complete" as const) : ("missing" as const),
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

type LotSummary = ReturnType<typeof buildLotSummary>;

function buildLotSummary(lotCode: string, lotEvents: TraceEvent[], lineage: LineageNode[]) {
    const product = lotEvents[0]?.product ?? "Unknown product";
    const supplier = lotEvents[0]?.supplier ?? null;
    const cases = lotEvents[0]?.cases ?? null;
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
        supplier: supplier ?? undefined,
        cases: cases ?? undefined,
    };
}

function FilterChip({
    label,
    active,
    onClick,
}: {
    label: string;
    active: boolean;
    onClick: () => void;
}) {
    return (
        <button
            type="button"
            onClick={onClick}
            className={cn(
                "rounded-md border px-2 py-0.5 font-mono text-[11px] uppercase tracking-wide transition-colors",
                active
                    ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                    : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50"
            )}
        >
            {label}
        </button>
    );
}

function StackedBar({ value, tone }: { value: number; tone: "ok" | "warn" | "bad" | "locked" }) {
    const toneClass = {
        ok: "bg-emerald-500",
        warn: "bg-amber-500",
        bad: "bg-rose-500",
        locked: "bg-slate-300",
    }[tone];
    return (
        <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
            <div className={cn("h-full", toneClass)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
        </div>
    );
}

export function DashboardInflowLab({ previewMode = false }: { previewMode?: boolean }) {
    const { isAuthenticated, isHydrated, user } = useAuth();
    const { tenantId: activeTenantId } = useTenant();

    const [tenantId, setTenantId] = useState("mock-tenant");
    const [serviceEvents, setServiceEvents] = useState<TraceEvent[]>([]);
    const [serviceLineage, setServiceLineage] = useState<Record<string, LineageNode[]>>({});
    const [serviceStatus, setServiceStatus] = useState<InflowStatus | null>(null);
    const [health, setHealth] = useState<InflowHealth | null>(null);
    const [serviceError, setServiceError] = useState<string | null>(null);
    const [selectedLot, setSelectedLot] = useState<string | null>(null);
    const [feederCsv, setFeederCsv] = useState("");
    const [feederResult, setFeederResult] = useState<SandboxEvaluationResult | null>(null);
    const [feederError, setFeederError] = useState<string | null>(null);
    const [isFeederEvaluating, setIsFeederEvaluating] = useState(false);
    const [backendReadiness, setBackendReadiness] = useState<ReadinessSummary | null>(null);
    const [isSavingRun, setIsSavingRun] = useState(false);
    const [savedRun, setSavedRun] = useState<WorkbenchRun | null>(null);
    const [loadedRun, setLoadedRun] = useState<WorkbenchRun | null>(null);
    const [workbenchSaveNote, setWorkbenchSaveNote] = useState<string | null>(null);
    const [workbenchSaveError, setWorkbenchSaveError] = useState<string | null>(null);
    const [activeFilter, setActiveFilter] = useState<"all" | ExceptionPatternId>("all");
    const [openGroups, setOpenGroups] = useState<Record<ExceptionPatternId, boolean>>({
        handoff: true,
        source: false,
        mixed: false,
    });
    const [selectedLotIds, setSelectedLotIds] = useState<Record<string, boolean>>({});
    const [isRunning, setIsRunning] = useState(false);
    const [showCsvDrawer, setShowCsvDrawer] = useState(false);
    const [proofLeadPulse, setProofLeadPulse] = useState(0);
    const [isProofLeadHighlighted, setIsProofLeadHighlighted] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const exceptionsSectionRef = useRef<HTMLDivElement>(null);
    const selectedLotPanelRef = useRef<HTMLDivElement>(null);
    const normalizedRoleName = user?.role_name?.toLowerCase() ?? null;
    const workbenchWriteCapability = Array.isArray(user?.permissions)
        ? hasPermission(user.permissions, "inflow.write")
        : normalizedRoleName === "viewer"
            ? false
            : null;
    const saveWorkbenchRunUnavailable = workbenchWriteCapability === false;

    useEffect(() => {
        if (!previewMode) return;
        document.body.dataset.inflowLab = "true";
        return () => {
            delete document.body.dataset.inflowLab;
        };
    }, [previewMode]);

    useEffect(() => {
        if (proofLeadPulse === 0) return;
        setIsProofLeadHighlighted(true);
        const timeoutId = window.setTimeout(() => {
            setIsProofLeadHighlighted(false);
        }, 1600);
        return () => window.clearTimeout(timeoutId);
    }, [proofLeadPulse]);

    useEffect(() => {
        if (!isHydrated || !isAuthenticated || !activeTenantId) return;
        setTenantId((current) => (current === activeTenantId ? current : activeTenantId));
    }, [activeTenantId, isAuthenticated, isHydrated]);

    useEffect(() => {
        if (!isHydrated || !isAuthenticated || !activeTenantId) {
            setLoadedRun(null);
            return;
        }

        let cancelled = false;

        const loadLatestWorkbenchRun = async () => {
            try {
                const summary = await workbenchJson<{
                    run_id?: string | null;
                }>(`/readiness/summary?tenant_id=${encodeURIComponent(activeTenantId)}`, {
                    method: "GET",
                });
                if (!summary.run_id) {
                    if (!cancelled) setLoadedRun(null);
                    return;
                }
                const latestRun = await workbenchJson<WorkbenchRun>(
                    `/runs/${encodeURIComponent(summary.run_id)}?tenant_id=${encodeURIComponent(activeTenantId)}`,
                    { method: "GET" },
                );
                if (!cancelled) {
                    setLoadedRun(latestRun);
                }
            } catch {
                if (!cancelled) {
                    setLoadedRun(null);
                }
            }
        };

        loadLatestWorkbenchRun().catch(() => undefined);

        return () => {
            cancelled = true;
        };
    }, [activeTenantId, isAuthenticated, isHydrated]);

    const refreshService = async () => {
        try {
            const [healthPayload, statusPayload, eventsPayload] = await Promise.all([
                inflowJson<InflowHealth>("/api/healthz"),
                inflowJson<InflowStatus>("/api/simulate/status"),
                inflowJson<OptionalOfflinePayload & { events?: InflowRecord[] }>("/api/events?limit=100"),
            ]);
            const nextEvents = (eventsPayload.events || []).map(toTraceEvent);
            setHealth(healthPayload);
            setServiceStatus(statusPayload);
            setServiceEvents(nextEvents);
            setServiceError(optionalOfflineDetail(healthPayload, statusPayload, eventsPayload));
            if (!selectedLot && nextEvents.length) {
                setSelectedLot(nextEvents[0].lotCode);
            }
        } catch (error) {
            setServiceError(error instanceof Error ? error.message : "Inflow Lab service unavailable");
        }
    };

    useEffect(() => {
        if (previewMode) {
            const previewLotCodes = Array.from(new Set(PREVIEW_TRACE_EVENTS.map((event) => event.lotCode)));
            const previewLineages = Object.fromEntries(
                previewLotCodes.map((lotCode) => [
                    lotCode,
                    toLineage(PREVIEW_TRACE_EVENTS.filter((event) => event.lotCode === lotCode)),
                ]),
            );
            const previewStatus = {
                running: false,
                stats: {
                    total_records: PREVIEW_TRACE_EVENTS.length,
                    unique_lots: 3,
                    delivery: {
                        posted: PREVIEW_TRACE_EVENTS.length,
                        failed: 0,
                        generated: 0,
                        attempts: PREVIEW_TRACE_EVENTS.length,
                        last_success_at: "2026-05-07T19:08:00.000Z",
                    },
                },
            } satisfies InflowStatus;

            setHealth({ ok: true, build: { version: "preview-proof" } });
            setServiceStatus(previewStatus);
            setServiceEvents(PREVIEW_TRACE_EVENTS);
            setServiceLineage(previewLineages);
            setServiceError(null);
            setSelectedLot("TLC-20260508-000022");
            setFeederCsv((current) => current || REALISTIC_SAMPLE_CSV);
            return;
        }

        refreshService().catch(() => undefined);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [previewMode]);

    const activeEvents = serviceEvents;
    const uniqueLots = useMemo(() => {
        const codes = Array.from(new Set(activeEvents.map((event) => event.lotCode)));
        return codes.map((lotCode) => {
            const lotEvents = activeEvents.filter((event) => event.lotCode === lotCode);
            const lineage = serviceLineage[lotCode] ?? toLineage(lotEvents);
            return buildLotSummary(lotCode, lotEvents, lineage);
        });
    }, [activeEvents, serviceLineage]);

    useEffect(() => {
        if (!selectedLot && uniqueLots.length) {
            const blocked = uniqueLots.find((lot) => !lot.readiness.exportReady) ?? uniqueLots[0];
            setSelectedLot(blocked.lotCode);
        }
    }, [selectedLot, uniqueLots]);

    useEffect(() => {
        if (!selectedLot || !activeEvents.length || serviceLineage[selectedLot]) return;
        inflowJson<{ records?: InflowRecord[] }>(`/api/lineage/${encodeURIComponent(selectedLot)}`)
            .then((payload) => {
                const lineageEvents = (payload.records || []).map(toTraceEvent);
                setServiceLineage((current) => ({ ...current, [selectedLot]: toLineage(lineageEvents) }));
            })
            .catch((error) => setServiceError(error instanceof Error ? error.message : "Could not trace lot"));
    }, [selectedLot, activeEvents.length, serviceLineage]);

    const exportReadyLots = uniqueLots.filter((lot) => lot.readiness.exportReady);
    const exceptionLots = uniqueLots.filter((lot) => !lot.readiness.exportReady);
    const totalLotCount = uniqueLots.length;
    const exportReadyCount = exportReadyLots.length;

    const exceptionGroups = useMemo(() => groupExceptionsByPattern(exceptionLots), [exceptionLots]);
    const sourceSupplierBreakdown = useMemo(() => {
        const sourceGroup = exceptionGroups.find((group) => group.id === "source");
        return sourceGroup ? summarizeSourceSuppliers(sourceGroup.lots) : null;
    }, [exceptionGroups]);

    // Hide empty groups in all cases so the section matches the redesign
    // mock (only non-empty patterns are listed). When the active filter
    // selects a group that has zero lots, ``visibleGroups`` is empty and
    // the section renders the dedicated "no lots match" empty state below
    // (with a Clear filter affordance) instead of a stub group heading.
    const visibleGroups = exceptionGroups.filter((group) => {
        if (group.lots.length === 0) return false;
        if (activeFilter === "all") return true;
        return group.id === activeFilter;
    });

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
    const postedCount = serviceStatus?.stats?.delivery?.posted ?? localDeliveryCounts.posted;
    const failedCount = serviceStatus?.stats?.delivery?.failed ?? localDeliveryCounts.failed;
    const generatedOnlyCount = serviceStatus?.stats?.delivery?.generated ?? localDeliveryCounts.generated;

    const engineConnected = Boolean(health?.ok && !serviceError);

    const selectedLotData = selectedLot
        ? uniqueLots.find((lot) => lot.lotCode === selectedLot) ?? null
        : null;
    const selectedLineage = selectedLot
        ? serviceLineage[selectedLot] ?? toLineage(activeEvents.filter((e) => e.lotCode === selectedLot))
        : [];

    const totalCteSlots = uniqueLots.reduce((acc, lot) => acc + lot.totalCount, 0);
    const completeCteSlots = uniqueLots.reduce((acc, lot) => acc + lot.completeCount, 0);
    const kdeCompleteness = totalCteSlots > 0 ? Math.round((completeCteSlots / totalCteSlots) * 100) : 0;
    const cteLifecycle = totalLotCount > 0 ? Math.round((exportReadyCount / totalLotCount) * 100) : 0;
    const deliveryDenominator = postedCount + failedCount + generatedOnlyCount;
    const deliveryQuality = deliveryDenominator > 0 ? Math.round((postedCount / deliveryDenominator) * 100) : 0;
    const sandboxPassRate = feederResult
        ? feederResult.total_events > 0
            ? Math.round((feederResult.compliant_events / feederResult.total_events) * 100)
            : 0
        : null;
    const connectionHealth = engineConnected ? 100 : 0;

    const readinessFactors: { id: string; label: string; value: number | null; tone: "ok" | "warn" | "bad" | "locked" }[] = [
        {
            id: "kde",
            label: "KDE completeness",
            value: kdeCompleteness,
            tone: kdeCompleteness >= 75 ? "ok" : kdeCompleteness >= 50 ? "warn" : "bad",
        },
        {
            id: "cte",
            label: "CTE lifecycle",
            value: cteLifecycle,
            tone: cteLifecycle >= 75 ? "ok" : cteLifecycle >= 50 ? "warn" : "bad",
        },
        {
            id: "delivery",
            label: "Delivery quality",
            value: deliveryQuality,
            tone: deliveryQuality >= 75 ? "ok" : deliveryQuality >= 50 ? "warn" : "bad",
        },
        {
            id: "sandbox",
            label: "Sandbox pass rate",
            value: sandboxPassRate,
            tone: sandboxPassRate === null ? "locked" : sandboxPassRate >= 75 ? "ok" : sandboxPassRate >= 50 ? "warn" : "bad",
        },
        {
            id: "connection",
            label: "Connection health",
            value: connectionHealth,
            tone: connectionHealth >= 75 ? "ok" : connectionHealth >= 50 ? "warn" : "bad",
        },
    ];

    const measuredFactors = readinessFactors.filter((f) => f.value !== null) as {
        id: string;
        label: string;
        value: number;
        tone: "ok" | "warn" | "bad" | "locked";
    }[];
    const latestSavedRun = savedRun ?? loadedRun;
    const activeWorkbenchReadiness = backendReadiness ?? latestSavedRun?.readiness ?? null;
    const compositeScore = activeWorkbenchReadiness
        ? activeWorkbenchReadiness.score
        : measuredFactors.length
        ? Math.round(measuredFactors.reduce((acc, f) => acc + f.value, 0) / measuredFactors.length)
        : 0;
    const biggestGap = measuredFactors.length
        ? measuredFactors.reduce((min, f) => (f.value < min.value ? f : min), measuredFactors[0])
        : null;

    const passingCount = exportReadyCount;
    const previewReadyCount = feederResult ? feederResult.compliant_events : 0;

    const openFixCount = savedRun
        ? savedRun.fix_queue.filter((item) => item.status === "open" || item.status === "waiting").length
        : 0;
    const latestSavedRunOpenFixCount = latestSavedRun
        ? latestSavedRun.fix_queue.filter((item) => item.status === "open" || item.status === "waiting").length
        : 0;

    const resetFeederPreview = () => {
        setFeederResult(null);
        setBackendReadiness(null);
        setFeederError(null);
        setIsSavingRun(false);
        setSavedRun(null);
        setLoadedRun(null);
        setWorkbenchSaveNote(null);
        setWorkbenchSaveError(null);
    };

    const loadRealisticSample = () => {
        setFeederCsv(REALISTIC_SAMPLE_CSV);
        resetFeederPreview();
        setShowCsvDrawer(true);
    };

    const handleFeederFile = (file: File | null) => {
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            setFeederCsv(String(reader.result || ""));
            resetFeederPreview();
            setShowCsvDrawer(true);
        };
        reader.onerror = () => setFeederError("Could not read the selected CSV file.");
        reader.readAsText(file);
    };

    const evaluateFeederData = async (csvOverride?: string) => {
        const csvToEvaluate = csvOverride ?? feederCsv;
        if (!csvToEvaluate.trim()) {
            setFeederError("Paste CSV text or upload a CSV file before evaluating.");
            setShowCsvDrawer(true);
            return;
        }
        if (csvOverride !== undefined) {
            setFeederCsv(csvOverride);
        }
        setIsFeederEvaluating(true);
        setIsRunning(true);
        setFeederError(null);
        setIsSavingRun(false);
        setSavedRun(null);
        setWorkbenchSaveNote(null);
        setWorkbenchSaveError(null);
        try {
            const response = await fetchWithCsrf("/api/ingestion/api/v1/sandbox/evaluate", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ csv: csvToEvaluate }),
            });
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                const detail =
                    typeof payload.detail === "string"
                        ? payload.detail
                        : `Sandbox evaluation failed: ${response.status}`;
                throw new Error(detail);
            }
            const result = (await response.json()) as SandboxEvaluationResult;
            setFeederResult(result);
            if (isAuthenticated && activeTenantId) {
                try {
                    const readiness = await fetchWithCsrf("/api/ingestion/api/v1/inflow-workbench/readiness/preview", {
                        method: "POST",
                        headers: { "content-type": "application/json" },
                        body: JSON.stringify(result),
                    });
                    if (readiness.ok) {
                        const payload = (await readiness.json()) as ReadinessSummary;
                        if (typeof payload.score === "number") setBackendReadiness(payload);
                    }
                } catch {
                    /* authenticated readiness preview is best-effort */
                }
            }
        } catch (error) {
            setFeederError(error instanceof Error ? error.message : "Could not evaluate pasted data");
        } finally {
            setIsFeederEvaluating(false);
            setIsRunning(false);
        }
    };

    const runGuidedProof = () => {
        resetFeederPreview();
        setShowCsvDrawer(true);
        void evaluateFeederData(REALISTIC_SAMPLE_CSV);
    };

    const saveWorkbenchRun = async () => {
        if (!feederResult || !feederCsv.trim()) {
            return;
        }
        if (saveWorkbenchRunUnavailable) {
            setWorkbenchSaveNote(
                "You can evaluate sandbox data here, but only users with write access can save an Inflow Workbench test run.",
            );
            return;
        }
        setIsSavingRun(true);
        setSavedRun(null);
        setWorkbenchSaveNote(null);
        setWorkbenchSaveError(null);
        try {
            const workbenchBody = {
                source: "inflow-lab-data-feeder",
                csv: feederCsv,
                result: feederResult,
                ...(activeTenantId ? { tenant_id: activeTenantId } : {}),
            };
            const savedPayload = await workbenchJson<WorkbenchRun>("/runs", {
                method: "POST",
                body: JSON.stringify(workbenchBody),
            });
            setSavedRun(savedPayload);
            setLoadedRun(savedPayload);
            setBackendReadiness(savedPayload.readiness);
        } catch (error) {
            if ((error as WorkbenchRequestError | undefined)?.status === 403) {
                setWorkbenchSaveNote(
                    "You can evaluate sandbox data here, but only users with write access can save an Inflow Workbench test run.",
                );
                return;
            }
            setWorkbenchSaveError(
                error instanceof Error ? error.message : "Could not save workbench run",
            );
        } finally {
            setIsSavingRun(false);
        }
    };

    const toggleLotSelection = (lotCode: string, checked: boolean) => {
        setSelectedLotIds((current) => ({ ...current, [lotCode]: checked }));
    };

    const focusProofLead = (target: "exceptions" | "selected" = "exceptions") => {
        if (leadProofGroup) {
            setActiveFilter(leadProofGroup.id);
            setOpenGroups((current) => ({ ...current, [leadProofGroup.id]: true }));
        }
        if (leadProofLot) {
            setSelectedLot(leadProofLot.lotCode);
        }
        setProofLeadPulse((current) => current + 1);
        requestAnimationFrame(() => {
            const targetNode = target === "selected" ? selectedLotPanelRef.current : exceptionsSectionRef.current;
            targetNode?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    };

    const lastTestRunAt = latestSavedRun?.saved_at || serviceStatus?.stats?.delivery?.last_success_at || null;
    const lastTestRunLabel = lastTestRunAt ? formatServiceTime(lastTestRunAt) : "never";
    const showLatestRunBanner = latestSavedRun && !(savedRun && showCsvDrawer);
    const leadProofLot = selectedLotData && !selectedLotData.readiness.exportReady
        ? selectedLotData
        : exceptionLots[0] ?? selectedLotData ?? null;
    const leadProofGroup =
        exceptionGroups.find((group) => group.lots.some((lot) => lot.lotCode === leadProofLot?.lotCode)) ??
        exceptionGroups.find((group) => group.lots.length > 0) ??
        null;
    const leadMissingEvidence = leadProofLot?.missingCtes.length ? leadProofLot.missingCtes.join(", ") : "DC receiving";
    const leadFixPath =
        leadProofGroup?.id === "handoff"
            ? "Map the missing handoff fields once, then re-run the lot group to clear the blocked export path."
            : leadProofGroup?.id === "source"
            ? "Push the missing harvest or cooling KDEs back to the supplier feed, then re-test before promotion."
            : "Triage the lot individually, patch the missing KDEs, and confirm the lifecycle closes end to end.";
    const proofAfterState = leadProofLot
        ? `Once corrected, ${leadProofLot.product} moves from blocked evidence to preview-ready traceability.`
        : "Once corrected, the blocked lot moves into the preview-ready path without touching production exports.";
    const leadLotLabel = leadProofLot ? leadProofLot.lotCode.slice(-6) : "active";
    const leadProductLabel = leadProofLot?.product ?? "Supplier lot";
    const leadPatternLabel = leadProofGroup?.label ?? "Missing handoff evidence";
    const readinessLeadNote = leadProofLot
        ? `Proof lead lot ${leadLotLabel} is dragging down ${biggestGap?.label?.toLowerCase() ?? "readiness"} because ${leadMissingEvidence} is still missing.`
        : "The current proof lead is the blocked lot holding readiness below export confidence.";
    const selectedLotIsProofLead = selectedLotData?.lotCode === leadProofLot?.lotCode;

    return (
        <main
            data-inflow-lab-app
            data-inflow-lab-mode="dashboard"
            data-dashboard-shell
            className="min-h-full bg-slate-50 text-slate-950"
        >
            <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                className="hidden"
                aria-label="Upload feeder CSV"
                onChange={(event) => handleFeederFile(event.target.files?.[0] ?? null)}
            />

            <div className="mx-auto flex w-full max-w-[1480px] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
                <header className="flex flex-col gap-3 border-b border-slate-200 pb-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                            <h1 className="text-xl font-semibold tracking-tight text-slate-950">Inflow Lab</h1>
                            <Badge
                                variant="outline"
                                className="border-blue-200 bg-blue-50 text-[10px] font-medium text-blue-700"
                            >
                                Sandbox
                            </Badge>
                        </div>
                        <p className="mt-1 text-sm text-slate-600">
                            See exactly why a supplier lot will fail before it reaches production export.
                        </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                        <Button asChild variant="ghost" className="h-9 text-slate-600">
                            <Link href="/dashboard/integrations">
                                <Settings2 className="mr-2 h-4 w-4" />
                                Connections
                            </Link>
                        </Button>
                        <Button
                            variant="outline"
                            className="h-9 border-slate-300 bg-white"
                            onClick={() => fileInputRef.current?.click()}
                        >
                            <Upload className="mr-2 h-4 w-4" />
                            Upload CSV
                        </Button>
                        <Button
                            variant="outline"
                            className="h-9 border-slate-300 bg-white"
                            onClick={loadRealisticSample}
                        >
                            <ClipboardList className="mr-2 h-4 w-4" />
                            Load realistic sample
                        </Button>
                    </div>
                </header>

                <div
                    role="status"
                    className="flex items-center gap-3 rounded-md border border-slate-200 bg-white px-4 py-2.5 text-[13px] shadow-sm"
                >
                    <span className="h-2 w-2 shrink-0 rounded-full bg-blue-500" aria-hidden />
                    <span className="font-medium text-slate-900">Sandbox preview only.</span>
                    <span className="text-slate-600">
                        Production FDA-oriented exports stay sealed and review-ready — nothing here writes to them.
                    </span>
                    <Link
                        href="/docs/connectors/inflow-lab"
                        className="ml-auto text-xs font-medium text-emerald-700 underline-offset-2 hover:underline"
                    >
                        What runs in sandbox →
                    </Link>
                </div>

                {serviceError && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
                        Inflow Lab service connection: {serviceError}
                    </div>
                )}

                {showLatestRunBanner && (
                    <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs text-emerald-900">
                        <span className="font-medium">Latest saved workbench run</span>{" "}
                        <code className="font-mono text-[11px]">{latestSavedRun.run_id}</code>.{" "}
                        {latestSavedRunOpenFixCount} open fix{latestSavedRunOpenFixCount === 1 ? "" : "es"} remain in workbench.
                    </div>
                )}

                <section
                    aria-label="How Inflow Lab works"
                    className="grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.9fr)]"
                >
                    <div
                        className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                        style={{ display: "block" }}
                    >
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                                    How it works
                                </div>
                                <h2 className="mt-1 text-lg font-semibold text-slate-950">
                                    Real supplier activity in. Clear failure evidence out.
                                </h2>
                                <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                                    Inflow Lab replays believable farm-to-DC lot activity, reconstructs the evidence
                                    trail, and flags the exact missing KDEs blocking readiness. We show the evidence and
                                    the fix recommendation, not the internal scoring recipe.
                                </p>
                            </div>
                            <Badge
                                variant="outline"
                                className="border-emerald-200 bg-emerald-50 text-[10px] text-emerald-700"
                            >
                                Trade-secret safe
                            </Badge>
                        </div>
                        <div className="mt-4 grid gap-3 md:grid-cols-3">
                            {EXPLAINER_STEPS.map((step) => (
                                <div key={step.title} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                                    <div className="text-sm font-semibold text-slate-900">{step.title}</div>
                                    <p className="mt-1 text-xs leading-5 text-slate-600">{step.detail}</p>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div
                        className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                        style={{ display: "block" }}
                    >
                        <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                            Example business activity
                        </div>
                        <h2 className="mt-1 text-base font-semibold text-slate-950">
                            A produce handoff a buyer can recognize in seconds
                        </h2>
                        <div className="mt-3 grid grid-cols-2 gap-2 text-[12px]">
                            <KdeTile label="Product" value="Spring Mix" />
                            <KdeTile label="Quantity" value="184 cases" />
                            <KdeTile label="Supplier" value="Riverbend Organics" />
                            <KdeTile label="Destination" value="North Bay DC" />
                        </div>
                        <p className="mt-3 text-xs leading-5 text-slate-600">
                            Load a fabricated sample based on a common farm-to-DC trace so buyers can see the input
                            shape, the caught break, and the fix path before any production feed is connected.
                        </p>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                            <Button
                                type="button"
                                className="h-8 bg-emerald-700 px-3 text-xs text-white hover:bg-emerald-800"
                                onClick={runGuidedProof}
                                disabled={isFeederEvaluating || isRunning}
                            >
                                {isFeederEvaluating ? (
                                    <>
                                        <RefreshCcw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                        Running
                                    </>
                                ) : (
                                    <>
                                        <Play className="mr-2 h-3.5 w-3.5" />
                                        Run guided proof
                                    </>
                                )}
                            </Button>
                            <Button
                                type="button"
                                variant="outline"
                                className="h-8 border-slate-300 bg-white px-3 text-xs"
                                onClick={loadRealisticSample}
                            >
                                Load sample flow
                            </Button>
                            <span className="text-xs text-slate-500">
                                Harvest → cool → pack → ship → receive
                            </span>
                        </div>
                    </div>
                </section>

                <section
                    aria-label="Proof walkthrough"
                    className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                    style={{ display: "block" }}
                >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                        <div>
                            <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                                Proof walkthrough
                            </div>
                            <h2 className="mt-1 text-lg font-semibold text-slate-950">
                                See the lot, the break, and the fastest path to clear it
                            </h2>
                            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                                This should read like product proof: normal supplier activity comes in, the broken
                                handoff is isolated, and the operator gets the next fix to unblock readiness.
                            </p>
                        </div>
                        <Badge
                            variant="outline"
                            className="border-slate-200 bg-slate-50 text-[10px] text-slate-700"
                        >
                            Buyer-readable
                        </Badge>
                    </div>

                    <div className="mt-4 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 lg:grid-cols-[minmax(280px,0.95fr)_minmax(0,1.35fr)]">
                        <div className="space-y-3">
                            <div className="rounded-md border border-slate-200 bg-white p-3">
                                <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                                    Current proof point
                                </div>
                                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                                    <div className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2">
                                        <div className="text-[11px] uppercase tracking-wider text-slate-500">Lot</div>
                                        <div className="mt-1 text-sm font-semibold text-slate-950">{leadLotLabel}</div>
                                    </div>
                                    <div className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-2">
                                        <div className="text-[11px] uppercase tracking-wider text-slate-500">Product</div>
                                        <div className="mt-1 text-sm font-semibold text-slate-950">{leadProductLabel}</div>
                                    </div>
                                    <div className="rounded-md border border-rose-200 bg-rose-50 px-2.5 py-2">
                                        <div className="text-[11px] uppercase tracking-wider text-rose-700">Status</div>
                                        <div className="mt-1 text-sm font-semibold text-rose-900">Readiness blocked</div>
                                    </div>
                                </div>
                            </div>

                            <div className="block rounded-md border border-slate-200 bg-white p-3">
                                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                                    1. Incoming business activity
                                </div>
                                <p className="mt-2 text-xs leading-5 text-slate-600">
                                    A normal leafy-greens handoff arrives as supplier rows, not perfect structured truth.
                                </p>
                                <ul className="mt-2 space-y-1 text-xs leading-5 text-slate-600">
                                    {DEFAULT_PROOF_INPUTS.map((item) => (
                                        <li key={item}>{item}</li>
                                    ))}
                                </ul>
                            </div>

                            <div className="block rounded-md border border-emerald-200 bg-emerald-50 p-3">
                                <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                                    <Lightbulb className="h-4 w-4 text-emerald-700" />
                                    3. Recommended fix path
                                </div>
                                <p className="mt-2 text-xs leading-5 text-slate-700">{leadFixPath}</p>
                                <div className="mt-2 rounded-md border border-emerald-200 bg-white px-2.5 py-2 text-xs text-slate-700">
                                    {proofAfterState}
                                </div>
                                {leadProofGroup && (
                                    <div className="mt-2 flex flex-wrap items-center gap-2">
                                        <Button
                                            type="button"
                                            variant="outline"
                                            className="h-7 border-slate-300 bg-white px-2 text-xs"
                                            onClick={() => focusProofLead("exceptions")}
                                        >
                                            Focus this defect
                                        </Button>
                                        <span className="text-[11px] text-slate-500">
                                            Jumps to the exact pattern group already visible below.
                                        </span>
                                    </div>
                                )}
                            </div>
                        </div>

                        <div className="block rounded-md border border-rose-200 bg-rose-50 p-4 shadow-sm shadow-rose-100/70">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <div>
                                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                                        <AlertTriangle className="h-4 w-4 text-rose-600" />
                                        2. Caught defect
                                    </div>
                                    <h3 className="mt-2 text-xl font-semibold tracking-tight text-slate-950">
                                        Missing evidence stops this lot before export.
                                    </h3>
                                </div>
                                <Badge className="border-0 bg-rose-600 text-[10px] text-white hover:bg-rose-600">
                                    Blocked now
                                </Badge>
                            </div>

                            <div className="mt-4 grid gap-2 sm:grid-cols-3">
                                <div className="rounded-md border border-rose-200 bg-white px-3 py-2">
                                    <div className="text-[11px] uppercase tracking-wider text-slate-500">Lot</div>
                                    <div className="mt-1 text-sm font-semibold text-slate-950">{leadLotLabel}</div>
                                </div>
                                <div className="rounded-md border border-rose-200 bg-white px-3 py-2">
                                    <div className="text-[11px] uppercase tracking-wider text-slate-500">Pattern</div>
                                    <div className="mt-1 text-sm font-semibold text-slate-950">{leadPatternLabel}</div>
                                </div>
                                <div className="rounded-md border border-rose-200 bg-white px-3 py-2">
                                    <div className="text-[11px] uppercase tracking-wider text-slate-500">Missing</div>
                                    <div className="mt-1 text-sm font-semibold text-slate-950">{leadMissingEvidence}</div>
                                </div>
                            </div>

                            <p className="mt-4 max-w-2xl text-sm leading-6 text-slate-700">
                                {leadProofLot
                                    ? `${leadProductLabel} lot ${leadLotLabel} is blocked because ${leadMissingEvidence} is missing from the handoff chain.`
                                    : `The current test set is blocked because ${leadMissingEvidence} is missing from the handoff chain.`}
                            </p>
                            <div className="mt-3 rounded-md border border-rose-200 bg-white px-3 py-3 text-sm text-slate-700">
                                RegEngine reconstructs the lifecycle, isolates the exact break, and points the operator to
                                the missing evidence instead of returning a generic failure.
                            </div>
                        </div>
                    </div>
                </section>

                <section aria-label="Pipeline funnel" data-testid="inflow-funnel">
                    <div className="flex items-center justify-between">
                        <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                            Pipeline
                        </div>
                        <div className="text-xs text-slate-500">Last test run · {lastTestRunLabel}</div>
                    </div>
                    <ol className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                        <FunnelStep
                            id="loaded"
                            label="Loaded"
                            value={String(totalLotCount)}
                            sub="lots ingested"
                            tone="ok"
                            tag="CSV"
                        />
                        <FunnelStep
                            id="validated"
                            label="Validated"
                            value={String(totalLotCount)}
                            sub="parse-clean"
                            tone="ok"
                            tag="schema"
                        />
                        <FunnelStep
                            id="passing"
                            label="Passing"
                            value={`${passingCount}`}
                            valueSuffix={`/ ${totalLotCount}`}
                            sub={`${exceptionLots.length} exception${exceptionLots.length === 1 ? "" : "s"} blocking`}
                            tone="warn"
                            active
                        >
                            <Button
                                onClick={() => void evaluateFeederData()}
                                disabled={isFeederEvaluating || isRunning}
                                className="mt-3 h-8 w-full bg-emerald-700 text-xs text-white hover:bg-emerald-800"
                            >
                                {isFeederEvaluating ? (
                                    <>
                                        <RefreshCcw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                        Running
                                    </>
                                ) : (
                                    <>
                                        <Play className="mr-2 h-3.5 w-3.5" />
                                        Run sandbox test
                                    </>
                                )}
                            </Button>
                        </FunnelStep>
                        <FunnelStep
                            id="preview"
                            label="Preview-ready"
                            value={String(previewReadyCount)}
                            sub="lots"
                            tone="muted"
                            tag="CTE"
                        />
                        <FunnelStep
                            id="production"
                            label="Production import"
                            value="—"
                            sub="locked until preview passes"
                            tone="locked"
                            locked
                        />
                    </ol>
                </section>

                <section className="grid grid-cols-12 gap-4">
                    <div className="col-span-12 space-y-4 xl:col-span-8">
                        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                                        Data Preflight Score
                                    </div>
                                    <div className="mt-1 flex items-baseline gap-2">
                                        <span className="text-3xl font-semibold text-slate-950">{compositeScore}</span>
                                        <span className="text-sm text-slate-500">/ 100</span>
                                        <Badge
                                            variant="outline"
                                            className="ml-1 border-amber-200 bg-amber-50 text-[10px] text-amber-800"
                                        >
                                            needs work
                                        </Badge>
                                    </div>
                                    <p className="mt-1 text-xs text-slate-500">Lowest factor sets the next fix.</p>
                                </div>
                                <div className="text-right text-xs text-slate-500">
                                    <div>Δ since last run</div>
                                    <div className="text-sm text-emerald-600">
                                        {feederResult ? `${feederResult.compliant_events} passing` : "+0 (first run pending)"}
                                    </div>
                                    </div>
                                </div>
                            {leadProofLot && (
                                <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
                                    <span className="font-medium">Proof lead:</span> {readinessLeadNote}
                                    <div className="mt-2">
                                        <Button
                                            type="button"
                                            variant="outline"
                                            className="h-7 border-rose-200 bg-white px-2 text-xs text-rose-700 hover:bg-rose-100"
                                            onClick={() => focusProofLead("exceptions")}
                                        >
                                            Open lead defect
                                        </Button>
                                    </div>
                                </div>
                            )}
                            <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
                                {readinessFactors.map((factor) => {
                                    const isLockedFactor = factor.value === null;
                                    const isBiggestGap = !isLockedFactor && biggestGap?.id === factor.id;
                                    return (
                                        <div key={factor.id} data-readiness-factor={factor.id}>
                                            <div className="flex items-center justify-between text-[13px]">
                                                <span className="text-slate-600">{factor.label}</span>
                                                <span className="flex items-center gap-1 font-medium text-slate-900">
                                                    {isLockedFactor ? "—" : `${factor.value}%`}
                                                    {isLockedFactor && (
                                                        <Badge
                                                            variant="outline"
                                                            className="border-slate-200 bg-slate-50 text-[10px] text-slate-500"
                                                        >
                                                            not run
                                                        </Badge>
                                                    )}
                                                    {isBiggestGap && (
                                                        <Badge
                                                            variant="outline"
                                                            className="border-rose-200 bg-rose-50 text-[10px] text-rose-700"
                                                        >
                                                            biggest gap
                                                        </Badge>
                                                    )}
                                                </span>
                                            </div>
                                            <StackedBar value={factor.value ?? 0} tone={factor.tone} />
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        <div
                            ref={exceptionsSectionRef}
                            className={cn(
                                "overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm transition-all",
                                isProofLeadHighlighted && "border-rose-300 shadow-[0_0_0_2px_rgba(244,63,94,0.12)]"
                            )}
                            data-proof-lead-highlight={isProofLeadHighlighted ? "true" : "false"}
                        >
                            <div className="flex flex-col gap-3 border-b border-slate-200 p-4 sm:flex-row sm:items-end sm:justify-between">
                                <div>
                                    <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                                        Exceptions
                                    </div>
                                    <h2 className="mt-0.5 text-base font-semibold text-slate-950">
                                        {exceptionLots.length} lots blocked across {exceptionGroups.filter((g) => g.lots.length).length} patterns
                                    </h2>
                                    <p className="mt-0.5 text-xs text-slate-500">Clear the pattern once, unblock the group.</p>
                                    {leadProofGroup && leadProofLot && (
                                        <div className="mt-2 inline-flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-2.5 py-1 text-[11px] text-rose-900">
                                            <span className="font-medium">Proof lead pattern</span>
                                            <span>{leadPatternLabel}</span>
                                            <span className="text-rose-700">Lot {leadLotLabel}</span>
                                        </div>
                                    )}
                                </div>
                                <div className="flex flex-wrap items-center gap-2">
                                    <div className="flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
                                        <span className="text-slate-500">Filter</span>
                                        {FILTER_CHIPS.map((chip) => (
                                            <FilterChip
                                                key={chip.id}
                                                label={chip.label}
                                                active={activeFilter === chip.id}
                                                onClick={() => setActiveFilter(chip.id)}
                                            />
                                        ))}
                                    </div>
                                    <Button asChild variant="outline" className="h-9 border-slate-300 bg-white">
                                        <Link href="/exceptions">Open fix queue</Link>
                                    </Button>
                                </div>
                            </div>

                            {visibleGroups.map((group) => {
                                const isOpen = openGroups[group.id];
                                return (
                                    <details
                                        key={group.id}
                                        open={isOpen}
                                        className={cn(
                                            "border-b border-slate-200 last:border-b-0",
                                            group.id === leadProofGroup?.id && "bg-rose-50/40",
                                            isProofLeadHighlighted &&
                                                group.id === leadProofGroup?.id &&
                                                "bg-rose-100/70 ring-1 ring-inset ring-rose-200"
                                        )}
                                        onToggle={(event) => {
                                            const target = event.currentTarget as HTMLDetailsElement;
                                            setOpenGroups((current) => ({ ...current, [group.id]: target.open }));
                                        }}
                                        data-exception-group={group.id}
                                    >
                                        <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 hover:bg-slate-50 [&::-webkit-details-marker]:hidden">
                                            <ChevronRight
                                                className={cn(
                                                    "h-4 w-4 shrink-0 text-slate-400 transition-transform",
                                                    isOpen && "rotate-90"
                                                )}
                                            />
                                            <div className="min-w-0 flex-1">
                                                <div className="flex items-center gap-2">
                                                    <span className="text-sm font-medium text-slate-900">{group.label}</span>
                                                    {group.id === leadProofGroup?.id && (
                                                        <Badge
                                                            variant="outline"
                                                            className="border-rose-200 bg-rose-50 text-[10px] text-rose-700"
                                                        >
                                                            proof lead
                                                        </Badge>
                                                    )}
                                                    <Badge
                                                        variant="outline"
                                                        className={cn(
                                                            "border text-[10px]",
                                                            group.id === "handoff"
                                                                ? "border-rose-200 bg-rose-50 text-rose-700"
                                                                : group.id === "source"
                                                                ? "border-amber-200 bg-amber-50 text-amber-800"
                                                                : "border-slate-200 bg-slate-50 text-slate-700"
                                                        )}
                                                        data-group-count={group.id}
                                                    >
                                                        {group.lots.length} lot{group.lots.length === 1 ? "" : "s"}
                                                    </Badge>
                                                </div>
                                                <p className="mt-0.5 truncate text-xs text-slate-500">{group.description}</p>
                                            </div>
                                            <div className="hidden text-xs text-slate-500 md:block">
                                                Likely owner: <span className="text-slate-700">{group.owner}</span>
                                            </div>
                                            {group.bulkActionable && group.lots.length > 0 ? (
                                                <Button
                                                    type="button"
                                                    onClick={(event) => event.preventDefault()}
                                                    className={cn(
                                                        "h-8 px-3 text-xs",
                                                        group.id === "handoff"
                                                            ? "bg-emerald-700 text-white hover:bg-emerald-800"
                                                            : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
                                                    )}
                                                >
                                                    {group.id === "handoff"
                                                        ? `Fix all ${group.lots.length}`
                                                        : `Fix all ${group.lots.length}`}
                                                </Button>
                                            ) : (
                                                group.lots.length > 0 && (
                                                    <Button
                                                        type="button"
                                                        onClick={(event) => event.preventDefault()}
                                                        variant="outline"
                                                        className="h-8 border-slate-300 bg-white px-3 text-xs"
                                                    >
                                                        Review each
                                                    </Button>
                                                )
                                            )}
                                        </summary>

                                        <div className="space-y-3 px-4 pb-4">
                                            {group.lots.length === 0 ? (
                                                <div className="rounded-md border border-dashed border-slate-200 bg-slate-50 px-3 py-4 text-center text-xs text-slate-500">
                                                    No lots in this pattern.
                                                </div>
                                            ) : (
                                                <>
                                                    <GroupRootCausePanel
                                                        groupId={group.id}
                                                        sourceSupplierBreakdown={
                                                            group.id === "source" ? sourceSupplierBreakdown : null
                                                        }
                                                        lotCount={group.lots.length}
                                                    />
                                                    <div className="overflow-hidden rounded-md border border-slate-200">
                                                        {group.lots.slice(0, 6).map((lot) => (
                                                            <LotRow
                                                                key={lot.lotCode}
                                                                lot={lot}
                                                                groupId={group.id}
                                                                isSelected={lot.lotCode === selectedLot}
                                                                checked={Boolean(selectedLotIds[lot.lotCode])}
                                                                onCheckedChange={(checked) =>
                                                                    toggleLotSelection(lot.lotCode, checked)
                                                                }
                                                                onSelect={() => setSelectedLot(lot.lotCode)}
                                                            />
                                                        ))}
                                                        {group.lots.length > 6 && (
                                                            <div className="bg-slate-50 px-3 py-2 text-center text-xs text-slate-500">
                                                                + {group.lots.length - 6} more lots in this pattern ·{" "}
                                                                <button
                                                                    type="button"
                                                                    className="font-medium text-emerald-700 hover:underline"
                                                                    onClick={() => undefined}
                                                                >
                                                                    show all
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    </details>
                                );
                            })}

                            {exceptionLots.length > 0 && visibleGroups.length === 0 && (
                                <div
                                    className="border-t border-slate-200 p-6 text-center text-sm text-slate-500"
                                    data-empty-filter-state
                                >
                                    No lots match the <span className="font-mono text-slate-700">{activeFilter}</span> filter.{" "}
                                    <button
                                        type="button"
                                        className="font-medium text-emerald-700 hover:underline"
                                        onClick={() => setActiveFilter("all")}
                                    >
                                        Clear filter
                                    </button>
                                </div>
                            )}

                            {exceptionLots.length === 0 && (
                                <div className="border-t border-slate-200 p-6 text-center text-sm text-slate-500">
                                    No blocking exceptions in the current test data.
                                </div>
                            )}
                        </div>
                    </div>

                    <aside className="col-span-12 xl:col-span-4">
                        <div className="space-y-4 xl:sticky xl:top-4">
                            <div
                                ref={selectedLotPanelRef}
                                className={cn(
                                    "rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition-all",
                                    isProofLeadHighlighted && selectedLotIsProofLead && "border-rose-300 shadow-[0_0_0_2px_rgba(244,63,94,0.12)]"
                                )}
                                data-selected-lot-panel
                                data-proof-lead-highlight={isProofLeadHighlighted && selectedLotIsProofLead ? "true" : "false"}
                            >
                                <div className="flex items-center justify-between">
                                    <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-500">
                                        Selected lot
                                    </div>
                                    {selectedLotData && (
                                        <Button variant="ghost" className="h-7 px-2 text-xs text-slate-500 hover:text-slate-900">
                                            Change
                                        </Button>
                                    )}
                                </div>
                                {selectedLotData ? (
                                    <>
                                        <div className="mt-1 break-all font-mono text-sm text-slate-900">
                                            {selectedLotData.lotCode}
                                        </div>
                                        <div className="mt-1 flex flex-wrap items-center gap-2">
                                            {selectedLotIsProofLead && (
                                                <Badge
                                                    variant="outline"
                                                    className="border-rose-200 bg-rose-50 text-[10px] text-rose-700"
                                                >
                                                    proof lead
                                                </Badge>
                                            )}
                                            <Badge
                                                variant="outline"
                                                className={cn(
                                                    "border text-[10px]",
                                                    selectedLotData.readiness.exportReady
                                                        ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                                                        : selectedLotData.readiness.state === "blocked"
                                                        ? "border-rose-200 bg-rose-50 text-rose-700"
                                                        : "border-amber-200 bg-amber-50 text-amber-800"
                                                )}
                                            >
                                                {selectedLotData.readiness.exportReady ? "ready" : "blocked"}
                                            </Badge>
                                            <span className="text-xs text-slate-500">
                                                {selectedLotData.product}
                                            </span>
                                        </div>
                                        {selectedLotIsProofLead && (
                                            <div className="mt-3 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-900">
                                                This proof lead is blocked on {leadPatternLabel.toLowerCase()}: {leadMissingEvidence} missing.
                                                <div className="mt-2">
                                                    <Button
                                                        type="button"
                                                        variant="outline"
                                                        className="h-7 border-rose-200 bg-white px-2 text-xs text-rose-700 hover:bg-rose-100"
                                                        onClick={() => focusProofLead("exceptions")}
                                                    >
                                                        Show matching queue group
                                                    </Button>
                                                </div>
                                            </div>
                                        )}

                                        <div className="mt-4">
                                            <div className="text-xs text-slate-500">Lifecycle</div>
                                            <ol className="relative mt-2 space-y-3 border-l border-slate-200 pl-4 text-[13px]">
                                                {selectedLineage.map((node) => (
                                                    <li key={node.cte} className="relative">
                                                        <span
                                                            className={cn(
                                                                "absolute -left-[21px] mt-1 h-2.5 w-2.5 rounded-full",
                                                                node.state === "complete"
                                                                    ? "bg-emerald-500"
                                                                    : "bg-rose-500"
                                                            )}
                                                            aria-hidden
                                                        />
                                                        <div className="flex flex-wrap items-center gap-1">
                                                            <span className="font-medium text-slate-900">{node.cte}</span>
                                                            {node.state === "missing" && (
                                                                <Badge
                                                                    variant="outline"
                                                                    className="border-rose-200 bg-rose-50 text-[9px] text-rose-700"
                                                                >
                                                                    missing ts
                                                                </Badge>
                                                            )}
                                                        </div>
                                                        <div className="text-xs text-slate-500">
                                                            {node.location} · {node.time}
                                                        </div>
                                                    </li>
                                                ))}
                                            </ol>
                                        </div>

                                        <div className="mt-4">
                                            <div className="text-xs text-slate-500">Lot KDE summary</div>
                                            <div className="mt-2 grid grid-cols-2 gap-2 text-[12px]">
                                                <KdeTile label="Lot" value={selectedLotData.lotCode.slice(-6)} />
                                                <KdeTile
                                                    label="Events"
                                                    value={String(selectedLotData.events)}
                                                />
                                                <KdeTile
                                                    label="CTE coverage"
                                                    value={`${selectedLotData.completeCount}/${selectedLotData.totalCount}`}
                                                />
                                                <KdeTile
                                                    label="Delivery"
                                                    value={selectedLotData.readiness.deliveryLabel}
                                                    tone={selectedLotData.readiness.exportReady ? "ok" : "bad"}
                                                />
                                            </div>
                                        </div>

                                        <div className="mt-4 flex gap-2">
                                            <Button className="h-9 flex-1 bg-emerald-700 text-xs text-white hover:bg-emerald-800">
                                                Fix this lot
                                            </Button>
                                            <Button asChild variant="outline" className="h-9 border-slate-300 bg-white text-xs">
                                                <Link href="/exceptions">Open in queue</Link>
                                            </Button>
                                        </div>
                                    </>
                                ) : (
                                    <div className="mt-3 text-xs text-slate-500">
                                        No lots loaded yet. Upload a CSV or load test data.
                                    </div>
                                )}
                            </div>

                            <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-[12px] text-slate-600">
                                <div className="mb-1 font-medium text-slate-800">Why this lot?</div>
                                Current proof lead. Confirm the break here, then clear the matching pattern on the left.
                            </div>
                        </div>
                    </aside>
                </section>

                {showCsvDrawer && (
                    <section
                        aria-label="CSV input"
                        className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm font-semibold text-slate-950">Paste or upload inbound CSV</p>
                                <p className="mt-1 text-xs text-slate-500">
                                    Sandbox evaluation is stateless until you explicitly save a test run. Running a check does not promote anything to production ingestion.
                                </p>
                            </div>
                            <Button
                                variant="ghost"
                                className="h-8 text-xs text-slate-500"
                                onClick={() => setShowCsvDrawer(false)}
                            >
                                Hide
                            </Button>
                        </div>
                        <Textarea
                            value={feederCsv}
                            onChange={(event) => {
                                setFeederCsv(event.target.value);
                                resetFeederPreview();
                            }}
                            spellCheck={false}
                            aria-label="Inbound CSV data"
                            className="mt-3 min-h-[200px] resize-y border-slate-300 bg-slate-50 font-mono text-xs leading-5 text-slate-900"
                        />
                        {feederError && (
                            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                                {feederError}
                            </div>
                        )}
                        {feederResult && (
                            <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-700">
                                Sandbox evaluator processed {feederResult.total_events} event{feederResult.total_events === 1 ? "" : "s"}.
                                {" "}
                                {feederResult.compliant_events} compliant. {feederResult.total_kde_errors} KDE error{feederResult.total_kde_errors === 1 ? "" : "s"}.
                            </div>
                        )}
                        {feederResult && isAuthenticated && isHydrated && (
                            <div className="mt-3 flex flex-wrap items-center gap-2">
                                <Button
                                    type="button"
                                    className="h-8 bg-emerald-700 px-3 text-xs text-white hover:bg-emerald-800"
                                    disabled={saveWorkbenchRunUnavailable || isSavingRun || savedRun !== null}
                                    onClick={saveWorkbenchRun}
                                >
                                    {isSavingRun ? (
                                        <>
                                            <RefreshCcw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                            Saving
                                        </>
                                    ) : saveWorkbenchRunUnavailable ? (
                                        "Save unavailable"
                                    ) : savedRun ? (
                                        "Saved"
                                    ) : (
                                        "Save test run"
                                    )}
                                </Button>
                                <span className="text-xs text-slate-500">
                                    Save only when you want this sandbox result recorded in Inflow Workbench.
                                </span>
                            </div>
                        )}
                        {saveWorkbenchRunUnavailable && feederResult && isAuthenticated && isHydrated && (
                            <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                                You can evaluate sandbox data here, but only users with write access can save an Inflow Workbench test run.
                            </div>
                        )}
                        {savedRun && (
                            <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                                Saved to Inflow Workbench as <code className="font-mono text-[11px]">{savedRun.run_id}</code>.
                                {" "}
                                {openFixCount} open fix{openFixCount === 1 ? "" : "es"} remain for this saved test run.
                            </div>
                        )}
                        {workbenchSaveNote && (
                            <div className="mt-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
                                {workbenchSaveNote}
                            </div>
                        )}
                        {workbenchSaveError && (
                            <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                                Sandbox evaluation finished, but RegEngine could not save the workbench run. {workbenchSaveError}
                            </div>
                        )}
                    </section>
                )}
            </div>
        </main>
    );
}

function FunnelStep({
    id,
    label,
    value,
    valueSuffix,
    sub,
    tone,
    tag,
    active,
    locked,
    children,
}: {
    id: string;
    label: string;
    value: string;
    valueSuffix?: string;
    sub: string;
    tone: "ok" | "warn" | "muted" | "locked";
    tag?: string;
    active?: boolean;
    locked?: boolean;
    children?: React.ReactNode;
}) {
    const toneClass =
        tone === "ok"
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : tone === "warn"
            ? "border-amber-200 bg-amber-50 text-amber-800"
            : tone === "muted"
            ? "border-slate-200 bg-slate-50 text-slate-600"
            : "border-slate-200 bg-slate-100 text-slate-500";

    return (
        <li
            data-funnel-step={id}
            className={cn(
                "rounded-lg border bg-white p-3 shadow-sm transition-shadow",
                active && "border-emerald-500 shadow-[0_0_0_1px_rgba(16,185,129,0.4)]",
                locked && "opacity-70"
            )}
        >
            <div className="flex items-center justify-between">
                <Badge variant="outline" className={cn("border text-[9px]", toneClass)}>
                    {label}
                </Badge>
                <span className="text-[11px] text-slate-500">
                    {locked ? <Lock className="h-3 w-3" aria-hidden /> : tag ?? (active ? "▶ next" : "")}
                </span>
            </div>
            <div className="mt-2 text-2xl font-semibold text-slate-950">
                {value}
                {valueSuffix && <span className="ml-1 text-sm font-normal text-slate-500">{valueSuffix}</span>}
            </div>
            <div className="text-[11px] text-slate-500">{sub}</div>
            {children}
        </li>
    );
}

function GroupRootCausePanel({
    groupId,
    sourceSupplierBreakdown,
    lotCount,
}: {
    groupId: ExceptionPatternId;
    sourceSupplierBreakdown:
        | ReturnType<typeof summarizeSourceSuppliers>
        | null;
    lotCount: number;
}) {
    if (groupId === "handoff") {
        return (
            <div className="rounded-md border border-violet-200 bg-violet-50 p-3 text-[13px]">
                <div className="flex items-start gap-2">
                    <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-violet-700" />
                    <div>
                        <div className="font-medium text-slate-900">
                            Root cause: 1 mapping fix likely clears all {lotCount}.
                        </div>
                        <div className="mt-0.5 text-slate-600">
                            Map the <code className="font-mono text-xs text-slate-800">handoff_evidence</code> column from your shipping CSV, or upload a corrected file with packing/shipping/DC-receive timestamps.
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                            <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                                Map handoff fields
                            </Button>
                            <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                                Upload corrected CSV
                            </Button>
                            <Button variant="ghost" className="h-7 px-2 text-xs text-slate-500">
                                View example
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    if (groupId === "source") {
        const supplierCount =
            (sourceSupplierBreakdown?.harvestSuppliers.length ?? 0) +
            (sourceSupplierBreakdown?.coolingSuppliers.length ?? 0);
        return (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-[13px]">
                <div className="flex items-start gap-2">
                    <Package className="mt-0.5 h-4 w-4 shrink-0 text-amber-700" />
                    <div className="flex-1">
                        <div className="font-medium text-slate-900">
                            Root cause: {Math.max(1, supplierCount)} supplier{supplierCount === 1 ? "" : "s"} aren&apos;t sending harvest/cool timestamps.
                        </div>
                        <div className="mt-0.5 text-slate-600">
                            Fix at the source — sandbox can&apos;t fabricate KDEs.
                        </div>
                        {sourceSupplierBreakdown && supplierCount > 0 && (
                            <div className="mt-2 grid grid-cols-1 gap-2 text-xs sm:grid-cols-3">
                                {sourceSupplierBreakdown.harvestSuppliers.map((s) => (
                                    <div
                                        key={`harvest-${s.supplier}`}
                                        className="rounded-md border border-amber-200 bg-white px-2.5 py-2"
                                    >
                                        <div className="text-slate-500">{s.supplier}</div>
                                        <div className="font-medium text-slate-900">
                                            {s.lotCount} lot{s.lotCount === 1 ? "" : "s"} · harvest_ts
                                        </div>
                                    </div>
                                ))}
                                {sourceSupplierBreakdown.coolingSuppliers.map((s) => (
                                    <div
                                        key={`cooling-${s.supplier}`}
                                        className="rounded-md border border-amber-200 bg-white px-2.5 py-2"
                                    >
                                        <div className="text-slate-500">{s.supplier}</div>
                                        <div className="font-medium text-slate-900">
                                            {s.lotCount} lot{s.lotCount === 1 ? "" : "s"} · cooling_ts
                                        </div>
                                    </div>
                                ))}
                                {sourceSupplierBreakdown.overlapCount > 0 && (
                                    <div className="rounded-md border border-amber-200 bg-white px-2.5 py-2">
                                        <div className="text-slate-500">Both missing</div>
                                        <div className="font-medium text-slate-900">
                                            {sourceSupplierBreakdown.overlapCount} lot{sourceSupplierBreakdown.overlapCount === 1 ? "" : "s"}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-2">
                            <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                                <Mail className="mr-1.5 h-3.5 w-3.5" />
                                Email suppliers
                            </Button>
                            <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                                Map source columns
                            </Button>
                            <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                                Upload supplier CSV
                            </Button>
                            <Button variant="ghost" className="h-7 px-2 text-xs text-slate-500">
                                View FSMA 204 KDE list
                            </Button>
                        </div>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div
            className="rounded-md border border-slate-200 bg-slate-50 p-3 text-[13px]"
            data-mixed-no-bulk-fix="true"
        >
            <div className="flex items-start gap-2">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-slate-500" />
                <div className="flex-1">
                    <div className="font-medium text-slate-900">No single root cause. These need lot-by-lot triage.</div>
                    <div className="mt-0.5 text-slate-600">
                        Each lot has a different combination of missing KDEs. A bulk fix would either over-match or under-match. Recommend triaging individually — start with the largest case counts.
                    </div>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                            Sort by case count
                        </Button>
                        <Button variant="outline" className="h-7 border-slate-300 bg-white px-2 text-xs">
                            Sort by recency
                        </Button>
                        <Button variant="ghost" className="h-7 px-2 text-xs text-slate-500">
                            <ClipboardList className="mr-1.5 h-3.5 w-3.5" />
                            Export to CSV
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}

function LotRow({
    lot,
    groupId,
    isSelected,
    checked,
    onCheckedChange,
    onSelect,
}: {
    lot: LotSummary;
    groupId: ExceptionPatternId;
    isSelected: boolean;
    checked: boolean;
    onCheckedChange: (checked: boolean) => void;
    onSelect: () => void;
}) {
    const missingFieldsLabel = lot.missingCtes.length
        ? `missing: ${lot.missingCtes.slice(0, 2).join(", ")}${lot.missingCtes.length > 2 ? "…" : ""}`
        : `delivery: ${lot.readiness.deliveryLabel}`;

    const showHandoffChip = groupId !== "source";
    const showSourceChip = groupId !== "handoff";

    return (
        <div
            data-lot-row={lot.lotCode}
            className={cn(
                "flex items-center gap-3 border-b border-slate-100 px-3 py-2 text-[13px] transition-colors last:border-b-0 hover:bg-slate-50",
                isSelected && "bg-emerald-50/40 outline outline-1 outline-emerald-200"
            )}
        >
            <Checkbox
                checked={checked}
                onCheckedChange={(value) => onCheckedChange(value === true)}
                aria-label={`Select ${lot.lotCode}`}
                className="h-4 w-4 shrink-0"
            />
            <button
                type="button"
                onClick={onSelect}
                className="flex min-w-0 flex-1 flex-wrap items-center gap-2 text-left"
            >
                <span className="font-mono text-xs text-slate-900">{lot.lotCode}</span>
                {groupId === "handoff" && (
                    <Badge variant="outline" className="border-rose-200 bg-rose-50 text-[9px] text-rose-700">
                        handoff
                    </Badge>
                )}
                {groupId === "source" && (
                    <Badge variant="outline" className="border-amber-200 bg-amber-50 text-[9px] text-amber-800">
                        source
                    </Badge>
                )}
                {groupId === "mixed" && (
                    <>
                        {showHandoffChip && (
                            <Badge variant="outline" className="border-rose-200 bg-rose-50 text-[9px] text-rose-700">
                                handoff
                            </Badge>
                        )}
                        {showSourceChip && (
                            <Badge variant="outline" className="border-amber-200 bg-amber-50 text-[9px] text-amber-800">
                                source
                            </Badge>
                        )}
                    </>
                )}
                <span className="truncate text-xs text-slate-500">{lot.product}</span>
            </button>
            <span className="ml-auto truncate text-xs text-slate-500">{missingFieldsLabel}</span>
            {groupId === "mixed" && (
                <Button variant="ghost" className="h-6 px-2 text-[11px] text-slate-500 hover:text-slate-900">
                    Triage
                </Button>
            )}
        </div>
    );
}

function KdeTile({
    label,
    value,
    tone = "default",
}: {
    label: string;
    value: string;
    tone?: "default" | "ok" | "bad";
}) {
    return (
        <div
            className={cn(
                "rounded-md border bg-slate-50 px-2.5 py-2",
                tone === "bad" ? "border-rose-200" : "border-slate-200"
            )}
        >
            <div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div>
            <div
                className={cn(
                    "font-mono text-xs",
                    tone === "bad" ? "text-rose-700" : "text-slate-900"
                )}
            >
                {value}
            </div>
        </div>
    );
}

export { classifyExceptionLot, groupExceptionsByPattern };
