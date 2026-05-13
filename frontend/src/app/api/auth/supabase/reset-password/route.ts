import { NextRequest, NextResponse } from 'next/server';
import { getAdminTargets, shouldRetryAdminProxyResponse } from '@/lib/admin-targets';
import { createSupabaseRouteClient, getSupabaseRouteConfig } from '@/lib/supabase/route-client';

export async function POST(request: NextRequest) {
    const config = getSupabaseRouteConfig();
    if (!config) {
        return NextResponse.json({ error: 'Password reset is unavailable' }, { status: 503 });
    }

    const body = await request.json().catch(() => null);
    const newPassword = typeof body?.new_password === 'string' ? body.new_password : '';
    if (newPassword.length < 8) {
        return NextResponse.json({ error: 'Password must be at least 8 characters' }, { status: 400 });
    }

    const client = createSupabaseRouteClient(request, config);
    if (!client) {
        return NextResponse.json({ error: 'Password reset is unavailable' }, { status: 503 });
    }

    const { data: { session }, error: sessionError } = await client.supabase.auth.getSession();
    const accessToken = session?.access_token;
    if (sessionError || !accessToken) {
        return NextResponse.json({ error: 'Reset session expired' }, { status: 401 });
    }

    let lastResponse: Response | null = null;
    for (const target of getAdminTargets()) {
        const response = await fetch(`${target}/auth/reset-password`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Authorization: `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ new_password: newPassword }),
        }).catch(() => null);

        if (!response) {
            continue;
        }
        lastResponse = response;
        if (shouldRetryAdminProxyResponse(response, 'auth/reset-password')) {
            continue;
        }

        if (!response.ok) {
            const payload = await response.json().catch(() => null);
            return NextResponse.json(
                { error: payload?.detail || 'Failed to update password' },
                { status: response.status },
            );
        }

        await client.supabase.auth.signOut();
        return client.applyCookies(NextResponse.json({ ok: true }));
    }

    return NextResponse.json(
        { error: 'Authentication service unavailable' },
        { status: lastResponse?.status || 502 },
    );
}
