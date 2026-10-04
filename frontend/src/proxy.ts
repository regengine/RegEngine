import { NextRequest, NextResponse } from 'next/server';
import { createServerClient } from '@supabase/ssr';
import { decodeRegEngineClaims } from '@/lib/jwt-claims';
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
// Sysadmin status cache — avoids a DB query on every /sysadmin/* request.
// In-memory LRU with a 60-second TTL, keyed by auth_user_id.
// ---------------------------------------------------------------------------
// #1180: raised from 5 sec → 10 min. user_metadata.is_sysadmin is the
// primary path now; this cache is only hit on legacy accounts missing the
// claim. The previous 5-sec TTL fanned out a DB query every 5 sec per
// sysadmin on edge cold starts; revocation freshness is now bounded by
// the access-token TTL anyway (logout forces re-auth within 60 min).
const SYSADMIN_CACHE_TTL_MS = 10 * 60 * 1000;
const SYSADMIN_CACHE_MAX_SIZE = 256;

interface SysadminCacheEntry {
    isSysadmin: boolean;
    expiresAt: number;
}

const sysadminCache = new Map<string, SysadminCacheEntry>();

// ---------------------------------------------------------------------------
// Tenant status cache — avoids a DB query on every Supabase-path request.
// In-memory LRU with a 2-minute TTL, keyed by tenant_id.
// ---------------------------------------------------------------------------
// #1180: raised from 2 min → 10 min. user_metadata.tenant_status is the
// primary path; this cache is only hit on legacy accounts missing the
// field. Tenant suspensions are rare enough that a 10-min staleness window
// is acceptable, and the access-token TTL already bounds freshness.
const TENANT_STATUS_CACHE_TTL_MS = 10 * 60 * 1000;
const TENANT_STATUS_CACHE_MAX_SIZE = 256;

interface TenantStatusCacheEntry {
    status: string | null;
    expiresAt: number;
}

const tenantStatusCache = new Map<string, TenantStatusCacheEntry>();

function getTenantStatusCached(tenantId: string): string | null | undefined {
    const entry = tenantStatusCache.get(tenantId);
    if (!entry) return undefined; // cache miss
    if (Date.now() > entry.expiresAt) {
        tenantStatusCache.delete(tenantId);
        return undefined;
    }
    tenantStatusCache.delete(tenantId);
    tenantStatusCache.set(tenantId, entry);
    return entry.status;
}

