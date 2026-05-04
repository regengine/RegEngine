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
 * Cookie settings: httpOnly, secure (prod), sameSite=lax, path=/, maxAge=7d
 */
import { NextRequest, NextResponse } from 'next/server';
import { jwtVerify } from 'jose';
import { generateCsrfToken, signCsrfToken, CSRF_COOKIE, CSRF_SIG_COOKIE } from '@/lib/csrf';
import { getVerificationKeys } from '@/lib/jwt-keys';

const SEVEN_DAYS = 60 * 60 * 24 * 7;

const COOKIE_OPTIONS = {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: SEVEN_DAYS,
};

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { access_token, api_key, admin_key, tenant_id, user } = body;

        let verifiedTenantId: string | null = null;
        if (isUsableCredential(access_token)) {
            const payload = await verifyRegEngineSessionToken(access_token);
            if (!payload) {
                return NextResponse.json({ error: 'Invalid session token' }, { status: 401 });
            }
            verifiedTenantId = extractJwtTenantId(payload);
        } else if (isUsableCredential(tenant_id)) {
            const existingAccessToken = request.cookies.get('re_access_token')?.value;
            if (isUsableCredential(existingAccessToken)) {
                const payload = await verifyRegEngineSessionToken(existingAccessToken);
                if (!payload) {
                    return NextResponse.json({ error: 'Invalid existing session token' }, { status: 401 });
                }
                verifiedTenantId = extractJwtTenantId(payload);
            }
        }

        if (verifiedTenantId && isUsableCredential(tenant_id) && tenant_id !== verifiedTenantId) {
            return NextResponse.json(
                { error: 'Tenant context does not match authenticated session' },
                { status: 403 },
            );
        }

        const resolvedTenantId = isUsableCredential(tenant_id) ? tenant_id : verifiedTenantId;

        const response = NextResponse.json({ ok: true });

        if (access_token) {
            response.cookies.set('re_access_token', access_token, COOKIE_OPTIONS);
        }
        if (api_key) {
            response.cookies.set('re_api_key', api_key, COOKIE_OPTIONS);
        }
        if (admin_key) {
            response.cookies.set('re_admin_key', admin_key, COOKIE_OPTIONS);
        }
        if (resolvedTenantId) {
            response.cookies.set('re_tenant_id', resolvedTenantId, {
                ...COOKIE_OPTIONS,
                httpOnly: false, // tenant_id is not sensitive — UI reads it
            });
        }
        if (user) {
            response.cookies.set('re_user', JSON.stringify(user), {
                ...COOKIE_OPTIONS,
                httpOnly: false, // client needs user info for UI rendering
            });
        }

        // CSRF double-submit cookies — set on every session POST so the
        // client always has a valid token after login / credential update.
        const csrfToken = generateCsrfToken();
        const csrfSig = await signCsrfToken(csrfToken);

        response.cookies.set(CSRF_COOKIE, csrfToken, {
            ...COOKIE_OPTIONS,
            httpOnly: false, // JS must read this to send as X-CSRF-Token header
        });
        response.cookies.set(CSRF_SIG_COOKIE, csrfSig, COOKIE_OPTIONS);

        return response;
    } catch {
        return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
    }
}

async function verifyRegEngineSessionToken(token: string): Promise<Record<string, unknown> | null> {
    const keys = getVerificationKeys();
    if (keys.length === 0) return null;

    for (const key of keys) {
        try {
            const { payload } = await jwtVerify(token, key.secret, {
                algorithms: ['HS256'],
            });
            if (isRegEngineSessionPayload(payload as Record<string, unknown>)) {
                return payload as Record<string, unknown>;
            }
            return null;
        } catch {
            // Try the next configured key during rotation.
        }
    }
    return null;
}

function extractJwtTenantId(payload: Record<string, unknown>): string | null {
    const value = payload.tenant_id ?? payload.tid;
    return typeof value === 'string' && value.length > 0 ? value : null;
}

function isUsableCredential(value: unknown): value is string {
    return typeof value === 'string' && value.trim().length > 0 && value !== 'cookie-managed';
}

function isRegEngineSessionPayload(payload: Record<string, unknown>): boolean {
    const audience = payload.aud;
    if (typeof audience === 'string' && audience !== 'regengine-api') return false;
    if (Array.isArray(audience) && !audience.includes('regengine-api')) return false;
    const issuer = payload.iss;
    if (typeof issuer === 'string' && issuer !== 'regengine-admin') return false;
    return true;
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

    // NEVER return raw tokens/keys — only booleans indicating their presence
    return NextResponse.json({
        authenticated: !!access_token,
        has_api_key: !!api_key,
        has_admin_key: !!admin_key,
        has_credentials: !!(access_token || api_key || admin_key),
        tenant_id,
        user,
    });
}

export async function DELETE() {
    const response = NextResponse.json({ ok: true });
    response.cookies.delete('re_access_token');
    response.cookies.delete('re_api_key');
    response.cookies.delete('re_admin_key');
    response.cookies.delete('re_tenant_id');
    response.cookies.delete('re_user');
    response.cookies.delete(CSRF_COOKIE);
    response.cookies.delete(CSRF_SIG_COOKIE);
    return response;
}
