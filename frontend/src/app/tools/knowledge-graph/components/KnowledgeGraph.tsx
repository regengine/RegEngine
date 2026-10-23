'use client';

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { GitBranch, Search } from "lucide-react";

// ── Utilities ──
function clamp(n: number, min: number, max: number) { return Math.max(min, Math.min(max, n)); }

// ── Types ──
type NodeType = "Supplier" | "Facility" | "Product" | "Lot" | "CTE" | "Location";
type EdgeType = "Supplies" | "Contains" | "Transforms" | "ShipsTo" | "TracedFrom" | "LocatedAt";
type GraphNode = { id: string; type: NodeType; label: string; meta?: Record<string, unknown>; x: number; y: number };
type GraphEdge = { id: string; type: EdgeType; from: string; to: string; meta?: Record<string, unknown> };
type TraceMode = "forward" | "backward" | "bidirectional";
type Viewport = { scale: number; panX: number; panY: number };

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

export function SupplyChainKnowledgeGraphBuilder() {
    const [nodes, setNodes] = useState<GraphNode[]>([]);
    const [edges, setEdges] = useState<GraphEdge[]>([]);

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

    const selNodeObj = useMemo(() => nodes.find(n => n.id === selNode) || null, [nodes, selNode]);
    const trace = useMemo(() => selNode ? traceNodes(selNode, edges, trMode, trDepth) : null, [selNode, edges, trMode, trDepth]);

    const visNodes = useMemo(() => { const q = search.trim().toLowerCase(); return nodes.filter(n => { if (filterType !== "All" && n.type !== filterType) return false; if (!q) return true; return n.label.toLowerCase().includes(q) || n.id.includes(q); }); }, [nodes, filterType, search]);
    const visIds = useMemo(() => new Set(visNodes.map(n => n.id)), [visNodes]);
    const visEdges = useMemo(() => edges.filter(e => visIds.has(e.from) && visIds.has(e.to)), [edges, visIds]);

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
    // Keep a ref pointing at the latest `draw` after each render so the
    // once-bound resize listener repaints from current state.
    const drawRef = useRef(draw);
    useEffect(() => { drawRef.current = draw; });
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

    if (nodes.length === 0) {
        return (
            <div className="space-y-6">
                <div>
                    <div className="text-heading text-re-text-primary">Knowledge Graph Builder</div>
                    <div className="mt-1 text-ui text-re-text-secondary">FSMA 204-native traceability graph.</div>
                </div>
                <EmptyState
                    title="No supply chain data yet"
                    titleAs="h2"
                    description="This view has no data source connected yet. It renders suppliers, facilities, products, lots, and Critical Tracking Events only when traceability records are provided to it; it does not fetch data on its own."
                    action={
                        <Button variant="secondary" size="sm" asChild>
                            <Link href="/tools/data-import" className="no-underline">
                                Import traceability data
                            </Link>
                        </Button>
                    }
                />
            </div>
        );
    }

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
