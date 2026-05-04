/**
 * Shared utilities for API proxy routes.
 *
 * – sanitizePath: prevents path traversal and null-byte injection
 * – proxyError: returns a consistent JSON error shape across all proxies
 * – requireEnvApiKey: resolves the server-side API key without hardcoded fallbacks
 * – validateProxySession: validates Supabase session tokens before proxying
 */

import { NextRequest, NextResponse } from 'next/server';
import { createServerClient } from '@supabase/ssr';
import { jwtVerify } from 'jose';
import { getVerificationKeys } from './jwt-keys';

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
// Typed path-segment validators
// ---------------------------------------------------------------------------
//
// Proxies that use named dynamic segments ([tenantId], [snapshotId], etc.)
// interpolate the segment directly into the upstream URL. Without validation,
// a malicious value like `../../admin/key` or `%2e%2e/%2e%2e/admin` can
// escape the intended path and hit an unintended backend endpoint.
// Validate UUIDs before forwarding; return null on invalid input so the
// caller can respond with 400.

// RFC 4122 UUID v1-v5, case-insensitive.
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/** Return the value lowercased if it is a valid UUID, else null. */
export function validateUuid(value: string | undefined | null): string | null {
  if (!value || typeof value !== 'string') return null;
  if (!UUID_RE.test(value)) return null;
  return value.toLowerCase();
}

/** Percent-encode a path segment after validating it is URL-safe.
 *  Rejects segments with slashes, control chars, nulls, or `..` traversal. */
