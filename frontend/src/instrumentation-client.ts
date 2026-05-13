/**
 * Client-side instrumentation shim.
 *
 * Browser Sentry is intentionally disabled from the initial app graph. Server
 * instrumentation still lives in instrumentation.ts, and client capture helpers
 * remain safe no-ops in production so dashboard performance is not dominated by
 * observability code.
 */

type SeverityLevel = "fatal" | "error" | "warning" | "log" | "info" | "debug";

export const onRouterTransitionStart = () => {
    // No-op: router instrumentation requires the browser SDK, which is excluded
    // from the dashboard initial bundle.
};

export const captureError = (error: Error, context?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === "development") {
        console.error("[Client instrumentation disabled]", error.message, context);
    }
};

export const captureMessage = (message: string, level: SeverityLevel = "info") => {
    if (process.env.NODE_ENV === "development") {
        console.warn(`[${level}] ${message}`);
    }
};

export const setUserContext = (_user: { id: string; email?: string; username?: string }) => {
    // No-op.
};

export const clearUserContext = () => {
    // No-op.
};