function setTenantStatusCached(tenantId: string, tenantStatus: string | null): void {
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
    if (Date.now() > entry.expiresAt) {
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

// Only FSMA verticals are supported — all others redirect to home.
const ALLOWED_VERTICALS = ['food-safety', 'fsma', 'fsma-204'];

// Developer-facing routes that require a signed-in session.
// Documentation (/docs) and the public developers page (/developers) are PUBLIC
// to enable developer evaluation. The developer portal at /developer/portal
// (and everything under it) is gated.
//
// This is a UX gate, not an authority: for the opaque __Host-regengine_session
// cookie, requireAppAuth() below only checks that the cookie is present, not
// that it is valid. The portal layout (DashboardLayout, via useAuth) is the
// second UX gate, and the backend authorizes every API call the page makes.
//
// #2886 These MUST be the real rendered page paths. isGatedRoute() matches on
// `pathname === route || pathname.startsWith(route + '/')`, so a route listed
// here that has no corresponding page under src/app gates nothing. The portal
// lives at src/app/developer/portal. (The leftover src/app/api-keys/page.tsx is
// a bare redirect() to /developer/portal/keys, so it is gated transitively by
// its destination.) Exported for the structural guard in
// src/__tests__/proxy-gated-dev-routes.test.ts, which fails the build if an
// entry here stops naming a real page.
export const GATED_DEV_ROUTES = [
    '/developer/portal',
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
 * Decode the RegEngine JWT from the re_access_token cookie.
 *
 * Signature verification is delegated to the backend (services/admin owns
 * `JWTKeyRegistry` and is the authoritative verifier). Mirroring backend
 * signing keys into Vercel env vars caused silent 401 storms every time
 * the backend rotated via `JWTKeyRegistry.rotate()`. The middleware now
 * decodes claims, sanity-checks issuer/audience/exp, and reads
 * tenant_status / is_sysadmin from the payload. Every gated action the
 * user can reach from here proxies to the backend, which enforces the
 * signature; an attacker forging an unsigned token still cannot do
 * anything except hit a backend that immediately rejects them.
 *
 * Revocation freshness was already best-effort in this layer (Edge can't
 * reach Redis); the backend /auth/refresh endpoint remains the revocation
 * gate.
 *
 * Returns the decoded payload if the claims look valid, null otherwise.
 */
async function verifyRegEngineToken(token: string): Promise<Record<string, unknown> | null> {
    return decodeRegEngineClaims(token);
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
 *   1. __Host-regengine_session opaque backend session cookie
 *   2. re_access_token HTTP-only cookie (legacy custom JWT)
 *   3. Supabase session cookies (from Supabase Auth)
 *
 * If neither is present, redirect to /login.
 *
 * @param requestHeaders  Enriched headers including x-nonce (#543). When provided,
 *                        NextResponse.next() forwards them to the route handler so
 *                        server components can read the nonce via headers().get('x-nonce').
 */
async function requireAppAuth(request: NextRequest, requestHeaders?: Headers): Promise<NextResponse> {
    const { pathname } = request.nextUrl;

    // Strategy 1: Check opaque backend session cookie. The backend remains the
    // source of truth for validity and authorization on every proxied API call;
    // this middleware only prevents a logged-in browser from bouncing back to
    // /login because the session is opaque to the edge runtime.
    const opaqueSession = request.cookies.get('__Host-regengine_session')?.value;
    if (opaqueSession) {
        return NextResponse.next({ request: { headers: requestHeaders ?? request.headers } });
    }

    // Strategy 2: Check legacy custom RegEngine JWT cookie
    const reToken = request.cookies.get('re_access_token')?.value;
    if (reToken) {
        const payload = await verifyRegEngineToken(reToken);
        if (payload) {
            // Reject suspended/archived tenants — the tenant_status claim is
            // set at token creation and checked here to prevent suspended
            // tenants from accessing the app. Since JWTs are short-lived
            // (60 min default), the worst-case delay is one token lifetime.
            const tenantStatus = payload.tenant_status as string | undefined;
            if (tenantStatus && tenantStatus !== 'active' && tenantStatus !== 'trial') {
                if (process.env.NODE_ENV !== 'production') {
                    console.warn(`[middleware] Tenant status "${tenantStatus}" — blocking access`);
                }
                const url = request.nextUrl.clone();
                url.pathname = '/login';
                url.searchParams.set('error', 'tenant_suspended');
                return NextResponse.redirect(url);
            }

            // #1180 Sysadmin check on the JWT path — read the claim directly
            // instead of a DB query. Backend embeds is_sysadmin into the
            // custom JWT at mint time (see services/admin auth). When the
            // claim is absent (older tokens pre-rollout), fall through to
            // the Supabase path which has its own check.
            if (pathname.startsWith('/sysadmin')) {
                const isSysadminClaim = payload.is_sysadmin === true;
                if (!isSysadminClaim) {
                    return NextResponse.redirect(new URL('/dashboard', request.url));
                }
            }

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
                const url = request.nextUrl.clone();
                url.pathname = '/login';
                url.searchParams.set('next', pathname);
                url.searchParams.set('error', 'session_expired');
                return NextResponse.redirect(url);
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
        const url = request.nextUrl.clone();
        url.pathname = '/login';
        url.searchParams.set('next', pathname);
        url.searchParams.set('error', 'session_expired');
        return NextResponse.redirect(url);
    }

    // Strategy 3: Check Supabase session
    const { user, response: supabaseResponse } = await checkSupabaseSession(request);
    if (user) {
        // #538 Check tenant_status in Supabase path — mirrors the JWT path check.
        // The JWT embeds tenant_status at mint time; here we read it from user_metadata
        // (if synced) or fall back to a DB query (cached) via the tenants table.
        const supabaseUser = user as {
            id: string;
            user_metadata?: { tenant_id?: string; tenant_status?: string; is_sysadmin?: boolean };
        };
        const tenantId = supabaseUser.user_metadata?.tenant_id;
        // #1180 Prefer user_metadata for tenant_status. The DB fallback
        // previously queried the tenants table on cache miss for every
        // first-hit-per-instance request. user_metadata is the canonical
        // place for this — the backend mirrors status updates there.
        // We still keep a cache-based DB fallback for older accounts that
        // haven't been resynced, but the fallback TTL is raised to 10 min
        // (was 2 min) so fan-out on cold deploys stops beating the DB.
        let resolvedTenantStatus: string | undefined = supabaseUser.user_metadata?.tenant_status;

        if (tenantId && !resolvedTenantStatus) {
            // tenant_status not in user_metadata — look it up with a cached DB query
            let cached = getTenantStatusCached(tenantId);
            if (cached === undefined) {
                // Cache miss — query the tenants table
                const supabase = createServerClient(
                    process.env.NEXT_PUBLIC_SUPABASE_URL!,
                    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
                    {
                        cookies: {
                            getAll() { return request.cookies.getAll(); },
                            setAll() { /* read-only for this check */ },
                        },
                    }
                );
                const { data: tenantRow, error } = await supabase
                    .from('tenants')
                    .select('status')
                    .eq('id', tenantId)
                    .maybeSingle();
                if (error) {
                    // Query FAILED — distinct from "no such tenant": the
                    // tenants RLS policy is USING(true), so a missing row
                    // returns data:null/error:null, not an error. Previously
                    // `error` was ignored, so a failure looked identical to
                    // "status is fine" and the suspension gate below was
                    // skipped (fail-open). Fail closed instead, and do NOT
                    // cache — caching null here would turn a one-request blip
                    // into a full-TTL (10 min) gate bypass. Skipping the cache
                    // write means the next request retries.
                    if (process.env.NODE_ENV !== 'production') {
                        console.warn(`[middleware] tenant status query failed for ${tenantId}: ${error.message}`);
                    }
                    const url = request.nextUrl.clone();
                    url.pathname = '/login';
                    url.searchParams.set('error', 'tenant_status_unavailable');
                    return NextResponse.redirect(url);
                }
                const freshStatus: string | null = tenantRow?.status ?? null;
                setTenantStatusCached(tenantId, freshStatus);
                cached = freshStatus;
            }
            resolvedTenantStatus = cached ?? undefined;
        }

        if (resolvedTenantStatus && resolvedTenantStatus !== 'active' && resolvedTenantStatus !== 'trial') {
            if (process.env.NODE_ENV !== 'production') {
                console.warn(`[middleware] Supabase path: Tenant status "${resolvedTenantStatus}" — blocking access`);
            }
            const url = request.nextUrl.clone();
            url.pathname = '/login';
            url.searchParams.set('error', 'tenant_suspended');
            return NextResponse.redirect(url);
        }

        // Sysadmin check for /sysadmin routes.
        // #1180 Prefer user_metadata.is_sysadmin (synced at login / invite
        // acceptance) over the developer_profiles DB lookup. The DB
        // fallback remains for older accounts missing the claim but now
        // caches for 10 min instead of 5 sec — the 5-sec TTL was a
        // revocation-freshness trade-off that burned a query every 5 sec
        // per sysadmin, which is a low-volume concern relative to the
        // edge-cold-start fan-out it caused.
        if (pathname.startsWith('/sysadmin')) {
            const userId = supabaseUser.id;
            const claimedSysadmin = supabaseUser.user_metadata?.is_sysadmin;

            let isSysadmin: boolean;
            if (typeof claimedSysadmin === 'boolean') {
                isSysadmin = claimedSysadmin;
            } else {
                const cached = getSysadminCached(userId);
                if (cached === null) {
                    // Cache miss — query the database
                    const supabase = createServerClient(
                        process.env.NEXT_PUBLIC_SUPABASE_URL!,
                        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
                        {
                            cookies: {
                                getAll() { return request.cookies.getAll(); },
                                setAll() { /* read-only for this check */ },
                            },
                        }
                    );
                    const { data: profile, error } = await supabase
                        .from('developer_profiles')
                        .select('is_sysadmin')
                        .eq('auth_user_id', userId)
                        .maybeSingle();

                    if (error) {
                        // Cannot confirm sysadmin — fail closed (redirect to
                        // /dashboard, same as a non-sysadmin) and do NOT cache
                        // the failure, so the next request retries rather than
                        // locking a real sysadmin out for the full TTL. This
                        // path previously ignored `error`, so it failed closed
                        // by accident with no signal.
                        if (process.env.NODE_ENV !== 'production') {
                            console.warn(`[middleware] sysadmin lookup failed for ${userId}: ${error.message}`);
                        }
                        return NextResponse.redirect(new URL('/dashboard', request.url));
                    }

                    isSysadmin = !!profile?.is_sysadmin;
                    setSysadminCached(userId, isSysadmin);
                } else {
                    isSysadmin = cached;
                }
            }

            if (!isSysadmin) {
                return NextResponse.redirect(new URL('/dashboard', request.url));
            }
        }
        // Forward enriched request headers (including x-nonce) to the route handler.
        // The Supabase response may carry refreshed auth cookies; preserve them on
        // the new NextResponse.next() instead of writing request headers onto the
        // response, which does not make headers().get('x-nonce') visible.
        const response = NextResponse.next({ request: { headers: requestHeaders ?? request.headers } });
        supabaseResponse.cookies.getAll().forEach((cookie) => response.cookies.set(cookie));
        return response;
    }

    // Neither auth method succeeded — redirect to login
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('next', pathname);

    // Signal the reason so the login page can display a contextual message.
    // Only show "session expired" when a token actually existed but failed verification.
    // First-time visitors (no token) see a clean login form with no error.
    if (reToken) {
        url.searchParams.set('error', 'session_expired');
    }
    // auth_config errors are logged server-side, not shown to visitors.

    return NextResponse.redirect(url);
}

function shouldUpgradeInsecureRequests(request: NextRequest): boolean {
    const forwardedProto = request.headers.get('x-forwarded-proto')?.toLowerCase();
    const isHttps = request.nextUrl.protocol === 'https:' || forwardedProto === 'https';
    const hostname = request.nextUrl.hostname.toLowerCase();
    const isLocalHost =
        hostname === 'localhost' ||
        hostname === '127.0.0.1' ||
        hostname === '::1' ||
        hostname.endsWith('.local');

    return process.env.NODE_ENV === 'production' && isHttps && !isLocalHost;
}

function isReleaseDisabledApiSurface(pathname: string): boolean {
    const isGraphSurface = pathname === '/api/graph' || pathname.startsWith('/api/graph/');
    return (
        isGraphSurface &&
        (process.env.NODE_ENV === 'production' || process.env.REGENGINE_ENABLE_GRAPH_PROXY !== '1')
    );
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
        upgradeInsecureRequests: shouldUpgradeInsecureRequests(request),
    });

    // Clone request headers and inject the nonce so server components can use it
    const requestHeaders = new Headers(request.headers);
    requestHeaders.set('x-nonce', nonce);
    // #2821 Next.js derives the nonce for its OWN bootstrap/chunk <script> tags
    // exclusively from the INCOMING REQUEST's content-security-policy header —
    // see getScriptNonceFromHeader() in next/dist/server/app-render/app-render.js,
    // which parses script-src/default-src out of that string. There is no
    // `x-nonce` convention inside the framework; `x-nonce` above is purely our
    // own channel for layout.tsx / providers.tsx. Without the CSP on the
    // request, the framework emits un-nonced script tags, and because
    // buildCsp() includes 'strict-dynamic' (which makes CSP3 browsers ignore
    // 'self' for scripts) every /_next/static/chunks/*.js is refused and no
    // page hydrates. Setting it here is what makes hydration work in prod.
    requestHeaders.set('Content-Security-Policy', csp);

    // Helper: attach the enforced CSP to any response before returning.
    // Applied to ALL responses (redirects, 4xx, page responses) so the
    // browser CSP state is updated regardless of which code path fires.
    const withCsp = (res: NextResponse): NextResponse => {
        res.headers.set('Content-Security-Policy', csp);
        return res;
    };

    // Release-disabled surfaces must be indistinguishable from absent routes.
    // Resolve this before CSRF so writes cannot reveal that a disabled handler
    // exists by returning a middleware-generated 403 instead of exact 404.
    if (isReleaseDisabledApiSurface(pathname)) {
        return withCsp(new NextResponse(null, { status: 404 }));
    }

    // -----------------------------------------------------------------------
    // CSRF protection for mutating API requests (double-submit cookie check)
    // -----------------------------------------------------------------------
    const csrfProtectedRequest =
        pathname.startsWith('/api/') &&
        CSRF_PROTECTED_METHODS.has(request.method) &&
        !isCsrfExempt(pathname, request.method) &&
        // #537 Bearer tokens only bypass CSRF for non-browser API clients (curl, SDKs, server-to-server).
        // Browser requests ALWAYS include an Origin or Referer header. If either is present alongside
        // a Bearer token, the request is from a browser — CSRF protection still applies.
        // This closes the attack vector where stolen Bearer tokens in browser JS bypass CSRF.
        !(
            request.headers.get('authorization')?.startsWith('Bearer ') &&
            !request.headers.get('origin') &&
            !request.headers.get('referer')
        );

    if (csrfProtectedRequest) {
        const sourceUrl = request.headers.get('origin') || request.headers.get('referer');
        let sourceOrigin: string | null = null;
        try {
            sourceOrigin = sourceUrl ? new URL(sourceUrl).origin : null;
        } catch {
            sourceOrigin = null;
        }
        if (sourceOrigin !== request.nextUrl.origin) {
            return withCsp(NextResponse.json(
                { error: 'Cross-origin mutation rejected' },
                { status: 403 },
            ));
        }

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
    // -----------------------------------------------------------------------
    if (pathname.startsWith('/developers')) {
        return withCsp(NextResponse.next({ request: { headers: requestHeaders } }));
    }

    // Authenticated app routes — server-side session check
    if (isAuthenticatedAppRoute(pathname)) {
        return withCsp(await requireAppAuth(request, requestHeaders));
    }

    // Developer portal: /developer/portal and every sub-path need a session.
    // /docs and /developers stay public for developer evaluation.
    // #2886 GATED_DEV_ROUTES carries the real page path, so isGatedRoute()
    // covers the portal landing page and its sub-paths (e.g. /keys).
    if (isGatedRoute(pathname)) {
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
