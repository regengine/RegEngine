import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient, getSupabaseRouteConfig } from '@/lib/supabase/route-client';

// We expose Supabase's real status code and message instead of collapsing every
// failure to a 502. Background: the previous collapse caused the LoginClient to
// run `clearCredentials()` on a perfectly legitimate "Invalid login credentials"
// response, which wiped the just-set custom-JWT cookie from `/api/admin/auth/login`.
// The user then saw "An unexpected error occurred" and got locked out even when
// their primary login had actually succeeded — masked the real cause (the user's
// Supabase password being out of sync with custom auth, missing Supabase user,
// etc.). See 2026-05-14 login outage diagnosis.
//
// Pass through 4xx as-is so LoginClient's existing 401/403/etc. branches fire
// and the user sees a useful message. Reserve 502 for actual upstream-unreachable.
function mapSupabaseError(status: number | undefined): number {
    if (typeof status === 'number' && status >= 400 && status < 500) {
        return status;
    }
    return 502;
}

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
        // Surface the real Supabase status + message so the frontend can branch
        // on it (401 → "Invalid email or password") instead of swallowing every
        // failure as a fatal session-sync error.
        const status = mapSupabaseError(error.status);
        // Log on the function side too so we can correlate without depending on
        // the user reading their DevTools Network panel.
        console.error('[supabase-sign-in] sync failed', {
            supabaseStatus: error.status,
            supabaseCode: error.code,
            // Do NOT log email or message verbatim — message may include the email
            // for "User not found" responses. Length is a useful fingerprint without
            // leaking PII.
            messageLength: error.message?.length ?? 0,
            mappedStatus: status,
        });
        return NextResponse.json(
            { error: 'Supabase session sync failed', detail: error.message, code: error.code ?? null },
            { status },
        );
    }

    return client.applyCookies(NextResponse.json({ ok: true }));
}
