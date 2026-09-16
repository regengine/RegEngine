'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Callout } from "@/components/ui/callout";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/components/ui/use-toast";
import { useAuth } from "@/lib/auth-context";
import { useTenant } from "@/lib/tenant-context";
import { getServiceURL } from "@/lib/api-config";
import { AlertTriangle, GitBranch, Search } from "lucide-react";

// ── Utilities ──
function mulberry32(seed: number) {
    let a = seed >>> 0;
    return function () {
        a |= 0; a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}
function clamp(n: number, min: number, max: number) { return Math.max(min, Math.min(max, n)); }

// ── Types ──
type NodeType = "Supplier" | "Facility" | "Product" | "Lot" | "CTE" | "Location";
type EdgeType = "Supplies" | "Contains" | "Transforms" | "ShipsTo" | "TracedFrom" | "LocatedAt";
type GraphNode = { id: string; type: NodeType; label: string; meta?: Record<string, unknown>; x: number; y: number };
type GraphEdge = { id: string; type: EdgeType; from: string; to: string; meta?: Record<string, unknown> };
type TraceMode = "forward" | "backward" | "bidirectional";
type Viewport = { scale: number; panX: number; panY: number };
type TraceabilityQueryEvidence = {
    endpoint: string;
    params?: Record<string, unknown>;
    result_count?: number;
    next_cursor?: string | null;
};
type TraceabilityQueryResponse = {
    intent: string;
    filters?: Record<string, unknown>;
    answer: string;
    results: Array<Record<string, unknown>>;
    evidence: TraceabilityQueryEvidence[];
    confidence: number;
    warnings: string[];
};
type TraceabilityTableRow = {
    tlc: string;
    product: string;
    facility: string;
    date: string;
    eventType: string;
};

// Node and edge hues are CATEGORICAL, so they come from the `--re-cat-*` set
// (SPEC §1.6.6) rather than the status palette: a "Location" node is a kind of
// thing, not a failing one. Every value is a token, so the canvas repaints
// correctly in both themes instead of assuming a dark ground.
const NTS: Record<NodeType, { color: string; icon: string; kde: string }> = {
    Supplier: { color: "var(--re-cat-1)", icon: "🏭", kde: "Source" },
    Facility: { color: "var(--re-cat-3)", icon: "🏗️", kde: "Location" },
    Product: { color: "var(--re-cat-2)", icon: "📦", kde: "Product" },
    Lot: { color: "var(--re-cat-4)", icon: "🔖", kde: "Traceability Lot" },
    CTE: { color: "var(--re-cat-5)", icon: "📍", kde: "Critical Tracking Event" },
    Location: { color: "var(--re-cat-6)", icon: "📌", kde: "Ship-to/Ship-from" },
};

const ETS: Record<EdgeType, { color: string; dash: boolean }> = {
    Supplies: { color: "var(--re-cat-1)", dash: false }, Contains: { color: "var(--re-cat-4)", dash: false },
    Transforms: { color: "var(--re-cat-2)", dash: false }, ShipsTo: { color: "var(--re-cat-3)", dash: false },
    TracedFrom: { color: "var(--re-cat-5)", dash: true }, LocatedAt: { color: "var(--re-cat-6)", dash: true },
};

/** Canvas has no `color-mix`, so tints are built from a resolved token hex. */
function hexToRgba(hex: string, a: number) {
    const r = parseInt(hex.slice(1, 3), 16) || 0;
    const g = parseInt(hex.slice(3, 5), 16) || 0;
    const b = parseInt(hex.slice(5, 7), 16) || 0;
    return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function nodeR(t: NodeType) { return t === "Facility" ? 20 : t === "Supplier" || t === "Product" ? 18 : t === "Location" ? 14 : 16; }

function seededScenario(seed = 204) {
    const rng = mulberry32(seed); const j = () => (rng() - 0.5) * 30;
    const nodes: GraphNode[] = [
        { id: "sup-1", type: "Supplier", label: "Arroyo Farms", x: 120 + j(), y: 140 + j(), meta: { region: "CA" } },
        { id: "loc-1", type: "Location", label: "Salinas, CA", x: 110 + j(), y: 260 + j() },
        { id: "fac-1", type: "Facility", label: "Cooler • Farm Pack", x: 280 + j(), y: 160 + j() },
        { id: "cte-1", type: "CTE", label: "Harvest / Cooling", x: 280 + j(), y: 260 + j() },
        { id: "prod-1", type: "Product", label: "Romaine Lettuce", x: 460 + j(), y: 140 + j() },
        { id: "lot-1", type: "Lot", label: "TLC: RML-021-744", x: 460 + j(), y: 260 + j() },
        { id: "fac-2", type: "Facility", label: "Processor • Wash/Trim", x: 640 + j(), y: 150 + j() },
        { id: "cte-2", type: "CTE", label: "Transform", x: 640 + j(), y: 260 + j() },
        { id: "lot-2", type: "Lot", label: "TLC: RML-021-744-A", x: 800 + j(), y: 260 + j() },
        { id: "fac-3", type: "Facility", label: "DC • West", x: 960 + j(), y: 150 + j() },
        { id: "cte-3", type: "CTE", label: "Ship to DC", x: 960 + j(), y: 260 + j() },
        { id: "fac-4", type: "Facility", label: "Retail • Pasadena", x: 1120 + j(), y: 150 + j() },
        { id: "cte-4", type: "CTE", label: "Receive / Sell", x: 1120 + j(), y: 260 + j() },
    ];
    const edges: GraphEdge[] = [
        { id: "e-1", type: "LocatedAt", from: "sup-1", to: "loc-1" }, { id: "e-2", type: "Supplies", from: "sup-1", to: "fac-1" },
        { id: "e-3", type: "TracedFrom", from: "cte-1", to: "fac-1" }, { id: "e-4", type: "Contains", from: "prod-1", to: "lot-1" },
        { id: "e-5", type: "TracedFrom", from: "cte-1", to: "lot-1" }, { id: "e-6", type: "ShipsTo", from: "fac-1", to: "fac-2" },
        { id: "e-7", type: "TracedFrom", from: "cte-2", to: "fac-2" }, { id: "e-8", type: "Transforms", from: "lot-1", to: "lot-2" },
        { id: "e-9", type: "TracedFrom", from: "cte-2", to: "lot-2" }, { id: "e-10", type: "ShipsTo", from: "fac-2", to: "fac-3" },
        { id: "e-11", type: "TracedFrom", from: "cte-3", to: "fac-3" }, { id: "e-12", type: "ShipsTo", from: "fac-3", to: "fac-4" },
        { id: "e-13", type: "TracedFrom", from: "cte-4", to: "fac-4" }, { id: "e-14", type: "TracedFrom", from: "cte-3", to: "lot-2" },
        { id: "e-15", type: "TracedFrom", from: "cte-4", to: "lot-2" },
    ];
    return { nodes, edges };
}

function traceNodes(startId: string, edges: GraphEdge[], mode: TraceMode, depth: number) {
    const out = new Map<string, string[]>(), inn = new Map<string, string[]>();
    edges.forEach(e => { if (!out.has(e.from)) out.set(e.from, []); if (!inn.has(e.to)) inn.set(e.to, []); out.get(e.from)!.push(e.to); inn.get(e.to)!.push(e.from); });
    const visited = new Set([startId]), usedEdges = new Set<string>();
    const epMap = new Map<string, string[]>(); edges.forEach(e => { const k = `${e.from}→${e.to}`; if (!epMap.has(k)) epMap.set(k, []); epMap.get(k)!.push(e.id); });
    const q: { id: string; d: number }[] = [{ id: startId, d: 0 }];
    while (q.length) {
        const c = q.shift()!; if (c.d >= depth) continue;
        const nexts: string[] = [];
        if (mode !== "backward") { (out.get(c.id) || []).forEach(to => { nexts.push(to); (epMap.get(`${c.id}→${to}`) || []).forEach(id => usedEdges.add(id)); }); }
        if (mode !== "forward") { (inn.get(c.id) || []).forEach(from => { nexts.push(from); (epMap.get(`${from}→${c.id}`) || []).forEach(id => usedEdges.add(id)); }); }
        nexts.forEach(n => { if (!visited.has(n)) { visited.add(n); q.push({ id: n, d: c.d + 1 }); } });
    }
    return { nodes: visited, edges: usedEdges };
}

function useAnimFrame(cb: () => void, on: boolean) {
    const raf = useRef<number | null>(null);
    useEffect(() => { if (!on) return; const tick = () => { cb(); raf.current = requestAnimationFrame(tick); }; raf.current = requestAnimationFrame(tick); return () => { if (raf.current) cancelAnimationFrame(raf.current); }; }, [cb, on]);
}

function getConfidenceDescriptor(confidence: number): { label: string; tone: "neutral" | "warning" | "danger" } {
    if (confidence >= 0.85) {
        return { label: "high", tone: "neutral" };
    }
    if (confidence >= 0.7) {
        return { label: "medium", tone: "warning" };
    }
    return { label: "low", tone: "danger" };
}

function toRow(candidate: Record<string, unknown>, fallbackTlc = ""): TraceabilityTableRow {
    const str = (v: unknown): string => (typeof v === "string" ? v : "");
    const facilityValue = candidate.facility;
    const facilityName =
        (typeof facilityValue === "string" ? facilityValue : str((facilityValue as Record<string, unknown> | undefined)?.name)) ||
        str(candidate.facility_name) ||
        str(candidate.location_description) ||
        str(candidate.location_gln) ||
        "";
    return {
        tlc: str(candidate.tlc) || str(candidate.lot_id) || str(candidate.traceability_lot_code) || fallbackTlc || "",
        product: str(candidate.product_description) || str(candidate.product) || str(candidate.description) || "",
        facility: facilityName,
        date: str(candidate.event_date) || str(candidate.last_event_date) || "",
        eventType: str(candidate.type) || str(candidate.event_type) || str(candidate.last_event_type) || "",
    };
}

function collectQueryRows(intent: string, results: Array<Record<string, unknown>>): TraceabilityTableRow[] {
    const rows: TraceabilityTableRow[] = [];

    for (const item of results) {
        if (intent === "trace_forward" || intent === "trace_backward") {
            const nestedEvents = Array.isArray(item.events) ? (item.events as Record<string, unknown>[]) : [];
            if (nestedEvents.length > 0) {
                const facilities = Array.isArray(item.facilities) ? item.facilities : [];
                const lotId = typeof item.lot_id === "string" ? item.lot_id : "";
                for (const event of nestedEvents) {
                    rows.push(toRow({ ...event, facility: facilities[0] as unknown, lot_id: item.lot_id }, lotId));
                }
                continue;
            }
        }

        if (Array.isArray(item.events)) {
            for (const nested of item.events as Record<string, unknown>[]) {
                rows.push(toRow(nested));
            }
            continue;
        }

        rows.push(toRow(item));
    }

    return rows.slice(0, 200);
}

export function SupplyChainKnowledgeGraphBuilder() {
    const { apiKey } = useAuth();
    const { tenantId } = useTenant();
    const { toast } = useToast();
    const [seed] = useState(204);
    const scenario = useMemo(() => seededScenario(seed), [seed]);
    const [nodes, setNodes] = useState<GraphNode[]>(scenario.nodes);
    const [edges, setEdges] = useState<GraphEdge[]>(scenario.edges);
    useEffect(() => { setNodes(scenario.nodes); setEdges(scenario.edges); }, [scenario]);

    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const containerRef = useRef<HTMLDivElement | null>(null);
    const [vp, setVp] = useState<Viewport>({ scale: 1, panX: 0, panY: 0 });
    const [dragId, setDragId] = useState<string | null>(null);
    const [dragOff, setDragOff] = useState<{ x: number; y: number } | null>(null);
    const [panning, setPanning] = useState(false);
    const [lastPan, setLastPan] = useState<{ x: number; y: number } | null>(null);
    const [selNode, setSelNode] = useState<string | null>(null);
    const [selEdge, setSelEdge] = useState<string | null>(null);
    const [trMode, setTrMode] = useState<TraceMode>("forward");
    const trDepth = 3;
    const filterType: NodeType | "All" = "All";
    const [search, setSearch] = useState("");
    const [traceabilityQuery, setTraceabilityQuery] = useState("");
    const [queryLoading, setQueryLoading] = useState(false);
    const [queryResponse, setQueryResponse] = useState<TraceabilityQueryResponse | null>(null);

    const selNodeObj = useMemo(() => nodes.find(n => n.id === selNode) || null, [nodes, selNode]);
    const trace = useMemo(() => selNode ? traceNodes(selNode, edges, trMode, trDepth) : null, [selNode, edges, trMode, trDepth]);

    const visNodes = useMemo(() => { const q = search.trim().toLowerCase(); return nodes.filter(n => { if (filterType !== "All" && n.type !== filterType) return false; if (!q) return true; return n.label.toLowerCase().includes(q) || n.id.includes(q); }); }, [nodes, filterType, search]);
    const visIds = useMemo(() => new Set(visNodes.map(n => n.id)), [visNodes]);
    const visEdges = useMemo(() => edges.filter(e => visIds.has(e.from) && visIds.has(e.to)), [edges, visIds]);
    const queryRows = useMemo(
        () => collectQueryRows(queryResponse?.intent || "", queryResponse?.results || []),
        [queryResponse],
    );
    const confidenceInfo = queryResponse
        ? getConfidenceDescriptor(queryResponse.confidence)
        : null;
    const showWarningBanner = Boolean(
        queryResponse && (queryResponse.confidence < 0.7 || queryResponse.warnings.length > 0)
    );

    const [relaxing, setRelaxing] = useState(false);
    useAnimFrame(() => {
        setNodes(prev => {
            const next = prev.map(n => ({ ...n })); const byId = new Map(next.map(n => [n.id, n]));
            for (let i = 0; i < next.length; i++) for (let j = i + 1; j < next.length; j++) {
                const a = next[i], b = next[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy + .001;
                const md = nodeR(a.type) + nodeR(b.type) + 18;
                if (d2 < md * md) { const d = Math.sqrt(d2), p = ((md - d) / md) * .9, nx = dx / d, ny = dy / d; a.x += nx * p; a.y += ny * p; b.x -= nx * p; b.y -= ny * p; }
            }
            for (const e of edges) { const a = byId.get(e.from), b = byId.get(e.to); if (!a || !b) continue; const dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) + .001, pull = (d - 180) * .008, nx = dx / d, ny = dy / d; a.x += nx * pull; a.y += ny * pull; b.x -= nx * pull; b.y -= ny * pull; }
            return next;
        });
    }, relaxing);
    useEffect(() => { if (!relaxing) return; const t = setTimeout(() => setRelaxing(false), 900); return () => clearTimeout(t); }, [relaxing]);

    const toW = (cx: number, cy: number) => { const r = canvasRef.current?.getBoundingClientRect(); return r ? { x: (cx - r.left - vp.panX) / vp.scale, y: (cy - r.top - vp.panY) / vp.scale } : { x: 0, y: 0 }; };
    const hitNode = (wx: number, wy: number) => { for (let i = visNodes.length - 1; i >= 0; i--) { const n = visNodes[i], r = nodeR(n.type), dx = wx - n.x, dy = wy - n.y; if (dx * dx + dy * dy <= r * r) return n.id; } return null; };

    function draw() {
        const canvas = canvasRef.current; if (!canvas) return; const ctx = canvas.getContext("2d"); if (!ctx) return;
        const dpr = typeof window !== 'undefined' ? (window.devicePixelRatio || 1) : 1, rect = canvas.getBoundingClientRect();
        const w = Math.floor(rect.width * dpr), h = Math.floor(rect.height * dpr);

        // Resolve the design tokens once per frame — Canvas cannot read CSS
        // variables, so the ink, rules and ground are pulled from the live
        // computed style and therefore follow the light/dark switch.
        const rootStyles = getComputedStyle(document.documentElement);
        const resolveColor = (c: string) => c.startsWith('var(') ? rootStyles.getPropertyValue(c.slice(4, -1)).trim() : c;
        const ink = resolveColor('var(--re-text-primary)');
        const mutedInk = resolveColor('var(--re-text-tertiary)');
        const rule = resolveColor('var(--re-border-subtle)');
        const well = resolveColor('var(--re-surface-inset)');

        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
        ctx.save(); ctx.translate(vp.panX, vp.panY); ctx.scale(vp.scale, vp.scale);

        // Grid
        ctx.strokeStyle = rule; ctx.lineWidth = 0.5;
        const gs = 40, sx = Math.floor(-vp.panX / vp.scale / gs) * gs - gs, sy = Math.floor(-vp.panY / vp.scale / gs) * gs - gs;
        for (let x = sx; x < sx + rect.width / vp.scale + gs * 3; x += gs) { ctx.beginPath(); ctx.moveTo(x, sy); ctx.lineTo(x, sy + rect.height / vp.scale + gs * 3); ctx.stroke(); }
        for (let y = sy; y < sy + rect.height / vp.scale + gs * 3; y += gs) { ctx.beginPath(); ctx.moveTo(sx, y); ctx.lineTo(sx + rect.width / vp.scale + gs * 3, y); ctx.stroke(); }

        // Edges
        for (const e of visEdges) {
            const a = nodes.find(n => n.id === e.from), b = nodes.find(n => n.id === e.to); if (!a || !b) continue;
            const hl = trace?.edges.has(e.id), sel = selEdge === e.id, dim = trace && !hl && !sel, es = ETS[e.type] || ETS.Supplies;
            const bColor = resolveColor(es.color);
            ctx.lineWidth = sel ? 3 : hl ? 2.5 : 1.2;

            ctx.strokeStyle = sel ? ink : hl ? bColor : dim ? hexToRgba(bColor, 0.2) : hexToRgba(bColor, 0.45);
            if (es.dash) ctx.setLineDash([6, 4]); else ctx.setLineDash([]);
            ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.setLineDash([]);
            const dx = b.x - a.x, dy = b.y - a.y, dist = Math.sqrt(dx * dx + dy * dy) || 1, ux = dx / dist, uy = dy / dist;
            const px = b.x - ux * nodeR(b.type), py = b.y - uy * nodeR(b.type);
            ctx.fillStyle = ctx.strokeStyle; ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px - ux * 10 - uy * 5, py - uy * 10 + ux * 5); ctx.lineTo(px - ux * 10 + uy * 5, py - uy * 10 - ux * 5); ctx.closePath(); ctx.fill();
        }

        // Nodes
        for (const n of visNodes) {
            const r = nodeR(n.type), sel2 = selNode === n.id, hl = trace?.nodes.has(n.id), dim = trace && trace.nodes.size > 0 && !hl && !sel2, s = NTS[n.type];
            const sColor = resolveColor(s.color);

            if (sel2 || hl) { ctx.beginPath(); ctx.arc(n.x, n.y, r + 8, 0, Math.PI * 2); ctx.fillStyle = hexToRgba(sColor, 0.15); ctx.fill(); }
            ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fillStyle = dim ? hexToRgba(well, 0.75) : hexToRgba(sColor, 0.15); ctx.fill();
            ctx.lineWidth = sel2 ? 2.5 : 1.5; ctx.strokeStyle = dim ? hexToRgba(mutedInk, 0.25) : sel2 ? ink : sColor; ctx.stroke();
            ctx.font = "14px serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = dim ? hexToRgba(mutedInk, 0.3) : ink; ctx.fillText(s.icon, n.x, n.y);
            ctx.font = `11px ${rootStyles.getPropertyValue('--re-font-sans').trim() || 'ui-sans-serif'}`; ctx.fillStyle = dim ? hexToRgba(mutedInk, 0.35) : ink; ctx.textBaseline = "top";
            ctx.fillText(n.label, n.x, n.y + r + 5);
        }
        ctx.restore();
    }

    // `draw` is a plain render-scope function that reads the canvas and every
    // piece of view state. The dependency list below is the state it actually
    // paints from; adding `draw` itself would change identity on every render
    // and repaint in a loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { draw(); }, [nodes, edges, vp, selNode, selEdge, trace, visNodes, visEdges]);
    // Keep a ref pointing at the latest `draw` so the once-bound resize listener
    // below always repaints from current state instead of the first render's
    // stale closure.
    const drawRef = useRef(draw);
    drawRef.current = draw;
    // The resize listener is bound once (empty deps) — the `drawRef` indirection
    // lets it read fresh state without re-registering on every render.
    useEffect(() => { const h = () => drawRef.current(); if (typeof window !== 'undefined') window.addEventListener("resize", h); return () => { if (typeof window !== 'undefined') window.removeEventListener("resize", h); }; }, []);

    const fitView = () => {
        if (!containerRef.current || !visNodes.length) return;
        const rect = containerRef.current.getBoundingClientRect();
        const xs = visNodes.map(n => n.x), ys = visNodes.map(n => n.y);
        const [mx, Mx, my, My] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
        const scale = clamp(Math.min(rect.width / (Mx - mx + 140), rect.height / (My - my + 140)), 0.5, 2);
        setVp({ scale, panX: rect.width / 2 - ((mx + Mx) / 2) * scale, panY: rect.height / 2 - ((my + My) / 2) * scale });
    };
    // One-shot initial framing after the container has been laid out. fitView
    // calls setVp, so depending on it would re-frame the graph on every pan or
    // zoom and fight the user's own view changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(() => { setTimeout(fitView, 50); }, []);

    const onWheel = (e: React.WheelEvent) => { e.preventDefault(); const f = e.deltaY < 0 ? 1.08 : 0.92; const ns = clamp(vp.scale * f, 0.4, 2.6); const r = canvasRef.current?.getBoundingClientRect(); if (!r) return; const cx = e.clientX - r.left, cy = e.clientY - r.top; const wx = (cx - vp.panX) / vp.scale, wy = (cy - vp.panY) / vp.scale; setVp({ scale: ns, panX: cx - wx * ns, panY: cy - wy * ns }); };
    const onDown = (e: React.MouseEvent) => { const w = toW(e.clientX, e.clientY); const h = hitNode(w.x, w.y); if (h) { setSelEdge(null); setSelNode(h); setDragId(h); const n = nodes.find(x => x.id === h); if (n) setDragOff({ x: w.x - n.x, y: w.y - n.y }); } else { setSelNode(null); setSelEdge(null); setPanning(true); setLastPan({ x: e.clientX, y: e.clientY }); } };
    const onMove = (e: React.MouseEvent) => { if (dragId && dragOff) { const w = toW(e.clientX, e.clientY); setNodes(p => p.map(n => n.id === dragId ? { ...n, x: w.x - dragOff.x, y: w.y - dragOff.y } : n)); } else if (panning && lastPan) { setVp(v => ({ ...v, panX: v.panX + e.clientX - lastPan.x, panY: v.panY + e.clientY - lastPan.y })); setLastPan({ x: e.clientX, y: e.clientY }); } };
    const onUp = () => { setDragId(null); setDragOff(null); setPanning(false); setLastPan(null); };
    const runTraceabilityQuery = async (e: React.FormEvent) => {
        e.preventDefault();
        const rawQuery = traceabilityQuery.trim();
        if (!rawQuery || queryLoading) return;

        if (!apiKey) {
            toast({
                title: "Missing API key",
                description: "Please sign in to run traceability queries.",
                variant: "destructive",
            });
            return;
        }

        setQueryLoading(true);

        try {
            const response = await fetchWithCsrf(`${getServiceURL("nlp")}/api/v1/query/traceability`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-RegEngine-API-Key": apiKey,
                    "X-Tenant-ID": tenantId,
                },
                body: JSON.stringify({
                    query: rawQuery,
                    limit: 50,
                }),
            });

            let payload: TraceabilityQueryResponse | null = null;
            try {
                payload = await response.json() as TraceabilityQueryResponse;
            } catch {
                payload = null;
            }

            if (!response.ok) {
                const detail = (payload as Record<string, unknown> | null)?.detail as string | undefined || `Request failed with status ${response.status}`;
                throw new Error(detail);
            }

            setQueryResponse(payload as TraceabilityQueryResponse);
        } catch (error) {
            const message = error instanceof Error ? error.message : "Unknown query error";
            toast({
                title: "Traceability query failed",
                description: message,
                variant: "destructive",
            });
        } finally {
            setQueryLoading(false);
        }
    };

    const queryColumns: DataTableColumn<TraceabilityTableRow>[] = [
        { key: "tlc", header: "TLC", mono: true, cell: (row) => row.tlc || "—" },
        { key: "product", header: "Product", cell: (row) => row.product || "—" },
        { key: "facility", header: "Facility", cell: (row) => row.facility || "—" },
        { key: "date", header: "Date", mono: true, cell: (row) => row.date || "—" },
        { key: "eventType", header: "Event Type", cell: (row) => row.eventType || "—" },
    ];

    return (
        <div className="space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                <div>
                    <div className="text-heading text-re-text-primary">Knowledge Graph Builder</div>
                    <div className="mt-1 text-ui text-re-text-secondary">FSMA 204-native traceability graph.</div>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" onClick={fitView}>Fit View</Button>
                    <Button
                        variant="secondary"
                        onClick={() => setRelaxing(true)}
                        leadingIcon={<GitBranch aria-hidden="true" strokeWidth={1.75} />}
                    >
                        Relax Layout
                    </Button>
                </div>
            </div>

            <form className="rounded-md border border-re-border bg-re-surface-card p-4" onSubmit={runTraceabilityQuery}>
                <div className="flex flex-col gap-2 md:flex-row">
                    <label htmlFor="kg-traceability-query" className="sr-only">
                        Ask your traceability data
                    </label>
                    <Input
                        id="kg-traceability-query"
                        placeholder="Ask your traceability data… (e.g. Where did lot ABC-2025-001 come from?)"
                        value={traceabilityQuery}
                        onChange={(e) => setTraceabilityQuery(e.target.value)}
                    />
                    <Button
                        type="submit"
                        loading={queryLoading}
                        disabled={queryLoading || !traceabilityQuery.trim()}
                    >
                        {queryLoading ? "Querying" : "Ask"}
                    </Button>
                </div>
                <p className="mt-2 text-small text-re-text-tertiary">
                    Try: “Where did lot ABC-2025-001 come from?” or “Show lettuce events from last 30 days”.
                </p>
            </form>

            {queryResponse && (
                <div className="space-y-4">
                    <Card>
                        <CardContent className="p-4">
                            <div className="mb-1 flex flex-wrap items-center gap-2">
                                <div className="text-subheading text-re-text-primary">Answer</div>
                                {confidenceInfo && (
                                    <Badge tone={confidenceInfo.tone}>
                                        Confidence {confidenceInfo.label} ({Math.round(queryResponse.confidence * 100)}%)
                                    </Badge>
                                )}
                            </div>
                            <p className="text-ui text-re-text-secondary">{queryResponse.answer}</p>
                        </CardContent>
                    </Card>

                    {showWarningBanner && (
                        <Callout tone="warning" role="status" title="Query warnings" icon={AlertTriangle}>
                            {queryResponse.warnings.length > 0
                                ? queryResponse.warnings.join(" ")
                                : "Interpretation confidence is below 70%; verify filters before acting."}
                        </Callout>
                    )}

                    <div>
                        <div className="mb-2 text-label text-re-text-muted">Results ({queryRows.length})</div>
                        <DataTable
                            caption={`Traceability query results (${queryRows.length})`}
                            columns={queryColumns}
                            data={queryRows}
                            rowKey={(row, idx) => `${row.tlc}-${row.eventType}-${row.date}-${idx}`}
                            status={queryRows.length === 0 ? "empty" : "idle"}
                            empty={{ title: "No rows returned for this query.", size: "sm" }}
                        />
                    </div>

                    <details className="rounded-md border border-re-border bg-re-surface-card p-4">
                        <summary className="cursor-pointer text-ui font-medium text-re-text-primary">
                            Evidence ({queryResponse.evidence?.length || 0})
                        </summary>
                        <div className="mt-3 space-y-2">
                            {(queryResponse.evidence || []).map((item, idx) => (
                                <div key={`${item.endpoint}-${idx}`} className="rounded-md border border-re-border-subtle p-3 text-small text-re-text-secondary">
                                    <div><span className="font-medium text-re-text-primary">Endpoint:</span> <span className="font-mono text-[0.8125rem]">{item.endpoint}</span></div>
                                    <div><span className="font-medium text-re-text-primary">Result count:</span> <span className="tabular-nums">{item.result_count ?? 0}</span></div>
                                    {item.next_cursor ? (
                                        <div><span className="font-medium text-re-text-primary">Next cursor:</span> <span className="font-mono text-[0.8125rem] break-all">{item.next_cursor}</span></div>
                                    ) : null}
                                    {item.params ? (
                                        <pre className="mt-2 overflow-auto rounded-md bg-re-surface-inset p-2 font-mono text-[0.8125rem] text-re-text-secondary">
                                            {JSON.stringify(item.params, null, 2)}
                                        </pre>
                                    ) : null}
                                </div>
                            ))}
                        </div>
                    </details>
                </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
                <div className="w-full sm:w-60">
                    <label htmlFor="kg-node-search" className="sr-only">Search</label>
                    <Input
                        id="kg-node-search"
                        placeholder="Search..."
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        leadingIcon={<Search aria-hidden="true" strokeWidth={1.75} />}
                    />
                </div>
                <div>
                    <label htmlFor="kg-trace-mode" className="sr-only">Trace direction</label>
                    <Select value={trMode} onValueChange={v => setTrMode(v as TraceMode)}>
                        <SelectTrigger id="kg-trace-mode" className="w-40"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="forward">→ Forward</SelectItem>
                            <SelectItem value="backward">← Backward</SelectItem>
                            <SelectItem value="bidirectional">↔ Both</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>

            <div ref={containerRef} className="relative h-[360px] w-full overflow-hidden rounded-lg border border-re-border bg-re-surface-inset sm:h-[440px]">
                <canvas
                    ref={canvasRef}
                    className="h-full w-full outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-inset"
                    style={{ cursor: dragId ? "grabbing" : "crosshair" }}
                    onWheel={onWheel}
                    onMouseDown={onDown}
                    onMouseMove={onMove}
                    onMouseUp={onUp}
                    onMouseLeave={onUp}
                    tabIndex={0}
                    role="img"
                    aria-label="Interactive visual representation of the Supply Chain Knowledge Graph. Use the mouse to pan, zoom, and explore nodes such as Suppliers and Critical Tracking Events."
                >
                    <p className="p-4 text-ui text-re-text-muted">
                        Your browser does not support the HTML5 canvas element, or screen reader mode is active.
                        This widget allows visual exploration of {visNodes.length} supply chain nodes and {visEdges.length} tracking events connecting them.
                    </p>
                </canvas>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
                <Card>
                    <CardContent className="p-4">
                        <div className="text-subheading text-re-text-primary">Inspector</div>
                        <div className="mt-2 text-ui text-re-text-secondary">
                            {selNodeObj ? (
                                <div className="space-y-1">
                                    <div className="font-medium text-re-text-primary">{selNodeObj.label}</div>
                                    <div>Type: {selNodeObj.type}</div>
                                    <div>KDE: {NTS[selNodeObj.type]?.kde}</div>
                                </div>
                            ) : (
                                <EmptyState
                                    bare
                                    size="sm"
                                    title="Select a node to view details."
                                />
                            )}
                        </div>
                    </CardContent>
                </Card>
                <Card>
                    <CardContent className="p-4">
                        <div className="text-subheading text-re-text-primary">Insights</div>
                        <p className="mt-2 text-ui leading-relaxed text-re-text-secondary">
                            Connect your physical supply chain nodes to cryptographic traceability lot codes (TLCs).
                        </p>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
