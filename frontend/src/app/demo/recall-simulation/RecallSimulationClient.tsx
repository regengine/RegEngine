"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Download,
  Loader2,
  Network,
  PlayCircle,
  ShieldCheck,
  Timer,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { generateBrandedPDF, type PDFSection } from "@/lib/pdf-report";

type Scenario = {
  id: string;
  name: string;
  description?: string;
  product_category?: string;
  contaminant?: string;
  baseline_response_hours?: number;
  regengine_response_minutes?: number;
};

type GraphNode = {
  id: string;
  name: string;
  type: string;
  affected: boolean;
  lot_count?: number;
};

type GraphLink = {
  source: string;
  target: string;
  affected: boolean;
};

type TimelineEvent = {
  timestamp: string;
  event: string;
  location?: string;
  status?: string;
};

type SimulationResult = {
  id: string;
  scenario_id: string;
  created_at: string;
  metrics: {
    scenario: string;
    contaminant: string;
    total_lots_in_system: number;
    affected_lots: number;
    affected_locations: number;
    states_affected: number;
    without_regengine: {
      response_time_hours: number;
      data_sources_consulted: number;
      kde_completeness: number;
    };
    with_regengine: {
      response_time_minutes: number;
      data_sources_consulted: number;
      kde_completeness: number;
      hash_verified: boolean;
    };
    time_reduction_percent: number;
  };
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toDisplayValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "-";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `${value.length} items`;
  if (isRecord(value)) return "Object";
  return String(value);
}

