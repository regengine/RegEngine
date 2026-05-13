import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient, getSupabaseRouteConfig } from '@/lib/supabase/route-client';

export async function POST(request: NextRequest) {
    const config = getSupabaseRouteConfig();
    if (!config) {
        return NextResponse.json({ ok: true, skipped: true });
    }

    const body = await request.json().catch(() => null);
    const email = typeof body?.email === 'string' ? body.email.trim() : '';
    const password = typeof body?.password === 'string' ? body.password : '';
    if (!email || !password) {
        return NextResponse.json({ error: 'Missing Supabase sign-in credentials' }, { status: 400 });
    }

    const client = createSupabaseRouteClient(request, config);
    if (!client) {
        return NextResponse.json({ ok: true, skipped: true });
    }

    const { error } = await client.supabase.auth.signInWithPassword({ email, password });
    if (error) {
        return NextResponse.json({ error: 'Supabase session sync failed' }, { status: 502 });
    }

    return client.applyCookies(NextResponse.json({ ok: true }));
}
