import { NextRequest, NextResponse } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';
import { createServerClient } from '@supabase/ssr';
import { jwtVerify, decodeJwt } from 'jose';
import { getVerificationKeys } from '@/lib/jwt-keys';
import {
    verifyCsrfToken,
    CSRF_HEADER,
    CSRF_SIG_COOKIE,
    CSRF_PROTECTED_METHODS,
    isCsrfExempt,
} from '@/lib/csrf';

// ---------------------------------------------------------------------------
// Sysadmin status cache — avoids a DB query on every /sysadmin/* request.
// In-memory LRU with a 5-minute TTL, keyed by auth_user_id.
// ---------------------------------------------------------------------------
const SYSADMIN_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const SYSADMIN_CACHE_MAX_SIZE = 256;

interface SysadminCacheEntry {
    isSysadmin: boolean;
    expiresAt: number;
}

const sysadminCache = new Map<string, SysadminCacheEntry>();

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

// ---------------------------------------------------------------------------
// Silent token refresh — proactively refresh access tokens nearing expiry
// to prevent mid-session logouts during long compliance workflows.
// ---------------------------------------------------------------------------
const TOKEN_REFRESH_WINDOW_SECONDS = 5 * 60; // Refresh if <5 min until expiry

/**
 * Resolve the admin service base URL for server-side calls.
 * Checks env vars in priority order, matching the admin proxy route logic.
 */
function getAdminBaseURL(): string {
    return (
        process.env.NEXT_PUBLIC_ADMIN_URL ||
        process.env.ADMIN_SERVICE_URL ||
        process.env.NEXT_PUBLIC_API_BASE_URL ||
        'http://localhost:8400'
    );
}

/**
 * Check if the access token is close to expiry (within TOKEN_REFRESH_WINDOW_SECONDS).
 * Decodes the JWT without verification to read the `exp` claim.
 * Returns true if the token should be refreshed.
 */
function isTokenNearExpiry(token: string): boolean {
    try {
        const payload = decodeJwt(token);
        if (typeof payload.exp !== 'number') return false;
        const now = Math.floor(Date.now() / 1000);
        return (payload.exp - now) < TOKEN_REFRESH_WINDOW_SECONDS;
    } catch {
        return false;
    }
}

/**
 * Attempt a silent token refresh using the refresh token cookie.
 *
 * Calls POST /auth/refresh on the admin service with the refresh token.
 * On success, returns the new access and refresh tokens.
 * On failure, returns null (caller should redirect to login or let the
 * existing token attempt proceed).
 */
