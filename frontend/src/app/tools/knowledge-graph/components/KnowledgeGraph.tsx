'use client';

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { useToast } from "@/components/ui/use-toast";
import { Spinner } from "@/components/ui/spinner";
import { useAuth } from "@/lib/auth-context";
import { useTenant } from "@/lib/tenant-context";
import { getServiceURL } from "@/lib/api-config";
import { AlertTriangle, GitBranch, Network, Search } from "lucide-react";

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
type GraphNode = { id: string; type: NodeType; label: string; meta?: Record<string, any>; x: number; y: number };
type GraphEdge = { id: string; type: EdgeType; from: string; to: string; meta?: Record<string, any> };
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
    results: Array<Record<string, any>>;
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

const NTS: Record<NodeType, { color: string; dim: string; icon: string; kde: string }> = {
    Supplier: { color: "var(--re-info)", dim: "rgba(14, 165, 233, 0.15)", icon: "🏭", kde: "Source" },
    Facility: { color: "var(--re-brand)", dim: "rgba(34, 197, 94, 0.15)", icon: "🏗️", kde: "Location" },
    Product: { color: "var(--re-warning)", dim: "rgba(245, 158, 11, 0.15)", icon: "📦", kde: "Product" },
    Lot: { color: "var(--re-purple)", dim: "rgba(168, 85, 247, 0.15)", icon: "🔖", kde: "Traceability Lot" },
    CTE: { color: "var(--re-cyan)", dim: "rgba(6, 182, 212, 0.15)", icon: "📍", kde: "Critical Tracking Event" },
    Location: { color: "var(--re-danger)", dim: "rgba(239, 68, 68, 0.15)", icon: "📌", kde: "Ship-to/Ship-from" },
};

const ETS: Record<EdgeType, { color: string; dash: boolean }> = {
    Supplies: { color: "var(--re-info)", dash: false }, Contains: { color: "var(--re-purple)", dash: false },
    Transforms: { color: "var(--re-warning)", dash: false }, ShipsTo: { color: "var(--re-brand)", dash: false },
    TracedFrom: { color: "var(--re-cyan)", dash: true }, LocatedAt: { color: "var(--re-danger)", dash: true },
};

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

function getConfidenceDescriptor(confidence: number) {
    if (confidence >= 0.85) {
        return {
            label: "high",
            className: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
        };
    }
    if (confidence >= 0.7) {
        return {
            label: "medium",
            className: "bg-amber-500/20 text-amber-300 border-amber-500/30",
        };
    }
    return {
        label: "low",
        className: "bg-rose-500/20 text-rose-300 border-rose-500/30",
    };
}

function toRow(candidate: Record<string, any>, fallbackTlc = ""): TraceabilityTableRow {
    const facilityValue = candidate.facility;
    const facilityName =
        (typeof facilityValue === "string" ? facilityValue : facilityValue?.name) ||
        candidate.facility_name ||
        candidate.location_description ||
        candidate.location_gln ||
        "";
    return {
        tlc: candidate.tlc || candidate.lot_id || candidate.traceability_lot_code || fallbackTlc || "",
        product: candidate.product_description || candidate.product || candidate.description || "",
        facility: facilityName,
        date: candidate.event_date || candidate.last_event_date || "",
        eventType: candidate.type || candidate.event_type || candidate.last_event_type || "",
    };
}

