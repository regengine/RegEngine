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
        if (tenant_id) {
            response.cookies.set('re_tenant_id', tenant_id, {
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

        return response;
    } catch {
        return NextResponse.json({ error: 'Invalid request' }, { status: 400 });
    }
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
    return response;
}
