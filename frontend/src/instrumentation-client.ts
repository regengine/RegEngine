/**
 * Sentry Client-Side Configuration
 *
 * Initializes browser error tracking when NEXT_PUBLIC_SENTRY_DSN is set.
 * Falls back to console logging when DSN is absent (local dev, CI).
 */

import * as Sentry from "@sentry/nextjs";

const SENTRY_DSN = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (SENTRY_DSN) {
    Sentry.init({
        dsn: SENTRY_DSN,
        environment: process.env.NEXT_PUBLIC_VERCEL_ENV || process.env.NODE_ENV || "development",
        release: process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA || "local",

        // Performance Monitoring — sample 10% of transactions in production
        tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,

        // Session Replay — capture 1% of sessions, 100% of error sessions
        replaysSessionSampleRate: 0.01,
        replaysOnErrorSampleRate: 1.0,

        integrations: [
            Sentry.replayIntegration(),
            Sentry.browserTracingIntegration(),
        ],

        // Filter out noisy errors
        ignoreErrors: [
            "ResizeObserver loop",
            "Non-Error promise rejection",
            /Loading chunk \d+ failed/,
            /Failed to fetch/,
        ],

        // Don't send PII
        sendDefaultPii: false,
    });
}

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;

// Re-export convenience helpers for use across the app
export const captureError = (error: Error, context?: Record<string, unknown>) => {
    if (SENTRY_DSN) {
        Sentry.captureException(error, { extra: context });
    } else if (process.env.NODE_ENV === "development") {
        console.error("[Sentry Disabled]", error.message, context);
    }
};

export const captureMessage = (message: string, level: Sentry.SeverityLevel = "info") => {
    if (SENTRY_DSN) {
        Sentry.captureMessage(message, level);
    } else if (process.env.NODE_ENV === "development") {
        console.log(`[${level}] ${message}`);
    }
};

export const setUserContext = (user: { id: string; email?: string; username?: string }) => {
    if (SENTRY_DSN) {
        Sentry.setUser(user);
    }
};

export const clearUserContext = () => {
    if (SENTRY_DSN) {
        Sentry.setUser(null);
    }
};
