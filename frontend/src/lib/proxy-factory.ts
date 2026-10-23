/**
 * Proxy factory — shared scaffolding for Next.js catch-all proxy route
 * handlers (the files under src/app/api/<service>/[...path]/route.ts).
 *
 * The frontend fronts several backend services (admin, ingestion, compliance,
 * graph, fsma, controls, review). Each route handler used to duplicate the
 * same preflight + sanitize + forward pipeline, and drift between copies
 * produced at least one security bug (#1152). This module exposes two factory
 * functions that each proxy configures with just its service-specific bits.
 *
 * Two shapes are supported:
 *
 *   - createJsonProxy:    buffers the request/response body as JSON. Used by
 *                         services that return structured JSON responses and
 *                         don't need streaming or multi-target fallback.
 *
 *   - createStreamProxy:  streams the body both directions, supports multiple
 *                         upstream base URLs with retry-on-error. Used by the
 *                         admin and ingestion proxies which can forward large
 *                         uploads/downloads and need Vercel-to-Railway fallback.
 *
 * Both share the same preflight: static-mode guard, requireProxyAuth,
 * validateProxySession, sanitizePath, query string capture.
 */

import { NextRequest, NextResponse } from 'next/server';
import {
    sanitizePath,
    validateUuid,
    proxyError,
    requireProxyAuth,
    validateProxySession,
    staticExportGuard,
    isCookieManagedCredentialHeader,
    isUsableCallerCredential,
    hasSupabaseSessionCookies,
} from './api-proxy';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS';

const DEFAULT_METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const METHODS_WITHOUT_BODY: ReadonlySet<HttpMethod> = new Set(['GET', 'OPTIONS']);

/** Reject a credential-bearing upstream redirect without reflecting Location. */
export function rejectUpstreamRedirect(
    response: Pick<Response, 'status'>,
    serviceName: string,
): NextResponse | null {
    if (response.status < 300 || response.status >= 400) return null;

    console.error(`[proxy/${serviceName}] upstream redirect refused`);
    return NextResponse.json(
        { error: `${serviceName} upstream redirect refused` },
        { status: 502 },
    );
}

// ---------------------------------------------------------------------------
// Handler export shape
// ---------------------------------------------------------------------------

export type ProxyHandler = (
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) => Promise<NextResponse>;

export interface MethodHandlers {
    GET?: ProxyHandler;
    POST?: ProxyHandler;
    PUT?: ProxyHandler;
    PATCH?: ProxyHandler;
    DELETE?: ProxyHandler;
    OPTIONS?: ProxyHandler;
}

function buildMethodHandlers(
    methods: HttpMethod[],
    inner: (request: NextRequest, pathParts: string[], method: HttpMethod) => Promise<NextResponse>,
): MethodHandlers {
    const result: MethodHandlers = {};
    for (const method of methods) {
        result[method] = async (request, { params }) => {
            const { path } = await params;
            return inner(request, path, method);
        };
    }
    return result;
}

// ---------------------------------------------------------------------------
// JSON proxy (compliance, graph, controls, review, fsma)
// ---------------------------------------------------------------------------

export interface JsonProxyConfig {
    /** Label used in log lines (e.g. "compliance"). */
    serviceName: string;
    /** Build the upstream URL from the sanitized path + query string.
     *  Return undefined to respond with a 503 "backend not configured" error. */
    buildTargetUrl: (path: string, queryString: string, request: NextRequest) => string | undefined;
    /** Build outbound headers. Called per-request. */
    buildHeaders: (request: NextRequest, path: string) => Headers;
    /** Optional post-auth transport metadata hook. */
    prepareHeaders?: (
        headers: Headers,
        request: NextRequest,
        path: string,
    ) => NextResponse | null | Promise<NextResponse | null>;
    /** Optional: transform a parsed JSON body before forwarding. */
    transformBody?: (body: unknown, path: string) => unknown;
    /** Optional: synthesize a body when the incoming request has none. */
    defaultBody?: (path: string) => unknown;
    /** Methods to export. Defaults to GET/POST/PUT/PATCH/DELETE. */
    methods?: HttpMethod[];
}

