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
import { decodeRegEngineClaims, extractRegEngineTenantId } from './jwt-claims';
import { getServerServiceURL } from './api-config';
import { getAdminTargets, shouldRetryAdminProxyResponse } from './admin-targets';

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

/**
 * Resolve the authoritative tenant for an opaque `__Host-regengine_session`
 * by calling the backend `/auth/me`. The session cookie is httpOnly and
 * server-validated, so the returned `organization_id` is trustworthy — unlike
 * the client-writable `re_tenant_id` cookie. Returns the tenant id (lowercased)
 * or `null` when no server-derived tenant is available (caller must fail closed).
 *
 * Mirrors `getOpaqueSessionInfo` in `app/api/session/route.ts`.
 */
export async function resolveOpaqueSessionTenantId(sessionToken: string): Promise<string | null> {
  const cookieHeader = `__Host-regengine_session=${sessionToken}`;

  for (const target of getAdminTargets()) {
    const baseUrl = target.replace(/\/+$/, '');
    try {
      const response = await fetch(`${baseUrl}/auth/me`, {
        method: 'GET',
        headers: { accept: 'application/json', cookie: cookieHeader },
        cache: 'no-store',
      });

      if (shouldRetryAdminProxyResponse(response, 'auth/me')) {
        continue;
      }
      if (response.status === 401 || response.status === 403) {
        return null;
      }
      if (!response.ok) {
        continue;
      }

      // Resolve the session's TENANT, not its organization. /auth/me returns
      // both; tenant_id is the identifier ingestion/readiness routes are
      // scoped by (organization_id is a different entity and is null for
      // users whose tenancy lives only in the memberships table). Fall back to
      // organization_id only for backends that predate the tenant_id field.
      const body = await response.json().catch(() => null);
      const record = body && typeof body === 'object' ? (body as Record<string, unknown>) : null;
      const tenantId =
        record && typeof record.tenant_id === 'string'
          ? record.tenant_id
          : record && typeof record.organization_id === 'string'
            ? (record.organization_id as string)
            : null;
      return tenantId ? tenantId.toLowerCase() : null;
    } catch {
      // Try the next configured admin target.
    }
  }

  return null;
}

/**
 * Cross-tenant authorization guard for `[tenantId]` proxy routes.
 *
 * The path `tenantId` is attacker-controlled and the proxy injects a
 * privileged first-party API key regardless of caller, so without this check
 * any logged-in user could read/export another tenant's data by guessing its
 * UUID (IDOR). We bind the request to the caller's authoritative tenant:
 *  - RegEngine JWT (`re_access_token`): the `tenant_id` claim is authoritative
 *    (issuer/audience/exp already checked by `decodeRegEngineClaims`). A
 *    tenant-unbound principal — no claim, i.e. master/sysadmin/dev — is
 *    legitimately cross-tenant capable and is allowed through.
 *  - Opaque `__Host-regengine_session` (SSO / passkey / email-OTP): there is
 *    no JWT, so the authoritative tenant is derived server-side from the
 *    backend `/auth/me` `organization_id`. The client-writable `re_tenant_id`
 *    cookie is NEVER trusted as an authorization input (it is set
 *    `httpOnly:false` and is forgeable from `document.cookie`). We fail closed
 *    when no server-derived tenant is available (#2501).
 *  - API-key callers (`re_api_key` / `x-regengine-api-key` / `x-api-key`): the
 *    caller's key is never forwarded upstream by these routes, so the backend
 *    cannot bind key→tenant and the path `tenantId` would be unchecked. Fails
 *    closed with `E_APIKEY_TENANT_UNVERIFIABLE` (#2896).
 *
 * Returns a 403 `NextResponse` on mismatch, or `null` when access is allowed.
 * Callers must still run `requireProxyAuth` + `validateProxySession` first.
 */
