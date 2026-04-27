/** @type {import('next').NextConfig} */
// Last deployed: 2026-02-13
const { withSentryConfig } = require("@sentry/nextjs");

const isStatic = process.env.REGENGINE_DEPLOY_MODE === 'static';
const apiGatewayUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
const ingestionUrl = process.env.INGESTION_SERVICE_URL || (apiGatewayUrl && `${apiGatewayUrl}:8002`);
// Note: COMPLIANCE_SERVICE_URL is read directly by the compliance route handler
// (src/app/api/compliance/[...path]/route.ts) — no longer referenced here since
// the /api/compliance rewrite was removed in #1221.

// Validate service URLs at dev-server startup, not during build/lint/test.
const isDevServer = process.env.NODE_ENV === 'development' && !process.env.NEXT_PHASE;
if (!isStatic && isDevServer) {
    const hasIndividualServiceUrls =
        process.env.INGESTION_SERVICE_URL &&
        process.env.COMPLIANCE_SERVICE_URL &&
        process.env.ADMIN_SERVICE_URL;

    if (!apiGatewayUrl && !hasIndividualServiceUrls) {
        console.warn(
            'Warning: No API routing env vars are set — configure NEXT_PUBLIC_API_BASE_URL, ' +
            'or set INGESTION_SERVICE_URL, COMPLIANCE_SERVICE_URL, and ADMIN_SERVICE_URL individually. ' +
            'The dashboard will fall back to demo data.'
        );
    }

    if (!apiGatewayUrl && hasIndividualServiceUrls) {
        console.warn(
            'Warning: NEXT_PUBLIC_API_BASE_URL is not set. ' +
            'Individual service URLs are present so routing will work, ' +
            'but the /api/v1/health proxy rewrite will be skipped.'
        );
    }
}

