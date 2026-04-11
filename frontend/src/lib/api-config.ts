// API Configuration for RegEngine services

/** FSMA 204 is the only supported vertical. */
export const DEFAULT_VERTICAL = "food-safety" as const;

/** Default port for each backend service (used only for local dev fallback). */
const SERVICE_PORTS = { ingestion: 8002, graph: 8200, compliance: 8500, admin: 8400, nlp: 8100 } as const;

type ServiceName = keyof typeof SERVICE_PORTS;

/**
 * Server-side only — resolve backend URL from env vars with localhost fallback.
 * Use this in Next.js API routes instead of inline `|| 'http://localhost:XXXX'`.
 */
export function getServerServiceURL(service: ServiceName): string {
    const envMap: Record<ServiceName, string | undefined> = {
        ingestion: process.env.INGESTION_SERVICE_URL,
        graph: process.env.GRAPH_SERVICE_URL,
        compliance: process.env.COMPLIANCE_SERVICE_URL,
        admin: process.env.ADMIN_SERVICE_URL,
        nlp: process.env.NLP_SERVICE_URL,
    };
    const url = envMap[service] || process.env.NEXT_PUBLIC_API_BASE_URL;
    if (url) return url;

    if (process.env.VERCEL) {
        console.error(
            `[api-config] ${service.toUpperCase()}_SERVICE_URL not configured — localhost is unreachable from Vercel`,
        );
        return '';
    }
    return `http://localhost:${SERVICE_PORTS[service]}`;
}

export function isStaticExport(): boolean {
    return typeof window !== 'undefined' &&
        process.env.NEXT_PUBLIC_OUTPUT_MODE === 'export';
}

function localFallback(service: ServiceName): string {
    return `http://localhost:${SERVICE_PORTS[service]}`;
}

export function getServiceURL(service: ServiceName): string {
    const isClient = typeof window !== 'undefined';

    const gatewayUrl = isClient ? process.env.NEXT_PUBLIC_API_BASE_URL : null;

    if (!isClient) {
        return getServerServiceURL(service);
    }

    if (service === 'admin') {
        return gatewayUrl ? `${gatewayUrl}/admin` : '/api/admin';
    }

    if (service === 'ingestion') {
        return '/api/ingestion';
    }

    if (service === 'compliance') {
        return '/api/compliance';
    }

    if (service === 'graph') {
        return '/api/graph';
    }

    if (gatewayUrl) {
        return `${gatewayUrl}/${service}`;
    }

    const clientEnvMap: Record<ServiceName, string | undefined> = {
        ingestion: process.env.NEXT_PUBLIC_INGESTION_URL,
        graph: process.env.NEXT_PUBLIC_GRAPH_URL,
        compliance: process.env.NEXT_PUBLIC_COMPLIANCE_URL,
        admin: process.env.NEXT_PUBLIC_ADMIN_URL,
        nlp: process.env.NEXT_PUBLIC_NLP_URL,
    };
    return clientEnvMap[service] || localFallback(service);
}
