// API Configuration for RegEngine services

export function getServiceURL(service: 'ingestion' | 'graph' | 'compliance' | 'admin' | 'opportunity'): string {
    if (typeof window === 'undefined') {
        // Server-side - connect directly to backend services
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

    // Client-side - Always use direct backend URLs
    // Note: Static export mode (output: 'export') doesn't support Next.js rewrites
    // so we must connect directly to backend services
    switch (service) {
        case 'ingestion':
            return 'http://localhost:8002';
        case 'admin':
            return 'http://localhost:8400';
        case 'graph':
            return 'http://localhost:8200';
        case 'opportunity':
            return 'http://localhost:8300';
        case 'compliance':
            return 'http://localhost:8500';
        default:
            return 'http://localhost:8400';
    }
}