export function createJsonProxy(config: JsonProxyConfig): MethodHandlers {
    const handler = async (
        request: NextRequest,
        pathParts: string[],
        method: HttpMethod,
    ): Promise<NextResponse> => {
        try {
            const staticResponse = staticExportGuard(config.serviceName);
            if (staticResponse) return staticResponse;

            const authError = requireProxyAuth(request);
            const requireSupabaseSession = Boolean(authError && hasSupabaseSessionCookies(request));
            if (authError && !requireSupabaseSession) return authError;

            const sessionError = await validateProxySession(request, { requireSupabaseSession });
            if (sessionError) return sessionError;

            const path = sanitizePath(pathParts);
            if (!path) {
                return proxyError('Invalid path', 400, { code: 'INVALID_PATH' });
            }

            const queryString = new URL(request.url).search;
            const targetUrl = config.buildTargetUrl(path, queryString, request);
            if (!targetUrl) {
                console.error(`[proxy/${config.serviceName}] 503: backend not configured`);
                return proxyError(`${config.serviceName} backend not configured`, 503);
            }

            const headers = config.buildHeaders(request, path);
            const headerError = await config.prepareHeaders?.(headers, request, path);
            if (headerError) return headerError;
            // Never let fetch forward caller or scoped service credentials to
            // a redirect target. Undici strips some standard auth headers but
            // preserves custom X-RegEngine-API-Key values cross-origin.
            const fetchOptions: RequestInit = { method, headers, redirect: 'manual' };

            if (!METHODS_WITHOUT_BODY.has(method)) {
                let body: unknown = undefined;
                let hadRawBody = false;
                try {
                    body = await request.json();
                    hadRawBody = true;
                } catch {
                    /* no body or invalid JSON */
                }
                if (hadRawBody && config.transformBody) {
                    body = config.transformBody(body, path);
                } else if (!hadRawBody && config.defaultBody) {
                    body = config.defaultBody(path);
                }
                if (body !== undefined) {
                    fetchOptions.body = JSON.stringify(body);
                }
            }

            const response = await fetch(targetUrl, fetchOptions);
            if (response.status >= 300 && response.status < 400) {
                console.error(`[proxy/${config.serviceName}] redirect refused`);
                return proxyError(`${config.serviceName} request failed`, 502);
            }
            const data = await response.json().catch(() => ({} as unknown));

            if (!response.ok) {
                const detail = extractDetail(data);
                if (response.status >= 500) {
                    console.error(`[proxy/${config.serviceName}] ${response.status}: upstream request failed`, {
                        targetUrl,
                        detail: data,
                    });
                    return proxyError(`${config.serviceName} request failed`, response.status);
                }
                return NextResponse.json(
                    { error: detail ?? `${config.serviceName} request failed` },
                    { status: response.status },
                );
            }

            if (process.env.NODE_ENV !== 'production') {
                console.warn(`[proxy/${config.serviceName}] ${method} ${path} → ${response.status}`);
            }
            return NextResponse.json(data);
        } catch (error: unknown) {
            console.error(`[proxy/${config.serviceName}] 500: proxy request failed`, { error });
            return proxyError(`${config.serviceName} request failed`, 500);
        }
    };

    return buildMethodHandlers(config.methods ?? DEFAULT_METHODS, handler);
}

function extractDetail(data: unknown): string | null {
    if (data && typeof data === 'object' && 'detail' in data) {
        const detail = (data as { detail: unknown }).detail;
        if (typeof detail === 'string') return detail;
    }
    return null;
}

// ---------------------------------------------------------------------------
// Stream proxy (admin, ingestion)
// ---------------------------------------------------------------------------

export interface StreamProxyConfig {
    /** Label used in log lines. */
    serviceName: string;
    /** Resolve ordered list of upstream bases to try. Empty array → 503. */
    resolveTargetBases: () => string[];
    /** Build outbound headers. */
    buildHeaders: (request: NextRequest) => Headers;
    /** Optional post-auth hook to mutate/validate outbound headers before fetch. */
    prepareHeaders?: (
        headers: Headers,
        request: NextRequest,
        path: string,
    ) => NextResponse | null | Promise<NextResponse | null>;
    /** Run prepareHeaders for intentionally unauthenticated paths as well. */
    prepareHeadersForUnauthenticatedPaths?: boolean;
    /** Upstream response headers to pass through to the client. */
    responseHeaderPassthrough?: string[];
    /** Methods to export. Defaults to GET/POST/PUT/PATCH/DELETE/OPTIONS. */
    methods?: HttpMethod[];
    /** Should we retry this response against the next target base? */
    shouldRetry?: (response: Response, path: string) => boolean;
    /** Optional: paths that skip the auth + session checks (used for passwordless auth starts). */
    isUnauthenticatedPath?: (path: string) => boolean;
    /** Maximum request body bytes buffered for retryable stream proxy forwarding. */
    maxBodyBytes?: number;
}

