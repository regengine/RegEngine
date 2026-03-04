// API Configuration for RegEngine services

export function isStaticExport(): boolean {
    // Detect if we are running in a static/mobile context (e.g. Capacitor)
    return typeof window !== 'undefined' &&
        ((window as any).Capacitor !== undefined ||
            process.env.NEXT_PUBLIC_OUTPUT_MODE === 'export');
}

export function getServiceURL(service: 'ingestion' | 'graph' | 'compliance' | 'admin' | 'opportunity'): string {
    const isClient = typeof window !== 'undefined';

    // In production static export (Capacitor), we MUST use absolute URLs
    // We prefer a unified API gateway if NEXT_PUBLIC_API_BASE_URL is set
    const gatewayUrl = isClient ? process.env.NEXT_PUBLIC_API_BASE_URL : null;

    if (!isClient) {
        // Server-side (Standard Next.js Server Components or SSR)
        switch (service) {
            case 'ingestion':
                return process.env.INGESTION_SERVICE_URL || 'http://localhost:8002';
            case 'graph':
                return process.env.GRAPH_SERVICE_URL || 'http://localhost:8200';
            case 'compliance':
                return process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';
            case 'admin':
                return process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';
            case 'opportunity':
                return process.env.OPPORTUNITY_SERVICE_URL || 'http://localhost:8300';
        }
    }

    if (service === 'admin') {
        if (!isStaticExport()) {
            return '/api/admin';
        }
        if (gatewayUrl) {
            return `${gatewayUrl}/admin`;
        }
        return process.env.NEXT_PUBLIC_ADMIN_URL || 'http://localhost:8400';
    }

    // Client-side / Static Export
    if (gatewayUrl) {
        // If a gateway is provided (e.g. Nginx proxy), use it for non-admin services
        // The gateway should route based on paths like /ingestion, /graph, etc.
        return `${gatewayUrl}/${service}`;
    }

    switch (service) {
        case 'ingestion':
            return process.env.NEXT_PUBLIC_INGESTION_URL || 'http://localhost:8002';
        case 'graph':
            return process.env.NEXT_PUBLIC_GRAPH_URL || 'http://localhost:8200';
        case 'opportunity':
            return process.env.NEXT_PUBLIC_OPPORTUNITY_URL || 'http://localhost:8300';
        case 'compliance':
            return process.env.NEXT_PUBLIC_COMPLIANCE_URL || 'http://localhost:8500';
        default:
            return process.env.NEXT_PUBLIC_ADMIN_URL || 'http://localhost:8400';
    }
}
