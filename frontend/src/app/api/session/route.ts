/**
 * Server-side session endpoint — HTTP-only cookie auth (CRITICAL #2 fix).
 *
 * This API route is the ONLY place where sensitive credentials (access token,
 * API key, admin key) are stored. They live in HTTP-only cookies that
 * JavaScript cannot read, so XSS attacks cannot exfiltrate them.
 *
 * Usage:
 *   POST   /api/session — set credentials (access_token, api_key, admin_key, tenant_id, user)
 *   GET    /api/session — return session info (user, tenant) WITHOUT exposing raw tokens
 *   DELETE /api/session — clear all session cookies (logout)
 *
 * Cookie settings: httpOnly, secure (prod), sameSite=lax, path=/,
 * maxAge=7d for remembered sessions or browser-session cookies otherwise.
 */
import { NextRequest, NextResponse } from 'next/server';
import { createServerClient } from '@supabase/ssr';
import { generateCsrfToken, signCsrfToken, CSRF_COOKIE, CSRF_SIG_COOKIE } from '@/lib/csrf';
import { getAdminTargets, shouldRetryAdminProxyResponse } from '@/lib/admin-targets';
import { decodeRegEngineClaims, extractRegEngineTenantId } from '@/lib/jwt-claims';

const SEVEN_DAYS = 60 * 60 * 24 * 7;
const AUTH_SESSION_COOKIE = '__Host-regengine_session';

type AuthMethod = 'email_otp' | 'webauthn' | 'sso';

type SessionUser = {
    id: string;
    email: string;
    is_sysadmin: boolean;
    status: string;
    role_name?: string;
    organization_id?: string | null;
    auth_method?: AuthMethod;
    permissions?: string[];
};

type AuthMeResponse = {
    user_id: string;
    email: string;
    organization_id: string | null;
    tenant_id: string | null;
    role: string | null;
    auth_method: AuthMethod;
};

function cookieOptionsFor(rememberSession: boolean) {
    const baseCookieOptions = {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax' as const,
        path: '/',
    };

    return rememberSession
        ? { ...baseCookieOptions, maxAge: SEVEN_DAYS }
        : baseCookieOptions;
}

export async function POST(request: NextRequest) {
    try {
        // RE-SEC-003: strict same-origin enforcement on POST /api/session.
        // /api/session is in CSRF_EXEMPT_PREFIXES (it bootstraps the CSRF
        // cookies on first login), so a cross-origin attacker holding their
        // own valid RegEngine JWT could otherwise log a victim's browser
        // into the attacker's tenant via login-CSRF / session fixation.
        // Origin header is reliable because the browser sets it on every
        // POST and JS cannot forge it cross-origin.
        const origin = request.headers.get('origin');
        const allowedOrigins = (process.env.ALLOWED_ORIGINS ?? '')
            .split(',')
            .map((s) => s.trim())
            .filter(Boolean);

        if (process.env.NODE_ENV === 'production' && allowedOrigins.length === 0) {
            console.error('[session] ALLOWED_ORIGINS not configured in production');
            return NextResponse.json({ error: 'Server misconfigured' }, { status: 500 });
        }

        if (process.env.NODE_ENV === 'production') {
            if (!origin || !allowedOrigins.includes(origin)) {
                return NextResponse.json(
                    { error: 'Cross-origin session POST rejected' },
                    { status: 403 },
                );
            }
        }

        const body = await request.json();
        const { access_token, api_key, admin_key, tenant_id, user, remember_me } = body;
        const cookieOptions = cookieOptionsFor(remember_me !== false);

        // Decode-only — the admin backend owns JWTKeyRegistry and remains
        // the authoritative verifier. We extract the tenant_id claim for
        // the cookie/body cross-check; signature trust comes from the
        // backend on every authenticated proxy call.
        let claimedTenantId: string | null = null;
        if (isUsableCredential(access_token)) {
            const payload = decodeRegEngineClaims(access_token);
            if (!payload) {
                return NextResponse.json({ error: 'Invalid session token' }, { status: 401 });
            }
            claimedTenantId = extractRegEngineTenantId(payload);
        } else if (isUsableCredential(tenant_id)) {
            const existingAccessToken = request.cookies.get('re_access_token')?.value;
            if (isUsableCredential(existingAccessToken)) {
                const payload = decodeRegEngineClaims(existingAccessToken);
                if (!payload) {
                    return NextResponse.json({ error: 'Invalid existing session token' }, { status: 401 });
                }
                claimedTenantId = extractRegEngineTenantId(payload);
            }
        }

        if (claimedTenantId && isUsableCredential(tenant_id) && tenant_id !== claimedTenantId) {
            return NextResponse.json(
                { error: 'Tenant context does not match authenticated session' },
                { status: 403 },
            );
        }

        const resolvedTenantId = isUsableCredential(tenant_id) ? tenant_id : claimedTenantId;

        const response = NextResponse.json({ ok: true });

        if (isUsableCredential(access_token)) {
            if (!isUsableCredential(api_key)) {
                response.cookies.delete('re_api_key');
            }
            if (!isUsableCredential(admin_key)) {
                response.cookies.delete('re_admin_key');
            }
        }

        if (isUsableCredential(access_token)) {
            response.cookies.set('re_access_token', access_token, cookieOptions);
        }
        if (isUsableCredential(api_key)) {
            response.cookies.set('re_api_key', api_key, cookieOptions);
        }
        if (isUsableCredential(admin_key)) {
            response.cookies.set('re_admin_key', admin_key, cookieOptions);
        }
        if (resolvedTenantId) {
            response.cookies.set('re_tenant_id', resolvedTenantId, {
                ...cookieOptions,
                httpOnly: false, // tenant_id is not sensitive — UI reads it
            });
        }
        if (user) {
            response.cookies.set('re_user', JSON.stringify(user), {
                ...cookieOptions,
                httpOnly: false, // client needs user info for UI rendering
            });
        }

        // CSRF double-submit cookies — set on every session POST so the
        // client always has a valid token after login / credential update.
        const csrfToken = generateCsrfToken();
        const csrfSig = await signCsrfToken(csrfToken);

        response.cookies.set(CSRF_COOKIE, csrfToken, {
            ...cookieOptions,
            httpOnly: false, // JS must read this to send as X-CSRF-Token header
        });
        response.cookies.set(CSRF_SIG_COOKIE, csrfSig, cookieOptions);

        return response;
    } catch {
        return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
    }
}

