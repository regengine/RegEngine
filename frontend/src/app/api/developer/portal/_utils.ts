import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient } from '@/lib/supabase/route-client';

export type DeveloperProfile = {
    id: string;
    email: string;
    display_name: string | null;
    company_name: string | null;
    created_at: string;
};

function deriveDisplayName(email: string, metadata: Record<string, unknown> | null | undefined): string {
    const preferred = [metadata?.full_name, metadata?.name, metadata?.display_name]
        .find((value) => typeof value === 'string' && value.trim().length > 0);

    if (typeof preferred === 'string') {
        return preferred.trim();
    }

    const localPart = email.split('@')[0]?.trim();
    return localPart || 'Developer';
}

async function ensureDeveloperProfile(
    client: NonNullable<ReturnType<typeof createSupabaseRouteClient>>,
    user: { id: string; email?: string | null; user_metadata?: Record<string, unknown> | null },
) {
    const { data: existingProfile, error: profileError } = await client.supabase
        .from('developer_profiles')
        .select('id, email, display_name, company_name, created_at')
        .eq('auth_user_id', user.id)
        .maybeSingle();

    if (profileError) {
        return { error: profileError };
    }

    if (existingProfile) {
        return { profile: existingProfile as DeveloperProfile };
    }

    const email = user.email?.trim();
    if (!email) {
        return { error: new Error('Authenticated user is missing email') };
    }

    const { data: insertedProfile, error: insertError } = await client.supabase
        .from('developer_profiles')
        .insert({
            auth_user_id: user.id,
            email,
            display_name: deriveDisplayName(email, user.user_metadata),
            company_name: null,
        })
        .select('id, email, display_name, company_name, created_at')
        .single();

    if (!insertError && insertedProfile) {
        return { profile: insertedProfile as DeveloperProfile };
    }

    // A parallel request may have created the row first. Re-read once before failing.
    const { data: retriedProfile, error: retryError } = await client.supabase
        .from('developer_profiles')
        .select('id, email, display_name, company_name, created_at')
        .eq('auth_user_id', user.id)
        .maybeSingle();

    if (retryError) {
        return { error: retryError };
    }

    if (retriedProfile) {
        return { profile: retriedProfile as DeveloperProfile };
    }

    return { error: insertError ?? new Error('Failed to create developer profile') };
}

export async function getDeveloperPortalContext(request: NextRequest) {
    const client = createSupabaseRouteClient(request);
    if (!client) {
        return { response: NextResponse.json({ error: 'Developer portal unavailable' }, { status: 503 }) };
    }

    const { data: { user }, error: userError } = await client.supabase.auth.getUser();
    if (userError || !user) {
        return { response: NextResponse.json({ error: 'Authentication required' }, { status: 401 }) };
    }

    const profileResult = await ensureDeveloperProfile(client, user);
    if (profileResult.error) {
        return { response: NextResponse.json({ error: 'Failed to load developer profile' }, { status: 502 }) };
    }

    return {
        client,
        user,
        profile: profileResult.profile,
    };
}

export function withDeveloperCookies(
    context: Awaited<ReturnType<typeof getDeveloperPortalContext>>,
    response: NextResponse,
) {
    return 'client' in context && context.client ? context.client.applyCookies(response) : response;
}
