import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient, getSupabaseRouteConfig } from '@/lib/supabase/route-client';

export function buildPasswordResetRedirect(request: NextRequest): string {
    const origin = new URL(request.url).origin;
    return `${origin}/auth/callback?next=/reset-password`;
}

export async function POST(request: NextRequest) {
    const config = getSupabaseRouteConfig();
    if (!config) {
        return NextResponse.json({ error: 'Password reset is unavailable' }, { status: 503 });
    }

    const body = await request.json().catch(() => null);
    const email = typeof body?.email === 'string' ? body.email.trim() : '';
    if (!email) {
        return NextResponse.json({ error: 'Missing password reset request fields' }, { status: 400 });
    }
    const redirectTo = buildPasswordResetRedirect(request);

    const client = createSupabaseRouteClient(request, config);
    if (!client) {
        return NextResponse.json({ error: 'Password reset is unavailable' }, { status: 503 });
    }

    const { error } = await client.supabase.auth.resetPasswordForEmail(email, { redirectTo });
    if (error) {
        return NextResponse.json(
            { error: error.message || 'Failed to send reset email' },
            { status: 400 },
        );
    }

    return client.applyCookies(NextResponse.json({ ok: true }));
}
