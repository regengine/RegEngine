/** @type {import('next').NextConfig} */
// Last deployed: 2026-02-13
const { withSentryConfig } = require("@sentry/nextjs");

const isStatic = process.env.REGENGINE_DEPLOY_MODE === 'static';
const apiGatewayUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost';

const nextConfig = {
    output: isStatic ? 'export' : undefined,
    eslint: {
        ignoreDuringBuilds: true,
    },
    images: {
        unoptimized: isStatic,
    },
    async redirects() {
        return [
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
                source: '/tools/supply-chain-explorer',
                destination: '/demo/supply-chains',
                permanent: true,
            },
        ];
    },
    async rewrites() {
        if (isStatic) return []; // Rewrites not supported in static export

        return [
            {
                source: '/api/v1/ingestion/:path*',
                destination: `${apiGatewayUrl}:8002/v1/ingestion/:path*`,
            },
            {
                source: '/api/admin/:path*',
                destination: `${apiGatewayUrl}:8400/:path*`,
            },
            {
                source: '/api/auth/:path*',
                destination: `${apiGatewayUrl}:8400/auth/:path*`,
            },
            {
                source: '/api/fsma/:path*',
                destination: `${apiGatewayUrl}:8200/v1/:path*`,
            },
            {
                source: '/api/compliance/:path*',
                destination: `${apiGatewayUrl}:8500/:path*`,
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

    // Automatically tree-shake Sentry logger in production
    hideSourceMaps: true,
};

module.exports = withSentryConfig(withPWA(nextConfig), sentryWebpackPluginOptions);
