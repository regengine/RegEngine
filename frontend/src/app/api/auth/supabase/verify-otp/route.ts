import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient, getSupabaseRouteConfig } from '@/lib/supabase/route-client';

export async function POST(request: NextRequest) {
    const config = getSupabaseRouteConfig();
    if (!config) {
        return NextResponse.json({ error: 'Password reset verification is unavailable' }, { status: 503 });
    }

    const body = await request.json().catch(() => null);
    const tokenHash = typeof body?.token_hash === 'string' ? body.token_hash : '';
    if (!tokenHash) {
        return NextResponse.json({ error: 'Missing verification token' }, { status: 400 });
    }

    const client = createSupabaseRouteClient(request, config);
    if (!client) {
        return NextResponse.json({ error: 'Password reset verification is unavailable' }, { status: 503 });
    }

    const { error } = await client.supabase.auth.verifyOtp({
        token_hash: tokenHash,
        type: 'recovery',
    });
    if (error) {
        return NextResponse.json({ error: 'Reset link is invalid or expired' }, { status: 401 });
    }

    return client.applyCookies(NextResponse.json({ ok: true }));
}
