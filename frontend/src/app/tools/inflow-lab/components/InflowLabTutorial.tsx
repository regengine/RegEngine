"use client";

import { useCallback, useSyncExternalStore } from "react";
import { ChevronRight, GraduationCap, X } from "lucide-react";

import type { TutorialStep } from "@/components/ui/tutorial";

// One key for the tutorial's own "don't show again" checkbox, a separate key
// for the banner so dismissing the banner never suppresses the walkthrough
// itself (it stays reachable from the header's "How to use" button).
export const INFLOW_LAB_TUTORIAL_STORAGE_KEY = "inflow-lab-dashboard-tutorial";
export const INFLOW_LAB_TUTORIAL_BANNER_KEY = "inflow-lab-dashboard-tutorial-banner-dismissed";

// Step-by-step operating guide for the dashboard Inflow Lab tab. Targets are
// stable anchors on the page: data-tutorial markers, the funnel test id, and
// the selected-lot panel marker the tests already rely on.
export const INFLOW_LAB_TUTORIAL_STEPS: TutorialStep[] = [
    {
        target: '[data-tutorial="inflow-load-data"]',
        title: "Bring supplier data in",
        content:
            "Everything starts with data. Upload CSV takes your own supplier rows; Load realistic sample fills the workspace with a believable farm-to-DC trace so you can explore safely.",
        position: "bottom",
    },
    {
        target: 'section[aria-label="How Inflow Lab works"]',
        title: "Know what the lab does",
        content:
            "Inflow Lab is a sandbox. It replays lot activity, rebuilds each lot's evidence trail, and shows exactly which FSMA 204 records are missing. Nothing you do here writes to production exports.",
        position: "bottom",
    },
    {
        target: '[data-tutorial="inflow-guided-proof"]',
        title: "Run your first test",
        content:
            "Click Run guided proof to evaluate the sample end to end: it loads the sample rows, runs the sandbox evaluation, and lights up the panels below with real results.",
        position: "bottom",
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
            "Five factors roll up into one readiness score. The “biggest gap” badge marks the factor holding you back — that is always the next thing to fix.",
        position: "right",
    },
    {
        target: '[data-tutorial="inflow-exceptions"]',
        title: "Clear exceptions by pattern",
        content:
            "Blocked lots are grouped by shared root cause — handoff, source, or mixed. Fix the pattern once (for example, map a missing handoff field) and the whole group unblocks.",
        position: "top",
    },
    {
        target: "[data-selected-lot-panel]",
        title: "Trace one lot, then save your run",
        content:
            "Click any lot code to see its five-step lifecycle and exactly which CTE evidence is missing. When an evaluation looks right, Save test run persists it to the Inflow Workbench (write access required). Reopen this guide any time from “How to use” in the header.",
        position: "left",
    },
];

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

function readBannerDismissed(): boolean {
    try {
        return window.localStorage.getItem(INFLOW_LAB_TUTORIAL_BANNER_KEY) === "true";
    } catch {
        return false;
    }
}

function bannerDismissedOnServer() {
    return true;
}

export function InflowLabTutorialBanner({ onStart }: { onStart: () => void }) {
    const dismissed = useSyncExternalStore(
        subscribeToBanner,
        readBannerDismissed,
        bannerDismissedOnServer,
    );

    const dismiss = useCallback(() => {
        try {
            window.localStorage.setItem(INFLOW_LAB_TUTORIAL_BANNER_KEY, "true");
        } catch {
            /* private mode — banner simply reappears next visit */
        }
        bannerListeners.forEach((listener) => listener());
    }, []);

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
                    <span className="mt-0.5 block truncate text-xs text-slate-600">
                        A guided walkthrough: load supplier data, run a sandbox test, read the readiness
                        score, and clear blocked lots.
                    </span>
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
