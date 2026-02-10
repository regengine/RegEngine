/** @type {import('next').NextConfig} */
// Last deployed: 2026-02-10
const nextConfig = {
    // output: 'export',
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

module.exports = nextConfig
