/**
 * Shared route ownership for app chrome and middleware.
 *
 * Keep this list in sync with authenticated product routes. Public marketing,
 * docs, and free tools should not be added here.
 */
export const AUTHENTICATED_APP_ROUTE_PREFIXES = [
    '/dashboard',
    '/admin',
    '/sysadmin',
    '/fsma',
    '/settings',
    '/onboarding',
    '/owner',
    '/rules',
    '/records',
    '/exceptions',
    '/requests',
    '/identity',
    '/review',
    '/audit',
    '/incidents',
    '/controls',
    '/trace',
    '/compliance',
    '/ingest',
] as const;

const CHROMELESS_EXACT_ROUTES = new Set([
    '/mobile/capture',
    '/fsma/field-capture',
    '/login',
    '/forgot-password',
    '/reset-password',
    '/auth/verify',
]);

export function matchesRoutePrefix(pathname: string, prefixes: readonly string[]): boolean {
    return prefixes.some((route) => pathname === route || pathname.startsWith(`${route}/`));
}

export function isAuthenticatedAppRoute(pathname: string): boolean {
    return matchesRoutePrefix(pathname, AUTHENTICATED_APP_ROUTE_PREFIXES);
}

export function shouldHideMarketingChrome(pathname: string): boolean {
    return CHROMELESS_EXACT_ROUTES.has(pathname) || isAuthenticatedAppRoute(pathname);
}
