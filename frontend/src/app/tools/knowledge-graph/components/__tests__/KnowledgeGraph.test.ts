import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

// The graph component must ship with no hardcoded supply-chain records and
// must show an empty state when no data is loaded. These tests assert that
// invariant directly against the component source, plus keep coverage of the
// pure trace logic with an abstract structure (no invented records).

const componentPath = join(
    dirname(fileURLToPath(import.meta.url)),
    '..',
    'KnowledgeGraph.tsx'
);
const source = readFileSync(componentPath, 'utf8');

// ── Types (mirrored from KnowledgeGraph.tsx) ──
type EdgeType = "Supplies" | "Contains" | "Transforms" | "ShipsTo" | "TracedFrom" | "LocatedAt";
type GraphEdge = { id: string; type: EdgeType; from: string; to: string; meta?: Record<string, unknown> };
type TraceMode = "forward" | "backward" | "bidirectional";

// ── Pure function mirrored from KnowledgeGraph.tsx ──
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

describe('KnowledgeGraph data policy', () => {
    it('ships no hardcoded graph scenario or seeded generator', () => {
        expect(source).not.toContain('seededScenario');
        expect(source).not.toContain('mulberry32');
    });

    it('contains no invented supply-chain records (companies, lots, locations)', () => {
        expect(source).not.toMatch(/Arroyo|Salinas|Pasadena|RML-\d|TLC:/);
    });

    it('initializes with empty nodes and edges', () => {
        expect(source).toContain('useState<GraphNode[]>([])');
        expect(source).toContain('useState<GraphEdge[]>([])');
    });

    it('renders an empty state when no graph data is loaded', () => {
        expect(source).toContain('EmptyState');
        expect(source).toContain('nodes.length === 0');
    });
});

describe('traceNodes BFS pathfinding', () => {
    // Abstract structural graph: identifiers only, no records.
    const edges: GraphEdge[] = [
        { id: 'e1', type: 'ShipsTo', from: 'a', to: 'b' },
        { id: 'e2', type: 'ShipsTo', from: 'b', to: 'c' },
    ];

    it('traces forward across edges', () => {
        const trace = traceNodes('a', edges, 'forward', 2);
        expect(trace.nodes.has('a')).toBe(true);
        expect(trace.nodes.has('b')).toBe(true);
        expect(trace.nodes.has('c')).toBe(true);
        expect(trace.edges.has('e1')).toBe(true);
        expect(trace.edges.has('e2')).toBe(true);
    });

    it('traces backward across edges', () => {
        const trace = traceNodes('c', edges, 'backward', 2);
        expect(trace.nodes.has('a')).toBe(true);
        expect(trace.nodes.has('b')).toBe(true);
        expect(trace.nodes.has('c')).toBe(true);
    });

    it('respects depth limits', () => {
        const trace0 = traceNodes('a', edges, 'bidirectional', 0);
        expect(trace0.nodes.size).toBe(1);
        expect(trace0.edges.size).toBe(0);

        const trace1 = traceNodes('a', edges, 'forward', 1);
        expect(trace1.nodes.has('b')).toBe(true);
        expect(trace1.nodes.has('c')).toBe(false);
    });

    it('handles an empty graph', () => {
        const trace = traceNodes('a', [], 'bidirectional', 3);
        expect(trace.nodes.size).toBe(1);
        expect(trace.edges.size).toBe(0);
    });
});