export async function enforceTenantMatch(
  request: NextRequest,
  pathTenantId: string,
): Promise<NextResponse | null> {
  const mismatch = NextResponse.json(
    { error: 'Tenant context does not match authenticated session' },
    { status: 403 },
  );

  const regengineToken = request.cookies.get('re_access_token')?.value;
  if (isUsableCallerCredential(regengineToken)) {
    const payload = decodeRegEngineClaims(regengineToken);
    if (payload) {
      const tokenTenantId = extractRegEngineTenantId(payload);
      // No tenant claim => tenant-unbound principal (master/sysadmin/dev),
      // which is legitimately cross-tenant capable.
      if (tokenTenantId && tokenTenantId.toLowerCase() !== pathTenantId.toLowerCase()) {
        return mismatch;
      }
      return null;
    }
  }

  // Opaque session: derive the authoritative tenant from the server, never
  // from the client-writable `re_tenant_id` cookie. Fail closed if the backend
  // does not yield a tenant.
  const sessionToken = request.cookies.get('__Host-regengine_session')?.value;
  if (isUsableCallerCredential(sessionToken)) {
    const serverTenantId = await resolveOpaqueSessionTenantId(sessionToken);
    if (!serverTenantId || serverTenantId !== pathTenantId.toLowerCase()) {
      return mismatch;
    }
    return null;
  }

  // API-key caller (re_api_key cookie / x-regengine-api-key / x-api-key
  // header). This branch used to return null (ALLOW), justified by the claim
  // that the backend binds tenant to the key's server-side row. That
  // justification is unreachable on these routes (#2896): the `[tenantId]`
  // proxies never forward the caller's key — they attach the server's own
  // privileged `REGENGINE_API_KEY` / `ADMIN_MASTER_KEY` (see
  // `app/api/v1/compliance/snapshots/[tenantId]/route.ts`, which calls
  // `getServerApiKey()` right after this guard). The backend therefore never
  // sees the caller's key and cannot bind key→tenant, so any non-empty string
  // in one of these slots authorized a cross-tenant read/write of another
  // tenant's frozen compliance evidence. `x-api-key` is not even a backend auth
  // header (services/shared/auth.py reads `X-RegEngine-API-Key`).
  //
  // Fail closed, with a distinct code so API-key integrations get a documented
  // rejection instead of silent cross-tenant access. Restoring API-key support
  // here requires forwarding the caller's own key upstream instead of the
  // first-party key, which is a route-level change.
  if (
    isUsableCallerCredential(request.cookies.get('re_api_key')?.value) ||
    isUsableCallerCredential(request.headers.get('x-regengine-api-key')) ||
    isUsableCallerCredential(request.headers.get('x-api-key'))
  ) {
    return NextResponse.json(
      {
        error:
          'API-key callers cannot be bound to a tenant on this route — use a session-authenticated request',
        code: 'E_APIKEY_TENANT_UNVERIFIABLE',
      },
      { status: 403 },
    );
  }

  // No authoritative, server-validated tenant signal available. The
  // client-writable `re_tenant_id` cookie is never trusted here (#2501), so we
  // fail closed for cross-tenant path access by default.
  return mismatch;
}

/**
 * Resolve the caller's authoritative tenant id from server-verifiable signals
 * only: the RegEngine JWT `tenant_id` claim (issuer/audience/exp already checked
 * by `decodeRegEngineClaims`), or the backend `/auth/me` lookup for an opaque
 * `__Host-regengine_session`. The client-writable `re_tenant_id` cookie is never
 * consulted. Returns `null` when no server-derived tenant is available, so
 * callers forward no tenant header rather than a forgeable one.
 */
