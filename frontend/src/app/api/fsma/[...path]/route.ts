import { NextRequest } from 'next/server';
import { applyCookieCredentials, createJsonProxy, passthroughRequestHeaders } from '@/lib/proxy-factory';

// Proxy FSMA-204 API requests across two backend services based on the path.
//
// #2836 Every mapping below is pinned to a real backend mount point:
//
//   Graph service, mounted at /api/v1 (server/main.py:910
//   `app.include_router(graph_router, prefix="/api/v1", ...)`), sub-routers from
//   services/graph/app/routes.py:
//     :59  trace_router      prefix="/fsma/traceability"  -> /api/v1/fsma/traceability/*
//     :60  science_router    prefix="/fsma/science"       -> /api/v1/fsma/science/*
//     :61  recall_router     prefix="/fsma/recall"        -> /api/v1/fsma/recall/*
//     :62  metrics_router    prefix="/fsma/metrics"       -> /api/v1/fsma/metrics/*
//     :63  compliance_router prefix="/fsma/compliance"    -> /api/v1/fsma/compliance/*
//
//   `gaps` and `export/` are NOT top-level FSMA routes — they are endpoints on
//   the compliance sub-router (services/graph/app/routers/fsma/compliance.py):
//     :640 @router.get("/gaps")                    -> /api/v1/fsma/compliance/gaps
//     :681 @router.get("/gaps/orphans")            -> /api/v1/fsma/compliance/gaps/orphans
//     :741 @router.get("/export/gaps")             -> /api/v1/fsma/compliance/export/gaps
//     :419 @router.get("/export/trace/{tlc}")      -> /api/v1/fsma/compliance/export/trace/*
//     :550 @router.get("/export/recall-contacts/{tlc}")
//     :84  @router.get("/export/fda-request")
//     :185 @router.get("/export/epcis")
//   so they need the `compliance/` segment spliced in, which is what
//   GRAPH_COMPLIANCE_PATH_PREFIXES below does.
//
//   `drift/` is deliberately absent: there is NO drift router anywhere in the
//   backend. `grep -rn "/drift" services/ server/` returns zero results, and no
//   route decorator or APIRouter prefix mentions drift. The former 'drift/'
//   entry pointed at /api/v1/fsma/drift/* which has never existed. Do not add
//   it back without a real backend router to point it at.
//
//   Compliance service — services/compliance/app/routes.py:64 declares
//   `APIRouter(tags=["fsma-compliance"])` with NO prefix, and server/main.py:929
//   mounts it with no prefix either (`app.include_router(fsma_router, ...)`), so
//   its routes are /industries, /checklists, /checklists/{id} and
//   /v1/fsma/audit/spreadsheet. The previous `/fsma-204/` fallback segment is
//   registered by nothing (`grep -rn "fsma-204" services/ server/ --include=*.py`
//   matches only a JSON payload field in services/graph/app/fsma_metrics.py:350),
//   so it is dropped.

function guardUrl(envVar: string, fallback: string): string {
    const url = process.env[envVar] || process.env.NEXT_PUBLIC_API_BASE_URL;
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (url) {
        if (onVercel && url.includes('.railway.internal')) {
            console.warn(`[proxy/fsma] ${envVar} points to internal Railway URL; unreachable from Vercel.`);
            return '';
        }
        return url;
    }
    if (onVercel) {
        console.error(`[proxy/fsma] ${envVar} not configured; localhost is unreachable from Vercel`);
        return '';
    }
    return fallback;
}

const COMPLIANCE_URL = guardUrl('COMPLIANCE_SERVICE_URL', 'http://localhost:8500');
const GRAPH_SERVICE_URL = guardUrl('GRAPH_SERVICE_URL', 'http://localhost:8200');

// Paths that map 1:1 onto a /api/v1/fsma/<prefix> graph sub-router.
const GRAPH_PATH_PREFIXES = [
    'compliance/', 'traceability/', 'recall/', 'science/', 'metrics/',
];

// Paths that live on the graph compliance sub-router and therefore need the
// 'compliance/' segment inserted: /api/v1/fsma/compliance/<path>.
const GRAPH_COMPLIANCE_PATH_PREFIXES = [
    'gaps', 'export/',
];

function routesToGraphService(path: string): boolean {
    return GRAPH_PATH_PREFIXES.some(prefix => path.startsWith(prefix));
}

function routesToGraphCompliance(path: string): boolean {
    return GRAPH_COMPLIANCE_PATH_PREFIXES.some(prefix => path.startsWith(prefix));
}

export const dynamic = 'force-dynamic';

const { GET, POST, PUT, PATCH, DELETE } = createJsonProxy({
    serviceName: 'fsma',
    buildTargetUrl: (path, queryString) => {
        if (routesToGraphCompliance(path)) {
            if (!GRAPH_SERVICE_URL) return undefined;
            return `${GRAPH_SERVICE_URL}/api/v1/fsma/compliance/${path}${queryString}`;
        }
        if (routesToGraphService(path)) {
            if (!GRAPH_SERVICE_URL) return undefined;
            return `${GRAPH_SERVICE_URL}/api/v1/fsma/${path}${queryString}`;
        }
        if (!COMPLIANCE_URL) return undefined;
        return `${COMPLIANCE_URL}/${path}${queryString}`;
    },
    buildHeaders: (request: NextRequest) => {
        const headers = new Headers({ 'Content-Type': 'application/json' });
        passthroughRequestHeaders(headers, request, [
            'authorization',
            'x-regengine-api-key',
            'x-api-key',
            'x-tenant-id',
        ]);
        return applyCookieCredentials(headers, request);
    },
});

export { GET, POST, PUT, PATCH, DELETE };
