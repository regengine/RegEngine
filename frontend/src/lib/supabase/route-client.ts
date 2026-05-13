import { NextRequest, NextResponse } from 'next/server';
import { createServerClient } from '@supabase/ssr';

type SupabaseCookie = {
    name: string;
    value: string;
    options?: Parameters<NextResponse['cookies']['set']>[2];
};

export function getSupabaseRouteConfig(): { url: string; anonKey: string } | null {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
    return url && anonKey ? { url, anonKey } : null;
}

export function createSupabaseRouteClient(request: NextRequest, config = getSupabaseRouteConfig()) {
    if (!config) {
        return null;
    }

    const pendingCookies: SupabaseCookie[] = [];
    const supabase = createServerClient(config.url, config.anonKey, {
        cookies: {
            getAll() {
                return request.cookies.getAll();
            },
            setAll(cookiesToSet) {
                pendingCookies.length = 0;
                cookiesToSet.forEach(({ name, value, options }) => {
                    request.cookies.set(name, value);
                    pendingCookies.push({ name, value, options });
                });
            },
        },
    });

    return {
        supabase,
        applyCookies(response: NextResponse) {
            pendingCookies.forEach(({ name, value, options }) => {
                response.cookies.set(name, value, options);
            });
            return response;
        },
    };
}
