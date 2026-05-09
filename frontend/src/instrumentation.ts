/**
 * Next.js Instrumentation — Server and Edge Runtime
 * 
 * This file initializes Sentry for server-side and edge runtime contexts.
 * See: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

import * as Sentry from "@sentry/nextjs";

export const onRequestError = Sentry.captureRequestError;

/**
 * Production startup assertions for cryptographic key separation (RE-SEC-005).
 *
 * Verifies that CSRF_SECRET and JWT_SIGNING_KEY are both set, distinct from
 * each other, and distinct from the legacy AUTH_SECRET_KEY. Reusing one key
 * across HMAC (CSRF) and JWT signing contexts violates NIST SP 800-57 §5.2.
 * Throws on misconfiguration so cold-start fails fast and surfaces in logs.
 */
function assertSecretSeparation(): void {
    if (process.env.NODE_ENV !== "production") return;

    const csrf = process.env.CSRF_SECRET;
    const jwt = process.env.JWT_SIGNING_KEY;
    const auth = process.env.AUTH_SECRET_KEY;

    const errors: string[] = [];
    if (!csrf) errors.push("CSRF_SECRET must be set in production");
    if (!jwt) errors.push("JWT_SIGNING_KEY must be set in production");
    if (csrf && jwt && csrf === jwt) {
        errors.push("CSRF_SECRET and JWT_SIGNING_KEY must be distinct (key separation)");
    }
    if (csrf && auth && csrf === auth) {
        errors.push("CSRF_SECRET must not equal legacy AUTH_SECRET_KEY");
    }

    if (errors.length > 0) {
        for (const e of errors) console.error(`[startup-assertion] ${e}`);
        throw new Error(`Startup assertions failed:\n  - ${errors.join("\n  - ")}`);
    }
}

export async function register() {
    assertSecretSeparation();

    if (process.env.NEXT_RUNTIME === "nodejs") {
        // Server-side Sentry initialization
        const sentry = await import("@sentry/nextjs");
        const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;

        if (dsn) {
            sentry.init({
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
        const sentry = await import("@sentry/nextjs");
        const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN;

        if (dsn) {
            sentry.init({
                dsn,
                environment: process.env.VERCEL_ENV || process.env.NODE_ENV || "development",
                tracesSampleRate: process.env.NODE_ENV === "production" ? 0.1 : 1.0,
            });
        }
    }
}
