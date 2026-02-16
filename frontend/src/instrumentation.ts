/**
 * Next.js Instrumentation — Server and Edge Runtime
 * 
 * This file initializes Sentry for server-side and edge runtime contexts.
 * See: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

export async function register() {
    if (process.env.NEXT_RUNTIME === "nodejs") {
        // Server-side Sentry initialization
        const Sentry = await import("@sentry/nextjs");
        const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;

        if (dsn) {
            Sentry.init({
                dsn,
                environment: process.env.VERCEL_ENV || process.env.NODE_ENV || "development",
                release: process.env.VERCEL_GIT_COMMIT_SHA || "local",
                tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
                sendDefaultPii: false,
            });
        }
    }

    if (process.env.NEXT_RUNTIME === "edge") {
        // Edge runtime Sentry initialization (middleware)
        const Sentry = await import("@sentry/nextjs");
        const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;

        if (dsn) {
            Sentry.init({
                dsn,
                environment: process.env.VERCEL_ENV || process.env.NODE_ENV || "development",
                tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
            });
        }
    }
}
