import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient } from '@/lib/supabase/route-client';

export type DeveloperProfile = {
    id: string;
    email: string;
    display_name: string | null;
    company_name: string | null;
    created_at: string;
};

export async function getDeveloperPortalContext(request: NextRequest) {
    const client = createSupabaseRouteClient(request);
    if (!client) {
        return { response: NextResponse.json({ error: 'Developer portal unavailable' }, { status: 503 }) };
    }

    const { data: { user }, error: userError } = await client.supabase.auth.getUser();
    if (userError || !user) {
        return { response: NextResponse.json({ error: 'Authentication required' }, { status: 401 }) };
    }

    const { data: profile, error: profileError } = await client.supabase
        .from('developer_profiles')
        .select('id, email, display_name, company_name, created_at')
        .eq('auth_user_id', user.id)
        .maybeSingle();

    if (profileError) {
        return { response: NextResponse.json({ error: 'Failed to load developer profile' }, { status: 502 }) };
    }

    return {
        client,
        user,
        profile: profile as DeveloperProfile | null,
    };
}

export function withDeveloperCookies(
    context: Awaited<ReturnType<typeof getDeveloperPortalContext>>,
    response: NextResponse,
) {
    return 'client' in context && context.client ? context.client.applyCookies(response) : response;
}
