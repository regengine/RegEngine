import { NextRequest, NextResponse } from 'next/server';
import { getDeveloperPortalContext, withDeveloperCookies } from '../../_utils';

export async function DELETE(
    request: NextRequest,
    { params }: { params: Promise<{ keyId: string }> },
) {
    const context = await getDeveloperPortalContext(request);
    if (!context.ok) return context.response;

    const { keyId } = await params;
    const { error } = await context.client.supabase
        .from('developer_api_keys')
        .update({ enabled: false, revoked_at: new Date().toISOString() })
        .eq('id', keyId)
        .eq('developer_id', context.profile.id);

    if (error) {
        return NextResponse.json({ error: 'Failed to revoke API key' }, { status: 502 });
    }

    return withDeveloperCookies(context, NextResponse.json({ ok: true }));
}
