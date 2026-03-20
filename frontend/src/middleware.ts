import { NextRequest, NextResponse } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';
import { createServerClient } from '@supabase/ssr';

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

// Authenticated app routes — require a valid Supabase session.
// Client-side useEffect redirects are NOT sufficient because:
//   1. SSR/SSG HTML is served before JS runs (competitor can view page shell)
//   2. JavaScript can be disabled or redirect intercepted
//   3. API keys in localStorage are still sent by fetch() regardless
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
 * Check Supabase session and redirect to /login if missing.
 * For /sysadmin routes, also verify the is_sysadmin flag server-side.
 */
async function requireAppAuth(request: NextRequest): Promise<NextResponse> {
    let supabaseResponse = NextResponse.next({ request });

    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_SUPABASE_URL!,
        process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
        {
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
        }
    );

    const { data: { user } } = await supabase.auth.getUser();
    const { pathname } = request.nextUrl;

    if (!user) {
        const url = request.nextUrl.clone();
        url.pathname = '/login';
        url.searchParams.set('next', pathname);
        return NextResponse.redirect(url);
    }

    // MEDIUM #8: Server-side sysadmin role check — don't trust localStorage
    if (pathname.startsWith('/sysadmin')) {
        const { data: profile } = await supabase
            .from('developer_profiles')
            .select('is_sysadmin')
            .eq('auth_user_id', user.id)
            .single();

        if (!profile?.is_sysadmin) {
            return NextResponse.redirect(new URL('/dashboard', request.url));
        }
    }

    return supabaseResponse;
}

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Authenticated app routes — server-side session check (CRITICAL #1 + MEDIUM #8)
    if (isAuthenticatedAppRoute(pathname)) {
        return await requireAppAuth(request);
    }

    // Developer portal routes — full Supabase session check
    if (pathname.startsWith('/developer')) {
        return await updateSession(request);
    }

    // Gated dev routes — redirect to developer login
    if (isGatedRoute(pathname)) {
        return await updateSession(request);
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
