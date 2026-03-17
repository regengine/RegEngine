/** @type {import('next').NextConfig} */
// Last deployed: 2026-02-13
const { withSentryConfig } = require("@sentry/nextjs");
const createNextIntlPlugin = require('next-intl/plugin');
const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

const isStatic = process.env.REGENGINE_DEPLOY_MODE === 'static';
const apiGatewayUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost';
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
                source: '/architecture',
                destination: '/security',
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
        ]
    },
}

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

module.exports = withSentryConfig(withNextIntl(nextConfig), sentryWebpackPluginOptions);