function isUsableCredential(value: unknown): value is string {
    return typeof value === 'string' && value.trim().length > 0 && value !== 'cookie-managed';
}

function hasSupabaseSessionCookies(request: NextRequest): boolean {
    return request.cookies.getAll().some((cookie) => cookie.name.startsWith('sb-'));
}

async function getSupabaseSessionInfo(request: NextRequest): Promise<{
    tenant_id: string | null;
    user: SessionUser;
} | null> {
    const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const supabaseKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    if (!supabaseUrl || !supabaseKey || !hasSupabaseSessionCookies(request)) {
        return null;
    }

    try {
        const supabase = createServerClient(supabaseUrl, supabaseKey, {
            cookies: {
                getAll() {
                    return request.cookies.getAll();
                },
                setAll() {
                    // /api/session GET only mirrors state; middleware handles
                    // Supabase auth cookie refreshes.
                },
            },
        });
        const {
            data: { user },
            error,
        } = await supabase.auth.getUser();
        if (error || !user) return null;

        const metadata = {
            ...(user.user_metadata || {}),
            ...(user.app_metadata || {}),
        } as Record<string, unknown>;
        const permissions = Array.isArray(metadata.permissions)
            ? metadata.permissions.filter((permission): permission is string => typeof permission === 'string')
            : [];
        const roleName = typeof metadata.role_name === 'string'
            ? metadata.role_name
            : typeof metadata.role === 'string'
                ? metadata.role
                : undefined;
        const tenantId = typeof metadata.tenant_id === 'string' ? metadata.tenant_id : null;

        return {
            tenant_id: tenantId,
            user: {
                id: user.id,
                email: user.email || '',
                is_sysadmin: Boolean(metadata.is_sysadmin),
                status: typeof metadata.status === 'string' ? metadata.status : 'active',
                role_name: roleName,
                permissions,
            },
        };
    } catch {
        return null;
    }
}

function isAuthMethod(value: unknown): value is AuthMethod {
    return value === 'email_otp' || value === 'webauthn' || value === 'sso';
}

function parseAuthMeResponse(payload: unknown): AuthMeResponse | null {
    if (!payload || typeof payload !== 'object') return null;
    const body = payload as Record<string, unknown>;
    if (typeof body.user_id !== 'string') return null;
    if (typeof body.email !== 'string') return null;
    if (!isAuthMethod(body.auth_method)) return null;

    return {
        user_id: body.user_id,
        email: body.email,
        organization_id: typeof body.organization_id === 'string' ? body.organization_id : null,
        tenant_id: typeof body.tenant_id === 'string' ? body.tenant_id : null,
        role: typeof body.role === 'string' ? body.role : null,
        auth_method: body.auth_method,
    };
}

async function getOpaqueSessionInfo(request: NextRequest): Promise<{
    tenant_id: string | null;
    auth_method: AuthMethod;
    user: SessionUser;
} | null> {
    const sessionToken = request.cookies.get(AUTH_SESSION_COOKIE)?.value;
    if (!isUsableCredential(sessionToken)) return null;

    const cookieHeader = `${AUTH_SESSION_COOKIE}=${sessionToken}`;

    for (const target of getAdminTargets()) {
        const baseUrl = target.replace(/\/+$/, '');
        try {
            const response = await fetch(`${baseUrl}/auth/me`, {
                method: 'GET',
                headers: {
                    accept: 'application/json',
                    cookie: cookieHeader,
                },
                cache: 'no-store',
            });

            if (shouldRetryAdminProxyResponse(response, 'auth/me')) {
                continue;
            }
            if (response.status === 401 || response.status === 403) {
                return null;
            }
            if (!response.ok) {
                continue;
            }

            const profile = parseAuthMeResponse(await response.json().catch(() => null));
            if (!profile) {
                return null;
            }

            return {
                // Prefer the real tenant_id; fall back to organization_id only
                // for backward compatibility during rollout (older backends
                // that predate the tenant_id field on /auth/me).
                tenant_id: profile.tenant_id ?? profile.organization_id,
                auth_method: profile.auth_method,
                user: {
                    id: profile.user_id,
                    email: profile.email,
                    is_sysadmin: false,
                    status: 'active',
                    role_name: profile.role || undefined,
                    organization_id: profile.organization_id,
                    auth_method: profile.auth_method,
                    permissions: [],
                },
            };
        } catch {
            // Try the next configured admin target.
        }
    }

    return null;
}