export function safeSegment(value: string | undefined | null): string | null {
  if (!value || typeof value !== 'string') return null;
  if (value.length === 0 || value.length > 256) return null;
  if (NULL_BYTE_RE.test(value)) return null;
  if (value.includes('/') || value.includes('\\')) return null;
  if (value === '.' || value === '..') return null;
  if (/[\u0000-\u001f\u007f]/.test(value)) return null;
  return encodeURIComponent(value);
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
 * Caller credentials checked (in order):
 *   1. re_api_key cookie
 *   2. re_admin_key cookie
 *   3. re_access_token cookie
 *   4. x-regengine-api-key header (direct API calls)
 *   5. x-admin-key header (direct API calls)
 *   6. x-api-key header (direct API calls)
 *
 * Server-side env keys are intentionally not caller credentials. They may be
 * injected later only after this preflight sees a real caller credential or
 * session.
 */
export function requireProxyAuth(request: NextRequest): NextResponse | null {
  if (hasRealCallerCredential(request)) {
    return null;
  }

  return NextResponse.json(
    { error: 'Unauthorized — no valid credentials provided' },
    { status: 401 },
  );
}

const COOKIE_MANAGED_PLACEHOLDER = 'cookie-managed';
const PLACEHOLDER_CREDENTIAL_VALUES = new Set([
  COOKIE_MANAGED_PLACEHOLDER,
  `bearer ${COOKIE_MANAGED_PLACEHOLDER}`,
  'bearer',
  'null',
  'undefined',
  'bearer null',
  'bearer undefined',
]);
const CALLER_CREDENTIAL_COOKIES = ['re_api_key', 're_admin_key', 're_access_token'] as const;
const CALLER_CREDENTIAL_HEADERS = [
  'authorization',
  'x-regengine-api-key',
  'x-admin-key',
  'x-api-key',
] as const;
const CREDENTIAL_HEADER_NAMES = new Set<string>(CALLER_CREDENTIAL_HEADERS);

export function isUsableCallerCredential(value: string | null | undefined): value is string {
  const normalized = value?.trim().toLowerCase() ?? '';
  return normalized.length > 0 && !PLACEHOLDER_CREDENTIAL_VALUES.has(normalized);
}

export function isCookieManagedCredentialHeader(name: string, value: string): boolean {
  const normalizedName = name.toLowerCase();
  if (!CREDENTIAL_HEADER_NAMES.has(normalizedName)) {
    return false;
  }
  return !isUsableCallerCredential(value);
}

export function hasRealCallerCredential(request: NextRequest): boolean {
  for (const name of CALLER_CREDENTIAL_COOKIES) {
    if (isUsableCallerCredential(request.cookies.get(name)?.value)) {
      return true;
    }
  }

  for (const name of CALLER_CREDENTIAL_HEADERS) {
    if (isUsableCallerCredential(request.headers.get(name))) {
      return true;
    }
  }

  return false;
}

// ---------------------------------------------------------------------------
// Supabase session validation for proxy routes
// ---------------------------------------------------------------------------

/**
 * Validates Supabase session tokens before proxying to the backend.
 *
 * Only validates when Supabase cookies are present (sb-* cookies indicate
 * the user authenticated via Supabase). API-key-only requests (re_api_key,
 * re_admin_key) are validated by the backend — the proxy can't verify those.
 *
 * Returns a 401 NextResponse if the session is invalid/expired,
 * or null if the request should proceed.
 */
export async function validateProxySession(
  request: NextRequest,
): Promise<NextResponse | null> {
  const regengineToken = request.cookies.get('re_access_token')?.value;
  if (isUsableCallerCredential(regengineToken)) {
    const tokenPayload = await verifyRegEngineProxyToken(regengineToken);
    if (!tokenPayload) {
      return NextResponse.json(
        { error: 'Session expired or invalid — please log in again' },
        { status: 401 },
      );
    }

    const tokenTenantId = extractJwtTenantId(tokenPayload);
    const cookieTenantId = request.cookies.get('re_tenant_id')?.value;
    if (tokenTenantId && cookieTenantId && tokenTenantId !== cookieTenantId) {
      return NextResponse.json(
        { error: 'Tenant context does not match authenticated session' },
        { status: 403 },
      );
    }
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // Skip validation when Supabase is not configured
  if (!supabaseUrl || !supabaseKey) return null;

  // Only validate when Supabase session cookies are present
  const hasSupabaseCookies = request.cookies
    .getAll()
    .some((c) => c.name.startsWith('sb-'));
  if (!hasSupabaseCookies) return null;

  // Also skip if the request carries an API key — backend handles that auth
  const hasApiKey =
    !!request.cookies.get('re_api_key')?.value ||
    !!request.headers.get('x-regengine-api-key');
  if (hasApiKey) return null;

  try {
    const supabase = createServerClient(supabaseUrl, supabaseKey, {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll() {
          // Route handlers are read-only for cookies; session refresh
          // is handled by the middleware layer.
        },
      },
    });

    const {
      data: { user },
      error,
    } = await supabase.auth.getUser();

    if (error || !user) {
      return NextResponse.json(
        { error: 'Session expired or invalid — please log in again' },
        { status: 401 },
      );
    }
  } catch {
    // Supabase SDK error — don't block the request, let backend validate
    return null;
  }

  return null;
}

async function verifyRegEngineProxyToken(token: string): Promise<Record<string, unknown> | null> {
  const keys = getVerificationKeys();
  if (keys.length === 0) {
    console.error('[proxy] No JWT verification keys configured for RegEngine session validation');
    return null;
  }

  for (const key of keys) {
    try {
      const { payload } = await jwtVerify(token, key.secret, {
        algorithms: ['HS256'],
      });
      if (isRegEngineSessionPayload(payload as Record<string, unknown>)) {
        return payload as Record<string, unknown>;
      }
      return null;
    } catch {
      // Try the next configured key during rotation.
    }
  }
  return null;
}

function extractJwtTenantId(payload: Record<string, unknown>): string | null {
  const value = payload.tenant_id ?? payload.tid;
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function isRegEngineSessionPayload(payload: Record<string, unknown>): boolean {
  const audience = payload.aud;
  if (typeof audience === 'string' && audience !== 'regengine-api') return false;
  if (Array.isArray(audience) && !audience.includes('regengine-api')) return false;
  const issuer = payload.iss;
  if (typeof issuer === 'string' && issuer !== 'regengine-admin') return false;
  return true;
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
