import { NextRequest, NextResponse } from 'next/server';
import { createServerClient } from '@supabase/ssr';
import { jwtVerify } from 'jose';
import { getVerificationKeys } from '@/lib/jwt-keys';
import {
    verifyCsrfToken,
    CSRF_HEADER,
    CSRF_SIG_COOKIE,
    CSRF_PROTECTED_METHODS,
    isCsrfExempt,
} from '@/lib/csrf';
import { buildCsp } from '@/lib/csp';
import { isAuthenticatedAppRoute } from '@/lib/app-routes';

// ---------------------------------------------------------------------------
// Fresh authorization cache — bounded at 60 seconds so role revocations and
// tenant status changes are reflected on the next protected request promptly.
// ---------------------------------------------------------------------------
const FRESH_AUTHZ_CACHE_TTL_MS = 60 * 1000;

// Sysadmin status cache — avoids a DB query on every /sysadmin/* request.
// In-memory LRU keyed by auth_user_id.
const SYSADMIN_CACHE_TTL_MS = FRESH_AUTHZ_CACHE_TTL_MS;
const SYSADMIN_CACHE_MAX_SIZE = 256;

interface SysadminCacheEntry {
    isSysadmin: boolean;
    expiresAt: number;
}

const sysadminCache = new Map<string, SysadminCacheEntry>();

// ---------------------------------------------------------------------------
// Tenant status cache — avoids a DB query on every Supabase-path request.
// In-memory LRU keyed by tenant_id.
const TENANT_STATUS_CACHE_TTL_MS = FRESH_AUTHZ_CACHE_TTL_MS;
const TENANT_STATUS_CACHE_MAX_SIZE = 256;

interface TenantStatusCacheEntry {
    status: string;
    expiresAt: number;
}

const tenantStatusCache = new Map<string, TenantStatusCacheEntry>();

function hasSupabaseConfig(): boolean {
    return Boolean(process.env.NEXT_PUBLIC_SUPABASE_URL && process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY);
}

function getReturnPath(request: NextRequest): string {
    return `${request.nextUrl.pathname}${request.nextUrl.search}`;
}

function redirectToLogin(
    request: NextRequest,
    options: { error?: string; includeNext?: boolean } = {},
): NextResponse {
    const url = new URL('/login', request.url);
    if (options.includeNext !== false) {
        url.searchParams.set('next', getReturnPath(request));
    }
    if (options.error) {
        url.searchParams.set('error', options.error);
    }
    return NextResponse.redirect(url);
}

function createReadonlySupabaseClient(request: NextRequest) {
    if (!hasSupabaseConfig()) {
        return null;
    }

    return createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
            cookies: {
                getAll() { return request.cookies.getAll(); },
                setAll() { /* read-only for authz freshness checks */ },
            },
        },
    );
}

function getTenantStatusCached(tenantId: string): string | undefined {
    const entry = tenantStatusCache.get(tenantId);
    if (!entry) return undefined; // cache miss
    if (Date.now() >= entry.expiresAt) {
        tenantStatusCache.delete(tenantId);
        return undefined;
    }
    tenantStatusCache.delete(tenantId);
    tenantStatusCache.set(tenantId, entry);
    return entry.status;
}

function setTenantStatusCached(tenantId: string, tenantStatus: string): void {
    if (tenantStatusCache.size >= TENANT_STATUS_CACHE_MAX_SIZE) {
        const oldestKey = tenantStatusCache.keys().next().value;
        if (oldestKey) tenantStatusCache.delete(oldestKey);
    }
    tenantStatusCache.set(tenantId, {
        status: tenantStatus,
        expiresAt: Date.now() + TENANT_STATUS_CACHE_TTL_MS,
    });
}

function getSysadminCached(userId: string): boolean | null {
    const entry = sysadminCache.get(userId);
    if (!entry) return null;
    if (Date.now() >= entry.expiresAt) {
        sysadminCache.delete(userId);
        return null;
    }
    // Move to end for LRU ordering (Map preserves insertion order)
    sysadminCache.delete(userId);
    sysadminCache.set(userId, entry);
    return entry.isSysadmin;
}

function setSysadminCached(userId: string, isSysadmin: boolean): void {
    // Evict oldest entry if at capacity
    if (sysadminCache.size >= SYSADMIN_CACHE_MAX_SIZE) {
        const oldestKey = sysadminCache.keys().next().value;
        if (oldestKey) sysadminCache.delete(oldestKey);
    }
    sysadminCache.set(userId, {
        isSysadmin,
        expiresAt: Date.now() + SYSADMIN_CACHE_TTL_MS,
    });
}