export async function GET(request: NextRequest) {
    const access_token = request.cookies.get('re_access_token')?.value || null;
    const api_key = request.cookies.get('re_api_key')?.value || null;
    const admin_key = request.cookies.get('re_admin_key')?.value || null;
    const tenant_id = request.cookies.get('re_tenant_id')?.value || null;
    const userCookie = request.cookies.get('re_user')?.value || null;

    let user = null;
    if (userCookie) {
        try {
            user = JSON.parse(userCookie);
        } catch {
            // Corrupt cookie — ignore
        }
    }

    const opaqueSession = access_token ? null : await getOpaqueSessionInfo(request);
    const supabaseSession = access_token || opaqueSession ? null : await getSupabaseSessionInfo(request);
    const resolvedTenantId = opaqueSession ? opaqueSession.tenant_id : tenant_id || supabaseSession?.tenant_id || null;
    const resolvedUser = opaqueSession ? opaqueSession.user : user || supabaseSession?.user || null;
    const resolvedAuthMethod = opaqueSession?.auth_method || null;
    const isAuthenticated = Boolean(access_token || opaqueSession || supabaseSession);

    // NEVER return raw tokens/keys — only booleans indicating their presence
    const response = NextResponse.json({
        authenticated: isAuthenticated,
        has_api_key: !!api_key,
        has_admin_key: !!admin_key,
        has_credentials: !!(access_token || opaqueSession || api_key || admin_key || supabaseSession),
        tenant_id: resolvedTenantId,
        auth_method: resolvedAuthMethod,
        user: resolvedUser,
    });

    if (resolvedTenantId && (opaqueSession?.tenant_id || !tenant_id)) {
        response.cookies.set('re_tenant_id', resolvedTenantId, {
            ...cookieOptionsFor(true),
            httpOnly: false,
        });
    } else if (opaqueSession && tenant_id) {
        response.cookies.delete('re_tenant_id');
    }
    if (opaqueSession?.user || (!userCookie && resolvedUser)) {
        response.cookies.set('re_user', JSON.stringify(resolvedUser), {
            ...cookieOptionsFor(true),
            httpOnly: false,
        });
    }

    // CSRF bootstrap: issue the double-submit cookie pair on the first GET so
    // the subsequent POST /api/session (and every other mutating request) can
    // carry a valid X-CSRF-Token header. Before this, /api/session had to be
    // in CSRF_EXEMPT_PREFIXES because there was no token issued yet at login
    // time. Setting cookies here closes that bootstrap gap and lets the
    // exemption come out — the auth provider's hydrate() effect calls GET
    // /api/session on every page mount, so any client that ever reaches the
    // login form has these cookies in place before submitting.
    //
    // Idempotent: if the cookies already exist, we leave them alone.
    if (!request.cookies.get(CSRF_COOKIE) || !request.cookies.get(CSRF_SIG_COOKIE)) {
        const csrfToken = generateCsrfToken();
        const csrfSig = await signCsrfToken(csrfToken);

        response.cookies.set(CSRF_COOKIE, csrfToken, {
            ...cookieOptionsFor(true),
            httpOnly: false, // JS must read this to send as X-CSRF-Token header
        });
        response.cookies.set(CSRF_SIG_COOKIE, csrfSig, cookieOptionsFor(true));
    }

    return response;
}

export async function DELETE(request: NextRequest) {
    const accessToken = request.cookies.get('re_access_token')?.value;
    if (isUsableCredential(accessToken)) {
        await revokeBackendSession(accessToken);
    }

    const response = NextResponse.json({ ok: true });
    response.cookies.delete('re_access_token');
    response.cookies.delete('re_api_key');
    response.cookies.delete('re_admin_key');
    response.cookies.delete('re_tenant_id');
    response.cookies.delete('re_user');
    response.cookies.delete(AUTH_SESSION_COOKIE);
    response.cookies.delete(CSRF_COOKIE);
    response.cookies.delete(CSRF_SIG_COOKIE);
    return response;
}

async function revokeBackendSession(accessToken: string): Promise<void> {
    for (const target of getAdminTargets()) {
        try {
            const response = await fetch(`${target}/auth/logout`, {
                method: 'POST',
                headers: {
                    Authorization: `Bearer ${accessToken}`,
                },
            });

            if (!shouldRetryAdminProxyResponse(response, 'auth/logout')) {
                return;
            }
        } catch {
            // Best effort only: local cookie teardown must still complete.
        }
    }
}
