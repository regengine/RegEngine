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

/** Routes exempt from CSRF checks (pre-auth ceremonies, signed webhooks, and API-key routes).
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
export type CsrfExemptionRule = Readonly<{
    methods: readonly string[];
    path: string;
    match: 'exact' | 'segment-prefix' | 'regex';
}>;

/**
 * Reviewed route-and-method exemptions. A mutation is exempt only when both
 * its HTTP method and its full path match a rule. Segment prefixes enforce a
 * path boundary, so `/api/tools/verify-extra` cannot inherit an exemption for
 * `/api/tools/verify`.
 */
export const CSRF_EXEMPT_RULES: readonly CsrfExemptionRule[] = [
    // Pre-auth passwordless and passkey ceremonies. Registration, logout,
    // logout-all, and session revocation intentionally do not appear here.
    { methods: ['POST'], path: '/api/admin/auth/challenges', match: 'exact' },
    {
        methods: ['POST'],
        path: '^/api/admin/auth/challenges/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}/verify$',
        match: 'regex',
    },
    { methods: ['POST'], path: '/api/admin/auth/webauthn/login/generate-options', match: 'exact' },
    { methods: ['POST'], path: '/api/admin/auth/webauthn/login/verify', match: 'exact' },
    // Invite acceptance is authorized by the single-use opaque invite token.
    { methods: ['POST'], path: '/api/admin/auth/accept-invite', match: 'exact' },
    { methods: ['POST'], path: '/api/admin/v1/auth/accept-invite', match: 'exact' },
    // External senders authenticate webhooks with request signatures.
    { methods: ['POST', 'PUT', 'PATCH', 'DELETE'], path: '/api/webhooks', match: 'segment-prefix' },
    { methods: ['POST', 'PUT', 'PATCH', 'DELETE'], path: '/api/v1/webhooks', match: 'segment-prefix' },
    // These public surfaces use API keys, signed proof material, or caller-
    // supplied synthetic data rather than browser session cookies.
    { methods: ['POST', 'PUT', 'PATCH', 'DELETE'], path: '/api/v1/records', match: 'segment-prefix' },
    { methods: ['POST', 'PUT', 'PATCH', 'DELETE'], path: '/api/v1/fda', match: 'segment-prefix' },
    {
        methods: ['POST', 'PUT', 'PATCH', 'DELETE'],
        path: '/api/ingestion/api/v1/sandbox',
        match: 'segment-prefix',
    },
    {
        methods: ['POST', 'PUT', 'PATCH', 'DELETE'],
        path: '/api/ingestion/api/v1/proof',
        match: 'segment-prefix',
    },
    { methods: ['POST'], path: '/api/tools/check-access', match: 'exact' },
    { methods: ['POST'], path: '/api/tools/verify', match: 'exact' },
];

function pathMatchesRule(pathname: string, rule: CsrfExemptionRule): boolean {
    if (rule.match === 'exact') return pathname === rule.path;
    if (rule.match === 'segment-prefix') {
        return pathname === rule.path || pathname.startsWith(`${rule.path}/`);
    }
    return new RegExp(rule.path).test(pathname);
}

/** Check whether a request route and method are exempt from CSRF verification. */
export function isCsrfExempt(pathname: string, method: string): boolean {
    const normalizedMethod = method.toUpperCase();
    return CSRF_EXEMPT_RULES.some(
        (rule) => rule.methods.includes(normalizedMethod) && pathMatchesRule(pathname, rule),
    );
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
