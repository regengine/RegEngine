/**
 * CSRF Protection — Double-Submit Cookie Pattern
 *
 * Defense-in-depth on top of SameSite=Lax cookies. State-changing requests
 * (POST/PUT/PATCH/DELETE) to /api/* must include an X-CSRF-Token header
 * whose value matches the HMAC signature stored in the re_csrf_sig cookie.
 *
 * Token flow:
 *   1. POST /api/session sets two cookies:
 *      - re_csrf       (httpOnly: false, JS-readable) — random token
 *      - re_csrf_sig   (httpOnly: true)               — HMAC-SHA256(token, secret)
 *   2. Client reads re_csrf from document.cookie and sends it as X-CSRF-Token header
 *   3. Middleware verifies: HMAC(headerValue, secret) === re_csrf_sig cookie
 */

// ---------------------------------------------------------------------------
// Server-side helpers (used in route handlers and middleware)
// ---------------------------------------------------------------------------

const CSRF_COOKIE = 're_csrf';
const CSRF_SIG_COOKIE = 're_csrf_sig';
const CSRF_HEADER = 'x-csrf-token';

export { CSRF_COOKIE, CSRF_SIG_COOKIE, CSRF_HEADER };

/** Get the CSRF signing secret.
 *
 *  Production REQUIRES a dedicated CSRF_SECRET — reusing AUTH_SECRET_KEY (the
 *  JWT signing key) for HMAC violates cryptographic key separation
 *  (NIST SP 800-57 §5.2). The AUTH_SECRET_KEY fallback is preserved only for
 *  dev/test convenience. RE-SEC-005.
 */
function getSecret(): string {
    const secret = process.env.CSRF_SECRET || '';
    if (!secret) {
        if (process.env.NODE_ENV === 'production') {
            console.error('[csrf] CSRF_SECRET not set in production — all mutating requests will be rejected');
            return '';
        }
        return process.env.AUTH_SECRET_KEY || '';
    }
    return secret;
}

/** Generate a random CSRF token. */
export function generateCsrfToken(): string {
    return crypto.randomUUID();
}

/** Compute HMAC-SHA256 of a token using the server secret. */
export async function signCsrfToken(token: string): Promise<string> {
    const secret = getSecret();
    if (!secret) return '';

    const encoder = new TextEncoder();
    const key = await crypto.subtle.importKey(
        'raw',
        encoder.encode(secret),
        { name: 'HMAC', hash: 'SHA-256' },
        false,
        ['sign'],
    );
    const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(token));
    // Encode as hex string for cookie storage
    return Array.from(new Uint8Array(signature))
        .map(b => b.toString(16).padStart(2, '0'))
        .join('');
}

/** Verify that a token matches its HMAC signature.
 *
 *  Fail-closed in production: if no CSRF secret is configured we cannot
 *  verify the token, so we reject the request. In dev/test we allow
 *  through with a warning so local development doesn't require the env
 *  var to be set.
 */
export async function verifyCsrfToken(token: string, signature: string): Promise<boolean> {
    if (!token || !signature) return false;
    const secret = getSecret();
    if (!secret) {
        if (process.env.NODE_ENV === 'production') {
            console.error('[csrf] CSRF_SECRET / AUTH_SECRET_KEY not set — rejecting mutating request');
            return false;
        }
        return true;
    }
    const expected = await signCsrfToken(token);
    // Constant-time comparison
    if (expected.length !== signature.length) return false;
    let mismatch = 0;
    for (let i = 0; i < expected.length; i++) {
        mismatch |= expected.charCodeAt(i) ^ signature.charCodeAt(i);
    }
    return mismatch === 0;
}

// ---------------------------------------------------------------------------
// Client-side helpers (browser only)
// ---------------------------------------------------------------------------

/** Read the re_csrf cookie value from document.cookie (JS-readable). */
export function getCsrfTokenFromCookie(): string {
    if (typeof document === 'undefined') return '';
    const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${CSRF_COOKIE}=([^;]*)`));
    return match ? decodeURIComponent(match[1]) : '';
}

/** HTTP methods that require CSRF validation. */
export const CSRF_PROTECTED_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

/** Paths exempt from CSRF checks (auth callbacks, webhooks, public sandbox, public tools).
 *
 *  Keep this list narrow. Broad prefixes like /api/tools/ silently exempt
 *  every future handler placed there — list the specific public endpoints
 *  instead so adding a new /api/tools/* route is a deliberate decision.
 *
 *  /api/session is intentionally NOT exempt. GET /api/session bootstraps the
 *  CSRF cookie pair on first load (idempotent), so by the time the client
 *  POSTs to /api/session (login, credential update) the double-submit cookie
 *  is already in place and the request carries a valid X-CSRF-Token header
 *  like every other mutating endpoint. The Origin allowlist on POST
 *  /api/session (RE-SEC-003) remains as defense-in-depth.
 */
export const CSRF_EXEMPT_PREFIXES = [
    '/api/auth/',
    '/api/admin/auth/',
    // Public invite acceptance arrives without an authenticated session and is
    // authorized by the opaque invite token itself.
    '/api/admin/v1/auth/accept-invite',
    // Both webhook paths: /api/webhooks/* for local handlers, /api/v1/webhooks/*
    // for the next.config.js rewrite to the ingestion service. External senders
    // authenticate via HMAC signatures, not Bearer tokens, so they don't hit
    // the Bearer bypass in src/proxy.ts.
    '/api/webhooks/',
    '/api/v1/webhooks/',
    // Public read API rewrites (next.config.js) — API-key callers send
    // X-RegEngine-API-Key, not session cookies, so the double-submit check
    // can never pass for them; the backend routers are the auth layer.
    // Trailing-slash prefixes are safe here: the only bare paths are
    // GET /api/v1/records (list) and the /api/v1/fda prefix root (no route),
    // and GETs are never CSRF-checked (CSRF_PROTECTED_METHODS).
    '/api/v1/records/',
    '/api/v1/fda/',
    // Public ingestion endpoints that are unauthenticated, tenantless, and
    // operate only on caller-supplied or frozen synthetic data.
    '/api/ingestion/api/v1/sandbox/',
    '/api/ingestion/api/v1/proof/',
    // Public unauthenticated tool endpoints — add new entries explicitly.
    '/api/inflow-lab/',
    '/api/tools/check-access',
    '/api/tools/verify',
];

/** Check whether a request path is exempt from CSRF verification. */
export function isCsrfExempt(pathname: string): boolean {
    return CSRF_EXEMPT_PREFIXES.some(prefix => pathname.startsWith(prefix));
}

/**
 * Returns headers to attach to mutating API requests.
 * Usage: `{ ...getCsrfHeaders() }` in your fetch/axios config.
 */
export function getCsrfHeaders(): Record<string, string> {
    const token = getCsrfTokenFromCookie();
    if (!token) return {};
    return { [CSRF_HEADER]: token };
}