const DEFAULT_STREAM_RESPONSE_HEADERS = [
    'content-type',
    'content-disposition',
    'cache-control',
    'x-fda-record-count',
];
const AUTH_BROWSER_NONCE_COOKIE = 'regengine_auth_browser_nonce';
const OPAQUE_SESSION_COOKIE = '__Host-regengine_session';
const RETIRED_CREDENTIAL_HEADERS = new Set(['x-admin-key']);

const VERCEL_PRIVATE_DNS_ERROR = 'DNS_HOSTNAME_RESOLVED_PRIVATE';
const SYSTEM_TENANT_ID = '00000000-0000-0000-0000-000000000001';
const DEFAULT_STREAM_PROXY_MAX_BODY_BYTES = 100 * 1024 * 1024;

class ProxyRequestBodyTooLargeError extends Error {
    constructor(readonly maxBytes: number) {
        super(`Request body too large (max ${maxBytes} bytes)`);
        this.name = 'ProxyRequestBodyTooLargeError';
    }
}

function defaultShouldRetry(response: Response): boolean {
    const header = response.headers.get('x-vercel-error') || '';
    return header.includes(VERCEL_PRIVATE_DNS_ERROR);
}

async function readUpstreamErrorForLog(response: Response): Promise<string | undefined> {
    try {
        const text = await response.clone().text();
        return text ? text.slice(0, 1000) : undefined;
    } catch {
        return undefined;
    }
}

async function readRequestBodyWithLimit(
    request: NextRequest,
    maxBytes: number,
): Promise<ArrayBuffer | undefined> {
    const contentLength = Number(request.headers.get('content-length') || 0);
    if (Number.isFinite(contentLength) && contentLength > maxBytes) {
        throw new ProxyRequestBodyTooLargeError(maxBytes);
    }

    if (!request.body) return undefined;

    const reader = request.body.getReader();
    const chunks: Uint8Array[] = [];
    let total = 0;

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > maxBytes) {
            throw new ProxyRequestBodyTooLargeError(maxBytes);
        }
        chunks.push(value);
    }

    if (total === 0) return undefined;

    const merged = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) {
        merged.set(chunk, offset);
        offset += chunk.byteLength;
    }
    return merged.buffer;
}

function getSetCookieHeaders(headers: Headers): string[] {
    const withGetSetCookie = headers as Headers & { getSetCookie?: () => string[] };
    const setCookies = withGetSetCookie.getSetCookie?.();
    if (setCookies && setCookies.length > 0) {
        return setCookies;
    }

    const singleHeader = headers.get('set-cookie');
    return singleHeader ? [singleHeader] : [];
}

function rewriteProxiedSetCookie(cookie: string): string {
    if (!cookie.trim().toLowerCase().startsWith(`${AUTH_BROWSER_NONCE_COOKIE.toLowerCase()}=`)) {
        return cookie;
    }

    if (/;\s*path=/i.test(cookie)) {
        return cookie.replace(/;\s*path=[^;]*/i, '; Path=/api/admin/auth');
    }
    return `${cookie}; Path=/api/admin/auth`;
}

