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
    proxyError,
    requireProxyAuth,
    validateProxySession,
    staticExportGuard,
    isCookieManagedCredentialHeader,
    isUsableCallerCredential,
} from './api-proxy';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'OPTIONS';

const DEFAULT_METHODS: HttpMethod[] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const METHODS_WITHOUT_BODY: ReadonlySet<HttpMethod> = new Set(['GET', 'OPTIONS']);

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
            if (authError) return authError;

            const sessionError = await validateProxySession(request);
            if (sessionError) return sessionError;

            const path = sanitizePath(pathParts);
            if (!path) {
                return proxyError('Invalid path', 400, { code: 'INVALID_PATH' });
            }

            const queryString = new URL(request.url).search;
            const targetUrl = config.buildTargetUrl(path, queryString, request);
            if (!targetUrl) {
                return proxyError(`${config.serviceName} backend not configured`, 503);
            }

            const headers = config.buildHeaders(request, path);
            const fetchOptions: RequestInit = { method, headers };

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
            const data = await response.json().catch(() => ({} as unknown));

            if (!response.ok) {
                const detail = extractDetail(data);
                return NextResponse.json(
                    { error: detail ?? `${config.serviceName} request failed` },
                    { status: response.status },
                );
            }

            if (process.env.NODE_ENV !== 'production') {
                console.info(`[proxy/${config.serviceName}] ${method} ${path} → ${response.status}`);
            }
            return NextResponse.json(data);
        } catch (error: unknown) {
            const message = error instanceof Error ? error.message : `${config.serviceName} request failed`;
            console.error(`[proxy/${config.serviceName}] 500 —`, message);
            return proxyError(message, 500);
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
    /** Upstream response headers to pass through to the client. */
    responseHeaderPassthrough?: string[];
    /** Methods to export. Defaults to GET/POST/PUT/PATCH/DELETE/OPTIONS. */
    methods?: HttpMethod[];
    /** Should we retry this response against the next target base? */
    shouldRetry?: (response: Response) => boolean;
    /** Optional: paths that skip the auth + session checks (used for admin/auth/login etc.). */
    isUnauthenticatedPath?: (path: string) => boolean;
}

const DEFAULT_STREAM_RESPONSE_HEADERS = [
    'content-type',
    'content-disposition',
    'cache-control',
    'x-fda-record-count',
];

const VERCEL_PRIVATE_DNS_ERROR = 'DNS_HOSTNAME_RESOLVED_PRIVATE';

function defaultShouldRetry(response: Response): boolean {
    const header = response.headers.get('x-vercel-error') || '';
    return header.includes(VERCEL_PRIVATE_DNS_ERROR);
}

export function createStreamProxy(config: StreamProxyConfig): MethodHandlers {
    const methods = config.methods ?? [...DEFAULT_METHODS, 'OPTIONS' as HttpMethod];
    const shouldRetry = config.shouldRetry ?? defaultShouldRetry;
    const responseHeaders = config.responseHeaderPassthrough ?? DEFAULT_STREAM_RESPONSE_HEADERS;

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
                if (authError) return authError;

                const sessionError = await validateProxySession(request);
                if (sessionError) return sessionError;
            }

            const queryString = new URL(request.url).search;
            const bases = config.resolveTargetBases();
            if (bases.length === 0) {
                return proxyError(`${config.serviceName} backend not configured`, 503);
            }

            const headers = config.buildHeaders(request);
            const fetchOptions: RequestInit = { method, headers };

            const hasRequestBody = !METHODS_WITHOUT_BODY.has(method);
            let requestBody: ArrayBuffer | undefined;
            if (hasRequestBody) {
                const buffer = await request.arrayBuffer();
                if (buffer.byteLength > 0) {
                    requestBody = buffer;
                    fetchOptions.body = requestBody;
                }
            }

            const attemptErrors: string[] = [];
            for (const base of bases) {
                const targetUrl = `${stripTrailingSlash(base)}/${path}${queryString}`;
                try {
                    const response = await fetch(targetUrl, fetchOptions);
                    if (shouldRetry(response)) {
                        attemptErrors.push(
                            `target=${base} status=${response.status} reason=${response.headers.get('x-vercel-error') || 'vercel_error'}`,
                        );
                        continue;
                    }

                    const outgoing = new Headers();
                    for (const name of responseHeaders) {
                        const value = response.headers.get(name);
                        if (value) outgoing.set(name, value);
                    }

                    if (process.env.NODE_ENV !== 'production') {
                        console.info(`[proxy/${config.serviceName}] ${method} ${path} → ${response.status}`);
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

            console.error(`[proxy/${config.serviceName}] 502 — all targets failed:`, attemptErrors);
            return proxyError(`Unable to reach ${config.serviceName} service`, 502, { details: attemptErrors });
        } catch (error: unknown) {
            const message = error instanceof Error ? error.message : `${config.serviceName} request failed`;
            console.error(`[proxy/${config.serviceName}] 500 —`, message);
            return proxyError(message, 500);
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
        const value = request.headers.get(name);
        if (value && !isCookieManagedCredentialHeader(name, value)) headers.set(name, value);
    }
    return headers;
}

/** Standard cookie → auth header injection used by the streaming proxies.
 *
 *  Populates (when present and not already set):
 *    - Authorization: Bearer {re_access_token}
 *    - X-RegEngine-API-Key: {re_api_key}
 *    - X-Admin-Key: {re_admin_key}
 *    - X-Tenant-ID: {re_tenant_id}
 *
 *  When `respectExistingAuthHeader` is true, an incoming Authorization header
 *  wins over the cookie — used by recovery flows (password reset) where the
 *  caller passes a Supabase token that must not be clobbered by a stale
 *  RegEngine session cookie.
 */
export function applyCookieCredentials(
    headers: Headers,
    request: NextRequest,
    options: { respectExistingAuthHeader?: boolean } = {},
): Headers {
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

    const existingApiKey = headers.get('x-regengine-api-key');
    if (existingApiKey && isCookieManagedCredentialHeader('x-regengine-api-key', existingApiKey)) {
        headers.delete('x-regengine-api-key');
    }
    if (!existingApiKey || isCookieManagedCredentialHeader('x-regengine-api-key', existingApiKey)) {
        const cookieApiKey = request.cookies.get('re_api_key')?.value;
        if (isUsableCallerCredential(cookieApiKey)) {
            headers.set('x-regengine-api-key', cookieApiKey);
        }
    }

    const existingAdminKey = headers.get('x-admin-key');
    if (existingAdminKey && isCookieManagedCredentialHeader('x-admin-key', existingAdminKey)) {
        headers.delete('x-admin-key');
    }
    if (!existingAdminKey || isCookieManagedCredentialHeader('x-admin-key', existingAdminKey)) {
        const cookieAdminKey = request.cookies.get('re_admin_key')?.value;
        if (isUsableCallerCredential(cookieAdminKey)) {
            headers.set('x-admin-key', cookieAdminKey);
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