async function getFreshTenantStatus(
    request: NextRequest,
    tenantId: string | undefined,
    fallbackStatus: string | undefined,
): Promise<string | undefined> {
    if (!tenantId || !hasSupabaseConfig()) {
        return fallbackStatus;
    }

    const cached = getTenantStatusCached(tenantId);
    if (cached !== undefined) {
        return cached;
    }

    const supabase = createReadonlySupabaseClient(request);
    if (!supabase) {
        return fallbackStatus;
    }

    const { data: tenantRow, error } = await supabase
        .from('tenants')
        .select('status')
        .eq('id', tenantId)
        .maybeSingle();

    if (error) {
        if (process.env.NODE_ENV !== 'production') {
            console.warn('[middleware] Tenant status freshness lookup failed', error);
        }
        return '__lookup_failed__';
    }

    const freshStatus = typeof tenantRow?.status === 'string' ? tenantRow.status : undefined;
    if (!freshStatus) {
        if (process.env.NODE_ENV !== 'production') {
            console.warn('[middleware] Tenant status freshness lookup returned no tenant row');
        }
        return '__lookup_failed__';
    }
    setTenantStatusCached(tenantId, freshStatus);
    return freshStatus;
}

async function getFreshSysadminStatus(
    request: NextRequest,
    userId: string | undefined,
    fallbackIsSysadmin: boolean,
): Promise<boolean | null> {
    if (!userId) {
        return hasSupabaseConfig() ? null : fallbackIsSysadmin;
    }
    if (!hasSupabaseConfig()) {
        return fallbackIsSysadmin;
    }

    const cached = getSysadminCached(userId);
    if (cached !== null) {
        return cached;
    }

    const supabase = createReadonlySupabaseClient(request);
    if (!supabase) {
        return fallbackIsSysadmin;
    }

    const { data: userRow, error: userError } = await supabase
        .from('users')
        .select('is_sysadmin')
        .eq('id', userId)
        .maybeSingle();

    if (userError) {
        if (process.env.NODE_ENV !== 'production') {
            console.warn('[middleware] User sysadmin freshness lookup failed', userError);
        }
        return null;
    }

    if (typeof userRow?.is_sysadmin === 'boolean') {
        setSysadminCached(userId, userRow.is_sysadmin);
        return userRow.is_sysadmin;
    }

    const { data: profile, error } = await supabase
        .from('developer_profiles')
        .select('is_sysadmin')
        .eq('auth_user_id', userId)
        .maybeSingle();

    if (error) {
        if (process.env.NODE_ENV !== 'production') {
            console.warn('[middleware] Sysadmin freshness lookup failed', error);
        }
        return null;
    }

    const isSysadmin = !!profile?.is_sysadmin;
    setSysadminCached(userId, isSysadmin);
    return isSysadmin;
}

// Only FSMA verticals are supported — all others redirect to home.
const ALLOWED_VERTICALS = ['food-safety', 'fsma', 'fsma-204'];

// Developer-facing routes that require portal auth.
// Documentation and developer portal are PUBLIC to enable developer evaluation.
// Only key generation and playground (makes real API calls) are gated.
const GATED_DEV_ROUTES = [
    '/api-keys',
    '/playground',
];

// All docs are public — developer evaluation requires accessible documentation.
const PUBLIC_DOCS = [
    '/docs',
    '/docs/fsma-204',
    '/docs/api',
    '/docs/authentication',
    '/docs/quickstart',
    '/docs/sdks',
    '/docs/webhooks',
    '/docs/rate-limits',
    '/docs/errors',
    '/docs/changelog',
];

function isGatedRoute(pathname: string): boolean {
    return GATED_DEV_ROUTES.some(route =>
        pathname === route || pathname.startsWith(route + '/')
    );
}

function isPublicDoc(pathname: string): boolean {
    return PUBLIC_DOCS.some(route => pathname === route);
}

/**
 * Lightweight local check for Supabase session cookie presence.
 *
 * Used for #538 cross-validation: when a custom JWT is valid, we also
 * require that a Supabase session cookie exists. A missing Supabase cookie
 * while a custom JWT is present indicates a desync (e.g. logged out on
 * another tab via Supabase signOut) and triggers re-authentication.
 *
 * Uses cookie name pattern inspection — no network call — to keep
 * middleware fast. Returns true (skip validation) when Supabase is not
 * configured so non-Supabase deployments are unaffected.
 */
