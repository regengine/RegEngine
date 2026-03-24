import { NextRequest, NextResponse } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';
import { createServerClient } from '@supabase/ssr';
import { jwtVerify } from 'jose';

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
        console.warn('[middleware] AUTH_SECRET_KEY is not set — skipping RegEngine JWT verification. Falling back to Supabase auth.');
        return null;
    }
    try {
        const secretKey = new TextEncoder().encode(secret);
        const { payload } = await jwtVerify(token, secretKey, {
            algorithms: ['HS256'],
        });
        return payload as Record<string, unknown>;
    } catch {
        // Token expired, invalid signature, malformed, etc.
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
            // Token is valid — check sysadmin for /sysadmin routes
            if (pathname.startsWith('/sysadmin')) {
                // The JWT doesn't carry is_sysadmin, so we need a secondary check.
                // For now, allow access if they have a valid token — the page-level
                // check against the backend (/auth/me) will enforce sysadmin.
                // This is acceptable because /sysadmin page already verifies server-side.
            }
            return NextResponse.next({ request });
        }
        // Token invalid/expired — fall through to Supabase check
    }

    // Strategy 2: Check Supabase session
    const { user, response: supabaseResponse } = await checkSupabaseSession(request);
    if (user) {
        // Sysadmin check for /sysadmin routes
        if (pathname.startsWith('/sysadmin')) {
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
                .eq('auth_user_id', (user as { id: string }).id)
                .single();

            if (!profile?.is_sysadmin) {
                return NextResponse.redirect(new URL('/dashboard', request.url));
            }
        }
        return supabaseResponse;
    }

    // Neither auth method succeeded — redirect to login
    const url = request.nextUrl.clone();
    url.pathname = '/login';
    url.searchParams.set('next', pathname);

    // Signal the reason so the login page can display a message and
    // avoid auto-redirecting back into a loop.
    if (!process.env.AUTH_SECRET_KEY) {
        url.searchParams.set('error', 'auth_config');
    } else {
        url.searchParams.set('error', 'session_expired');
    }

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
    ],
};