export async function resolveCallerTenantId(request: NextRequest): Promise<string | null> {
  const regengineToken = request.cookies.get('re_access_token')?.value;
  if (isUsableCallerCredential(regengineToken)) {
    const payload = decodeRegEngineClaims(regengineToken);
    if (payload) {
      const tokenTenantId = extractRegEngineTenantId(payload);
      if (tokenTenantId) return tokenTenantId.toLowerCase();
    }
  }

  const sessionToken = request.cookies.get('__Host-regengine_session')?.value;
  if (isUsableCallerCredential(sessionToken)) {
    return resolveOpaqueSessionTenantId(sessionToken);
  }

  return null;
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

function isServerErrorStatus(status: number): boolean {
  return status >= 500 && status <= 599;
}

export function genericProxyErrorMessage(status: number): string {
  if (status === 502) return 'Bad gateway';
  if (status === 503) return 'Service temporarily unavailable';
  if (status === 504) return 'Gateway timeout';
  return 'Internal server error';
}

/**
 * Returns a NextResponse with a standardised error JSON shape.
 */
export function proxyError(
  message: string,
  status: number,
  opts?: { code?: string; details?: string[] },
): NextResponse<ProxyErrorBody> {
  const serverError = isServerErrorStatus(status);
  const body: ProxyErrorBody = {
    error: serverError ? genericProxyErrorMessage(status) : message,
  };
  if (!serverError && opts?.code) body.code = opts.code;
  if (!serverError && opts?.details) body.details = opts.details;
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
 *   4. __Host-regengine_session cookie
 *   5. x-regengine-api-key header (direct API calls)
 *   6. x-admin-key header (direct API calls)
 *   7. x-api-key header (direct API calls)
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
const CALLER_CREDENTIAL_COOKIES = [
  're_api_key',
  're_admin_key',
  're_access_token',
  '__Host-regengine_session',
] as const;
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

export function hasSupabaseSessionCookies(request: NextRequest): boolean {
  // A real Supabase session is the `sb-<project>-auth-token` cookie (and its
  // chunked `.0` / `.1` variants when the payload is large). The PKCE flow
  // also writes a transient `sb-<project>-auth-token-code-verifier` cookie
  // that is NOT a session — it's just the verifier for an in-flight OAuth
  // exchange and can outlive the flow if the user navigates away. Matching
  // it as a session caused authenticated RegEngine sessions to 401 at the
  // proxy when supabase.auth.getUser() returned no user.
  return request.cookies.getAll().some((cookie) => {
    if (!cookie.name.startsWith('sb-')) return false;
    if (!cookie.name.includes('-auth-token')) return false;
    if (cookie.name.endsWith('-code-verifier')) return false;
    return true;
  });
}

/**
 * Constant-time string equality.
 *
 * Compares every position rather than exiting at the first difference, so the
 * time taken does not reveal how much of a guess was correct. Written against
 * WebCrypto-era primitives only (no `node:crypto`) so this module stays usable
 * from an Edge route; the length of the configured key is not treated as a
 * secret, its contents are.
 */
function constantTimeEquals(candidate: string, expected: string): boolean {
  const length = Math.max(candidate.length, expected.length);
  let difference = candidate.length ^ expected.length;
  for (let i = 0; i < length; i += 1) {
    difference |= (candidate.charCodeAt(i) || 0) ^ (expected.charCodeAt(i) || 0);
  }
  return difference === 0;
}

/** True only when `value` IS the configured admin master key.
 *
 *  #2825: presence used to be enough. Neither slot is a secret the caller had
 *  to know — `POST /api/session` writes any `admin_key` string from the request
 *  body straight into the `re_admin_key` cookie without validating it, and the
 *  `x-admin-key` header needs no `/api/session` call at all. The review proxies
 *  then swap in the real `ADMIN_MASTER_KEY` via `getAdminMasterKey()`, so a
 *  self-asserted capability was unlocking a server-held secret. Requiring the
 *  caller to already hold that secret makes the substitution a no-op for them
 *  and a 403 for everyone else; session-authenticated admins without the key go
 *  through `requireFreshAdminCapability`'s `/auth/me` lookup instead.
 */
function isAdminMasterKey(value: string | null | undefined): boolean {
  if (!isUsableCallerCredential(value)) return false;
  const expected = getAdminMasterKey();
  // Unconfigured server: nothing to match, and every consumer of this gate
  // fails with a 500 immediately afterwards. Never fall back to presence.
  if (!expected) return false;
  return constantTimeEquals(value, expected);
}

export function hasAdminCapability(request: NextRequest): boolean {
  if (isAdminMasterKey(request.cookies.get('re_admin_key')?.value)) {
    return true;
  }

  if (isAdminMasterKey(request.headers.get('x-admin-key'))) {
    return true;
  }

  return false;
}

export function requireAdminCapability(request: NextRequest): NextResponse | null {
  if (hasAdminCapability(request)) {
    return null;
  }

  return NextResponse.json(
    { error: 'Forbidden — admin capability required' },
    { status: 403 },
  );
}

function getSessionBearerToken(request: NextRequest): string | null {
  const authorization = request.headers.get('authorization');
  if (isUsableCallerCredential(authorization) && authorization.toLowerCase().startsWith('bearer ')) {
    const token = authorization.slice('bearer '.length).trim();
    return isUsableCallerCredential(token) ? token : null;
  }

  const cookieToken = request.cookies.get('re_access_token')?.value;
  return isUsableCallerCredential(cookieToken) ? cookieToken : null;
}

function hasFreshAdminRole(body: {
  status?: unknown;
  is_sysadmin?: unknown;
  role_name?: unknown;
  role?: unknown;
  permissions?: unknown;
}): boolean {
  if (typeof body.status === 'string' && body.status !== 'active') {
    return false;
  }
  if (body.is_sysadmin === true) {
    return true;
  }
  const roleName = typeof body.role_name === 'string'
    ? body.role_name.toLowerCase()
    : typeof body.role === 'string'
      ? body.role.toLowerCase()
      : '';
  if (roleName === 'admin' || roleName === 'owner') {
    return true;
  }
  return Array.isArray(body.permissions) && body.permissions.includes('*');
}

export async function requireFreshAdminCapability(request: NextRequest): Promise<NextResponse | null> {
  if (hasAdminCapability(request)) {
    return null;
  }

  const token = getSessionBearerToken(request);
  if (!token) {
    return requireAdminCapability(request);
  }

  const adminBase = getServerServiceURL('admin');
  if (!adminBase) {
    console.error('[api-proxy] 503 — admin service is not configured');
    return proxyError('Admin capability check unavailable', 503);
  }

  try {
    const response = await fetch(`${adminBase.replace(/\/+$/, '')}/auth/me`, {
      method: 'GET',
      headers: {
        accept: 'application/json',
        authorization: `Bearer ${token}`,
      },
      cache: 'no-store',
    });

    if (!response.ok) {
      return requireAdminCapability(request);
    }

    const body = await response.json().catch(() => null);
    if (body && typeof body === 'object' && hasFreshAdminRole(body as Record<string, unknown>)) {
      return null;
    }
  } catch (error) {
    console.warn('[api-proxy] Fresh admin capability check failed', error);
    return proxyError('Admin capability check unavailable', 503);
  }

  return requireAdminCapability(request);
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
  options: { requireSupabaseSession?: boolean } = {},
): Promise<NextResponse | null> {
  const regengineToken = request.cookies.get('re_access_token')?.value;
  if (isUsableCallerCredential(regengineToken)) {
    // Decode-only check — the backend (services/admin) owns JWTKeyRegistry
    // and is the authoritative verifier. We reject malformed/expired tokens
    // and obvious iss/aud mismatches up front, then compare the JWT's
    // tenant_id claim against the re_tenant_id cookie for defense-in-depth.
    // Signature verification happens at the backend boundary.
    const tokenPayload = decodeRegEngineClaims(regengineToken);
    if (!tokenPayload) {
      return NextResponse.json(
        { error: 'Session expired or invalid — please log in again' },
        { status: 401 },
      );
    }

    const tokenTenantId = extractRegEngineTenantId(tokenPayload);
    const cookieTenantId = request.cookies.get('re_tenant_id')?.value;
    if (tokenTenantId && cookieTenantId && tokenTenantId !== cookieTenantId) {
      return NextResponse.json(
        { error: 'Tenant context does not match authenticated session' },
        { status: 403 },
      );
    }

    // The RegEngine JWT is an authoritative caller credential. Don't fall
    // through to the Supabase check — stale `sb-*` cookies (e.g. leftover
    // PKCE `-code-verifier`) would otherwise fail Supabase validation and
    // 401 a request that already authenticated successfully.
    return null;
  }

  if (isUsableCallerCredential(request.cookies.get('__Host-regengine_session')?.value)) {
    return null;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  // Skip validation when Supabase is not configured unless this request relies
  // on Supabase cookies as its only caller credential.
  if (!supabaseUrl || !supabaseKey) {
    if (options.requireSupabaseSession) {
      return NextResponse.json(
        { error: 'Supabase session validation unavailable' },
        { status: 401 },
      );
    }
    return null;
  }

  // Only validate when Supabase session cookies are present
  const hasSupabaseCookies = hasSupabaseSessionCookies(request);
  if (!hasSupabaseCookies) {
    if (options.requireSupabaseSession) {
      return NextResponse.json(
        { error: 'Session expired or invalid — please log in again' },
        { status: 401 },
      );
    }
    return null;
  }

  // Also skip if the request carries an API key — backend handles that auth
  const hasApiKey =
    !!request.cookies.get('re_api_key')?.value ||
    !!request.headers.get('x-regengine-api-key');
  if (hasApiKey && !options.requireSupabaseSession) return null;

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
    if (options.requireSupabaseSession) {
      return NextResponse.json(
        { error: 'Session expired or invalid — please log in again' },
        { status: 401 },
      );
    }
    // Supabase SDK error — don't block requests that also carry backend-validated
    // credentials; let the backend make the final auth decision.
    return null;
  }

  return null;
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
    console.error(`[proxy/${serviceName}] 503 — proxy unavailable in static export mode`);
    return proxyError(`${serviceName} proxy unavailable in static export mode`, 503);
  }
  return null;
}
