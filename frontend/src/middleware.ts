import { NextRequest, NextResponse } from 'next/server';

// Allowed vertical paths that bypass the waitlist
const ALLOWED_VERTICALS = ['food-safety', 'fsma', 'fsma-204'];

// Allowed root docs paths (these are generic or specifically permitted)
const ALLOWED_DOCS_ROOT = [
    '/docs',
    '/docs/api',
    '/docs/authentication',
    '/docs/changelog',
    '/docs/errors',
    '/docs/fsma-204',
    '/docs/quickstart',
    '/docs/rate-limits',
    '/docs/sdks',
    '/docs/webhooks'
];

export function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Check if the route is under /verticals/
    const verticalMatch = pathname.match(/^\/verticals\/([^/]+)/);
    if (verticalMatch) {
        const verticalPathSegment = verticalMatch[1];
        if (!ALLOWED_VERTICALS.includes(verticalPathSegment)) {
            // Unreleased vertical -> Rewrite to waitlist gate
            console.log(`[Middleware] Rewriting unreleased vertical access: ${pathname} -> /waitlist`);
            const url = request.nextUrl.clone();
            url.pathname = '/waitlist';
            url.searchParams.set('feature', verticalPathSegment);
            return NextResponse.rewrite(url);
        }
    }

    // Check if the route is a specific unreleased industry doc: /docs/[industry]
    const docsMatch = pathname.match(/^\/docs\/([^/]+)/);
    if (docsMatch && !ALLOWED_DOCS_ROOT.includes(pathname)) {
        const docsPathSegment = docsMatch[1];
        if (!ALLOWED_VERTICALS.includes(docsPathSegment)) {
            // Unreleased doc -> Rewrite to waitlist gate
            console.log(`[Middleware] Rewriting unreleased docs access: ${pathname} -> /waitlist`);
            const url = request.nextUrl.clone();
            url.pathname = '/waitlist';
            url.searchParams.set('feature', docsPathSegment);
            return NextResponse.rewrite(url);
        }
    }

    return NextResponse.next();
}

export const config = {
    // Only run middleware on /verticals/* and /docs/*
    matcher: ['/verticals/:path*', '/docs/:path*'],
};