export function createStreamProxy(config: StreamProxyConfig): MethodHandlers {
    const methods = config.methods ?? [...DEFAULT_METHODS, 'OPTIONS' as HttpMethod];
    const shouldRetry = config.shouldRetry ?? ((response: Response) => defaultShouldRetry(response));
    const responseHeaders = config.responseHeaderPassthrough ?? DEFAULT_STREAM_RESPONSE_HEADERS;
    const maxBodyBytes = config.maxBodyBytes ?? DEFAULT_STREAM_PROXY_MAX_BODY_BYTES;

    const handler = async (
        request: NextRequest,
        pathParts: string[],
        method: HttpMethod,
    ): Promise<NextResponse> => {
        try {
            const staticResponse = staticExportGuard(config.serviceName);
            if (staticResponse) return staticResponse;

            const path = sanitizePath(pathParts);
            if (!path) {
                return proxyError('Invalid path', 400, { code: 'INVALID_PATH' });
            }

            const skipAuth = config.isUnauthenticatedPath?.(path) ?? false;
            if (!skipAuth) {
                const authError = requireProxyAuth(request);
                const requireSupabaseSession = Boolean(authError && hasSupabaseSessionCookies(request));
                if (authError && !requireSupabaseSession) return authError;

                const sessionError = await validateProxySession(request, { requireSupabaseSession });
                if (sessionError) return sessionError;
            }

            const queryString = new URL(request.url).search;
            const bases = config.resolveTargetBases();
            if (bases.length === 0) {
                console.error(`[proxy/${config.serviceName}] 503: no upstream targets configured`);
                return proxyError(`${config.serviceName} backend not configured`, 503);
            }

            const headers = config.buildHeaders(request);
            if (!skipAuth || config.prepareHeadersForUnauthenticatedPaths) {
                const headerError = await config.prepareHeaders?.(headers, request, path);
                if (headerError) return headerError;
            }
            const fetchOptions: RequestInit = { method, headers, redirect: 'manual' };

            const hasRequestBody = !METHODS_WITHOUT_BODY.has(method);
            let requestBody: ArrayBuffer | undefined;
            if (hasRequestBody) {
                try {
                    requestBody = await readRequestBodyWithLimit(request, maxBodyBytes);
                } catch (error) {
                    if (error instanceof ProxyRequestBodyTooLargeError) {
                        return proxyError('Request body too large', 413);
                    }
                    throw error;
                }
                if (requestBody) {
                    fetchOptions.body = requestBody;
                }
            }

            const attemptErrors: string[] = [];
            for (const base of bases) {
                const targetUrl = `${stripTrailingSlash(base)}/${path}${queryString}`;
                try {
                    const response = await fetch(targetUrl, fetchOptions);
                    if (response.status >= 300 && response.status < 400) {
                        console.error(`[proxy/${config.serviceName}] redirect refused`);
                        return proxyError(`${config.serviceName} request failed`, 502);
                    }
                    if (shouldRetry(response, path)) {
                        attemptErrors.push(
                            `target=${base} status=${response.status} reason=${response.headers.get('x-vercel-error') || 'vercel_error'}`,
                        );
                        continue;
                    }

                    if (response.status >= 500) {
                        console.error(`[proxy/${config.serviceName}] ${response.status}: upstream request failed`, {
                            targetUrl,
                            upstreamError: await readUpstreamErrorForLog(response),
                        });
                        return proxyError(`${config.serviceName} request failed`, response.status);
                    }

                    const outgoing = new Headers();
                    for (const name of responseHeaders) {
                        const value = response.headers.get(name);
                        if (value) outgoing.set(name, value);
                    }
                    for (const cookie of getSetCookieHeaders(response.headers)) {
                        outgoing.append('set-cookie', rewriteProxiedSetCookie(cookie));
                    }

                    if (process.env.NODE_ENV !== 'production') {
                        console.warn(`[proxy/${config.serviceName}] ${method} ${path} → ${response.status}`);
                    }

                    return new NextResponse(response.body, {
                        status: response.status,
                        headers: outgoing,
                    });
                } catch (error: unknown) {
                    const message = error instanceof Error ? error.message : `${config.serviceName} request failed`;
                    attemptErrors.push(`target=${base} error=${message}`);
                    if (hasRequestBody && requestBody) {
                        fetchOptions.body = requestBody;
                    }
                }
            }

            console.error(`[proxy/${config.serviceName}] 502: all targets failed:`, attemptErrors);
            return proxyError(`Unable to reach ${config.serviceName} service`, 502);
        } catch (error: unknown) {
            console.error(`[proxy/${config.serviceName}] 500: proxy request failed`, { error });
            return proxyError(`${config.serviceName} request failed`, 500);
        }
    };

    return buildMethodHandlers(methods, handler);
}

// ---------------------------------------------------------------------------
// Shared helpers — used by proxy `buildHeaders` implementations
// ---------------------------------------------------------------------------

/** Strip trailing slashes from a URL base. */
export function stripTrailingSlash(value: string): string {
    return value.replace(/\/+$/, '');
}