function hasSomeSupabaseCookie(request: NextRequest): boolean {
    if (!process.env.NEXT_PUBLIC_SUPABASE_URL) return true; // Supabase not configured
    return request.cookies.getAll().some(c => c.name.includes('-auth-token'));
}

/**
 * Verify the custom RegEngine JWT from the re_access_token cookie.
 *
 * Supports key rotation: tries the current signing key first, then falls
 * back to the previous key (if configured). When a token verifies only
 * with the previous key, a warning is logged so ops knows rotation is
 * still in progress.
 *
 * NOTE: This check does NOT verify token revocation (e.g. logout-all).
 * The middleware runs in Edge Runtime and cannot reach Redis. Revoked
 * tokens remain valid until their JWT `exp` claim (60 min default).
 * The backend /auth/refresh endpoint DOES check session revocation,
 * so revoked users cannot obtain new tokens — only ride out existing ones.
 *
 * Returns the decoded payload if valid, null otherwise.
 */
async function verifyRegEngineToken(token: string): Promise<Record<string, unknown> | null> {
    const keys = getVerificationKeys();

    if (keys.length === 0) {
        console.error(
            '[middleware] No JWT verification keys configured. ' +
            'Set JWT_SIGNING_KEY (or AUTH_SECRET_KEY) in Vercel env vars ' +
            '(must match the backend Railway value).'
        );
        return null;
    }

    for (let i = 0; i < keys.length; i++) {
        const key = keys[i];
        try {
            const { payload } = await jwtVerify(token, key.secret, {
                algorithms: ['HS256'],
            });

            if (i > 0) {
                // Token verified with the previous (non-current) key — rotation in progress
                if (process.env.NODE_ENV !== 'production') {
                    console.warn(
                        `[middleware] JWT verified with previous key (kid=${key.kid}). ` +
                        'Key rotation is in progress — token was signed before the latest rotation.'
                    );
                }
            }

            return payload as Record<string, unknown>;
        } catch {
            // If this is the last key, fall through to return null below
            if (i === keys.length - 1 && process.env.NODE_ENV !== 'production') {
                console.warn(
                    '[middleware] JWT verification failed with all configured keys. ' +
                    'If "signature verification failed", check that JWT_SIGNING_KEY ' +
                    '(or AUTH_SECRET_KEY) on Vercel matches the backend signing key.'
                );
            }
        }
    }

    return null;
}

/**
 * Check for a valid Supabase session.
 * Returns the Supabase user if authenticated, null otherwise.
 */
async function checkSupabaseSession(request: NextRequest): Promise<{ user: Record<string, unknown> | null; response: NextResponse }> {
    let supabaseResponse = NextResponse.next({ request });
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (!supabaseUrl || !supabaseKey) {
        return { user: null, response: supabaseResponse };
    }

    const supabase = createServerClient(supabaseUrl, supabaseKey, {
        cookies: {
            getAll() {
                return request.cookies.getAll();
            },
            setAll(cookiesToSet) {
                cookiesToSet.forEach(({ name, value }) =>
                    request.cookies.set(name, value)
                );
                supabaseResponse = NextResponse.next({ request });
                cookiesToSet.forEach(({ name, value, options }) =>
                    supabaseResponse.cookies.set(name, value, options)
                );
            },
        },
    });

    const { data: { user } } = await supabase.auth.getUser();
    return { user: user as Record<string, unknown> | null, response: supabaseResponse };
}

/**
 * Auth gate for app routes.
 *
 * Authentication strategy (checked in order):
 *   1. re_access_token HTTP-only cookie (custom JWT from /auth/login)
 *   2. Supabase session cookies (from Supabase Auth)
 *
 * If neither is present, redirect to /login.
 *
 * @param requestHeaders  Enriched headers including x-nonce (#543). When provided,
 *                        NextResponse.next() forwards them to the route handler so
 *                        server components can read the nonce via headers().get('x-nonce').
 */
