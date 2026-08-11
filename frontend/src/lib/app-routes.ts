/**
 * Shared route ownership for app chrome and middleware.
 *
 * Keep this list in sync with authenticated product routes. Public marketing,
 * docs, and free tools should not be added here.
 */
export const AUTHENTICATED_APP_ROUTE_PREFIXES = [
  "/dashboard",
  "/admin",
  "/sysadmin",
  "/fsma",
  "/settings",
  "/onboarding",
  "/rules",
  "/records",
  "/exceptions",
  "/requests",
  "/reports",
  "/identity",
  "/review",
  "/audit",
  "/incidents",
  "/controls",
  "/trace",
  "/compliance",
  "/ingest",
] as const;

/**
 * Routes that carry their own chrome (the developer portal shell) but are NOT
 * middleware-auth-gated app routes — keep them out of
 * AUTHENTICATED_APP_ROUTE_PREFIXES, which proxy.ts uses for server-side auth.
 * Note "/developer" does not prefix-match "/developers" (the public marketing
 * page), which keeps its marketing header.
 */
export const SELF_CHROMED_ROUTE_PREFIXES = ["/developer"] as const;

const CHROMELESS_EXACT_ROUTES = new Set([
  "/mobile/capture",
  "/fsma/field-capture",
  "/login",
  "/accept-invite",
  "/auth/verify",
]);

export function matchesRoutePrefix(
  pathname: string,
  prefixes: readonly string[],
): boolean {
  return prefixes.some(
    (route) => pathname === route || pathname.startsWith(`${route}/`),
  );
}

export function isAuthenticatedAppRoute(pathname: string): boolean {
  return matchesRoutePrefix(pathname, AUTHENTICATED_APP_ROUTE_PREFIXES);
}

export function shouldHideMarketingChrome(pathname: string): boolean {
  return (
    CHROMELESS_EXACT_ROUTES.has(pathname) ||
    isAuthenticatedAppRoute(pathname) ||
    matchesRoutePrefix(pathname, SELF_CHROMED_ROUTE_PREFIXES)
  );
}
