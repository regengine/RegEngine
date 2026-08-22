import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient } from '@/lib/supabase/route-client';

export type DeveloperProfile = {
    id: string;
    email: string;
    display_name: string | null;
    company_name: string | null;
    created_at: string;
};

type SupabaseRouteClient = NonNullable<ReturnType<typeof createSupabaseRouteClient>>;

type SupabaseUser = NonNullable<
    Awaited<ReturnType<SupabaseRouteClient['supabase']['auth']['getUser']>>['data']['user']
>;

/**
 * The result of resolving a developer-portal request.
 *
 * `ok` is an explicit discriminant rather than a structural one. The previous
 * shape was an untagged union narrowed with `'response' in context`, and the
 * TypeScript bump in #2773 stopped letting `in` prove the property was
 * *defined* — only that the key existed. Callers compensated with defensive
 * re-checks, and the portal tests had to assert `!context.response` on top of
 * the `in` test to stay honest. A literal discriminant removes that ambiguity:
 * narrowing on `context.ok` gives both arms exactly the fields they carry.
 *
 * On the success arm `profile` is always present. Every non-error path through
 * `ensureDeveloperProfile` returns a row, so a caller cannot be handed a
 * context that is authenticated but profile-less.
 */
export type DeveloperPortalContext =
    | {
          ok: false;
          response: NextResponse;
          client?: undefined;
          user?: undefined;
          profile?: undefined;
      }
    | {
          ok: true;
          response?: undefined;
          client: SupabaseRouteClient;
          user: SupabaseUser;
          profile: DeveloperProfile;
      };

/** The success arm, for helpers that may only be called once auth has passed. */
export type AuthenticatedDeveloperContext = Extract<DeveloperPortalContext, { ok: true }>;

type EnsureProfileResult =
    | { ok: true; profile: DeveloperProfile }
    | { ok: false; error: unknown };

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
    client: SupabaseRouteClient,
    user: { id: string; email?: string | null; user_metadata?: Record<string, unknown> | null },
): Promise<EnsureProfileResult> {
    const { data: existingProfile, error: profileError } = await client.supabase
        .from('developer_profiles')
        .select('id, email, display_name, company_name, created_at')
        .eq('auth_user_id', user.id)
        .maybeSingle();

    if (profileError) {
        return { ok: false, error: profileError };
    }

    if (existingProfile) {
        return { ok: true, profile: existingProfile as DeveloperProfile };
    }

    const email = user.email?.trim();
    if (!email) {
        return { ok: false, error: new Error('Authenticated user is missing email') };
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
        return { ok: true, profile: insertedProfile as DeveloperProfile };
    }

    // A parallel request may have created the row first. Re-read once before failing.
    const { data: retriedProfile, error: retryError } = await client.supabase
        .from('developer_profiles')
        .select('id, email, display_name, company_name, created_at')
        .eq('auth_user_id', user.id)
        .maybeSingle();

    if (retryError) {
        return { ok: false, error: retryError };
    }

    if (retriedProfile) {
        return { ok: true, profile: retriedProfile as DeveloperProfile };
    }

    return { ok: false, error: insertError ?? new Error('Failed to create developer profile') };
}

export async function getDeveloperPortalContext(request: NextRequest): Promise<DeveloperPortalContext> {
    const client = createSupabaseRouteClient(request);
    if (!client) {
        return { ok: false, response: NextResponse.json({ error: 'Developer portal unavailable' }, { status: 503 }) };
    }

    const { data: { user }, error: userError } = await client.supabase.auth.getUser();
    if (userError || !user) {
        return { ok: false, response: NextResponse.json({ error: 'Authentication required' }, { status: 401 }) };
    }

    const profileResult = await ensureDeveloperProfile(client, user);
    if (!profileResult.ok) {
        return { ok: false, response: NextResponse.json({ error: 'Failed to load developer profile' }, { status: 502 }) };
    }

    return {
        ok: true,
        client,
        user,
        profile: profileResult.profile,
    };
}

export function withDeveloperCookies(context: DeveloperPortalContext, response: NextResponse) {
    return context.ok ? context.client.applyCookies(response) : response;
}