function toTitleCase(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function buildObjectTableSections(data: Record<string, unknown>): PDFSection[] {
  const sections: PDFSection[] = [];
  const entries = Object.entries(data);

  const primitivePairs = entries
    .filter(([, value]) => ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 8)
    .map(([key, value]) => ({ key: toTitleCase(key), value: toDisplayValue(value) }));

  if (primitivePairs.length > 0) {
    sections.push({ type: "divider" });
    sections.push({ type: "heading", text: "Export Metadata", level: 2 });
    sections.push({ type: "keyValue", pairs: primitivePairs });
  }

  entries
    .filter(([, value]) => Array.isArray(value))
    .slice(0, 2)
    .forEach(([key, value]) => {
      const arrayValue = value as unknown[];
      const objectRows = arrayValue.filter(isRecord);
      if (objectRows.length === 0) return;

      const columnSet = new Set<string>();
      objectRows.slice(0, 30).forEach((row) => {
        Object.keys(row).forEach((column) => columnSet.add(column));
      });

      const headers = Array.from(columnSet).slice(0, 6);
      if (headers.length === 0) return;

      const rows = objectRows.slice(0, 30).map((row) =>
        headers.map((header) => toDisplayValue(row[header])),
      );

      sections.push({ type: "divider" });
      sections.push({ type: "heading", text: toTitleCase(key), level: 2 });
      sections.push({
        type: "table",
        headers: headers.map((header) => toTitleCase(header)),
        rows,
      });
    });

  return sections;
}

const FALLBACK_SCENARIOS: Scenario[] = [
  {
    id: "romaine-ecoli",
    name: "E. coli O157:H7 in Romaine Lettuce",
    description: "Farm to shelf contamination trace across leafy greens distribution.",
    product_category: "Leafy Greens",
    contaminant: "E. coli O157:H7",
    baseline_response_hours: 18,
    regengine_response_minutes: 42,
  },
  {
    id: "shrimp-sulfite",
    name: "Undeclared Sulfites in Imported Shrimp",
    description: "Importer and distributor chain trace for seafood allergen risk.",
    product_category: "Seafood",
    contaminant: "Undeclared sulfites",
    baseline_response_hours: 36,
    regengine_response_minutes: 38,
  },
  {
    id: "cheese-listeria",
    name: "Listeria monocytogenes in Soft Cheese",
    description: "Dairy lot tracing across multi-state retail distribution.",
    product_category: "Dairy",
    contaminant: "Listeria monocytogenes",
    baseline_response_hours: 14,
    regengine_response_minutes: 27,
  },
];

function useSimulationData() {
  const [scenarios, setScenarios] = useState<Scenario[]>(FALLBACK_SCENARIOS);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>(FALLBACK_SCENARIOS[0].id);
  const [loadingScenarios, setLoadingScenarios] = useState(false);

  const loadScenarios = async () => {
    setLoadingScenarios(true);
    try {
      const response = await fetch("/api/simulations/scenarios", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed to load scenarios (${response.status})`);
      }
      const payload = await response.json();
      const list = Array.isArray(payload?.scenarios) ? payload.scenarios : [];
      if (list.length > 0) {
        setScenarios(list);
        setSelectedScenarioId((prev) =>
          list.some((scenario: Scenario) => scenario.id === prev) ? prev : list[0].id,
        );
      }
    } catch {
      setScenarios(FALLBACK_SCENARIOS);
    } finally {
      setLoadingScenarios(false);
    }
  };

  return {
    scenarios,
    selectedScenarioId,
    setSelectedScenarioId,
    loadingScenarios,
    loadScenarios,
  };
}

export default function RecallSimulationClient() {
  const {
    scenarios,
    selectedScenarioId,
    setSelectedScenarioId,
    loadingScenarios,
    loadScenarios,
  } = useSimulationData();

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [graphNodes, setGraphNodes] = useState<GraphNode[]>([]);
  const [graphLinks, setGraphLinks] = useState<GraphLink[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.id === selectedScenarioId),
    [scenarios, selectedScenarioId],
  );

  const selectedNode = useMemo(
    () => graphNodes.find((node) => node.id === selectedNodeId) || null,
    [graphNodes, selectedNodeId],
  );

  const runSimulation = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    setTimeline([]);
    setGraphNodes([]);
    setGraphLinks([]);
    setSelectedNodeId(null);

    try {
      const runResponse = await fetch("/api/simulations/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_id: selectedScenarioId }),
      });

      if (!runResponse.ok) {
        const errorBody = await runResponse.json().catch(() => ({}));
        throw new Error(errorBody?.detail || errorBody?.error || "Failed to run simulation");
      }

      const runPayload = (await runResponse.json()) as SimulationResult;
      const simulationId = runPayload.id;

      const [detailResponse, timelineResponse, graphResponse] = await Promise.all([
        fetch(`/api/simulations/${simulationId}`, { cache: "no-store" }),
        fetch(`/api/simulations/${simulationId}/timeline`, { cache: "no-store" }),
        fetch(`/api/simulations/${simulationId}/impact-graph`, { cache: "no-store" }),
      ]);

      if (!detailResponse.ok || !timelineResponse.ok || !graphResponse.ok) {
        throw new Error("Simulation completed but some detail endpoints failed");
      }

      const detailPayload = (await detailResponse.json()) as SimulationResult;
      const timelinePayload = await timelineResponse.json();
      const graphPayload = await graphResponse.json();

      setResult(detailPayload);
      setTimeline(Array.isArray(timelinePayload?.timeline) ? timelinePayload.timeline : []);
      setGraphNodes(Array.isArray(graphPayload?.nodes) ? graphPayload.nodes : []);
      setGraphLinks(Array.isArray(graphPayload?.links) ? graphPayload.links : []);
    } catch (runError: unknown) {
      const message = runError instanceof Error ? runError.message : "Unexpected simulation error";
      setError(message);
    } finally {
      setRunning(false);
    }
  };

  const downloadExport = async () => {
    if (!result?.id) {
      return;
    }
    setExporting(true);
    try {
      const response = await fetch(`/api/simulations/${result.id}/export`, { cache: "no-store" });
      if (!response.ok) {
        throw new Error("Unable to export simulation report");
      }

      const exportData: unknown = await response.json();

      const sections: PDFSection[] = [
        { type: "heading", text: "Simulation Summary", level: 2 },
        {
          type: "keyValue",
          pairs: [
            { key: "Simulation ID", value: result.id },
            { key: "Scenario", value: result.metrics.scenario },
            { key: "Contaminant", value: result.metrics.contaminant },
            { key: "Created At", value: new Date(result.created_at).toLocaleString() },
            { key: "Total Lots", value: String(result.metrics.total_lots_in_system) },
            { key: "Affected Lots", value: String(result.metrics.affected_lots), status: "danger" },
            { key: "Affected Locations", value: String(result.metrics.affected_locations), status: "warning" },
            { key: "States Affected", value: String(result.metrics.states_affected), status: "warning" },
            {
              key: "Time Reduction",
              value: `${result.metrics.time_reduction_percent}%`,
              status: result.metrics.time_reduction_percent >= 50 ? "success" : "warning",
            },
          ],
        },
        { type: "divider" },
        { type: "heading", text: "Response Performance", level: 2 },
        {
          type: "keyValue",
          pairs: [
            {
              key: "Without RegEngine",
              value: `${result.metrics.without_regengine.response_time_hours} hours`,
              status: "danger",
            },
            {
              key: "With RegEngine",
              value: `${result.metrics.with_regengine.response_time_minutes} minutes`,
              status: "success",
            },
            {
              key: "KDE Completeness (Without)",
              value: `${Math.round(result.metrics.without_regengine.kde_completeness * 100)}%`,
              status: "warning",
            },
            {
              key: "KDE Completeness (With)",
              value: `${Math.round(result.metrics.with_regengine.kde_completeness * 100)}%`,
              status: "success",
            },
            {
              key: "Hash Verified",
              value: result.metrics.with_regengine.hash_verified ? "Yes" : "No",
              status: result.metrics.with_regengine.hash_verified ? "success" : "danger",
            },
          ],
        },
      ];

      if (graphNodes.length > 0) {
        sections.push({ type: "divider" });
        sections.push({ type: "heading", text: "Impact Graph Nodes", level: 2 });
        sections.push({
          type: "table",
          headers: ["Node", "Type", "Affected", "Lots"],
          rows: graphNodes.map((node) => [
            node.name,
            node.type,
            node.affected ? "Yes" : "No",
            node.lot_count !== undefined ? String(node.lot_count) : "-",
          ]),
        });
      }

      if (timeline.length > 0) {
        sections.push({ type: "divider" });
        sections.push({ type: "heading", text: "Timeline Events", level: 2 });
        sections.push({
          type: "table",
          headers: ["Timestamp", "Event", "Location", "Status"],
          rows: timeline.slice(0, 80).map((event) => [
            new Date(event.timestamp).toLocaleString(),
            event.event,
            event.location || "-",
            event.status || "-",
          ]),
        });
      }

      if (isRecord(exportData)) {
        const objectSections = buildObjectTableSections(exportData);
        sections.push(...objectSections);
      }

      generateBrandedPDF({
        title: "Recall Simulation Results",
        subtitle: `Simulation ID: ${result.id}`,
        reportType: "FDA FSMA 204 - Recall Readiness",
        sections,
        footer: {
          left: "Confidential",
          right: "regengine.co",
          legalLine: "FDA FSMA 204 - 21 CFR Part 1 Subpart S",
        },
        filename: `recall-simulation-${result.id}`,
      });
    } catch (exportError: unknown) {
      const message = exportError instanceof Error ? exportError.message : "Export failed";
      setError(message);
    } finally {
      setExporting(false);
    }
  };

  const graphSvgHeight = 320;
  const graphSvgWidth = 920;

  const positionedNodes = useMemo(() => {
    if (graphNodes.length === 0) {
      return [];
    }
    return graphNodes.map((node, index) => {
      const xPadding = 70;
      const yMid = graphSvgHeight / 2;
      const step = graphNodes.length > 1 ? (graphSvgWidth - xPadding * 2) / (graphNodes.length - 1) : 0;
      const yOffset = index % 2 === 0 ? -56 : 56;
      return {
        ...node,
        x: xPadding + step * index,
        y: yMid + yOffset,
      };
    });
  }, [graphNodes]);

  const getNodePosition = (nodeId: string) => positionedNodes.find((node) => node.id === nodeId);

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <section className="max-w-[1160px] mx-auto px-6 pt-20 pb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[var(--re-brand-muted)] bg-[var(--re-brand-muted)] text-[11px] uppercase tracking-[0.12em] text-[var(--re-brand)] mb-5">
          <Activity size={12} />
          Recall Simulation
        </div>

        <h1 className="text-[clamp(32px,4.8vw,56px)] font-bold leading-[1.05] tracking-[-0.02em] text-[var(--re-text-primary)] max-w-[880px]">
          Simulate an FDA recall request and trace impact in minutes.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-[var(--re-text-muted)] max-w-[760px]">
          This demo runs realistic contamination scenarios, maps affected locations, and compares manual
          response timelines against RegEngine infrastructure.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Button
            onClick={runSimulation}
            disabled={running}
            className="h-12 px-7 rounded-2xl bg-[var(--re-brand)] text-white font-bold"
          >
            {running ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <PlayCircle className="h-4 w-4 mr-2" />}
            Run Simulation
          </Button>
          <Button
            variant="outline"
            onClick={downloadExport}
            disabled={!result || exporting}
            className="h-12 px-7 rounded-2xl"
          >
            {exporting ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Download className="h-4 w-4 mr-2" />}
            Export Report
          </Button>
          <Button variant="outline" onClick={loadScenarios} disabled={loadingScenarios} className="h-12 px-7 rounded-2xl">
            {loadingScenarios ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Network className="h-4 w-4 mr-2" />}
            Refresh Scenarios
          </Button>
        </div>
      </section>

      <section className="max-w-[1160px] mx-auto px-6 pb-8">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {scenarios.map((scenario) => {
            const active = scenario.id === selectedScenarioId;
            return (
              <button
                key={scenario.id}
                onClick={() => setSelectedScenarioId(scenario.id)}
                className={`text-left p-5 rounded-xl border transition-all duration-200 ${
                  active
                    ? "border-[var(--re-brand-muted)] bg-[rgba(16,185,129,0.08)]"
                    : "border-[var(--re-surface-border)] bg-[var(--re-surface-card)] hover:border-[var(--re-brand-muted)]"
                }`}
              >
                <p className="text-[11px] uppercase tracking-[0.12em] text-[var(--re-text-disabled)] mb-2">
                  {scenario.product_category || "FSMA Scenario"}
                </p>
                <h2 className="text-[17px] font-semibold text-[var(--re-text-primary)] leading-snug">{scenario.name}</h2>
                <p className="text-sm text-[var(--re-text-muted)] mt-2 min-h-[40px]">
                  {scenario.description || scenario.contaminant || "Traceability recall simulation"}
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {error ? (
        <section className="max-w-[1160px] mx-auto px-6 pb-6">
          <div className="p-4 rounded-xl border border-red-300/30 bg-red-500/10 text-red-200 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 mt-0.5" />
            <div>
              <p className="font-semibold">Simulation error</p>
              <p className="text-sm text-red-200/90">{error}</p>
              <Button onClick={runSimulation} className="mt-3 h-9 px-4 rounded-xl bg-red-500 hover:bg-red-400 text-white">
                Retry
              </Button>
            </div>
          </div>
        </section>
      ) : null}

      {result ? (
        <>
          <section className="max-w-[1160px] mx-auto px-6 pb-8">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-6 rounded-2xl border border-red-300/20 bg-red-500/5">
                <p className="text-xs uppercase tracking-[0.12em] text-red-300 mb-3">Without RegEngine</p>
                <ul className="space-y-2 text-sm text-[var(--re-text-muted)]">
                  <li>Response time: {result.metrics.without_regengine.response_time_hours} hours</li>
                  <li>Data sources: {result.metrics.without_regengine.data_sources_consulted}</li>
                  <li>
                    KDE completeness: {Math.round(result.metrics.without_regengine.kde_completeness * 100)}%
                  </li>
                </ul>
              </div>
              <div className="p-6 rounded-2xl border border-[var(--re-brand-muted)] bg-[rgba(16,185,129,0.08)]">
                <p className="text-xs uppercase tracking-[0.12em] text-[var(--re-brand)] mb-3">With RegEngine</p>
                <ul className="space-y-2 text-sm text-[var(--re-text-primary)]">
                  <li>Response time: {result.metrics.with_regengine.response_time_minutes} minutes</li>
                  <li>Data sources: {result.metrics.with_regengine.data_sources_consulted}</li>
                  <li>
                    KDE completeness: {Math.round(result.metrics.with_regengine.kde_completeness * 100)}%
                  </li>
                </ul>
              </div>
            </div>

            <div className="mt-4 p-5 rounded-2xl bg-black text-white dark:bg-white dark:text-black flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-[40px] font-black leading-none">{result.metrics.time_reduction_percent}%</p>
                <p className="text-sm opacity-80">Reduction in recall response time</p>
              </div>
              <div className="text-sm space-y-1">
                <p>Total lots: {result.metrics.total_lots_in_system}</p>
                <p>Affected lots: {result.metrics.affected_lots}</p>
                <p>Affected states: {result.metrics.states_affected}</p>
              </div>
            </div>
          </section>

          <section className="max-w-[1160px] mx-auto px-6 pb-8">
            <div className="p-6 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
              <div className="flex items-center justify-between mb-4 gap-4 flex-wrap">
                <h3 className="text-xl font-semibold text-[var(--re-text-primary)] flex items-center gap-2">
                  <Network className="h-5 w-5 text-[var(--re-brand)]" />
                  Impact Graph
                </h3>
                <p className="text-xs text-[var(--re-text-disabled)] uppercase tracking-[0.1em]">
                  Click node for details
                </p>
              </div>

              {positionedNodes.length > 0 ? (
                <div className="overflow-x-auto">
                  <svg
                    viewBox={`0 0 ${graphSvgWidth} ${graphSvgHeight}`}
                    className="w-full min-w-[780px] h-[320px] rounded-xl bg-black/10"
                    role="img"
                    aria-label="Supply chain impact graph"
                  >
                    {graphLinks.map((link, index) => {
                      const source = getNodePosition(link.source);
                      const target = getNodePosition(link.target);
                      if (!source || !target) {
                        return null;
                      }
                      return (
                        <line
                          key={`${link.source}-${link.target}-${index}`}
                          x1={source.x}
                          y1={source.y}
                          x2={target.x}
                          y2={target.y}
                          stroke={link.affected ? "#ef4444" : "#6b7280"}
                          strokeOpacity={0.75}
                          strokeWidth={link.affected ? 2.5 : 1.5}
                        />
                      );
                    })}

                    {positionedNodes.map((node) => {
                      const selected = node.id === selectedNodeId;
                      return (
                        <g
                          key={node.id}
                          onClick={() => setSelectedNodeId(node.id)}
                          className="cursor-pointer"
                          role="button"
                          tabIndex={0}
                        >
                          <circle
                            cx={node.x}
                            cy={node.y}
                            r={selected ? 18 : 14}
                            fill={node.affected ? "#ef4444" : "#10b981"}
                            fillOpacity={selected ? 1 : 0.85}
                            stroke={selected ? "#ffffff" : "transparent"}
                            strokeWidth={2}
                          />
                          <text
                            x={node.x}
                            y={node.y + 28}
                            textAnchor="middle"
                            fontSize="11"
                            fill="#f3f4f6"
                          >
                            {node.name}
                          </text>
                        </g>
                      );
                    })}
                  </svg>
                </div>
              ) : (
                <p className="text-sm text-[var(--re-text-muted)]">No graph data returned for this simulation.</p>
              )}

              {selectedNode ? (
                <div className="mt-4 p-4 rounded-xl border border-[var(--re-surface-border)] bg-black/10">
                  <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-text-disabled)]">Selected Node</p>
                  <p className="text-base font-semibold text-[var(--re-text-primary)] mt-1">{selectedNode.name}</p>
                  <p className="text-sm text-[var(--re-text-muted)] mt-1">Type: {selectedNode.type}</p>
                  <p className="text-sm text-[var(--re-text-muted)]">
                    Impact: {selectedNode.affected ? "Affected" : "Observed"}
                  </p>
                  <p className="text-sm text-[var(--re-text-muted)]">Lots at node: {selectedNode.lot_count ?? "n/a"}</p>
                </div>
              ) : null}
            </div>
          </section>

          <section className="max-w-[1160px] mx-auto px-6 pb-10">
            <div className="p-6 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
              <h3 className="text-xl font-semibold text-[var(--re-text-primary)] flex items-center gap-2 mb-4">
                <Timer className="h-5 w-5 text-[var(--re-brand)]" />
                Timeline
              </h3>
              {timeline.length > 0 ? (
                <ol className="space-y-3">
                  {timeline.map((event, index) => (
                    <li key={`${event.timestamp}-${index}`} className="p-3 rounded-xl bg-black/10 border border-white/5">
                      <p className="text-xs uppercase tracking-[0.1em] text-[var(--re-text-disabled)]">
                        {new Date(event.timestamp).toLocaleString()}
                      </p>
                      <p className="text-sm text-[var(--re-text-primary)] mt-1">{event.event}</p>
                      {event.location ? (
                        <p className="text-xs text-[var(--re-text-muted)] mt-1">Location: {event.location}</p>
                      ) : null}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-[var(--re-text-muted)]">No timeline events returned.</p>
              )}
            </div>
          </section>
        </>
      ) : (
        <section className="max-w-[1160px] mx-auto px-6 pb-12">
          <div className="p-6 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
            <p className="text-sm text-[var(--re-text-muted)]">
              Select a scenario and run a simulation to generate impact graph, recall timeline, and
              response-time delta metrics.
            </p>
          </div>
        </section>
      )}

      <section className="max-w-[1160px] mx-auto px-6 pb-20">
        <div className="p-8 rounded-2xl border border-[var(--re-surface-border)] bg-[rgba(16,185,129,0.08)]">
          <h4 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Move from simulation to operational readiness</h4>
          <p className="text-sm text-[var(--re-text-muted)] mb-5">
            Use this simulation with your team, then run your own facility through the Retailer
            Readiness Assessment and FTL Coverage workflow.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/retailer-readiness">
              <Button className="h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold">
                Retailer Readiness Assessment
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
            <Link href="/tools/ftl-checker">
              <Button variant="outline" className="h-11 px-6 rounded-xl font-semibold">
                FTL Coverage Checker
                <ShieldCheck className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
