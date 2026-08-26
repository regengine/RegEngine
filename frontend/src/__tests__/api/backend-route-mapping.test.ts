/**
 * Release-surface guards for the same-origin BFF catch-all routes.
 *
 * Controls/overlay, graph-routed FSMA aliases, and remediation are outside the
 * approved router inventory. Their handlers must return an empty 404 before
 * evaluating credentials or calling an upstream. Approved FSMA aliases still
 * proxy to the compliance service.
 */
import { NextRequest } from 'next/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-proxy', async () => {
    const actual = await vi.importActual<typeof import('@/lib/api-proxy')>('@/lib/api-proxy');
    return {
        ...actual,
        requireProxyAuth: vi.fn(() => null),
        validateProxySession: vi.fn(async () => null),
        getServerApiKey: vi.fn(() => 'server-key'),
    };
});

type CatchAllHandler = (
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) => Promise<Response>;

const COMPLIANCE = 'http://compliance.test';
const EXPORTED_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'] as const;
const CREDENTIAL_STATES = [
    { label: 'anonymous', credentialed: false },
    { label: 'credential-bearing', credentialed: true },
] as const;

const mockFetch = vi.fn();

function makeRequest(
    frontendPath: string,
    method = 'GET',
    credentialed = false,
): NextRequest {
    const headers = new Headers();
    if (credentialed) {
        headers.set('authorization', 'Bearer attacker-controlled-token');
        headers.set('x-api-key', 'attacker-api-key');
        headers.set('x-regengine-api-key', 'attacker-regengine-key');
        headers.set('x-admin-key', 'retired-admin-key');
        headers.set('cookie', '__Host-regengine_session=attacker-session');
    }
    return new NextRequest(`http://localhost${frontendPath}`, { method, headers });
}

function contextFor(frontendPath: string): { params: Promise<{ path: string[] }> } {
    const pathname = new URL(`http://localhost${frontendPath}`).pathname;
    return {
        params: Promise.resolve({ path: pathname.split('/').filter(Boolean).slice(2) }),
    };
}

async function expectExact404(
    handler: CatchAllHandler,
    frontendPath: string,
    method: string,
    credentialed: boolean,
): Promise<void> {
    const response = await handler(
        makeRequest(frontendPath, method, credentialed),
        contextFor(frontendPath),
    );

    expect(response.status).toBe(404);
    await expect(response.text()).resolves.toBe('');
    expect(mockFetch).not.toHaveBeenCalled();
}

async function targetUrlFor(
    handler: CatchAllHandler,
    frontendPath: string,
    credentialed = false,
): Promise<string> {
    mockFetch.mockResolvedValue(
        new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { 'content-type': 'application/json' },
        }),
    );
    await handler(makeRequest(frontendPath, 'GET', credentialed), contextFor(frontendPath));
    expect(mockFetch).toHaveBeenCalledTimes(1);
    return mockFetch.mock.calls[0][0] as string;
}

beforeEach(() => {
    vi.clearAllMocks();
    vi.resetModules();
    vi.stubGlobal('fetch', mockFetch);
    process.env.COMPLIANCE_SERVICE_URL = COMPLIANCE;
    process.env.NEXT_PUBLIC_INGESTION_URL = 'http://ingestion.test';
});

afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.COMPLIANCE_SERVICE_URL;
    delete process.env.NEXT_PUBLIC_INGESTION_URL;
});

describe('release-disabled controls aliases', () => {
    const cases = [
        ['GET', 'anonymous', false],
        ['GET', 'credential-bearing', true],
        ['HEAD', 'anonymous', false],
        ['HEAD', 'credential-bearing', true],
        ['POST', 'anonymous', false],
        ['POST', 'credential-bearing', true],
        ['PUT', 'anonymous', false],
        ['PUT', 'credential-bearing', true],
        ['PATCH', 'anonymous', false],
        ['PATCH', 'credential-bearing', true],
        ['DELETE', 'anonymous', false],
        ['DELETE', 'credential-bearing', true],
        ['OPTIONS', 'anonymous', false],
        ['OPTIONS', 'credential-bearing', true],
    ] as const;

    it.each(cases)(
        'returns exact 404 for %s with %s credentials',
        async (method, _label, credentialed) => {
            const controls = await import('@/app/api/controls/[...path]/route');
            const handler = controls[method] as CatchAllHandler;
            await expectExact404(handler, '/api/controls/controls/abc123', method, credentialed);
        },
    );
});

describe('release-disabled graph-routed FSMA aliases', () => {
    const graphAliases = [
        '/api/fsma/compliance/score',
        '/api/fsma/traceability/trace/forward/LOT-1',
        '/api/fsma/recall/readiness',
        '/api/fsma/science/mass-balance/LOT-1',
        '/api/fsma/metrics/dashboard',
        '/api/fsma/gaps/orphans',
        '/api/fsma/export/trace/LOT-1',
    ];
    const cases = EXPORTED_METHODS.flatMap((method) =>
        CREDENTIAL_STATES.flatMap(({ label, credentialed }) =>
            graphAliases.map((path) => [method, label, credentialed, path] as const),
        ),
    );

    it.each(cases)(
        'returns exact 404 for %s with %s credentials at %s',
        async (method, _label, credentialed, path) => {
            const fsma = await import('@/app/api/fsma/[...path]/route');
            const handler = fsma[method] as CatchAllHandler;
            await expectExact404(handler, path, method, credentialed);
        },
    );

    it.each([
        ['/api/fsma/checklists?include=items', `${COMPLIANCE}/checklists?include=items`],
        ['/api/fsma/industries', `${COMPLIANCE}/industries`],
    ])(
        'keeps approved compliance alias %s on the compliance service',
        async (frontendPath, expected) => {
            const { GET } = await import('@/app/api/fsma/[...path]/route');
            expect(await targetUrlFor(GET, frontendPath)).toBe(expected);
        },
    );

    it('never forwards the retired x-admin-key header on approved FSMA aliases', async () => {
        const { GET } = await import('@/app/api/fsma/[...path]/route');
        await targetUrlFor(GET, '/api/fsma/checklists', true);

        const init = mockFetch.mock.calls[0][1] as RequestInit;
        expect(new Headers(init.headers).has('x-admin-key')).toBe(false);
    });
});

describe('release-disabled remediation aliases', () => {
    const cases = EXPORTED_METHODS.flatMap((method) =>
        CREDENTIAL_STATES.map(({ label, credentialed }) =>
            [method, label, credentialed] as const,
        ),
    );

    it.each(cases)(
        'returns exact 404 for %s with %s credentials before ingestion fetch',
        async (method, _label, credentialed) => {
            const ingestion = await import('@/app/api/ingestion/[...path]/route');
            const handler = ingestion[method] as CatchAllHandler;
            await expectExact404(
                handler,
                '/api/ingestion/api/v1/remediation/manifests',
                method,
                credentialed,
            );
        },
    );
});