async function requireAppAuth(request: NextRequest, requestHeaders?: Headers): Promise<NextResponse> {
    const { pathname } = request.nextUrl;

    // Strategy 1: Check custom RegEngine JWT cookie
    const reToken = request.cookies.get('re_access_token')?.value;
    if (reToken) {
        const payload = await verifyRegEngineToken(reToken);
        if (payload) {
            // #538 Cross-validate: require Supabase session alongside the custom JWT.
            // Both auth systems must be live. A missing Supabase cookie while a valid
            // custom JWT exists indicates a desync — e.g. the user signed out on
            // another tab via supabase.auth.signOut() which clears Supabase cookies
            // but leaves the HTTP-only re_access_token in place.
            // Re-authentication resyncs both systems.
            // Uses a local cookie name check (no network call) to keep Edge latency low.
            const isEmailCodeSession = payload.auth_method === 'email_code';
            if (!isEmailCodeSession && !hasSomeSupabaseCookie(request)) {
                if (process.env.NODE_ENV !== 'production') {
                    console.warn('[middleware] Custom JWT valid but Supabase session absent — forcing re-auth');
                }
                return redirectToLogin(request, { error: 'session_expired' });
            }

            // AUTHZ-002: reject suspended/archived tenants using a fresh
            // Supabase-backed lookup when configured. JWT tenant_status is only
            // a no-Supabase fallback, never the production authority.
            const payloadTenantId = typeof payload.tenant_id === 'string'
                ? payload.tenant_id
                : typeof payload.tid === 'string'
                    ? payload.tid
                    : undefined;
            const tenantStatus = await getFreshTenantStatus(
                request,
                payloadTenantId,
                typeof payload.tenant_status === 'string' ? payload.tenant_status : undefined,
            );
            if (tenantStatus === '__lookup_failed__') {
                return redirectToLogin(request, { error: 'auth_config' });
            }
            if (tenantStatus && tenantStatus !== 'active' && tenantStatus !== 'trial') {
                if (process.env.NODE_ENV !== 'production') {
                    console.warn(`[middleware] Tenant status "${tenantStatus}" — blocking access`);
                }
                return redirectToLogin(request, { error: 'tenant_suspended', includeNext: false });
            }

            // AUTHZ-002: /sysadmin uses fresh Supabase-backed state, not stale
            // JWT claims, so revocation is reflected within the bounded cache TTL.
            if (pathname.startsWith('/sysadmin')) {
                const isSysadmin = await getFreshSysadminStatus(
                    request,
                    typeof payload.sub === 'string' ? payload.sub : undefined,
                    payload.is_sysadmin === true,
                );
                if (!isSysadmin) {
                    return NextResponse.redirect(new URL('/dashboard', request.url));
                }
            }

            // Forward enriched request headers (including x-nonce) to the route handler
            return NextResponse.next({ request: { headers: requestHeaders ?? request.headers } });
        }
        // Token exists but verification failed (expired or invalid signature).
        // Do NOT fall back to cookie presence — an expired JWT must trigger re-auth.
        // This prevents a compromised or expired token from being silently bypassed.
        if (process.env.NODE_ENV !== 'production') {
            console.warn('[middleware] JWT verification failed — redirecting to login');
        }
        return redirectToLogin(request, { error: 'session_expired' });
    }

    // Strategy 2: Check Supabase session
    const { user, response: supabaseResponse } = await checkSupabaseSession(request);
    if (user) {
        // AUTHZ-002: Check tenant_status in Supabase path. The DB-backed
        // lookup wins over user_metadata so suspension freshness is bounded
        // by FRESH_AUTHZ_CACHE_TTL_MS instead of session metadata.
        const supabaseUser = user as {
            id: string;
            user_metadata?: { tenant_id?: string; tenant_status?: string; is_sysadmin?: boolean };
        };
        const tenantId = supabaseUser.user_metadata?.tenant_id;
        const resolvedTenantStatus = await getFreshTenantStatus(
            request,
            tenantId,
            supabaseUser.user_metadata?.tenant_status,
        );

        if (resolvedTenantStatus === '__lookup_failed__') {
            return redirectToLogin(request, { error: 'auth_config' });
        }

        if (resolvedTenantStatus && resolvedTenantStatus !== 'active' && resolvedTenantStatus !== 'trial') {
            if (process.env.NODE_ENV !== 'production') {
                console.warn(`[middleware] Supabase path: Tenant status "${resolvedTenantStatus}" — blocking access`);
            }
            return redirectToLogin(request, { error: 'tenant_suspended', includeNext: false });
        }

        // Sysadmin check for /sysadmin routes.
        // Always use the DB-backed check with a <=60s cache; user_metadata is
        // profile data, not a fresh authorization source.
        if (pathname.startsWith('/sysadmin')) {
            const isSysadmin = await getFreshSysadminStatus(
                request,
                supabaseUser.id,
                supabaseUser.user_metadata?.is_sysadmin === true,
            );

            if (!isSysadmin) {
                return NextResponse.redirect(new URL('/dashboard', request.url));
            }
        }
        // Forward x-nonce via Supabase response cookies (supabaseResponse is a NextResponse.next())
        if (requestHeaders) {
            requestHeaders.forEach((value, key) => supabaseResponse.headers.set(key, value));
        }
        return supabaseResponse;
    }

    // Neither auth method succeeded — redirect to login
    // Signal the reason so the login page can display a contextual message.
    // Only show "session expired" when a token actually existed but failed verification.
    // First-time visitors (no token) see a clean login form with no error.
    // auth_config errors are logged server-side, not shown to visitors.
    return redirectToLogin(request, reToken ? { error: 'session_expired' } : {});
}

