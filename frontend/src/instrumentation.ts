/**
 * Next.js Instrumentation — Server and Edge Runtime
 * 
 * This file initializes Sentry for server-side and edge runtime contexts.
 * See: https://nextjs.org/docs/app/building-your-application/optimizing/instrumentation
 */

import * as Sentry from "@sentry/nextjs";

export const onRequestError = Sentry.captureRequestError;

// Keep the restrictive v10 collection defaults in both server runtimes.
const piiDenyList = ["forwarded", "-ip", "remote-", "via", "-user"];
const dataCollection = {
    userInfo: false,
    cookies: false,
    httpHeaders: {
        request: { deny: piiDenyList },
        response: { deny: piiDenyList },
    },
    httpBodies: [],
    urlQueryParams: { deny: piiDenyList },
    genAI: { inputs: false, outputs: false },
    databaseQueryData: false,
    graphQL: { document: false, variables: false },
    queues: false,
} satisfies NonNullable<Parameters<typeof Sentry.init>[0]["dataCollection"]>;

/**
 * Production startup assertion: CSRF_SECRET must be set and must not collide
 * with any legacy JWT signing material the deployment may still be carrying.
 *
 * The frontend no longer signs or verifies RegEngine JWTs — the admin backend
 * owns `JWTKeyRegistry` and is the sole authority. JWT_SIGNING_KEY and
 * AUTH_SECRET_KEY are no-ops on the frontend post-Option-1; the only HMAC
 * key the frontend still uses is CSRF_SECRET. The collision checks below
 * remain as a guard against operators copying the wrong secret into both
 * slots during a future env rotation.
 */
function assertSecretSeparation(): void {
    if (process.env.NODE_ENV !== "production") return;

    const csrf = process.env.CSRF_SECRET;
    const jwt = process.env.JWT_SIGNING_KEY;
    const auth = process.env.AUTH_SECRET_KEY;

    const errors: string[] = [];
    if (!csrf) errors.push("CSRF_SECRET must be set in production");
    if (csrf && jwt && csrf === jwt) {
        errors.push("CSRF_SECRET must not equal legacy JWT_SIGNING_KEY material");
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
                traceLifecycle: "static",
                dataCollection,
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
                traceLifecycle: "static",
                dataCollection,
            });
        }
    }
}
