import { NextRequest, NextResponse } from 'next/server';
import { createSupabaseRouteClient } from '@/lib/supabase/route-client';

export async function GET(request: NextRequest) {
    const client = createSupabaseRouteClient(request);
    if (!client) {
        return NextResponse.json({ organizations: [] });
    }

    const { data, error } = await client.supabase
        .schema('fsma')
        .from('organizations')
        .select('id, name, slug, plan, type, primary_contact, contact_email, phone, address, fei_number')
        .order('name');

    if (error) {
        return NextResponse.json({ organizations: [], error: error.message }, { status: 200 });
    }

    return client.applyCookies(NextResponse.json({ organizations: data || [] }));
}
