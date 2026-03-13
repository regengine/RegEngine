// API Configuration for RegEngine services

/** FSMA 204 is the only supported vertical. */
export const DEFAULT_VERTICAL = "food-safety" as const;

export function isStaticExport(): boolean {
    // Detect if we are running in a static/mobile context (e.g. Capacitor)
    return typeof window !== 'undefined' &&
        ((window as any).Capacitor !== undefined ||
            process.env.NEXT_PUBLIC_OUTPUT_MODE === 'export');
}

export function getServiceURL(service: 'ingestion' | 'graph' | 'compliance' | 'admin' | 'nlp'): string {
    const isClient = typeof window !== 'undefined';
    const isCapacitorClient = isClient && (window as any).Capacitor !== undefined;

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
            case 'nlp':
                return process.env.NLP_SERVICE_URL || 'http://localhost:8100';
        }
    }

    if (service === 'admin') {
        // On web, always prefer same-origin proxy to avoid CORS and domain drift issues.
        if (!isCapacitorClient) {
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
        case 'compliance':
            return process.env.NEXT_PUBLIC_COMPLIANCE_URL || 'http://localhost:8500';
        case 'nlp':
            return process.env.NEXT_PUBLIC_NLP_URL || 'http://localhost:8100';
        default:
            return process.env.NEXT_PUBLIC_ADMIN_URL || 'http://localhost:8400';
    }
}
