import { NextRequest, NextResponse } from 'next/server';
import { updateSession } from '@/lib/supabase/middleware';

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

export async function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

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
        '/verticals/:path*',
        '/docs/:path*',
        '/developer/:path*',
        '/developers/:path*',
        '/playground/:path*',
        '/api-keys/:path*',
    ],
};
