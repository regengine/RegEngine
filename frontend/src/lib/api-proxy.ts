/**
 * Shared utilities for API proxy routes.
 *
 * – sanitizePath: prevents path traversal and null-byte injection
 * – proxyError: returns a consistent JSON error shape across all proxies
 * – requireEnvApiKey: resolves the server-side API key without hardcoded fallbacks
 */

import { NextRequest, NextResponse } from 'next/server';

// ---------------------------------------------------------------------------
// Path sanitisation
// ---------------------------------------------------------------------------

const PATH_TRAVERSAL_RE = /(?:^|\/)\.\.(?:\/|$)/;
const NULL_BYTE_RE = /\0/;
const ALLOWED_PATH_RE = /^[a-zA-Z0-9\-_./]+$/;

/**
 * Validates and joins path segments from a Next.js catch-all route.
 * Returns the sanitised path string, or null if the path is invalid.
 */
export function sanitizePath(pathParts: string[]): string | null {
  const joined = pathParts.join('/');

  if (joined.length === 0) return null;
  if (NULL_BYTE_RE.test(joined)) return null;
  if (PATH_TRAVERSAL_RE.test(joined)) return null;
  if (!ALLOWED_PATH_RE.test(joined)) return null;

  return joined;
}

// ---------------------------------------------------------------------------
// Standardised error responses
// ---------------------------------------------------------------------------

export interface ProxyErrorBody {
  error: string;
  code?: string;
  details?: string[];
}

/**
 * Returns a NextResponse with a standardised error JSON shape.
 */
export function proxyError(
  message: string,
  status: number,
  opts?: { code?: string; details?: string[] },
): NextResponse<ProxyErrorBody> {
  const body: ProxyErrorBody = { error: message };
  if (opts?.code) body.code = opts.code;
  if (opts?.details) body.details = opts.details;
  return NextResponse.json(body, { status });
}

// ---------------------------------------------------------------------------
// Server-side API key resolution
// ---------------------------------------------------------------------------

/**
 * Resolves the server-side RegEngine API key from environment variables.
 * Returns undefined when no key is configured — callers should decide
 * whether to reject the request or proceed without the header.
 */
export function getServerApiKey(): string | undefined {
  return process.env.REGENGINE_API_KEY || undefined;
}

/**
 * Resolves the server-side admin master key from environment variables.
 * Returns undefined when no key is configured.
 */
export function getAdminMasterKey(): string | undefined {
  return process.env.ADMIN_MASTER_KEY || undefined;
}

// ---------------------------------------------------------------------------
// Proxy auth validation (defense-in-depth)
// ---------------------------------------------------------------------------

/**
 * Validates that the request carries at least one auth credential before
 * proxying to the backend. Returns a 401 NextResponse if no credentials
 * are present, or null if the request should proceed.
 *
 * Credentials checked (in order):
 *   1. re_api_key cookie
 *   2. re_admin_key cookie
 *   3. re_access_token cookie
 *   4. x-regengine-api-key header (direct API calls)
 *   5. x-admin-key header (direct API calls)
 *   6. Server-side REGENGINE_API_KEY env var (service-to-service)
 */
export function requireProxyAuth(request: NextRequest): NextResponse | null {
  const hasApiKeyCookie = !!request.cookies.get('re_api_key')?.value;
  const hasAdminKeyCookie = !!request.cookies.get('re_admin_key')?.value;
  const hasAccessToken = !!request.cookies.get('re_access_token')?.value;
  const hasApiKeyHeader = !!request.headers.get('x-regengine-api-key');
  const hasAdminKeyHeader = !!request.headers.get('x-admin-key');
  const hasServerApiKey = !!process.env.REGENGINE_API_KEY;

  if (
    hasApiKeyCookie ||
    hasAdminKeyCookie ||
    hasAccessToken ||
    hasApiKeyHeader ||
    hasAdminKeyHeader ||
    hasServerApiKey
  ) {
    return null;
  }

  return NextResponse.json(
    { error: 'Unauthorized — no valid credentials provided' },
    { status: 401 },
  );
}

// ---------------------------------------------------------------------------
// Static export guard
// ---------------------------------------------------------------------------

/**
 * Returns a 503 response when running in static export mode.
 * Use at the top of proxy route handlers to short-circuit.
 * Returns null if not in static mode (caller should continue).
 */
export function staticExportGuard(serviceName: string): NextResponse | null {
  if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
    return NextResponse.json(
      {
        error: `${serviceName} proxy unavailable in static export mode`,
        static_mode: true,
        hint: 'Deploy with server-side rendering to enable API proxying',
      },
      { status: 503 },
    );
  }
  return null;
}
