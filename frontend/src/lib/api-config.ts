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

    // Client-side - use NEXT_PUBLIC_ env vars if available, else localhost
    switch (service) {
        case 'ingestion':
            return process.env.NEXT_PUBLIC_INGESTION_URL || 'http://localhost:8002';
        case 'admin':
            return process.env.NEXT_PUBLIC_ADMIN_URL || 'http://localhost:8400';
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