export async function proxy(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // -----------------------------------------------------------------------
    // Per-request nonce for enforced Content-Security-Policy (#543)
    // The nonce is injected into request headers so server components can
    // read it via `headers().get('x-nonce')` and attach it to inline scripts.
    // CSP is enforced (not report-only). Local dev keeps unsafe-eval only for
    // Next.js tooling; production stays nonce-only.
    // -----------------------------------------------------------------------
    const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
    const csp = buildCsp(nonce, {
        allowDevUnsafeEval: process.env.NODE_ENV === 'development',
        allowDevUnsafeInline: process.env.NODE_ENV === 'development',
        requestUrl: request.nextUrl,
    });

    // Clone request headers and inject the nonce so server components can use it
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('x-nonce', nonce);

    // Helper: attach the enforced CSP to any response before returning.
    // Applied to ALL responses (redirects, 4xx, page responses) so the
    // browser CSP state is updated regardless of which code path fires.
    const withCsp = (res: NextResponse): NextResponse => {
        res.headers.set('Content-Security-Policy', csp);
        return res;
    };

    // -----------------------------------------------------------------------
    // CSRF protection for mutating API requests (double-submit cookie check)
    // -----------------------------------------------------------------------
    if (
        pathname.startsWith('/api/') &&
        CSRF_PROTECTED_METHODS.has(request.method) &&
        !isCsrfExempt(pathname) &&
        // #537 Bearer tokens only bypass CSRF for non-browser API clients (curl, SDKs, server-to-server).
        // Browser requests ALWAYS include an Origin or Referer header. If either is present alongside
        // a Bearer token, the request is from a browser — CSRF protection still applies.
        // This closes the attack vector where stolen Bearer tokens in browser JS bypass CSRF.
        !(
            request.headers.get('authorization')?.startsWith('Bearer ') &&
            !request.headers.get('origin') &&
            !request.headers.get('referer')
        )
    ) {
        const headerToken = request.headers.get(CSRF_HEADER);
        const sigCookie = request.cookies.get(CSRF_SIG_COOKIE)?.value;

        if (!headerToken || !sigCookie) {
            return withCsp(NextResponse.json(
                { error: 'Missing CSRF token' },
                { status: 403 },
            ));
        }

        const valid = await verifyCsrfToken(headerToken, sigCookie);
        if (!valid) {
            return withCsp(NextResponse.json(
                { error: 'Invalid CSRF token' },
                { status: 403 },
            ));
        }
    }

    // -----------------------------------------------------------------------
    // PUBLIC: /developers — API showcase page for prospective customers.
    // Bypasses all auth checks; CSP headers are still applied.
    // (next.config.js redirects /developers → /developer/portal)
    // -----------------------------------------------------------------------
    if (pathname.startsWith('/developers')) {
        return withCsp(NextResponse.next({ request: { headers: requestHeaders } }));
    }

    // Authenticated app routes — server-side session check
    if (isAuthenticatedAppRoute(pathname)) {
        return withCsp(await requireAppAuth(request, requestHeaders));
    }

    // Developer portal: only gate key generation and playground behind auth.
    // All docs, codegen, and portal pages are public for developer evaluation.
    if (isGatedRoute(pathname) || pathname === '/developer/portal/keys') {
        return withCsp(await requireAppAuth(request, requestHeaders));
    }

    // Block non-FSMA verticals
    const verticalMatch = pathname.match(/^\/verticals\/([^/]+)/);
    if (verticalMatch && !ALLOWED_VERTICALS.includes(verticalMatch[1])) {
        return withCsp(NextResponse.redirect(new URL('/', request.url)));
    }

    // All /docs/* routes are public — no redirect needed.
    // Pass enriched request headers (including x-nonce) to the route handler.
    return withCsp(NextResponse.next({ request: { headers: requestHeaders } }));
}

export const config = {
    matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