/** Detect whether a host is publicly reachable (used by multi-target fallback
 *  to decide whether Railway internal URLs can be tried from Vercel). */
export function isPublicHost(urlValue: string): boolean {
    try {
        const parsed = new URL(urlValue);
        if (!['http:', 'https:'].includes(parsed.protocol)) return false;
        const hostname = parsed.hostname.toLowerCase();
        if (
            hostname === 'localhost' ||
            hostname === '127.0.0.1' ||
            hostname === '::1' ||
            hostname.endsWith('.local') ||
            hostname.endsWith('.internal') ||
            !hostname.includes('.')
        ) return false;
        if (hostname.startsWith('10.')) return false;
        if (hostname.startsWith('192.168.')) return false;
        const secondOctet = Number(hostname.split('.')[1]);
        if (hostname.startsWith('172.') && secondOctet >= 16 && secondOctet <= 31) return false;
        return true;
    } catch {
        return false;
    }
}

/** Copy selected request headers onto an outbound Headers object. */
export function passthroughRequestHeaders(
    headers: Headers,
    request: NextRequest,
    names: string[],
): Headers {
    for (const name of names) {
        if (RETIRED_CREDENTIAL_HEADERS.has(name.toLowerCase())) continue;
        const value = request.headers.get(name);
        if (value && !isCookieManagedCredentialHeader(name, value)) headers.set(name, value);
    }
    return headers;
}

/** Forward only server-selected opaque auth cookies to a backend.
 *
 * Never copy the caller's raw Cookie header: doing so would disclose unrelated
 * frontend cookies and make future cookies backend authentication inputs by
 * accident. The browser nonce is needed only while completing an auth
 * ceremony through the admin proxy.
 */
export function appendOpaqueSessionCookies(
    headers: Headers,
    request: NextRequest,
    options: { includeBrowserNonce?: boolean } = {},
): Headers {
    const names = options.includeBrowserNonce
        ? [OPAQUE_SESSION_COOKIE, AUTH_BROWSER_NONCE_COOKIE]
        : [OPAQUE_SESSION_COOKIE];
    const cookies = names
        .map((name) => {
            const value = request.cookies.get(name)?.value;
            return value ? `${name}=${value}` : null;
        })
        .filter((cookie): cookie is string => cookie !== null);

    if (cookies.length > 0) {
        headers.set('cookie', cookies.join('; '));
    } else {
        headers.delete('cookie');
    }
    return headers;
}

/** Standard cookie → auth header injection used by the streaming proxies.
 *
 *  Populates (when present and not already set):
 *    - Authorization: Bearer {re_access_token}
 *    - X-RegEngine-API-Key: {re_api_key}
 *    - X-Tenant-ID: {re_tenant_id}
 *
 *  When `respectExistingAuthHeader` is true, an incoming Authorization header
 *  wins over the cookie when a route explicitly needs to preserve a caller
 *  supplied bearer token.
 */
export function applyCookieCredentials(
    headers: Headers,
    request: NextRequest,
    options: { respectExistingAuthHeader?: boolean } = {},
): Headers {
    // The retired shared administrative credential is never forwarded, even
    // if a caller or future route accidentally pre-populates the header.
    headers.delete('x-admin-key');
    const isBrowserRequest = Boolean(request.headers.get('origin') || request.headers.get('referer'));
    const cookieAccessToken = request.cookies.get('re_access_token')?.value;
    const headerAuth = headers.get('authorization');
    if (headerAuth && isCookieManagedCredentialHeader('authorization', headerAuth)) {
        headers.delete('authorization');
    }
    const existingAuth = headers.get('authorization') || request.headers.get('authorization');
    const hasUsableExistingAuth = Boolean(
        existingAuth && !isCookieManagedCredentialHeader('authorization', existingAuth),
    );
    if (
        isUsableCallerCredential(cookieAccessToken) &&
        !(options.respectExistingAuthHeader && hasUsableExistingAuth)
    ) {
        headers.set('authorization', `Bearer ${cookieAccessToken}`);
    }

    let existingApiKey = headers.get('x-regengine-api-key');
    if (
        existingApiKey &&
        (isCookieManagedCredentialHeader('x-regengine-api-key', existingApiKey) || isBrowserRequest)
    ) {
        headers.delete('x-regengine-api-key');
        existingApiKey = null;
    }
    if (!existingApiKey) {
        const cookieApiKey = request.cookies.get('re_api_key')?.value;
        if (isUsableCallerCredential(cookieApiKey)) {
            headers.set('x-regengine-api-key', cookieApiKey);
        }
    }

    const cookieTenantId = request.cookies.get('re_tenant_id')?.value;
    if (cookieTenantId) {
        headers.set('x-tenant-id', cookieTenantId);
    } else if (request.headers.get('origin') || request.headers.get('referer')) {
        headers.delete('x-tenant-id');
    }

    return headers;
}

