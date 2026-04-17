import { NextRequest } from 'next/server';
import { createJsonProxy } from '@/lib/proxy-factory';

// Proxy FSMA-204 API requests across two backend services based on the path:
//   - Graph service       — compliance/, traceability/, recall/, science/, metrics/,
//                           drift/, gaps, export/ (live data queries)
//   - Compliance service  — everything else (wizard / applicability / exemptions)

function guardUrl(envVar: string, fallback: string): string {
    const url = process.env[envVar] || process.env.NEXT_PUBLIC_API_BASE_URL;
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (url) {
        if (onVercel && url.includes('.railway.internal')) {
            console.warn(`[proxy/fsma] ${envVar} points to internal Railway URL — unreachable from Vercel.`);
            return '';
        }
        return url;
    }
    if (onVercel) {
        console.error(`[proxy/fsma] ${envVar} not configured — localhost is unreachable from Vercel`);
        return '';
    }
    return fallback;
}

const COMPLIANCE_URL = guardUrl('COMPLIANCE_SERVICE_URL', 'http://localhost:8500');
const GRAPH_SERVICE_URL = guardUrl('GRAPH_SERVICE_URL', 'http://localhost:8200');

const GRAPH_PATH_PREFIXES = [
    'compliance/', 'traceability/', 'recall/', 'science/',
    'metrics/', 'drift/', 'gaps', 'export/',
];

function routesToGraphService(path: string): boolean {
    return GRAPH_PATH_PREFIXES.some(prefix => path.startsWith(prefix));
}

export const dynamic = 'force-dynamic';

const { GET, POST, PUT, PATCH, DELETE } = createJsonProxy({
    serviceName: 'fsma',
    buildTargetUrl: (path, queryString) => {
        if (routesToGraphService(path)) {
            if (!GRAPH_SERVICE_URL) return undefined;
            return `${GRAPH_SERVICE_URL}/api/v1/fsma/${path}${queryString}`;
        }
        if (!COMPLIANCE_URL) return undefined;
        return `${COMPLIANCE_URL}/fsma-204/${path}${queryString}`;
    },
    buildHeaders: (request: NextRequest) => {
        // FSMA proxy reads credentials from cookies first, falls back to incoming
        // headers, then to the server env var — preserving the pre-refactor
        // behavior which differed from the other JSON proxies.
        const apiKey = request.cookies.get('re_api_key')?.value
            || request.headers.get('X-RegEngine-API-Key')
            || process.env.REGENGINE_API_KEY
            || '';
        const tenantId = request.cookies.get('re_tenant_id')?.value
            || request.headers.get('X-Tenant-ID')
            || '';
        const headers = new Headers({
            'Content-Type': 'application/json',
            'X-RegEngine-API-Key': apiKey,
        });
        if (tenantId) headers.set('X-Tenant-ID', tenantId);
        return headers;
    },
});

export { GET, POST, PUT, PATCH, DELETE };
