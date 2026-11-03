"use client";

import { useCallback, useSyncExternalStore } from "react";
import { ChevronRight, GraduationCap, X } from "lucide-react";

import type { TutorialStep } from "@/components/ui/tutorial";

// One key for the tutorial's own "don't show again" checkbox, a separate key
// for the banner so dismissing the banner never suppresses the walkthrough
// itself (it stays reachable from the header's "How to use" button).
export const INFLOW_LAB_TUTORIAL_STORAGE_KEY = "inflow-lab-dashboard-tutorial";
export const INFLOW_LAB_TUTORIAL_BANNER_KEY = "inflow-lab-dashboard-tutorial-banner-dismissed";
// The standalone /tools/inflow-lab client carries its own tour with its own
// dismissal state — finishing one surface's tour must not hide the other's.
export const INFLOW_LAB_CLIENT_TUTORIAL_STORAGE_KEY = "inflow-lab-client-tutorial";
export const INFLOW_LAB_CLIENT_TUTORIAL_BANNER_KEY = "inflow-lab-client-tutorial-banner-dismissed";

// Step-by-step operating guide for the dashboard Inflow Lab tab. Targets are
// stable anchors on the page: data-tutorial markers, the funnel test id, and
// the selected-lot panel marker the tests already rely on.
//
// A builder rather than a constant: the "run your first test" step carries a
// real action button wired to the page's guided proof, so the walkthrough can
// evaluate the user's own rows and fill the panels its later steps describe.
export function buildInflowLabTutorialSteps({
    runGuidedProof,
}: {
    runGuidedProof: () => void;
}): TutorialStep[] {
    return [
        {
            target: '[data-testid="inflow-evidence-chain"]',
            title: "What Inflow Lab is",
            content:
                "A sandbox for supplier traceability data. This is one lot's chain of custody, harvest through receiving. A solid link is a record we have; a broken one is a record that never arrived. The gate at the end is what a missing link costs you. Nothing here writes to production exports.",
            position: "bottom",
        },
        {
            target: '[data-tutorial="inflow-load-data"]',
            title: "Bring supplier data in",
            content:
                "Upload CSV takes your own supplier rows and opens them in the data editor below, where you can also paste rows directly. Nothing is preloaded: until you add data, the panels show No data yet.",
            position: "bottom",
        },
        {
            target: '[data-tutorial="inflow-guided-proof"]',
            title: "Run your first test",
            content:
                "This evaluates the rows you uploaded or pasted, end to end. The highlighted button is live, or use the one right here. The chain, pipeline, score, and lot panels fill with the results. With no rows loaded, it opens the data editor instead.",
            position: "bottom",
            action: "Run trace",
            onAction: runGuidedProof,
        },
        {
            target: '[data-testid="inflow-funnel"]',
            title: "Read the pipeline funnel",
            content:
                "Lots flow Loaded → Validated → Passing → Preview-ready → Production import. Wherever the numbers drop is where your data is losing evidence.",
            position: "top",
        },
        {
            target: '[data-tutorial="inflow-readiness"]',
            title: "Check the Data Preflight Score",
            content:
                "Five factors roll up into one readiness score. The “biggest gap” badge marks the factor holding you back. That is always the next thing to fix.",
            position: "right",
        },
        {
            target: '[data-tutorial="inflow-exceptions"]',
            title: "Clear exceptions by pattern",
            content:
                "Blocked lots are grouped by shared root cause: handoff, source, or mixed. Fix the pattern once (for example, map a missing handoff field) and the whole group unblocks. This list stays empty until your data brings real exceptions.",
            position: "top",
        },
        {
            target: "[data-selected-lot-panel]",
            title: "Trace one lot",
            content:
                "Click any lot code to see its five-step lifecycle and which CTE evidence is missing. When an evaluation looks right, Save test run in the data editor persists it to the Inflow Workbench (write access required). Reopen this guide any time from “How to use” in the header.",
            position: "left",
        },
    ];
}

