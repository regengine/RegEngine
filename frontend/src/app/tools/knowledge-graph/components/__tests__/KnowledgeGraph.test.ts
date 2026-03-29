import { describe, it, expect } from 'vitest';

// We map out the internal functional logic from the KnowledgeGraph component
// For testing purposes without exporting them directly from the TSX file,
// we duplicate the pure functions here to ensure the logic holds up to our standards.

// ── Types ──
type NodeType = "Supplier" | "Facility" | "Product" | "Lot" | "CTE" | "Location";
type EdgeType = "Supplies" | "Contains" | "Transforms" | "ShipsTo" | "TracedFrom" | "LocatedAt";
type GraphNode = { id: string; type: NodeType; label: string; meta?: Record<string, unknown>; x: number; y: number };
type GraphEdge = { id: string; type: EdgeType; from: string; to: string; meta?: Record<string, unknown> };
type TraceMode = "forward" | "backward" | "bidirectional";

// ── Pure Functions from KnowledgeGraph.tsx ──
function mulberry32(seed: number) {
    let a = seed >>> 0;
    return function () {
        a |= 0; a = (a + 0x6d2b79f5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

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

describe('Supply Chain Knowledge Graph Logistics', () => {

    describe('seededScenario determinism', () => {
        it('should generate identical graphs for the same seed', () => {
            const graphA = seededScenario(204);
            const graphB = seededScenario(204);
            expect(graphA.nodes[0].x).toBeCloseTo(graphB.nodes[0].x);
            expect(graphA.nodes[0].y).toBeCloseTo(graphB.nodes[0].y);
            expect(graphA.edges.length).toBe(graphB.edges.length);
        });

        it('should generate different spatial layouts for different seeds', () => {
            const graphA = seededScenario(204);
            const graphB = seededScenario(999);
            expect(graphA.nodes[0].x).not.toBe(graphB.nodes[0].x);
        });
    });

    describe('traceNodes BFS pathfinding', () => {
        const { nodes, edges } = seededScenario();

        it('should trace FORWARD downstream accurately', () => {
            // Tracing forward from Supplier (sup-1) should hit Cooler (fac-1) at depth 1
            const trace = traceNodes('sup-1', edges, 'forward', 1);
            expect(trace.nodes.has('sup-1')).toBe(true);
            expect(trace.nodes.has('fac-1')).toBe(true);
            expect(trace.nodes.has('loc-1')).toBe(true);

            // Should not hit depth 2 yet
            expect(trace.nodes.has('fac-2')).toBe(false);

            // Edges e-1 and e-2 should be used
            expect(trace.edges.has('e-1')).toBe(true);
            expect(trace.edges.has('e-2')).toBe(true);
        });

        it('should trace BACKWARD upstream accurately', () => {
            // Trace backward from DC (fac-3) should hit Processor (fac-2) at depth 1
            const trace = traceNodes('fac-3', edges, 'backward', 1);
            expect(trace.nodes.has('fac-3')).toBe(true);
            expect(trace.nodes.has('fac-2')).toBe(true);
            expect(trace.nodes.has('cte-3')).toBe(true);

            // Should not see forward edges
            expect(trace.nodes.has('fac-4')).toBe(false);
        });

        it('should trace BIDIRECTIONALLY across the full graph deeply', () => {
            // Selecting a middle node like Processor (fac-2) and going depth 5 should capture almost everything
            const trace = traceNodes('fac-2', edges, 'bidirectional', 5);
            expect(trace.nodes.has('fac-2')).toBe(true);    // Self
            expect(trace.nodes.has('fac-1')).toBe(true);    // Upstream Cooler
            expect(trace.nodes.has('fac-4')).toBe(true);    // Downstream Retail
            expect(trace.nodes.has('sup-1')).toBe(true);    // Original Supplier

            // Should identify significant edges
            expect(trace.edges.has('e-6')).toBe(true);
            expect(trace.edges.has('e-12')).toBe(true);
        });

        it('should strictly respect depth parameters', () => {
            // Depth 0 should only contain the starting node
            const trace0 = traceNodes('lot-1', edges, 'bidirectional', 0);
            expect(trace0.nodes.size).toBe(1);
            expect(trace0.edges.size).toBe(0);

            // Depth 1 from Lot 1
            const trace1 = traceNodes('lot-1', edges, 'bidirectional', 1);
            expect(trace1.nodes.has('lot-1')).toBe(true);
            expect(trace1.nodes.has('prod-1')).toBe(true); // From 'Contains'
            expect(trace1.nodes.has('cte-1')).toBe(true);  // From 'TracedFrom'
            expect(trace1.nodes.has('lot-2')).toBe(true);  // From 'Transforms'

            // Should NOT have deeply nested items
            expect(trace1.nodes.has('fac-2')).toBe(false); // Depth 2 away from CTE-1/CTE-2
        });
    });
});