/** Finalize caller-owned service credentials without privilege substitution.
 *
 * This helper deliberately never reads a server-held API key. A BFF may
 * forward a caller's direct API key, API-key cookie, bearer token, or opaque
 * session for authoritative validation by the upstream service, but an
 * unverified browser credential must never be upgraded to ambient server
 * authority. The sole scoped browser-to-workload bridge lives in
 * `inflow-workbench-proxy.ts`, where `/auth/me` and the exact tenant are
 * verified before a dedicated read-only key is attached.
 */
export function finalizeCallerServiceCredentials(
    headers: Headers,
    request: NextRequest,
    requestedTenantId?: string,
): NextResponse | null {
    const explicitTenantId = requestedTenantId === undefined
        ? null
        : validateProxyTenantId(requestedTenantId);
    if (requestedTenantId !== undefined && !explicitTenantId) {
        headers.delete('x-regengine-api-key');
        headers.delete('x-api-key');
        return proxyError('Invalid tenant context for service proxy', 400, {
            code: 'INVALID_TENANT_CONTEXT',
        });
    }

    const existingApiKey = headers.get('x-regengine-api-key');
    const cookieApiKey = request.cookies.get('re_api_key')?.value;
    const isBrowserRequest = Boolean(request.headers.get('origin') || request.headers.get('referer'));

    // A browser can manufacture request headers. Preserve an API key only
    // when it came from the server-read cookie; otherwise remove it and let
    // the upstream reject the remaining credential rather than upgrading it.
    if (
        isBrowserRequest &&
        existingApiKey &&
        (!isUsableCallerCredential(cookieApiKey) || existingApiKey !== cookieApiKey)
    ) {
        headers.delete('x-regengine-api-key');
    }

    // Never forward the historical alias after normalization. Public callers
    // use X-RegEngine-API-Key and the upstream remains the credential authority.
    headers.delete('x-api-key');
    if (explicitTenantId) headers.set('x-tenant-id', explicitTenantId);
    return null;
}

/** Build the complete authentication envelope for a tenant-named BFF route.
 *
 * Caller-owned API keys/tokens and the opaque session cookie are forwarded.
 * No ambient server credential is attached; the upstream must validate the
 * presented caller credential and its tenant binding.
 */
export function prepareTenantScopedProxyHeaders(
    headers: Headers,
    request: NextRequest,
    tenantId: string,
): NextResponse | null {
    const validatedTenantId = validateProxyTenantId(tenantId);
    if (!validatedTenantId) {
        return proxyError('Invalid tenant context', 400, { code: 'INVALID_TENANT_CONTEXT' });
    }

    passthroughRequestHeaders(headers, request, [
        'authorization',
        'x-regengine-api-key',
        'x-api-key',
    ]);

    // Normalize the historical header alias. Never send two API credentials
    // upstream, and never synthesize one from server environment state.
    const aliasApiKey = headers.get('x-api-key');
    if (!headers.has('x-regengine-api-key') && isUsableCallerCredential(aliasApiKey)) {
        headers.set('x-regengine-api-key', aliasApiKey);
    }
    headers.delete('x-api-key');

    applyCookieCredentials(headers, request, { respectExistingAuthHeader: true });
    appendOpaqueSessionCookies(headers, request);

    const credentialError = finalizeCallerServiceCredentials(
        headers,
        request,
        validatedTenantId,
    );
    if (credentialError) return credentialError;

    headers.set('x-tenant-id', validatedTenantId);
    return null;
}

function validateProxyTenantId(value: string | null | undefined): string | null {
    const tenantId = validateUuid(value);
    if (tenantId) return tenantId;
    return value?.toLowerCase() === SYSTEM_TENANT_ID ? SYSTEM_TENANT_ID : null;
}