// Operating guide for the standalone /tools/inflow-lab workbench (also used
// by its embedded dashboard variant). Anchors are stable regardless of tab
// state; the demo step carries a live action so the tour can produce the data
// its later steps describe.
export function buildInflowLabClientTutorialSteps({
    runDemo,
    isStandalone,
}: {
    runDemo: () => void;
    isStandalone: boolean;
}): TutorialStep[] {
    return [
        {
            target: 'section[aria-label="Inflow Lab environment boundary"]',
            title: "What Inflow Lab is",
            content:
                "A mock environment for supplier traceability data. Everything here uses test or uploaded records only. Formal production records start after signed-in import, so you can experiment freely.",
            position: "bottom",
        },
        {
            target: '[data-tutorial="lab-primary-actions"]',
            title: "Run your first demo",
            content: isStandalone
                ? "Load mock scenario fills the lab with a believable supplier feed; Run pipeline processes it end to end. The button here does both in one go and jumps to the event log when it finishes."
                : "Start guided test run loads a mock supplier feed if the lab is empty, processes it end to end, and jumps to the record log when it finishes.",
            position: "bottom",
            action: "Run the demo",
            onAction: runDemo,
        },
        {
            target: '[data-tutorial="lab-tabs"]',
            title: "Find your way around",
            content:
                "Each tab is a workspace: Data feeder tests your own CSV before import, Fix queue groups blocking defects, Lots and Lineage trace individual lot codes, and the log tab shows every record the pipeline produced.",
            position: "bottom",
        },
        {
            target: '[data-tutorial="lab-workspace"]',
            title: "Read the results",
            content:
                "Pipeline results land here: connection status, lot counts, and delivery outcomes on the overview, with the full detail one tab away. Reopen this guide any time from “How to use” in the header.",
            position: "top",
        },
    ];
}

// The dismissed flag lives in localStorage, which React must treat as an
// external store: reading it during render would break SSR, and reading it in
// an effect would cascade an extra render. useSyncExternalStore handles both —
// the server snapshot reports "dismissed" so the server never renders a banner
// the client might immediately remove.
const bannerListeners = new Set<() => void>();

function subscribeToBanner(onStoreChange: () => void) {
    bannerListeners.add(onStoreChange);
    return () => {
        bannerListeners.delete(onStoreChange);
    };
}

function readBannerDismissed(key: string): boolean {
    try {
        return window.localStorage.getItem(key) === "true";
    } catch {
        return false;
    }
}

function bannerDismissedOnServer() {
    return true;
}

// Completing (or explicitly skipping) the walkthrough is the banner's job
// done — calling this retires it without requiring a separate dismissal.
export function dismissInflowLabTutorialBanner(key: string = INFLOW_LAB_TUTORIAL_BANNER_KEY) {
    try {
        window.localStorage.setItem(key, "true");
    } catch {
        /* private mode — banner simply reappears next visit */
    }
    bannerListeners.forEach((listener) => listener());
}

export function InflowLabTutorialBanner({
    onStart,
    dismissKey = INFLOW_LAB_TUTORIAL_BANNER_KEY,
    description = "A guided walkthrough: load supplier data, run a sandbox test, read the readiness score, and clear blocked lots.",
}: {
    onStart: () => void;
    dismissKey?: string;
    description?: string;
}) {
    const readDismissed = useCallback(() => readBannerDismissed(dismissKey), [dismissKey]);
    const dismissed = useSyncExternalStore(
        subscribeToBanner,
        readDismissed,
        bannerDismissedOnServer,
    );

    const dismiss = useCallback(() => {
        dismissInflowLabTutorialBanner(dismissKey);
    }, [dismissKey]);

    if (dismissed) return null;

    return (
        <div
            data-testid="inflow-tutorial-banner"
            className="flex items-stretch overflow-hidden rounded-lg border border-emerald-200 bg-gradient-to-r from-emerald-50 via-white to-blue-50 shadow-sm"
        >
            <button
                type="button"
                onClick={onStart}
                className="group flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-emerald-100/40"
            >
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-600 text-white">
                    <GraduationCap className="h-5 w-5" aria-hidden />
                </span>
                <span className="min-w-0">
                    <span className="block text-sm font-semibold text-slate-950">
                        New to Inflow Lab? Learn to operate it step by step
                    </span>
                    <span className="mt-0.5 block truncate text-xs text-slate-600">{description}</span>
                </span>
                <span className="ml-auto flex shrink-0 items-center gap-1 text-xs font-medium text-emerald-700 group-hover:underline">
                    Start walkthrough
                    <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                </span>
            </button>
            <button
                type="button"
                onClick={dismiss}
                aria-label="Dismiss tutorial banner"
                className="flex items-center border-l border-emerald-100 px-3 text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
            >
                <X className="h-4 w-4" aria-hidden />
            </button>
        </div>
    );
}
