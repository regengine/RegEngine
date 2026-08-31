import { NextRequest, NextResponse } from 'next/server';
import { getDeveloperPortalContext, withDeveloperCookies } from '../_utils';

export async function GET(request: NextRequest) {
    const context = await getDeveloperPortalContext(request);
    if (!context.ok) return context.response;

    const { profile, client } = context;

    const { data: keys, error } = await client.supabase
        .from('developer_api_keys')
        .select('id, enabled, total_requests')
        .eq('developer_id', profile.id);

    if (error) {
        return NextResponse.json({ error: 'Failed to load API keys' }, { status: 502 });
    }

    return withDeveloperCookies(context, NextResponse.json({
        profile,
        stats: {
            totalKeys: keys?.length || 0,
            activeKeys: (keys || []).filter((key) => key.enabled).length,
            totalRequests: (keys || []).reduce((sum, key) => sum + (key.total_requests || 0), 0),
        },
    }));
}
