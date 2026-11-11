/**
 * Which ingestion paths belong to the public supplier portal.
 *
 * Two places decide this and they must agree:
 *  - the ingestion BFF proxy (src/app/api/ingestion/[...path]/route.ts)
 *    forwards these paths without a session;
 *  - the CSRF gate (src/lib/csrf.ts) lets the two POSTs through without a
 *    CSRF token, still requiring same origin.
 * A path the CSRF gate exempts must be one the proxy treats as public, or a
 * supplier would pass one gate and be stopped at the other. Both read from
 * here; src/__tests__/lib/supplier-portal-paths.test.ts pins the relation.
 */

/** Browser-facing prefix of the ingestion BFF proxy. */
export const INGESTION_PROXY_PREFIX = '/api/ingestion/';

/**
 * Proxy-relative path (no leading slash) of a public portal call:
 * `api/v1/portal/{token}`, optionally `/preflight` or `/submit`. `links` is
 * link management, which is authenticated.
 */
export function isPublicSupplierPortalPath(path: string): boolean {
    const match = path.match(/^api\/v1\/portal\/([^/]+)(?:\/(submit|preflight))?$/);
    return Boolean(match && match[1] !== 'links');
}

/**
 * Full browser path of a portal POST that carries no CSRF token:
 * `/api/ingestion/api/v1/portal/{token}/(preflight|submit)`. Narrower than
 * isPublicSupplierPortalPath on purpose: it also requires a token-shaped
 * segment. Link tokens are secrets.token_urlsafe(16), 22 URL-safe characters;
 * the length floor keeps the literal segment "links" out.
 */
export const SUPPLIER_PORTAL_MUTATION_PATTERN =
    '^/api/ingestion/api/v1/portal/[A-Za-z0-9_-]{16,128}/(?:preflight|submit)$';
