import { NextRequest, NextResponse } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';
import { createServerClient } from '@supabase/ssr';
import { jwtVerify } from 'jose';

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

// Only FSMA verticals are supported — all others redirect to home.
const ALLOWED_VERTICALS = ['food-safety', 'fsma', 'fsma-204'];

// Developer-facing routes that require portal auth
const GATED_DEV_ROUTES = [
    '/developer',
    '/developers',
    '/docs/api',
    '/docs/authentication',
    '/docs/quickstart',
    '/docs/sdks',
    '/docs/webhooks',
    '/docs/rate-limits',
    '/docs/errors',
    '/docs/changelog',
    '/playground',
    '/api-keys',
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

// Public docs that remain accessible (product/compliance, not dev-facing)
const PUBLIC_DOCS = [
    '/docs',
    '/docs/fsma-204',
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
 * Returns the decoded payload if valid, null otherwise.
 */
async function verifyRegEngineToken(token: string): Promise<Record<string, unknown> | null> {
    const secret = process.env.AUTH_SECRET_KEY;
    if (!secret) {
        console.error(
            '[middleware] AUTH_SECRET_KEY is NOT set on this deployment. ' +
            'JWT verification is impossible — all authenticated routes will fail. ' +
            'Set AUTH_SECRET_KEY in Vercel env vars (must match the backend Railway value).'
        );
        return null;
    }
    try {
        const secretKey = new TextEncoder().encode(secret);
        const { payload } = await jwtVerify(token, secretKey, {
            algorithms: ['HS256'],
        });
        return payload as Record<string, unknown>;
    } catch (err) {
        // Log the specific failure reason to help diagnose key mismatches
        const message = err instanceof Error ? err.message : 'unknown';
        console.warn(
            `[middleware] JWT verification failed: ${message}. ` +
            'If "signature verification failed", AUTH_SECRET_KEY on Vercel does not match the backend.'
        );
        return null;
    }
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
            return NextResponse.next({ request });
        }
        // Token exists but verification failed.
        // Before redirecting to login, check if we have other valid credentials.
        // This handles the case where JWT expired but user has active localStorage
        // session or Supabase session — we don't want to kick them out.
        const hasApiKey = request.cookies.get('re_api_key')?.value;
        const hasTenantId = request.cookies.get('re_tenant_id')?.value;
        if (hasApiKey && hasTenantId) {
            // User has valid API credentials — let them through.
            // The page-level useAuth() will handle token refresh.
            console.info('[middleware] JWT expired but API credentials present — allowing access');
            return NextResponse.next({ request });
        }
        // Fall through to Supabase check
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
                    .single();

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
    // Only show "session expired" when a token actually existed but failed.
    if (!process.env.AUTH_SECRET_KEY) {
        url.searchParams.set('error', 'auth_config');
    } else if (reToken) {
        // Token exists but verification failed — likely expired or key mismatch
        url.searchParams.set('error', 'session_expired');
    }
    // No token at all = first visit. Don't set any error — just show login form.

    return NextResponse.redirect(url);
}

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Authenticated app routes — server-side session check
    if (isAuthenticatedAppRoute(pathname)) {
        return await requireAppAuth(request);
    }

    // Developer portal routes — same dual auth as app routes
    if (pathname.startsWith('/developer') || isGatedRoute(pathname)) {
        return await requireAppAuth(request);
    }

    // Block non-FSMA verticals
    const verticalMatch = pathname.match(/^\/verticals\/([^/]+)/);
    if (verticalMatch && !ALLOWED_VERTICALS.includes(verticalMatch[1])) {
        return NextResponse.redirect(new URL('/', request.url));
    }

    // Docs routing: only public docs pass through, others redirect
    if (pathname.startsWith('/docs/')) {
        if (!isPublicDoc(pathname) && !ALLOWED_VERTICALS.includes(pathname.split('/')[2])) {
            return NextResponse.redirect(new URL('/docs/fsma-204', request.url));
        }
    }

    return NextResponse.next();
}

export const config = {
    matcher: [
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
