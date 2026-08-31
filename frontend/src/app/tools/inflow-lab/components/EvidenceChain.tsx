"use client";

import { AlertTriangle, Check, Lock, Play, RefreshCcw, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type EvidenceChainNode = {
    cte: string;
    location: string;
    time: string;
    state: "complete" | "missing";
};

export type EvidenceChainLot = {
    code: string;
    product: string;
    supplier?: string;
    cases?: number;
};

export type EvidenceChainProps = {
    /** Five CTE nodes for the lead lot, harvest → receive. */
    nodes: EvidenceChainNode[];
    /** False before any evaluation has produced lots. */
    hasData: boolean;
    /** True only when a real lot failed — never inferred from an empty chain. */
    isBlocked: boolean;
    isBusy: boolean;
    lot: EvidenceChainLot | null;
    missingEvidence: string;
    patternLabel: string;
    fixPath: string;
    /** Lots sharing this failure pattern, when the lead lot belongs to a group. */
    lotsAffected: number | null;
    rowsRead: number;
    lotCount: number;
    /** Bumped on each evaluation so the reveal animation replays. */
    runKey: number;
    onRun: () => void;
    onLoadSample: () => void;
    onFocusDefect?: (() => void) | null;
};

/** Reveal cadence, in ms, for the staggered chain animation. */
const NODE_STAGGER_MS = 130;

function nodeDelay(index: number) {
    return { animationDelay: `${index * NODE_STAGGER_MS}ms` };
}

export function EvidenceChain({
    nodes,
    hasData,
    isBlocked,
    isBusy,
    lot,
    missingEvidence,
    patternLabel,
    fixPath,
    lotsAffected,
    rowsRead,
    lotCount,
    runKey,
    onRun,
    onLoadSample,
    onFocusDefect,
}: EvidenceChainProps) {
    const provenCount = hasData ? nodes.filter((node) => node.state === "complete").length : 0;
    const lotLine = lot
        ? [lot.product, lot.cases ? `${lot.cases} cases` : null, lot.supplier]
              .filter(Boolean)
              .join(" · ")
        : "No lot loaded yet";

    return (
        <section
            aria-label="Evidence chain"
            data-testid="inflow-evidence-chain"
            className="block overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm"
            style={{ display: "block" }}
        >
            {/* Header: which lot is on the bench, and the one control that matters. */}
            <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-slate-50 px-4 py-3">
                <div className="min-w-0">
                    <div className="font-mono text-[13px] font-medium text-slate-950">
                        {lot ? lot.code : "Awaiting supplier rows"}
                    </div>
                    <div className="truncate text-xs text-slate-600">{lotLine}</div>
                </div>
                <div
                    className="ml-auto flex flex-wrap items-center gap-2"
                    data-tutorial="inflow-guided-proof"
                >
                    <Button
                        type="button"
                        onClick={onRun}
                        disabled={isBusy}
                        className="h-8 bg-emerald-700 px-3 text-xs text-white hover:bg-emerald-800"
                    >
                        {isBusy ? (
                            <>
                                <RefreshCcw className="mr-2 h-3.5 w-3.5 animate-spin" />
                                Tracing
                            </>
                        ) : (
                            <>
                                <Play className="mr-2 h-3.5 w-3.5" />
                                {hasData ? "Run trace again" : "Run trace"}
                            </>
                        )}
                    </Button>
                    <Button
                        type="button"
                        variant="outline"
                        onClick={onLoadSample}
                        className="h-8 border-slate-300 bg-white px-3 text-xs"
                    >
                        Open sample in editor
                    </Button>
                </div>
            </div>

            {/* The chain itself: five events end to end, plus the export gate. */}
            <div className="overflow-x-auto px-4 pb-2 pt-6">
                <div
                    key={runKey}
                    className="grid min-w-[860px] grid-cols-[repeat(5,minmax(140px,1fr))_150px] items-start"
                >
                    {nodes.map((node, index) => {
                        const visual = hasData ? node.state : "idle";
                        const isMissing = visual === "missing";
                        const isComplete = visual === "complete";
                        const stateWord = isComplete ? "proven" : isMissing ? "missing" : "not yet traced";

                        return (
                            <div key={node.cte} className="relative px-2">
                                {index > 0 && (
                                    <div
                                        aria-hidden="true"
                                        className={cn(
                                            // Nodes are left-aligned in each cell: 8px of padding + a
                                            // 22px radius puts every centre 30px in. So a connector has
                                            // to start one column back, at that same 30px offset, to
                                            // land on the previous node's centre rather than short of it.
                                            "absolute left-[calc(30px-100%)] top-[21px] w-full animate-in fade-in fill-mode-backwards duration-300",
                                            isComplete && "h-0.5 bg-emerald-500",
                                            isMissing && "border-t-2 border-dashed border-rose-400",
                                            !isComplete && !isMissing && "h-0.5 bg-slate-200",
                                        )}
                                        style={nodeDelay(index)}
                                    />
                                )}

                                <div
                                    className={cn(
                                        "relative z-[1] grid h-11 w-11 animate-in fade-in zoom-in-50 fill-mode-backwards place-items-center rounded-full border-2 bg-white duration-300",
                                        isComplete && "border-emerald-500 bg-emerald-50 text-emerald-700",
                                        isMissing && "border-dashed border-rose-400 bg-rose-50 text-rose-600",
                                        !isComplete && !isMissing && "border-dashed border-slate-300 text-slate-400",
                                    )}
                                    style={nodeDelay(index)}
                                >
                                    {isComplete ? (
                                        <Check className="h-5 w-5" />
                                    ) : isMissing ? (
                                        <AlertTriangle className="h-4 w-4" />
                                    ) : (
                                        <span className="h-1.5 w-1.5 rounded-full bg-current" />
                                    )}
                                </div>

                                <div
                                    className={cn(
                                        "mt-3 text-[12.5px] font-semibold",
                                        isMissing ? "text-rose-700" : "text-slate-900",
                                    )}
                                >
                                    {node.cte}
                                    <span className="sr-only">{`: ${stateWord}`}</span>
                                </div>
                                <div
                                    className={cn(
                                        "mt-0.5 min-h-[34px] font-mono text-[11px] leading-[1.45]",
                                        isMissing ? "text-rose-600" : "text-slate-500",
                                    )}
                                >
                                    {!hasData ? (
                                        ""
                                    ) : isMissing ? (
                                        "no record received"
                                    ) : (
                                        <>
                                            {node.location}
                                            <br />
                                            {node.time}
                                        </>
                                    )}
                                </div>
                            </div>
                        );
                    })}

                    {/* Export gate — the consequence of the chain, not a separate verdict. */}
                    <div className="border-l border-slate-200 pl-4">
                        <div
                            className={cn(
                                "rounded-md border px-3 py-2",
                                !hasData && "border-slate-200 bg-slate-50",
                                hasData && isBlocked && "border-rose-300 bg-rose-50",
                                hasData && !isBlocked && "border-emerald-300 bg-emerald-50",
                            )}
                        >
                            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
                                <Lock className="h-3 w-3" />
                                Export gate
                            </div>
                            <div
                                className={cn(
                                    "mt-1 text-[13.5px] font-semibold",
                                    !hasData && "text-slate-600",
                                    hasData && isBlocked && "text-rose-800",
                                    hasData && !isBlocked && "text-emerald-800",
                                )}
                            >
                                {!hasData ? "Awaiting trace" : isBlocked ? "Blocked" : "Preview-ready"}
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* Ticker: only counts we can actually stand behind. */}
            <div className="flex flex-wrap gap-x-6 gap-y-1 px-4 pb-4 font-mono text-[11.5px] text-slate-500">
                <span>
                    rows read <span className="font-semibold tabular-nums text-slate-900">{rowsRead}</span>
                </span>
                <span>
                    links proven{" "}
                    <span className="font-semibold tabular-nums text-slate-900">
                        {provenCount}/{nodes.length}
                    </span>
                </span>
                <span>
                    lots in batch <span className="font-semibold tabular-nums text-slate-900">{lotCount}</span>
                </span>
            </div>

            {/* Verdict. Absent until there is real data to report on. */}
            {hasData && isBlocked && lot && (
                <div className="border-t border-slate-200 px-4 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <h2 className="text-lg font-semibold tracking-tight text-slate-950">
                            {nodes.filter((node) => node.state === "missing").length === 1
                                ? "One record never arrived."
                                : `${nodes.filter((node) => node.state === "missing").length} records never arrived.`}
                        </h2>
                        <Badge className="border-0 bg-rose-600 text-[10px] text-white hover:bg-rose-600">
                            Blocked now
                        </Badge>
                    </div>
                    <p className="mt-1.5 max-w-[60ch] text-sm leading-6 text-slate-600">
                        {`${lot.product} lot ${lot.code.slice(-6)} is blocked because ${missingEvidence} never reached the evidence chain, so the export cannot be certified.`}
                    </p>

                    <div className="mt-4 grid gap-2 sm:grid-cols-3">
                        <div className="rounded-md border border-slate-200 border-l-[3px] border-l-rose-500 bg-white px-3 py-2">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500">Missing</div>
                            <div className="mt-1 text-sm font-semibold text-slate-950">{missingEvidence}</div>
                        </div>
                        <div className="rounded-md border border-slate-200 border-l-[3px] border-l-rose-500 bg-white px-3 py-2">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500">Pattern</div>
                            <div className="mt-1 text-sm font-semibold text-slate-950">{patternLabel}</div>
                        </div>
                        <div className="rounded-md border border-slate-200 border-l-[3px] border-l-rose-500 bg-white px-3 py-2">
                            <div className="text-[10px] uppercase tracking-wider text-slate-500">
                                Lots affected
                            </div>
                            <div className="mt-1 text-sm font-semibold text-slate-950">
                                {lotsAffected && lotsAffected > 1
                                    ? `${lotsAffected} lots, same pattern`
                                    : "This lot only"}
                            </div>
                        </div>
                    </div>

                    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 border-t border-slate-200 pt-3">
                        {onFocusDefect && (
                            <Button
                                type="button"
                                variant="outline"
                                className="h-7 shrink-0 border-slate-300 bg-white px-2 text-xs"
                                onClick={onFocusDefect}
                            >
                                Focus this defect
                            </Button>
                        )}
                        <span className="max-w-[62ch] text-xs leading-5 text-slate-600">{fixPath}</span>
                    </div>
                </div>
            )}

            {hasData && !isBlocked && lot && (
                <div className="border-t border-slate-200 px-4 py-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                        <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight text-slate-950">
                            <ShieldCheck className="h-4.5 w-4.5 text-emerald-600" />
                            The chain closes end to end.
                        </h2>
                        <Badge className="border-0 bg-emerald-600 text-[10px] text-white hover:bg-emerald-600">
                            All passing
                        </Badge>
                    </div>
                    <p className="mt-1.5 max-w-[60ch] text-sm leading-6 text-slate-600">
                        {`${lot.product} lot ${lot.code.slice(-6)} has all five CTEs with complete KDE evidence. To watch a defect get caught, delete the receiving row from the sample CSV and run the trace again.`}
                    </p>
                </div>
            )}
        </section>
    );
}