async function attemptSilentRefresh(
    refreshToken: string,
): Promise<{ access_token: string; refresh_token: string } | null> {
    const adminUrl = getAdminBaseURL().replace(/\/+$/, '');

    try {
        const res = await fetch(`${adminUrl}/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken }),
        });

        if (!res.ok) {
            console.warn(
                `[middleware] Silent refresh failed: ${res.status} ${res.statusText}`,
            );
            return null;
        }

        const data = await res.json();
        if (!data.access_token) {
            console.warn('[middleware] Silent refresh response missing access_token');
            return null;
        }

        return {
            access_token: data.access_token,
            refresh_token: data.refresh_token || '',
        };
    } catch (err) {
        console.warn('[middleware] Silent refresh network error:', err);
        return null;
    }
}

/**
 * Apply refreshed tokens to the response as HTTP-only cookies.
 * Mirrors the cookie settings from /api/session (POST handler).
 */
function setTokenCookies(
    response: NextResponse,
    accessToken: string,
    refreshToken: string,
): void {
    const isProduction = process.env.NODE_ENV === 'production';
    const cookieOptions = {
        httpOnly: true,
        secure: isProduction,
        sameSite: 'lax' as const,
        path: '/',
        maxAge: 60 * 60 * 24 * 7, // 7 days
    };

    response.cookies.set('re_access_token', accessToken, cookieOptions);
    if (refreshToken) {
        response.cookies.set('re_refresh_token', refreshToken, cookieOptions);
    }
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

// Authenticated app routes — require a valid session.
const AUTHENTICATED_APP_ROUTES = [
    '/dashboard',
    '/admin',
    '/sysadmin',
    '/fsma',
    '/settings',
    '/onboarding',
    '/owner',
    // Control Plane pages — contain operational data, must be auth-gated
    '/rules',
    '/records',
    '/exceptions',
    '/requests',
    '/identity',
    '/review',
    '/audit',
    '/readiness',
    '/incidents',
    '/controls',
    '/trace',
    // Compliance subsystem
    '/compliance',
    // Ingestion
    '/ingest',
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

function isAuthenticatedAppRoute(pathname: string): boolean {
    return AUTHENTICATED_APP_ROUTES.some(route =>
        pathname === route || pathname.startsWith(route + '/')
    );
}

/**
 * Verify the custom RegEngine JWT from the re_access_token cookie.
 *
 * Supports key rotation: tries the current signing key first, then falls
 * back to the previous key (if configured). When a token verifies only
 * with the previous key, a warning is logged so ops knows rotation is
 * still in progress.
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
                console.warn(
                    `[middleware] JWT verified with previous key (kid=${key.kid}). ` +
                    'Key rotation is in progress — token was signed before the latest rotation.'
                );
            }

            return payload as Record<string, unknown>;
        } catch {
            // If this is the last key, fall through to return null below
            if (i === keys.length - 1) {
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
 */
async function requireAppAuth(request: NextRequest): Promise<NextResponse> {
    const { pathname } = request.nextUrl;

    // Strategy 1: Check custom RegEngine JWT cookie
    const reToken = request.cookies.get('re_access_token')?.value;
    if (reToken) {
        const payload = await verifyRegEngineToken(reToken);
        if (payload) {
            // Token is valid — check if it's near expiry and proactively refresh.
            // This prevents mid-session logouts during long compliance workflows.
            const refreshToken = request.cookies.get('re_refresh_token')?.value;
            if (refreshToken && isTokenNearExpiry(reToken)) {
                const refreshed = await attemptSilentRefresh(refreshToken);
                if (refreshed) {
                    console.info('[middleware] Silent token refresh succeeded');
                    const response = NextResponse.next({ request });
                    setTokenCookies(response, refreshed.access_token, refreshed.refresh_token);
                    return response;
                }
                // Refresh failed but current token is still valid — continue
                console.info('[middleware] Silent refresh failed, continuing with current token');
            }
            return NextResponse.next({ request });
        }

        // Token verification failed (expired or invalid signature).
        // Attempt a silent refresh before forcing re-auth — the token may have
        // just expired and the refresh token is still valid.
        const refreshToken = request.cookies.get('re_refresh_token')?.value;
        if (refreshToken) {
            const refreshed = await attemptSilentRefresh(refreshToken);
            if (refreshed) {
                // Verify the new token is actually valid before trusting it
                const newPayload = await verifyRegEngineToken(refreshed.access_token);
                if (newPayload) {
                    console.info('[middleware] Silent refresh recovered expired session');
                    const response = NextResponse.next({ request });
                    setTokenCookies(response, refreshed.access_token, refreshed.refresh_token);
                    return response;
                }
            }
        }

        // Neither the existing token nor refresh succeeded — redirect to login.
        console.info('[middleware] JWT verification failed and refresh unavailable — redirecting to login');
        const url = request.nextUrl.clone();
        url.pathname = '/login';
        url.searchParams.set('next', pathname);
        url.searchParams.set('error', 'session_expired');
        return NextResponse.redirect(url);
    }

    // Strategy 2: Check Supabase session
    const { user, response: supabaseResponse } = await checkSupabaseSession(request);
    if (user) {
        // Sysadmin check for /sysadmin routes (with in-memory LRU cache)
        if (pathname.startsWith('/sysadmin')) {
            const userId = (user as { id: string }).id;
            let isSysadmin = getSysadminCached(userId);

            if (isSysadmin === null) {
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
                const { data: profile } = await supabase
                    .from('developer_profiles')
                    .select('is_sysadmin')
                    .eq('auth_user_id', userId)
                    .maybeSingle();

                isSysadmin = !!profile?.is_sysadmin;
                setSysadminCached(userId, isSysadmin);
            }

            if (!isSysadmin) {
                return NextResponse.redirect(new URL('/dashboard', request.url));
            }
        }
        return supabaseResponse;
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

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // -----------------------------------------------------------------------
    // CSRF protection for mutating API requests (double-submit cookie check)
    // -----------------------------------------------------------------------
    if (
        pathname.startsWith('/api/') &&
        CSRF_PROTECTED_METHODS.has(request.method) &&
        !isCsrfExempt(pathname) &&
        !request.headers.get('authorization')?.startsWith('Bearer ')
    ) {
        const headerToken = request.headers.get(CSRF_HEADER);
        const sigCookie = request.cookies.get(CSRF_SIG_COOKIE)?.value;

        if (!headerToken || !sigCookie) {
            return NextResponse.json(
                { error: 'Missing CSRF token' },
                { status: 403 },
            );
        }

        const valid = await verifyCsrfToken(headerToken, sigCookie);
        if (!valid) {
            return NextResponse.json(
                { error: 'Invalid CSRF token' },
                { status: 403 },
            );
        }
    }

    // Authenticated app routes — server-side session check
    if (isAuthenticatedAppRoute(pathname)) {
        return await requireAppAuth(request);
    }

    // Developer portal: only gate key generation and playground behind auth.
    // All docs, codegen, and portal pages are public for developer evaluation.
    if (isGatedRoute(pathname) || pathname === '/developer/portal/keys') {
        return await requireAppAuth(request);
    }

    // Block non-FSMA verticals
    const verticalMatch = pathname.match(/^\/verticals\/([^/]+)/);
    if (verticalMatch && !ALLOWED_VERTICALS.includes(verticalMatch[1])) {
        return NextResponse.redirect(new URL('/', request.url));
    }

    // All /docs/* routes are public — no redirect needed.

    return NextResponse.next();
}

export const config = {
    matcher: [
        '/api/:path*',
        '/dashboard/:path*',
        '/admin/:path*',
        '/sysadmin/:path*',
        '/fsma/:path*',
        '/settings/:path*',
        '/onboarding/:path*',
        '/owner/:path*',
        '/verticals/:path*',
        '/docs/:path*',
        '/developer/:path*',
        '/developers/:path*',
        '/playground/:path*',
        '/api-keys/:path*',
        // Control Plane
        '/rules/:path*',
        '/records/:path*',
        '/exceptions/:path*',
        '/requests/:path*',
        '/identity/:path*',
        '/review/:path*',
        '/audit/:path*',
        '/readiness/:path*',
        '/incidents/:path*',
        '/controls/:path*',
        '/trace/:path*',
        // Compliance
        '/compliance/:path*',
        // Ingestion
        '/ingest/:path*',
    ],
};
