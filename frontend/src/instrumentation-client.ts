/**
 * Browser-side Sentry Instrumentation
 *
 * Initializes @sentry/nextjs for browser/client errors when NEXT_PUBLIC_SENTRY_DSN
 * is set. This runs in the browser context only — server and edge runtime
 * initialization remains in instrumentation.ts.
 *
 * See: https://docs.sentry.io/platforms/javascript/guides/nextjs/
 */

import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;

if (dsn) {
    Sentry.init({
        dsn,
        environment: process.env.NEXT_PUBLIC_VERCEL_ENV || process.env.NODE_ENV || "development",
        release: process.env.NEXT_PUBLIC_VERCEL_GIT_COMMIT_SHA || "local",
        tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
        replaysSessionSampleRate: 0.0,
        replaysOnErrorSampleRate: 0.0,
    });
}
