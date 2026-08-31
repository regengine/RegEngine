"use client";

import Image from "next/image";
import { type KeyboardEvent, type SyntheticEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
    AlertTriangle,
    ArrowRight,
    CheckCircle2,
    Database,
    FileCheck2,
    FileSpreadsheet,
    GitBranch,
    MapPin,
    PackageCheck,
    Pause,
    Play,
    ScanSearch,
    ShieldCheck,
    Sparkles,
    Truck,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePostHog } from "@/lib/posthog-provider";
import { cn } from "@/lib/utils";

const storyStages = [
    {
        id: "raw",
        label: "See the messy feed",
        shortLabel: "Raw feed",
        eyebrow: "01 · Ingest",
        summary: "Supplier rows arrive with recognizable business data and imperfect handoffs.",
        icon: FileSpreadsheet,
    },
    {
        id: "normalize",
        label: "Watch it become traceability",
        shortLabel: "Normalize",
        eyebrow: "02 · Structure",
        summary: "RegEngine maps ordinary columns into CTEs, KDEs, lots, locations, and provenance.",
        icon: Database,
    },
    {
        id: "detect",
        label: "Catch the defect",
        shortLabel: "Detect",
        eyebrow: "03 · Validate",
        summary: "The exact missing evidence is isolated before it can contaminate production records.",
        icon: ScanSearch,
    },
    {
        id: "trace",
        label: "Follow the lot",
        shortLabel: "Trace",
        eyebrow: "04 · Explain",
        summary: "Every handoff becomes a buyer-readable path from field through receiving.",
        icon: GitBranch,
    },
    {
        id: "evidence",
        label: "See the evidence package",
        shortLabel: "Evidence",
        eyebrow: "05 · Prove",
        summary: "Validated records become an audit-ready trail and FDA export preview.",
        icon: FileCheck2,
    },
] as const;

type StoryStageId = (typeof storyStages)[number]["id"];

const subscribeToHydration = () => () => undefined;
const getClientHydrationSnapshot = () => true;
const getServerHydrationSnapshot = () => false;

type InflowMagicStoryProps = {
    eventCount: number;
    readinessScore: number;
    exceptionCount: number;
    selectedLot: string;
    isBusy?: boolean;
    onStartGuidedRun?: () => void | Promise<void>;
};

function RawFeedFrame() {
    const rows = [
        ["shipping", "TLC-0427-A", "Salinas Packhouse", "Bay Area DC", "BOL-1842"],
        ["receiving", "TLC-0427-A", "Bay Area DC", "", "REC-1842"],
        ["shipping", "TLC-0427-B", "Imperial Packhouse", "LA DC", "BOL-1843"],
    ];

    return (
        <div className="grid h-full content-center gap-4 p-4 sm:p-6">
            <div className="flex items-center justify-between gap-3">
                <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">supplier_handoff.csv</p>
                    <p className="mt-1 text-sm font-semibold text-white">The feed looks ordinary. The risk is buried in one cell.</p>
                </div>
                <Badge className="border-amber-300/30 bg-amber-300/10 text-amber-200 hover:bg-amber-300/10">1 gap hiding</Badge>
            </div>
            <div data-magic-raw-table className="overflow-hidden rounded-xl border border-white/10 bg-black/25 font-mono text-[10px] text-slate-300 shadow-2xl sm:text-xs">
                <div className="grid grid-cols-5 gap-px border-b border-white/10 bg-slate-900 px-3 py-2 text-slate-400">
                    <span>cte_type</span>
                    <span>lot_code</span>
                    <span>ship_from</span>
                    <span>ship_to</span>
                    <span>document</span>
                </div>
                {rows.map((row, rowIndex) => (
                    <div key={row.join("-")} className="grid grid-cols-5 gap-px border-b border-white/5 px-3 py-3 last:border-0">
                        {row.map((value, cellIndex) => (
                            <span
                                key={`${rowIndex}-${cellIndex}`}
                                className={cn(
                                    "truncate pr-2",
                                    rowIndex === 1 && cellIndex === 3 && "rounded bg-rose-400/15 px-1 text-rose-200 ring-1 ring-inset ring-rose-400/30"
                                )}
                            >
                                {value || "∅ missing"}
                            </span>
                        ))}
                    </div>
                ))}
            </div>
            <div data-magic-raw-mobile className="rounded-xl border border-rose-300/25 bg-slate-900 p-4 shadow-2xl">
                <div className="flex items-center justify-between gap-3">
                    <div>
                        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-rose-200">Flagged receiving record</p>
                        <p className="mt-1 font-mono text-xs text-white">TLC-0427-A</p>
                    </div>
                    <AlertTriangle className="h-5 w-5 text-rose-300" />
                </div>
                <dl className="mt-4 grid gap-2 text-xs">
                    <div className="flex items-center justify-between gap-3 border-b border-white/10 pb-2">
                        <dt className="font-mono text-slate-500">ship_from</dt>
                        <dd className="text-right text-slate-200">Bay Area DC</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3 rounded-lg border border-rose-300/25 bg-rose-300/10 px-3 py-2">
                        <dt className="font-mono text-rose-200">ship_to</dt>
                        <dd className="font-semibold text-rose-100">∅ missing</dd>
                    </div>
                </dl>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
                <AlertTriangle className="h-4 w-4 text-amber-300" />
                Humans see three rows. RegEngine sees a broken receiving handoff.
            </div>
        </div>
    );
}

