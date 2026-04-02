/** @type {import('next').NextConfig} */
// Last deployed: 2026-02-13
const { withSentryConfig } = require("@sentry/nextjs");

const isStatic = process.env.REGENGINE_DEPLOY_MODE === 'static';
const apiGatewayUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
if (!apiGatewayUrl && !isStatic) {
    throw new Error('NEXT_PUBLIC_API_BASE_URL is not set — configure it in your environment or Vercel project settings');
}
const ingestionUrl = process.env.INGESTION_SERVICE_URL || `${apiGatewayUrl}:8002`;
const complianceUrl = process.env.COMPLIANCE_SERVICE_URL || `${apiGatewayUrl}:8500`;

const nextConfig = {
    output: isStatic ? 'export' : undefined,
    eslint: {
        ignoreDuringBuilds: true,
    },
    images: {
        unoptimized: isStatic,
    },
    async headers() {
        return [
            {
                source: '/(.*)',
                headers: [
                    { key: 'X-Frame-Options', value: 'DENY' },
                    { key: 'X-Content-Type-Options', value: 'nosniff' },
                    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
                    { key: 'X-DNS-Prefetch-Control', value: 'on' },
                    { key: 'Strict-Transport-Security', value: 'max-age=63072000; includeSubDomains; preload' },
                    { key: 'Permissions-Policy', value: 'camera=(), microphone=(), geolocation=()' },
                    // CSP in report-only mode — identifies violations without breaking the app.
                    // Next.js uses inline scripts for hydration; enforcing mode requires nonce support.
                    {
                        key: 'Content-Security-Policy-Report-Only',
                        value: [
                            "default-src 'self'",
                            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
                            "style-src 'self' 'unsafe-inline'",
                            "img-src 'self' data: blob: https:",
                            "font-src 'self'",
                            "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://*.railway.app https://*.vercel.app https://*.sentry.io",
                            "frame-ancestors 'none'",
                            "base-uri 'self'",
                            "form-action 'self'",
                        ].join('; '),
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
            // Canonical path for settings is /dashboard/settings
            {
                source: '/settings',
                destination: '/dashboard/settings',
                permanent: true,
            },
            {
                source: '/settings/:path*',
                destination: '/dashboard/settings',
                permanent: true,
            },
            // Canonical path for compliance is /dashboard/compliance
            {
                source: '/compliance',
                destination: '/dashboard/compliance',
                permanent: true,
            },
            {
                source: '/compliance/:path*',
                destination: '/dashboard/compliance',
                permanent: true,
            },
            // /about → /contact (founder info lives on contact page)
            {
                source: '/about',
                destination: '/contact',
                permanent: true,
            },
            // /developer and /developers → /developer/portal (fix 404s)
            {
                source: '/developer',
                destination: '/developer/portal',
                permanent: true,
            },
            {
                source: '/developers',
                destination: '/developer/portal',
                permanent: true,
            },
        ];
    },
    async rewrites() {
        if (isStatic) return []; // Rewrites not supported in static export

        return [
            {
                source: '/api/v1/ingestion/:path*',
                destination: `${ingestionUrl}/v1/ingestion/:path*`,
            },
            {
                source: '/api/auth/:path*',
                destination: '/api/admin/auth/:path*',
            },
            {
                source: '/api/compliance/:path*',
                destination: `${complianceUrl}/:path*`,
            },
            // Proxy webhook ingestion to backend (bypasses Next.js CSRF)
            {
                source: '/api/v1/webhooks/:path*',
                destination: `${ingestionUrl}/v1/webhooks/:path*`,
            },
            // API-03: Proxy admin health endpoint for external monitoring
            {
                source: '/api/v1/health',
                destination: `${apiGatewayUrl}/health`,
            },
        ]
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
