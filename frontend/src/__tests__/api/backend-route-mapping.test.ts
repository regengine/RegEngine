/**
 * Backend route-mapping guards for the same-origin BFF proxies.
 *
 * These proxies translate a frontend path into a backend URL. When the
 * translation drifts from where the backend actually mounts its router, every
 * request 404s — silently, because the pages consuming them did not check
 * response.ok. Each expectation below is pinned to a real mount point in the
 * Python source; the comment names the file and line so a backend move breaks
 * a test with a pointer to what to re-check.
 *
 *   #2835 controls — services/admin/app/api_overlay.py:55
 *                      router = APIRouter(prefix="/v1/overlay", tags=["overlay"])
 *                    :123 @router.post("/controls")   :168 @router.get("/controls")
 *                    mounted prefix-free at server/main.py:794.
 *                    Was built as /v1/admin/... — 404 on every call.
 *
 *   #2836 fsma     — services/graph/app/routes.py:59-63 mounts the FSMA
 *                    sub-routers, and server/main.py:869 mounts graph at
 *                    prefix="/api/v1". `gaps` and `export/` are endpoints on
 *                    the compliance sub-router
 *                    (services/graph/app/routers/fsma/compliance.py:624, :661,
 *                    :717), NOT top-level FSMA routes, so they need the
 *                    compliance/ segment. There is NO drift router anywhere in
 *                    the backend, and no /fsma-204 prefix is registered by
 *                    anything.
 */
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import type { NextRequest } from 'next/server';

vi.mock('@/lib/api-proxy', async () => {
    const actual = await vi.importActual<typeof import('@/lib/api-proxy')>('@/lib/api-proxy');
    return {
        ...actual,
        requireProxyAuth: vi.fn(() => null),
        validateProxySession: vi.fn(async () => null),
        getServerApiKey: vi.fn(() => 'server-key'),
    };
});

const GRAPH = 'http://graph.test';
const COMPLIANCE = 'http://compliance.test';
const ADMIN = 'http://admin.test';

function makeRequest(url: string): NextRequest {
    return {
        method: 'GET',
        url,
        nextUrl: new URL(url),
        headers: new Headers(),
        cookies: { get: () => undefined, getAll: () => [] },
        json: async () => ({}),
        text: async () => '',
    } as unknown as NextRequest;
}

const mockFetch = vi.fn();

/** Drive a catch-all proxy GET and return the backend URL it fetched. */
async function targetUrlFor(
    handler: (req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) => Promise<unknown>,
    frontendPath: string,
): Promise<string> {
    mockFetch.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({}),
    });
    const url = `http://localhost${frontendPath}`;
    const pathParts = new URL(url).pathname.split('/').filter(Boolean).slice(2);
    await handler(makeRequest(url), { params: Promise.resolve({ path: pathParts }) });
    expect(mockFetch).toHaveBeenCalled();
    return mockFetch.mock.calls[0][0] as string;
}

beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
    vi.stubGlobal('fetch', mockFetch);
    process.env.GRAPH_SERVICE_URL = GRAPH;
    process.env.COMPLIANCE_SERVICE_URL = COMPLIANCE;
    process.env.ADMIN_SERVICE_URL = ADMIN;
});

afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.GRAPH_SERVICE_URL;
    delete process.env.COMPLIANCE_SERVICE_URL;
    delete process.env.ADMIN_SERVICE_URL;
});

describe('#2835 controls proxy targets the overlay router', () => {
    it('maps /api/controls/controls to /v1/overlay/controls', async () => {
        const { GET } = await import('@/app/api/controls/[...path]/route');
        const target = await targetUrlFor(GET!, '/api/controls/controls');
        expect(target).toBe(`${ADMIN}/v1/overlay/controls`);
        // The old /v1/admin/ prefix is registered by nothing.
        expect(target).not.toContain('/v1/admin/');
    });

    it('maps a single control to /v1/overlay/controls/{id}', async () => {
        const { GET } = await import('@/app/api/controls/[...path]/route');
        const target = await targetUrlFor(GET!, '/api/controls/controls/abc123');
        expect(target).toBe(`${ADMIN}/v1/overlay/controls/abc123`);
    });
});

describe('#2836 fsma proxy routes each path to its real backend mount', () => {
    // gaps + export/ live on the graph COMPLIANCE sub-router.
    it.each([
        ['/api/fsma/gaps', `${GRAPH}/api/v1/fsma/compliance/gaps`],
        ['/api/fsma/gaps/orphans', `${GRAPH}/api/v1/fsma/compliance/gaps/orphans`],
        ['/api/fsma/export/gaps', `${GRAPH}/api/v1/fsma/compliance/export/gaps`],
        ['/api/fsma/export/trace/LOT-1', `${GRAPH}/api/v1/fsma/compliance/export/trace/LOT-1`],
    ])('maps %s to %s', async (frontendPath, expected) => {
        const { GET } = await import('@/app/api/fsma/[...path]/route');
        expect(await targetUrlFor(GET!, frontendPath)).toBe(expected);
    });

    // Sub-routers that ARE mounted directly under /api/v1/fsma.
    it.each([
        ['/api/fsma/traceability/trace/forward/LOT-1', `${GRAPH}/api/v1/fsma/traceability/trace/forward/LOT-1`],
        ['/api/fsma/metrics/dashboard', `${GRAPH}/api/v1/fsma/metrics/dashboard`],
        ['/api/fsma/compliance/score', `${GRAPH}/api/v1/fsma/compliance/score`],
        ['/api/fsma/recall/readiness', `${GRAPH}/api/v1/fsma/recall/readiness`],
        ['/api/fsma/science/mass-balance/LOT-1', `${GRAPH}/api/v1/fsma/science/mass-balance/LOT-1`],
    ])('maps %s to %s', async (frontendPath, expected) => {
        const { GET } = await import('@/app/api/fsma/[...path]/route');
        expect(await targetUrlFor(GET!, frontendPath)).toBe(expected);
    });

    it('never emits the unregistered /fsma-204/ prefix', async () => {
        const { GET } = await import('@/app/api/fsma/[...path]/route');
        const target = await targetUrlFor(GET!, '/api/fsma/checklists');
        expect(target).not.toContain('/fsma-204/');
        // services/compliance/app/routes.py:64 declares APIRouter with no
        // prefix and server/main.py:887 mounts it with none either.
        expect(target).toBe(`${COMPLIANCE}/checklists`);
    });

    it('does not route drift to a graph FSMA path that does not exist', async () => {
        // No drift router exists in services/ or server/. The proxy must not
        // fabricate /api/v1/fsma/drift/*; see #2837 for the UI-side handling.
        const { GET } = await import('@/app/api/fsma/[...path]/route');
        const target = await targetUrlFor(GET!, '/api/fsma/drift/health');
        expect(target).not.toBe(`${GRAPH}/api/v1/fsma/drift/health`);
    });

    it('preserves the query string', async () => {
        const { GET } = await import('@/app/api/fsma/[...path]/route');
        const target = await targetUrlFor(GET!, '/api/fsma/gaps?limit=50');
        expect(target).toBe(`${GRAPH}/api/v1/fsma/compliance/gaps?limit=50`);
    });
});
