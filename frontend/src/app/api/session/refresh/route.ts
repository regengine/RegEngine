/**
 * Session refresh endpoint — clears the expired re_access_token cookie
 * so the middleware falls through to Supabase session validation.
 *
 * The re_access_token is a RegEngine-signed JWT (HS256) with a 60-min
 * lifetime. When it expires, the middleware rejects it and redirects to
 * /login. But the Supabase session (Strategy 2 in middleware) typically
 * lives much longer. By clearing the expired cookie, subsequent requests
 * skip the failed JWT check and use Supabase auth instead.
 *
 * This endpoint does NOT issue new tokens — it only removes the stale one.
 */
import { NextResponse } from 'next/server';

export async function POST() {
    const response = NextResponse.json({ ok: true });
    // Delete only re_access_token — keep all other session cookies intact
    // (re_api_key, re_admin_key, re_tenant_id, re_user, CSRF, Supabase)
    response.cookies.delete('re_access_token');
    return response;
}
