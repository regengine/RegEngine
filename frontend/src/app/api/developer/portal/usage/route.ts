import { NextRequest, NextResponse } from 'next/server';
import { getDeveloperPortalContext, withDeveloperCookies } from '../_utils';

const VALID_RANGES = new Set(['24h', '7d', '30d']);

export async function GET(request: NextRequest) {
    const context = await getDeveloperPortalContext(request);
    if (!context.ok) return context.response;

    const rangeParam = request.nextUrl.searchParams.get('range') || '7d';
    const range = VALID_RANGES.has(rangeParam) ? rangeParam : '7d';
    const since = new Date();
    if (range === '24h') since.setHours(since.getHours() - 24);
    else if (range === '7d') since.setDate(since.getDate() - 7);
    else since.setDate(since.getDate() - 30);

    const { data, error } = await context.client.supabase
        .from('developer_api_usage')
        .select('endpoint, method, status_code, response_time_ms, created_at')
        .eq('developer_id', context.profile.id)
        .gte('created_at', since.toISOString())
        .order('created_at', { ascending: false })
        .limit(1000);

    if (error) {
        return NextResponse.json({ error: 'Failed to load usage data' }, { status: 502 });
    }

    return withDeveloperCookies(context, NextResponse.json({ usage: data || [] }));
}
