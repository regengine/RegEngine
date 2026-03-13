import { NextRequest, NextResponse } from 'next/server';

// Only FSMA verticals are supported — all others redirect to home.
const ALLOWED_VERTICALS = ['food-safety', 'fsma', 'fsma-204'];

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
    '/docs/webhooks',
];

export function middleware(request: NextRequest) {
    const { pathname } = request.nextUrl;

    // Block non-FSMA verticals
    const verticalMatch = pathname.match(/^\/verticals\/([^/]+)/);
    if (verticalMatch && !ALLOWED_VERTICALS.includes(verticalMatch[1])) {
        return NextResponse.redirect(new URL('/', request.url));
    }

    // Block non-FSMA doc verticals
    const docsMatch = pathname.match(/^\/docs\/([^/]+)/);
    if (docsMatch && !ALLOWED_DOCS_ROOT.includes(pathname) && !ALLOWED_VERTICALS.includes(docsMatch[1])) {
        return NextResponse.redirect(new URL('/docs/fsma-204', request.url));
    }

    return NextResponse.next();
}

export const config = {
    matcher: ['/verticals/:path*', '/docs/:path*'],
};
