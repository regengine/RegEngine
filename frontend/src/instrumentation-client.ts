/**
 * Client-side instrumentation.
 *
 * Browser Sentry is intentionally excluded from the initial app graph so
 * observability code cannot dominate dashboard performance. Server
 * instrumentation still lives in instrumentation.ts.
 *
 * WS-10: instead of a pure no-op (which made client errors vanish
 * silently in production), uncaught errors and unhandled promise
 * rejections are now reported to the first-party /api/client-errors
 * beacon — sampled, PII-free, and loop-guarded. No third-party SDK is
 * added to the bundle.
 */

type SeverityLevel = "fatal" | "error" | "warning" | "log" | "info" | "debug";

// Report at most this fraction of page loads (sampling decision is made
// once per page load so a sampled session reports all its errors and an
// unsampled one reports none — easier to correlate than per-event dice).
const SAMPLE_RATE = 0.1;
// Hard per-page-load cap so a render-loop error cannot flood the beacon.
const MAX_REPORTS_PER_LOAD = 10;

let reportsSent = 0;
let sampled: boolean | null = null;
const seenSignatures = new Set<string>();

function isSampled(): boolean {
    if (sampled === null) {
        sampled = Math.random() < SAMPLE_RATE;
    }
    return sampled;
}

function stripQuery(url: string): string {
    return url.split(/[?#]/, 1)[0] ?? "";
}

function sendReport(kind: "error" | "unhandledrejection", message: string, stack?: string) {
    if (typeof window === "undefined") return;
    if (process.env.NODE_ENV !== "production") return;
    if (!isSampled()) return;
    if (reportsSent >= MAX_REPORTS_PER_LOAD) return;

    // Dedupe identical errors within a page load (render loops, retry
    // storms) so the cap is spent on distinct failures.
    const signature = `${kind}:${message.slice(0, 200)}`;
    if (seenSignatures.has(signature)) return;
    seenSignatures.add(signature);
    reportsSent += 1;

    const body = JSON.stringify({
        kind,
        message: message.slice(0, 500),
        stack: (stack ?? "").slice(0, 4000),
        // PII hygiene: path only — query strings can carry tokens/emails.
        url: stripQuery(window.location.href).slice(0, 300),
    });

    try {
        if (navigator.sendBeacon) {
            navigator.sendBeacon("/api/client-errors", new Blob([body], { type: "application/json" }));
        } else {
            void fetch("/api/client-errors", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body,
                keepalive: true,
                credentials: "omit",
            });
        }
    } catch {
        // Reporting must never throw into the page.
    }
}

if (typeof window !== "undefined") {
    window.addEventListener("error", (event) => {
        const error = event.error instanceof Error ? event.error : null;
        sendReport(
            "error",
            error?.message || event.message || "Unknown error",
            error?.stack,
        );
    });

    window.addEventListener("unhandledrejection", (event) => {
        const reason = event.reason;
        const error = reason instanceof Error ? reason : null;
        sendReport(
            "unhandledrejection",
            error?.message || (typeof reason === "string" ? reason : "Unhandled rejection"),
            error?.stack,
        );
    });
}

export const onRouterTransitionStart = () => {
    // No-op: router instrumentation requires the browser SDK, which is excluded
    // from the dashboard initial bundle.
};

export const captureError = (error: Error, context?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === "development") {
        console.error("[Client instrumentation]", error.message, context);
    }
    sendReport("error", error.message, error.stack);
};

export const captureMessage = (message: string, level: SeverityLevel = "info") => {
    if (process.env.NODE_ENV === "development") {
        console.warn(`[${level}] ${message}`);
    }
};

export const setUserContext = (_user: { id: string; email?: string; username?: string }) => {
    // No-op: the beacon is intentionally anonymous (PII-free payloads).
};

export const clearUserContext = () => {
    // No-op.
};
