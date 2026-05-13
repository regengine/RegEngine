import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient, getSupabaseRouteConfig } from '@/lib/supabase/route-client';

export async function POST(request: NextRequest) {
    const config = getSupabaseRouteConfig();
    if (!config) {
        return NextResponse.json({ error: 'Password reset is unavailable' }, { status: 503 });
    }

    const body = await request.json().catch(() => null);
    const email = typeof body?.email === 'string' ? body.email.trim() : '';
    const redirectTo = typeof body?.redirectTo === 'string' ? body.redirectTo : '';
    if (!email || !redirectTo) {
        return NextResponse.json({ error: 'Missing password reset request fields' }, { status: 400 });
    }

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