function NormalizeFrame({ eventCount }: { eventCount: number }) {
    const mappedFields = [
        ["cte_type", "Receiving CTE"],
        ["lot_code", "Traceability lot"],
        ["ship_from", "Previous source"],
        ["document", "Reference evidence"],
    ];

    return (
        <div className="grid h-full content-center gap-5 p-4 sm:p-6">
            <div className="grid items-center gap-3 sm:grid-cols-[1fr_auto_1.25fr]">
                <div className="rounded-xl border border-sky-300/20 bg-sky-300/10 p-4">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-200">Inbound columns</p>
                    <div className="mt-3 space-y-2 font-mono text-xs text-slate-200">
                        {mappedFields.map(([source]) => (
                            <div key={source} className="rounded-md border border-white/10 bg-black/20 px-2.5 py-2">{source}</div>
                        ))}
                    </div>
                </div>
                <div className="hidden items-center sm:flex">
                    <ArrowRight className="h-6 w-6 text-emerald-300" />
                </div>
                <div className="rounded-xl border border-emerald-300/25 bg-emerald-300/10 p-4">
                    <div className="flex items-center justify-between gap-3">
                        <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-emerald-200">Canonical evidence</p>
                        <span className="text-xs font-semibold text-emerald-200">{eventCount || 5} records</span>
                    </div>
                    <div className="mt-3 space-y-2 text-xs text-white">
                        {mappedFields.map(([, target], index) => (
                            <div key={target} className="flex items-center gap-2 rounded-md border border-white/10 bg-black/20 px-2.5 py-2">
                                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />
                                <span>{target}</span>
                                <span className="ml-auto font-mono text-[10px] text-slate-500">0{index + 1}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
            <div className="flex flex-wrap items-center justify-center gap-2 text-[11px] text-slate-300">
                {['CTE typed', 'KDE mapped', 'Tenant scoped', 'Provenance attached'].map((label) => (
                    <span key={label} className="rounded-full border border-white/10 bg-slate-900 px-3 py-1.5">{label}</span>
                ))}
            </div>
        </div>
    );
}

function DetectFrame({ readinessScore, exceptionCount }: { readinessScore: number; exceptionCount: number }) {
    const score = Math.max(0, Math.min(100, readinessScore));

    return (
        <div className="grid h-full content-center gap-5 p-4 sm:grid-cols-[190px_minmax(0,1fr)] sm:items-center sm:p-6">
            <div className="mx-auto grid place-items-center">
                <div
                    className="grid h-36 w-36 place-items-center rounded-full p-3 shadow-[0_0_60px_rgba(52,211,153,0.12)]"
                    style={{ background: `conic-gradient(#34d399 ${score * 3.6}deg, rgba(255,255,255,.08) 0deg)` }}
                    aria-label={`Readiness score ${score} out of 100`}
                >
                    <div className="grid h-full w-full place-items-center rounded-full bg-slate-950 text-center">
                        <div>
                            <strong className="text-3xl text-white">{score}</strong>
                            <span className="text-sm text-slate-500"> / 100</span>
                            <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-slate-400">preflight</p>
                        </div>
                    </div>
                </div>
            </div>
            <div className="space-y-3">
                <div className="rounded-xl border border-rose-300/30 bg-rose-300/10 p-4 shadow-[0_18px_60px_rgba(244,63,94,0.08)]">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex items-center gap-2 text-sm font-semibold text-white">
                            <AlertTriangle className="h-4 w-4 text-rose-300" />
                            Missing receiving destination
                        </div>
                        <Badge className="border-rose-300/30 bg-rose-300/10 text-rose-200 hover:bg-rose-300/10">
                            {Math.max(1, exceptionCount)} blocker
                        </Badge>
                    </div>
                    <code className="mt-3 block rounded-lg border border-white/10 bg-black/25 px-3 py-2 text-xs text-rose-100">
                        ship_to_location = null
                    </code>
                    <p className="mt-3 text-xs leading-5 text-slate-300">
                        Add the receiving facility before this lot can become export-eligible evidence.
                    </p>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center text-[10px] text-slate-400">
                    <div className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-2"><strong className="block text-sm text-white">5/5</strong>CTEs</div>
                    <div className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-2"><strong className="block text-sm text-amber-200">1</strong>missing KDE</div>
                    <div className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-2"><strong className="block text-sm text-rose-200">held</strong>commit gate</div>
                </div>
            </div>
        </div>
    );
}

function TraceFrame({ selectedLot }: { selectedLot: string }) {
    const nodes = [
        { label: "Harvest", place: "Valley Fresh", icon: MapPin, tone: "emerald" },
        { label: "Cool", place: "Salinas Hub", icon: PackageCheck, tone: "emerald" },
        { label: "Pack", place: "Packhouse 7", icon: PackageCheck, tone: "emerald" },
        { label: "Ship", place: "Bay Area DC", icon: Truck, tone: "emerald" },
        { label: "Receive", place: "Destination?", icon: AlertTriangle, tone: "rose" },
    ];

    return (
        <div className="grid h-full content-center gap-5 p-4 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-400">Selected lot</p>
                    <p className="mt-1 max-w-[360px] truncate font-mono text-sm text-white">{selectedLot || "TLC-0427-A"}</p>
                </div>
                <Badge className="border-sky-300/25 bg-sky-300/10 text-sky-200 hover:bg-sky-300/10">one-up / one-down</Badge>
            </div>
            <div className="grid gap-2 sm:grid-cols-5">
                {nodes.map((node, index) => {
                    const Icon = node.icon;
                    const blocked = node.tone === "rose";
                    return (
                        <div key={node.label} className="relative">
                            {index < nodes.length - 1 && (
                                <div className={cn("absolute left-1/2 top-5 hidden h-px w-full sm:block", index === 3 ? "border-t border-dashed border-rose-300/50" : "bg-emerald-300/35")} />
                            )}
                            <div className={cn("relative z-10 rounded-xl border p-3 text-center", blocked ? "border-rose-300/35 bg-rose-300/10" : "border-emerald-300/25 bg-emerald-300/10")}>
                                <div className={cn("mx-auto grid h-10 w-10 place-items-center rounded-full border bg-slate-950", blocked ? "border-rose-300/40 text-rose-200" : "border-emerald-300/35 text-emerald-200")}>
                                    <Icon className="h-4 w-4" />
                                </div>
                                <p className="mt-2 text-xs font-semibold text-white">{node.label}</p>
                                <p className="mt-1 truncate text-[10px] text-slate-400">{node.place}</p>
                            </div>
                        </div>
                    );
                })}
            </div>
            <p className="text-center text-xs text-slate-400">The dotted handoff is the exact point an operator needs to repair.</p>
        </div>
    );
}

function EvidenceFrame({ eventCount }: { eventCount: number }) {
    return (
        <div className="grid h-full content-center gap-5 p-4 sm:grid-cols-[1fr_1fr] sm:items-center sm:p-6">
            <div className="relative mx-auto h-52 w-full max-w-[300px]">
                <div className="absolute inset-x-8 top-8 h-40 rotate-[-5deg] rounded-xl border border-sky-300/20 bg-sky-300/10" />
                <div className="absolute inset-x-5 top-5 h-40 rotate-[3deg] rounded-xl border border-emerald-300/20 bg-emerald-300/10" />
                <div className="absolute inset-x-2 top-2 h-44 rounded-xl border border-white/15 bg-slate-900 p-4 shadow-2xl">
                    <div className="flex items-center gap-2 text-sm font-semibold text-white">
                        <FileCheck2 className="h-4 w-4 text-emerald-300" />
                        FDA traceability package
                    </div>
                    <div className="mt-4 space-y-2 text-[11px] text-slate-300">
                        <div className="flex justify-between border-b border-white/10 pb-2"><span>Canonical events</span><strong className="text-white">{eventCount || 5}</strong></div>
                        <div className="flex justify-between border-b border-white/10 pb-2"><span>Evidence hashes</span><strong className="text-emerald-200">verified</strong></div>
                        <div className="flex justify-between"><span>Export state</span><strong className="text-amber-200">preview</strong></div>
                    </div>
                </div>
            </div>
            <div className="space-y-3">
                {[
                    ["Tenant-scoped records", "No cross-customer mixing"],
                    ["Tamper-evident history", "Hashes tie output to evidence"],
                    ["Buyer-readable export", "The same chain, ready to hand off"],
                ].map(([title, detail]) => (
                    <div key={title} className="flex gap-3 rounded-xl border border-slate-700 bg-slate-900 p-3">
                        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
                        <div>
                            <p className="text-xs font-semibold text-white">{title}</p>
                            <p className="mt-1 text-[11px] leading-4 text-slate-400">{detail}</p>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}

function StoryFrame({
    stage,
    eventCount,
    readinessScore,
    exceptionCount,
    selectedLot,
}: InflowMagicStoryProps & { stage: StoryStageId }) {
    if (stage === "raw") return <RawFeedFrame />;
    if (stage === "normalize") return <NormalizeFrame eventCount={eventCount} />;
    if (stage === "detect") return <DetectFrame readinessScore={readinessScore} exceptionCount={exceptionCount} />;
    if (stage === "trace") return <TraceFrame selectedLot={selectedLot} />;
    return <EvidenceFrame eventCount={eventCount} />;
}

export function InflowMagicStory(props: InflowMagicStoryProps) {
    const [activeStage, setActiveStage] = useState<StoryStageId>("raw");
    const [isPlaying, setIsPlaying] = useState(false);
    const [videoFailed, setVideoFailed] = useState(false);
    const hasMounted = useSyncExternalStore(
        subscribeToHydration,
        getClientHydrationSnapshot,
        getServerHydrationSnapshot
    );
    const shouldReduceMotion = useReducedMotion();
    const motionEnabled = hasMounted && !shouldReduceMotion;
    const posthog = usePostHog();
    const stageButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
    const videoRef = useRef<HTMLVideoElement>(null);
    const hasTrackedVideoStart = useRef(false);
    const hasTrackedVideoComplete = useRef(false);
    const hasTrackedVideoError = useRef(false);
    const currentStage = storyStages.find((stage) => stage.id === activeStage) || storyStages[0];
    const currentStageIndex = storyStages.findIndex((stage) => stage.id === activeStage);

    useEffect(() => {
        if (!isPlaying || !motionEnabled) return;

        const timer = window.setInterval(() => {
            setActiveStage((current) => {
                const index = storyStages.findIndex((stage) => stage.id === current);
                return storyStages[(index + 1) % storyStages.length].id;
            });
        }, 4200);

        return () => window.clearInterval(timer);
    }, [isPlaying, motionEnabled]);

    useEffect(() => {
        const video = videoRef.current;
        if (!video || videoFailed) return;

        if (typeof IntersectionObserver === "undefined") return;

        if (!motionEnabled) {
            video.pause();
            return;
        }

        const observer = new IntersectionObserver(
            ([entry]) => {
                if (entry.isIntersecting) {
                    void video.play().catch(() => undefined);
                } else {
                    video.pause();
                }
            },
            { threshold: 0.4 }
        );
        observer.observe(video);

        return () => observer.disconnect();
    }, [motionEnabled, videoFailed]);

    const selectStage = (
        stage: StoryStageId,
        pausePlayback = true,
        interaction: "click" | "keyboard" = "click"
    ) => {
        setActiveStage(stage);
        if (pausePlayback) setIsPlaying(false);
        posthog.capture("INFLOW_MAGIC_STAGE_SELECTED", {
            stage,
            stage_number: storyStages.findIndex((item) => item.id === stage) + 1,
            interaction,
        });
    };

    const handleStageKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
        let nextIndex: number | null = null;
        if (event.key === "ArrowRight" || event.key === "ArrowDown") nextIndex = (index + 1) % storyStages.length;
        if (event.key === "ArrowLeft" || event.key === "ArrowUp") nextIndex = (index - 1 + storyStages.length) % storyStages.length;
        if (event.key === "Home") nextIndex = 0;
        if (event.key === "End") nextIndex = storyStages.length - 1;
        if (nextIndex === null) return;

        event.preventDefault();
        selectStage(storyStages[nextIndex].id, true, "keyboard");
        stageButtonRefs.current[nextIndex]?.focus();
    };

    const togglePlayback = () => {
        const nextPlaying = !isPlaying;
        setIsPlaying(nextPlaying);
        posthog.capture("INFLOW_MAGIC_STORY_PLAYBACK_TOGGLED", {
            action: nextPlaying ? "played" : "paused",
            stage: activeStage,
        });
    };

    const startGuidedRun = () => {
        posthog.capture("INFLOW_MAGIC_GUIDED_RUN_STARTED", {
            source: "visual_story",
            stage: activeStage,
        });
        return props.onStartGuidedRun?.();
    };

    const handleVideoPlay = () => {
        if (hasTrackedVideoStart.current) return;
        hasTrackedVideoStart.current = true;
        posthog.capture("INFLOW_MAGIC_VIDEO_STARTED", { source: "visual_story" });
    };

    const handleVideoProgress = (event: SyntheticEvent<HTMLVideoElement>) => {
        if (hasTrackedVideoComplete.current) return;
        const video = event.currentTarget;
        if (!video.duration || video.currentTime / video.duration < 0.9) return;
        hasTrackedVideoComplete.current = true;
        posthog.capture("INFLOW_MAGIC_VIDEO_COMPLETED", { source: "visual_story" });
    };

    const handleVideoError = () => {
        setVideoFailed(true);
        if (hasTrackedVideoError.current) return;
        hasTrackedVideoError.current = true;
        posthog.capture("INFLOW_MAGIC_VIDEO_FAILED", { source: "visual_story" });
    };

    return (
        <section
            aria-labelledby="inflow-magic-heading"
            data-inflow-magic-story
            data-testid="inflow-magic-story"
            className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 text-white shadow-[0_24px_80px_rgba(15,23,42,0.18)]"
        >
            <div className="relative overflow-hidden border-b border-white/10 px-5 py-6 sm:px-7 sm:py-8">
                <div className="pointer-events-none absolute inset-0 opacity-40 [background-image:radial-gradient(circle_at_20%_20%,rgba(52,211,153,.2),transparent_32%),radial-gradient(circle_at_82%_32%,rgba(56,189,248,.16),transparent_28%)]" />
                <div className="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
                    <div className="max-w-3xl">
                        <div className="flex items-center gap-2 text-emerald-300">
                            <Sparkles className="h-4 w-4" />
                            <span className="text-[11px] font-semibold uppercase tracking-[0.22em]">The transformation, made visible</span>
                        </div>
                        <h2 id="inflow-magic-heading" className="mt-3 text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                            Watch messy supplier activity become defensible evidence.
                        </h2>
                        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-300">
                            Step through the exact moment RegEngine finds the hidden break, explains the lot journey, and prepares an audit-ready handoff.
                        </p>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2">
                            <strong className="block text-lg text-white">{props.eventCount || 5}</strong>
                            <span className="text-[10px] uppercase tracking-wide text-slate-400">events</span>
                        </div>
                        <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2">
                            <strong className="block text-lg text-emerald-200">{props.readinessScore}</strong>
                            <span className="text-[10px] uppercase tracking-wide text-slate-400">readiness</span>
                        </div>
                        <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2">
                            <strong className="block text-lg text-rose-200">{Math.max(1, props.exceptionCount)}</strong>
                            <span className="text-[10px] uppercase tracking-wide text-slate-400">proof lead</span>
                        </div>
                    </div>
                </div>
            </div>

            <div data-magic-main className="grid min-w-0 w-full lg:grid-cols-[300px_minmax(0,1fr)]">
                <div className="border-b border-white/10 bg-slate-950 p-3 lg:border-b-0 lg:border-r">
                    <div data-magic-nav className="grid gap-1 sm:grid-cols-5 lg:grid-cols-1" role="tablist" aria-label="Traceability transformation stages">
                        {storyStages.map((stage, index) => {
                            const Icon = stage.icon;
                            const selected = stage.id === activeStage;
                            return (
                                <button
                                    key={stage.id}
                                    ref={(element) => {
                                        stageButtonRefs.current[index] = element;
                                    }}
                                    type="button"
                                    data-magic-stage
                                    id={`inflow-magic-tab-${stage.id}`}
                                    role="tab"
                                    aria-controls="inflow-magic-stage"
                                    aria-selected={selected}
                                    tabIndex={selected ? 0 : -1}
                                    onClick={() => selectStage(stage.id)}
                                    onKeyDown={(event) => handleStageKeyDown(event, index)}
                                    className={cn(
                                        "group relative flex min-w-0 items-center gap-3 overflow-hidden rounded-xl border px-3 py-3 text-left transition duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950",
                                        selected
                                            ? "border-emerald-300/30 bg-emerald-300/10 text-white"
                                            : "border-transparent text-slate-400 hover:border-white/10 hover:bg-slate-900 hover:text-white"
                                    )}
                                >
                                    <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg border text-xs", selected ? "border-emerald-300/30 bg-emerald-300/10 text-emerald-200" : "border-white/10 bg-slate-900") }>
                                        <Icon className="h-4 w-4" />
                                    </span>
                                    <span className="min-w-0">
                                        <span className="block text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-500">0{index + 1}</span>
                                        <span className="mt-0.5 block truncate text-xs font-semibold sm:hidden lg:block">{stage.shortLabel}</span>
                                        <span className="mt-0.5 hidden text-xs font-semibold sm:block lg:hidden xl:block">{stage.label}</span>
                                    </span>
                                    <ArrowRight className={cn("ml-auto hidden h-3.5 w-3.5 lg:block", selected ? "text-emerald-300" : "text-slate-700 group-hover:text-slate-400")} />
                                    {selected && (
                                        <motion.span
                                            layoutId="active-inflow-stage"
                                            className="absolute inset-x-3 bottom-0 h-px bg-gradient-to-r from-transparent via-emerald-300 to-transparent"
                                            transition={{ duration: motionEnabled ? 0.28 : 0 }}
                                        />
                                    )}
                                </button>
                            );
                        })}
                    </div>
                </div>

                <div className="min-w-0 p-3 sm:p-5">
                    <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                        <div aria-live="polite" aria-atomic="true">
                            <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-emerald-300">{currentStage.eyebrow}</p>
                            <h3 className="mt-1 text-base font-semibold text-white">{currentStage.label}</h3>
                            <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">{currentStage.summary}</p>
                        </div>
                        <button
                            type="button"
                            data-magic-play
                            onClick={togglePlayback}
                            disabled={!motionEnabled}
                            className="inline-flex h-8 items-center gap-2 rounded-full border border-white/10 bg-slate-900 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-300 transition hover:border-emerald-300/30 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
                            aria-label={isPlaying ? "Pause transformation walkthrough" : "Play transformation walkthrough"}
                        >
                            {isPlaying ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                            {!motionEnabled ? "Reduced motion" : isPlaying ? "Pause story" : "Play story"}
                        </button>
                    </div>
                    <div
                        id="inflow-magic-stage"
                        role="tabpanel"
                        aria-labelledby={`inflow-magic-tab-${activeStage}`}
                        data-testid="magic-visual-stage"
                        className="relative min-h-[360px] overflow-hidden rounded-2xl border border-white/10 bg-[#0a111c] shadow-inner [background-image:linear-gradient(rgba(255,255,255,.025)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.025)_1px,transparent_1px)] [background-size:28px_28px]"
                    >
                        <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-emerald-300/[0.04] to-transparent" />
                        <AnimatePresence mode="wait" initial={false}>
                            <motion.div
                                key={activeStage}
                                className="relative min-h-[360px]"
                                initial={motionEnabled ? { opacity: 0, x: 18, filter: "blur(4px)" } : false}
                                animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
                                exit={motionEnabled ? { opacity: 0, x: -12, filter: "blur(3px)" } : undefined}
                                transition={{ duration: motionEnabled ? 0.32 : 0, ease: [0.22, 1, 0.36, 1] }}
                            >
                                <StoryFrame stage={activeStage} {...props} />
                            </motion.div>
                        </AnimatePresence>
                        <div className="absolute inset-x-4 bottom-3 flex gap-1" aria-hidden="true">
                            {storyStages.map((stage, index) => (
                                <span key={stage.id} className="h-0.5 flex-1 overflow-hidden rounded-full bg-white/10">
                                    <motion.span
                                        className="block h-full origin-left bg-emerald-300"
                                        animate={{ scaleX: index <= currentStageIndex ? 1 : 0 }}
                                        transition={{ duration: motionEnabled ? 0.35 : 0 }}
                                    />
                                </span>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid gap-4 border-t border-white/10 bg-black/20 p-4 sm:p-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(300px,.8fr)]">
                <div className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
                    <div className="flex items-center justify-between gap-3 border-b border-white/10 px-3 py-2">
                        <div>
                            <p className="text-xs font-semibold text-white">Product walkthrough</p>
                            <p id="inflow-magic-video-description" className="mt-0.5 text-[10px] text-slate-500">Silent loop · five interface states · synthetic test data</p>
                        </div>
                        <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-rose-200">
                            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-400 motion-reduce:animate-none" />
                            product capture
                        </span>
                    </div>
                    <div className="relative aspect-video w-full bg-slate-950">
                        <video
                            ref={videoRef}
                            className={cn("h-full w-full object-cover", videoFailed && "invisible")}
                            controls
                            loop
                            muted
                            playsInline
                            preload="metadata"
                            poster="/media/inflow-lab-magic-poster.png"
                            aria-label="Inflow Lab visual walkthrough"
                            aria-describedby="inflow-magic-video-description"
                            onPlay={handleVideoPlay}
                            onTimeUpdate={handleVideoProgress}
                            onCanPlay={() => setVideoFailed(false)}
                            onError={handleVideoError}
                        >
                            <source src="/media/inflow-lab-magic-loop.webm" type="video/webm" />
                            <source src="/media/inflow-lab-magic-loop.mp4" type="video/mp4" />
                            <track kind="captions" src="/media/inflow-lab-magic-captions.vtt" srcLang="en" label="English" default />
                        </video>
                        {videoFailed && (
                            <div className="absolute inset-0 grid place-items-center p-6 text-center" role="status">
                                <div className="max-w-sm rounded-xl border border-white/10 bg-slate-900 p-5 shadow-2xl">
                                    <ScanSearch className="mx-auto h-6 w-6 text-emerald-300" />
                                    <p className="mt-3 text-sm font-semibold text-white">The walkthrough could not load.</p>
                                    <p className="mt-2 text-xs leading-5 text-slate-400">Use the five interactive stages above—the same product states remain fully available.</p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
                <figure className="group relative min-h-[280px] overflow-hidden rounded-xl border border-white/10 bg-slate-900">
                    <Image
                        src="/media/inflow-lab-packhouse.webp"
                        alt="A food-safety operator reviewing leafy greens on a packing line"
                        fill
                        sizes="(min-width: 1024px) 38vw, 100vw"
                        className="object-cover transition duration-700 group-hover:scale-[1.025] motion-reduce:transition-none motion-reduce:group-hover:scale-100"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/45 to-transparent" />
                    <figcaption className="absolute inset-x-0 bottom-0 p-5">
                        <div className="flex items-center gap-2 text-emerald-200">
                            <MapPin className="h-4 w-4" />
                            <p className="text-[10px] font-semibold uppercase tracking-[0.18em]">The operational moment</p>
                        </div>
                        <p className="mt-2 text-lg font-semibold text-white">A handoff people can see, fix, and prove.</p>
                        <p className="mt-2 text-xs leading-5 text-slate-300">Illustrative facility image. The walkthrough uses synthetic test records.</p>
                    </figcaption>
                </figure>
            </div>

            <div className="flex flex-col gap-4 border-t border-white/10 bg-gradient-to-r from-emerald-300/[0.08] via-transparent to-sky-300/[0.06] px-5 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-7">
                <div>
                    <p className="text-sm font-semibold text-white">Don’t just watch the clean version.</p>
                    <p className="mt-1 text-xs leading-5 text-slate-400">Run the same mock scenario, inspect the defect, and trace the affected lot yourself.</p>
                </div>
                {props.onStartGuidedRun ? (
                    <Button
                        type="button"
                        data-magic-cta
                        onClick={startGuidedRun}
                        disabled={props.isBusy}
                        className="h-11 shrink-0 bg-emerald-300 px-5 font-semibold text-slate-950 shadow-[0_12px_30px_rgba(52,211,153,0.18)] hover:bg-emerald-200 focus-visible:ring-emerald-200"
                    >
                        <Play className="mr-2 h-4 w-4" />
                        {props.isBusy ? "Running test scenario…" : "Run this test scenario"}
                    </Button>
                ) : (
                    <div className="grid content-center gap-3">
                        <div className="flex items-center gap-2 text-emerald-300">
                            <Sparkles className="h-4 w-4" />
                            <p className="text-xs font-semibold uppercase tracking-[0.18em]">What becomes clear</p>
                        </div>
                        <div className="flex items-start gap-2 text-xs leading-5 text-slate-300">
                            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" />
                            The broken record, affected lot, and evidence boundary stay connected.
                        </div>
                    </div>
                )}
            </div>
        </section>
    );
}