const nextConfig = {
    output: isStatic ? 'export' : undefined,
    // (#558) Always enable Next.js image optimization.
    // sharp is installed (package.json) and handles build-time optimization for
    // both server-rendered and static-export builds — do not disable for static.
    images: {},
    async headers() {
        return [
            // ── Security headers — all routes (#543 enforced CSP lives in src/proxy.ts)
            {
                source: '/(.*)',
                headers: [
                    { key: 'X-Frame-Options', value: 'DENY' },
                    { key: 'X-Content-Type-Options', value: 'nosniff' },
                    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
                    { key: 'X-DNS-Prefetch-Control', value: 'on' },
                    { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
                    { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
                    // Content-Security-Policy is ENFORCED and injected per-request with a
                    // nonce by src/proxy.ts (#543). See frontend/src/lib/csp.ts.
                ],
            },
            // ── Cache-Control headers (#557) ─────────────────────────────────────────
            // Hashed static assets: immutable — content-addressable filenames change on
            // every build so browsers can cache indefinitely.
            {
                source: '/_next/static/(.*)',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'public, max-age=31536000, immutable',
                    },
                ],
            },
            // Public static files (images, fonts, favicon, etc.)
            {
                source: '/static/(.*)',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'public, max-age=31536000, immutable',
                    },
                ],
            },
            // API routes: never cache — always fetch fresh data
            {
                source: '/api/(.*)',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'no-store',
                    },
                ],
            },
            // HTML pages: revalidate on every request; CDN may serve stale for 60 s
            // while revalidating in the background (stale-while-revalidate).
            {
                source: '/((?!_next/static|_next/image|favicon.ico|api/).*)',
                headers: [
                    {
                        key: 'Cache-Control',
                        value: 'public, max-age=0, must-revalidate',
                    },
                ],
            },
        ];
    },
    async redirects() {
        return [
            // Existing redirects
            {
                source: '/ftl-checker',
                destination: '/tools/ftl-checker',
                permanent: true,
            },
            {
                source: '/walmart-readiness',
                destination: '/retailer-readiness',
                permanent: true,
            },
            {
                source: '/tools/exemption-qualifier',
                destination: '/tools/ftl-checker?step=exemptions',
                permanent: true,
            },
            {
                source: '/architecture',
                destination: '/security',
                permanent: true,
            },
            // HIGH #5 — Consolidate duplicate routes (UI Debug Audit 2026-03-19)
            // Canonical path for retailer readiness is /retailer-readiness (content lives there)
            // /tools/retailer-readiness redirects TO /retailer-readiness via page.tsx
            // (removed redirect that caused infinite loop with /tools/retailer-readiness/page.tsx)
            // Canonical path for settings is /dashboard/settings.
            // Only the bare /settings path is redirected. Sub-paths like /settings/users,
            // /settings/security, /settings/profile etc. have their own pages and must
            // NOT be redirected — the wildcard catch-all was incorrectly masking them.
            {
                source: '/settings',
                destination: '/dashboard/settings',
                permanent: true,
            },
            // Canonical path for the compliance landing is /dashboard/compliance.
            // The sub-pages under /compliance/* (labels, profile, snapshots,
            // status, traceability-plan) have their own content and are linked
            // from the dashboard header — the previous catch-all `/compliance/:path*`
            // redirect 301-ed every click to the bare /dashboard/compliance,
            // losing the sub-route and breaking navigation (#1183).
            // Only redirect the bare /compliance path.
            {
                source: '/compliance',
                destination: '/dashboard/compliance',
                permanent: true,
            },
            // /about page now exists — redirect removed
            // Keep the singular typo trap, but do not mask the real public
            // /developers page by redirecting it into the broken portal route.
            {
                source: '/developer',
                destination: '/developer/portal',
                permanent: true,
            },
        ];
    },
    async rewrites() {
        if (isStatic) return []; // Rewrites not supported in static export

        // ── Rewrites that coexist with /api/<service>/[...path]/route.ts handlers ──
        // Next.js "afterFiles" rewrites run before dynamic routes, so when an
        // external destination is set, the rewrite wins and the route handler
        // is bypassed. Any rewrite that shadows a service with its own auth-
        // checked handler (ingestion/compliance/controls/fsma/graph/review)
        // is a security hazard — it skips requireProxyAuth, validateProxySession,
        // and sanitizePath. Only keep rewrites for paths that have no handler.
        //
        // Removed 2026-04-17 (#1221):
        //   - /api/compliance/:path*    (shadowed by the compliance route handler)
        //
        // Filter out rewrites with undefined destinations — Vercel build may not
        // have INGESTION_SERVICE_URL env var set, and Next.js 16 treats
        // "undefined/:path*" as a fatal error.
        return [
            // External API surface (documented in docs/API_VERSIONING.md).
            // Keep as a rewrite — external callers use API-key auth, the frontend
            // auth-gate layers would reject them as missing cookies/session.
            ingestionUrl && {
                source: '/api/v1/ingestion/:path*',
                destination: `${ingestionUrl}/v1/ingestion/:path*`,
            },
            // Internal alias: /api/auth/* → /api/admin/auth/* so client code can
            // use the shorter path. Destination is a same-origin route handler,
            // so frontend auth layers still apply.
            {
                source: '/api/auth/:path*',
                destination: '/api/admin/auth/:path*',
            },
            // Proxy webhook ingestion to backend. External webhook senders
            // (Shopify/SafetyCulture/etc.) authenticate via HMAC signatures, so
            // the frontend auth-gate would reject them. The CSRF exempt list
            // (src/lib/csrf.ts) covers /api/v1/webhooks/ so middleware passes.
            // Destination keeps the /api prefix: the ingestion router in
            // services/ingestion/app/webhook_router_v2.py is mounted at
            // `/api/v1/webhooks`, so stripping /api here returns 404.
            ingestionUrl && {
                source: '/api/v1/webhooks/:path*',
                destination: `${ingestionUrl}/api/v1/webhooks/:path*`,
            },
            // API-03: proxy admin health endpoint for external monitoring.
            // Public, unauthenticated — no handler needed.
            apiGatewayUrl && {
                source: '/api/v1/health',
                destination: `${apiGatewayUrl}/health`,
            },
        ].filter(Boolean);
    },
}

const isProduction = process.env.VERCEL_ENV === 'production';

const sentryWebpackPluginOptions = {
    // Suppresses source map upload logs during build
    silent: true,

    // Only upload source maps in production builds (#25)
    widenClientFileUpload: isProduction,

    // Route Sentry requests through a Next.js rewrite to bypass ad blockers
    tunnelRoute: "/monitoring",

    // Hide source maps from client bundles
    hideSourceMaps: true,

    // Disable source map upload entirely for non-production builds
    disableServerWebpackPlugin: !isProduction,
    disableClientWebpackPlugin: !isProduction,
};

module.exports = withSentryConfig(nextConfig, sentryWebpackPluginOptions);