function collectQueryRows(intent: string, results: Array<Record<string, any>>): TraceabilityTableRow[] {
    const rows: TraceabilityTableRow[] = [];

    for (const item of results) {
        if (intent === "trace_forward" || intent === "trace_backward") {
            const nestedEvents = Array.isArray(item.events) ? item.events : [];
            if (nestedEvents.length > 0) {
                for (const event of nestedEvents) {
                    rows.push(toRow({ ...event, facility: item.facilities?.[0], lot_id: item.lot_id }, item.lot_id || ""));
                }
                continue;
            }
        }

        if (Array.isArray(item.events)) {
            for (const nested of item.events) {
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

        // Helper to resolve CSS variables into actual hex/rgba strings for Canvas
        const rootStyles = getComputedStyle(document.documentElement);
        const resolveColor = (c: string) => c.startsWith('var(') ? rootStyles.getPropertyValue(c.slice(4, -1)).trim() : c;

        if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, rect.width, rect.height);
        ctx.save(); ctx.translate(vp.panX, vp.panY); ctx.scale(vp.scale, vp.scale);

        // Grid
        ctx.strokeStyle = "rgba(148,163,184,0.08)"; ctx.lineWidth = 0.5;
        const gs = 40, sx = Math.floor(-vp.panX / vp.scale / gs) * gs - gs, sy = Math.floor(-vp.panY / vp.scale / gs) * gs - gs;
        for (let x = sx; x < sx + rect.width / vp.scale + gs * 3; x += gs) { ctx.beginPath(); ctx.moveTo(x, sy); ctx.lineTo(x, sy + rect.height / vp.scale + gs * 3); ctx.stroke(); }
        for (let y = sy; y < sy + rect.height / vp.scale + gs * 3; y += gs) { ctx.beginPath(); ctx.moveTo(sx, y); ctx.lineTo(sx + rect.width / vp.scale + gs * 3, y); ctx.stroke(); }

        // Edges
        for (const e of visEdges) {
            const a = nodes.find(n => n.id === e.from), b = nodes.find(n => n.id === e.to); if (!a || !b) continue;
            const hl = trace?.edges.has(e.id), sel = selEdge === e.id, dim = trace && !hl && !sel, es = ETS[e.type] || ETS.Supplies;
            const bColor = resolveColor(es.color);
            ctx.lineWidth = sel ? 3 : hl ? 2.5 : 1.2;

            // Reconstruct rgba strings for transparency handling
            const [baseHex, alpha] = bColor.startsWith('#') && bColor.length === 9
                ? [bColor.slice(0, 7), parseInt(bColor.slice(7), 16) / 255]
                : [bColor, 1];

            // A helper to create rgba strings from hex + custom opacity
            const hexToRgba = (hex: string, a: number) => {
                const r = parseInt(hex.slice(1, 3), 16) || 0;
                const g = parseInt(hex.slice(3, 5), 16) || 0;
                const b = parseInt(hex.slice(5, 7), 16) || 0;
                return `rgba(${r}, ${g}, ${b}, ${a})`;
            };

            ctx.strokeStyle = sel ? "rgba(99,102,241,0.9)" : hl ? bColor : dim ? hexToRgba(baseHex, 0.2) : hexToRgba(baseHex, 0.4);
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

            // Reconstruct rgba for hex
            const hexToRgba = (hex: string, a: number) => {
                const r = parseInt(hex.slice(1, 3), 16) || 0;
                const g = parseInt(hex.slice(3, 5), 16) || 0;
                const b = parseInt(hex.slice(5, 7), 16) || 0;
                return `rgba(${r}, ${g}, ${b}, ${a})`;
            };

            if (sel2 || hl) { ctx.beginPath(); ctx.arc(n.x, n.y, r + 8, 0, Math.PI * 2); ctx.fillStyle = hexToRgba(sColor, 0.15); ctx.fill(); }
            ctx.beginPath(); ctx.arc(n.x, n.y, r, 0, Math.PI * 2); ctx.fillStyle = dim ? "rgba(15,23,42,0.6)" : s.dim; ctx.fill();
            ctx.lineWidth = sel2 ? 2.5 : 1.5; ctx.strokeStyle = dim ? "rgba(148,163,184,0.2)" : sel2 ? "#fff" : sColor; ctx.stroke();
            ctx.font = "14px serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = dim ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.9)"; ctx.fillText(s.icon, n.x, n.y);
            ctx.font = "11px ui-sans-serif"; ctx.fillStyle = dim ? "rgba(148,163,184,0.3)" : "rgba(226,232,240,0.95)"; ctx.textBaseline = "top";
            ctx.fillText(n.label, n.x, n.y + r + 5);
        }
        ctx.restore();
    }

    useEffect(() => { draw(); }, [nodes, edges, vp, selNode, selEdge, trace, visNodes, visEdges]);
    useEffect(() => { const h = () => draw(); if (typeof window !== 'undefined') window.addEventListener("resize", h); return () => { if (typeof window !== 'undefined') window.removeEventListener("resize", h); }; }, []);

    const fitView = () => {
        if (!containerRef.current || !visNodes.length) return;
        const rect = containerRef.current.getBoundingClientRect();
        const xs = visNodes.map(n => n.x), ys = visNodes.map(n => n.y);
        const [mx, Mx, my, My] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
        const scale = clamp(Math.min(rect.width / (Mx - mx + 140), rect.height / (My - my + 140)), 0.5, 2);
        setVp({ scale, panX: rect.width / 2 - ((mx + Mx) / 2) * scale, panY: rect.height / 2 - ((my + My) / 2) * scale });
    };
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
            const response = await fetch(`${getServiceURL("nlp")}/api/v1/query/traceability`, {
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

            let payload: any = null;
            try {
                payload = await response.json();
            } catch {
                payload = null;
            }

            if (!response.ok) {
                const detail = payload?.detail || `Request failed with status ${response.status}`;
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

    return (
        <div className="space-y-4">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="flex items-center gap-2">
                    <div className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-muted"><Network className="h-5 w-5" /></div>
                    <div><div className="text-xl font-semibold">Knowledge Graph Builder</div><div className="text-sm text-muted-foreground">FSMA 204-native traceability graph.</div></div>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" className="rounded-2xl" onClick={fitView}>Fit View</Button>
                    <Button variant="outline" className="rounded-2xl" onClick={() => setRelaxing(true)}><GitBranch className="mr-2 h-4 w-4" />Relax Layout</Button>
                </div>
            </div>
            <Card className="rounded-3xl"><CardContent className="p-4 md:p-6">
                <div className="grid gap-4 md:grid-cols-12">
                    <div className="md:col-span-9">
                        <form className="mb-4 rounded-2xl border p-3" onSubmit={runTraceabilityQuery}>
                            <div className="flex flex-col gap-2 md:flex-row">
                                <Input
                                    className="rounded-2xl"
                                    placeholder="Ask your traceability data… (e.g. Where did lot ABC-2025-001 come from?)"
                                    value={traceabilityQuery}
                                    onChange={(e) => setTraceabilityQuery(e.target.value)}
                                />
                                <Button
                                    type="submit"
                                    className="rounded-2xl"
                                    disabled={queryLoading || !traceabilityQuery.trim()}
                                >
                                    {queryLoading ? (
                                        <span className="inline-flex items-center gap-2">
                                            <Spinner size="sm" className="h-4 w-4 border-2" />
                                            Querying
                                        </span>
                                    ) : (
                                        "Ask"
                                    )}
                                </Button>
                            </div>
                            <p className="mt-2 text-xs text-muted-foreground">
                                Try: “Where did lot ABC-2025-001 come from?” or “Show lettuce events from last 30 days”.
                            </p>
                        </form>

                        {queryResponse && (
                            <div className="mb-4 space-y-3">
                                <div className="rounded-2xl border bg-background/70 p-3">
                                    <div className="mb-1 flex items-center gap-2">
                                        <div className="text-sm font-semibold">Answer</div>
                                        {confidenceInfo && (
                                            <Badge className={confidenceInfo.className}>
                                                Confidence {confidenceInfo.label} ({Math.round(queryResponse.confidence * 100)}%)
                                            </Badge>
                                        )}
                                    </div>
                                    <p className="text-sm text-muted-foreground">{queryResponse.answer}</p>
                                </div>

                                {showWarningBanner && (
                                    <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 p-3 text-amber-200">
                                        <div className="mb-1 inline-flex items-center gap-2 text-sm font-medium">
                                            <AlertTriangle className="h-4 w-4" />
                                            Query warnings
                                        </div>
                                        <div className="text-xs leading-relaxed">
                                            {queryResponse.warnings.length > 0
                                                ? queryResponse.warnings.join(" ")
                                                : "Interpretation confidence is below 70%; verify filters before acting."}
                                        </div>
                                    </div>
                                )}

                                <div className="rounded-2xl border p-3">
                                    <div className="mb-2 text-sm font-medium">Results ({queryRows.length})</div>
                                    {queryRows.length > 0 ? (
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead>TLC</TableHead>
                                                    <TableHead>Product</TableHead>
                                                    <TableHead>Facility</TableHead>
                                                    <TableHead>Date</TableHead>
                                                    <TableHead>Event Type</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {queryRows.map((row, idx) => (
                                                    <TableRow key={`${row.tlc}-${row.eventType}-${row.date}-${idx}`}>
                                                        <TableCell>{row.tlc || "—"}</TableCell>
                                                        <TableCell>{row.product || "—"}</TableCell>
                                                        <TableCell>{row.facility || "—"}</TableCell>
                                                        <TableCell>{row.date || "—"}</TableCell>
                                                        <TableCell>{row.eventType || "—"}</TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    ) : (
                                        <p className="text-xs text-muted-foreground">No rows returned for this query.</p>
                                    )}
                                </div>

                                <details className="rounded-2xl border p-3">
                                    <summary className="cursor-pointer text-sm font-medium">
                                        Evidence ({queryResponse.evidence?.length || 0})
                                    </summary>
                                    <div className="mt-3 space-y-2">
                                        {(queryResponse.evidence || []).map((item, idx) => (
                                            <div key={`${item.endpoint}-${idx}`} className="rounded-xl border p-2 text-xs">
                                                <div><span className="font-medium">Endpoint:</span> {item.endpoint}</div>
                                                <div><span className="font-medium">Result count:</span> {item.result_count ?? 0}</div>
                                                {item.next_cursor ? (
                                                    <div><span className="font-medium">Next cursor:</span> {item.next_cursor}</div>
                                                ) : null}
                                                {item.params ? (
                                                    <pre className="mt-2 overflow-auto rounded-lg bg-muted p-2 text-[11px]">
                                                        {JSON.stringify(item.params, null, 2)}
                                                    </pre>
                                                ) : null}
                                            </div>
                                        ))}
                                    </div>
                                </details>
                            </div>
                        )}

                        <div className="flex flex-wrap items-center gap-2 mb-4">
                            <div className="relative"><Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><Input className="w-[240px] rounded-2xl pl-9" placeholder="Search..." value={search} onChange={e => setSearch(e.target.value)} /></div>
                            <Select value={trMode} onValueChange={v => setTrMode(v as any)}><SelectTrigger className="w-[160px] rounded-2xl"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="forward">→ Forward</SelectItem><SelectItem value="backward">← Backward</SelectItem><SelectItem value="bidirectional">↔ Both</SelectItem></SelectContent></Select>
                        </div>
                        <div ref={containerRef} className="h-[520px] w-full overflow-hidden rounded-3xl border bg-[var(--re-surface-base)] relative">
                            <canvas
                                ref={canvasRef}
                                className="h-full w-full outline-none focus:ring-2 focus:ring-[var(--re-brand)] focus:ring-inset"
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
                                <p className="p-4 text-sm text-[var(--re-text-muted)]">
                                    Your browser does not support the HTML5 canvas element, or screen reader mode is active.
                                    This widget allows visual exploration of {visNodes.length} supply chain nodes and {visEdges.length} tracking events connecting them.
                                </p>
                            </canvas>
                        </div>
                    </div>
                    <div className="md:col-span-3 space-y-3">
                        <div className="rounded-2xl border p-3">
                            <div className="text-sm font-medium">Inspector</div>
                            <div className="mt-2 text-xs text-muted-foreground">
                                {selNodeObj ? (
                                    <div className="space-y-1">
                                        <div className="font-bold">{selNodeObj.label}</div>
                                        <div>Type: {selNodeObj.type}</div>
                                        <div>KDE: {NTS[selNodeObj.type]?.kde}</div>
                                    </div>
                                ) : "Select a node to view details."}
                            </div>
                        </div>
                        <div className="rounded-2xl border p-3">
                            <div className="text-sm font-medium">Insights</div>
                            <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                                Connect your physical supply chain nodes to cryptographic traceability lot codes (TLCs).
                            </p>
                        </div>
                    </div>
                </div>
            </CardContent></Card>
        </div>
    );
}
