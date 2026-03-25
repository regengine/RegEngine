/**
 * Server-side session proxy — CRITICAL #2 fix.
 *
 * This API route stores the RegEngine access token, API key, and admin key
 * in HTTP-only cookies instead of localStorage. The browser cannot read
 * HTTP-only cookies via JavaScript, so XSS attacks cannot exfiltrate credentials.
 *
 * Usage:
 *   POST /api/session — set credentials (access_token, api_key, admin_key, tenant_id)
 *   GET  /api/session — retrieve current session (server reads cookies)
 *   DELETE /api/session — clear session (logout)
 */
import { NextRequest, NextResponse } from 'next/server';

const COOKIE_OPTIONS = {
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax' as const,
    path: '/',
    maxAge: 60 * 60 * 24 * 7, // 7 days
};

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        const { access_token, api_key, admin_key, tenant_id } = body;

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
                httpOnly: false, // tenant_id is not sensitive — UI needs it
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

    return NextResponse.json({
        authenticated: !!access_token,
        has_api_key: !!api_key,
        has_admin_key: !!admin_key,
        has_credentials: !!(access_token || api_key || admin_key),
        tenant_id,
    });
}

export async function DELETE() {
    const response = NextResponse.json({ ok: true });
    response.cookies.delete('re_access_token');
    response.cookies.delete('re_api_key');
    response.cookies.delete('re_admin_key');
    response.cookies.delete('re_tenant_id');
    return response;
}
