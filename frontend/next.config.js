/** @type {import('next').NextConfig} */
// Last deployed: 2026-02-13
const { withSentryConfig } = require("@sentry/nextjs");

const nextConfig = {
    output: 'export',
    images: {
        // unoptimized: true, // Enabled for production optimization (requires sharp)
    },
    // Rewrites are NOT supported in static export mode.
    // For mobile app, we must point API clients to the absolute URL.
    async redirects() {
        return [
            {
                source: '/walmart-readiness',
                destination: '/retailer-readiness',
                permanent: true,
            },
            {
                source: '/walmart-suppliers',
                destination: '/retailer-readiness',
                permanent: true,
            },
        ];
    },
    async rewrites() {
        return [
            // Proxy ingestion routes to ingestion service
            {
                source: '/api/v1/ingestion/:path*',
                destination: 'http://localhost:8002/v1/ingestion/:path*',
            },
            // Proxy ingest routes to ingestion service
            {
                source: '/api/v1/ingest/:path*',
                destination: 'http://localhost:8002/v1/ingest/:path*',
            },
            // Proxy Admin Routes
            {
                source: '/api/admin/:path*',
                destination: 'http://localhost:8400/:path*',
            },
            // Proxy Auth Routes (assuming they are at root of admin service)
            {
                source: '/api/auth/:path*',
                destination: 'http://localhost:8400/auth/:path*',
            },
            // Proxy Graph/FSMA
            {
                source: '/api/fsma/:path*',
                destination: 'http://localhost:8200/v1/:path*',
            },
            // Proxy Compliance
            {
                source: '/api/compliance/:path*',
                destination: 'http://localhost:8500/:path*',
            },
        ]
    },
}

const withPWA = require("next-pwa")({
    dest: "public",
    disable: process.env.NODE_ENV === "development",
    register: true,
    skipWaiting: true,
});

// Compose: PWA → Sentry → Next.js
const sentryWebpackPluginOptions = {
    // Suppresses source map upload logs during build
    silent: true,

    // Upload source maps for better stack traces
    widenClientFileUpload: true,

    // Route Sentry requests through a Next.js rewrite to bypass ad blockers
    tunnelRoute: "/monitoring",

    // Disable Sentry telemetry during build
    disableLogger: true,

    // Automatically tree-shake Sentry logger in production
    hideSourceMaps: true,
};

module.exports = withSentryConfig(withPWA(nextConfig), sentryWebpackPluginOptions);

