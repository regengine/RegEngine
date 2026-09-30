import { NextRequest, NextResponse } from 'next/server';
import {
    getDeveloperPortalContext,
    withDeveloperCookies,
    type AuthenticatedDeveloperContext,
} from '../_utils';

type ApiKeyRow = {
    id: string;
    name: string;
    key_prefix: string;
    enabled: boolean;
    total_requests: number;
    created_at: string;
    last_used_at: string | null;
    revoked_at: string | null;
};

// Portal keys are SANDBOX-ONLY by design: they live in the Supabase
// developer_api_keys table, which no backend service reads, so an `rge_test_`
// key can never authenticate a live API request. Live `rge_live_` keys come
// from the backend key store (services/shared/api_key_store.py, minted via
// POST /v1/admin/keys); wiring the portal to it is blocked on per-developer
// tenant provisioning. Keep the portal UI's sandbox labeling in sync with this.
function generateApiKey(): string {
    // CSPRNG, not Math.random() — these are real credentials (hashed + stored).
    // Rejection-sample to avoid modulo bias against the 62-char alphabet.
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    const limit = 256 - (256 % chars.length); // discard bytes >= limit
    let result = 'rge_test_';
    const buf = new Uint8Array(1);
    while (result.length < 'rge_test_'.length + 32) {
        crypto.getRandomValues(buf);
        if (buf[0] >= limit) continue;
        result += chars[buf[0] % chars.length];
    }
    return result;
}

async function hashKey(key: string): Promise<string> {
    const encoder = new TextEncoder();
    const data = encoder.encode(key);
    const hash = await crypto.subtle.digest('SHA-256', data);
    return Array.from(new Uint8Array(hash)).map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function loadKeys(context: AuthenticatedDeveloperContext): Promise<ApiKeyRow[]> {
    const { data, error } = await context.client.supabase
        .from('developer_api_keys')
        .select('*')
        .eq('developer_id', context.profile.id)
        .order('created_at', { ascending: false });

    if (error) {
        throw new Error('Failed to load API keys');
    }
    return (data || []) as ApiKeyRow[];
}

export async function GET(request: NextRequest) {
    const context = await getDeveloperPortalContext(request);
    if (!context.ok) return context.response;

    try {
        const keys = await loadKeys(context);
        return withDeveloperCookies(context, NextResponse.json({ developerId: context.profile.id, keys }));
    } catch {
        return NextResponse.json({ error: 'Failed to load API keys' }, { status: 502 });
    }
}

export async function POST(request: NextRequest) {
    const context = await getDeveloperPortalContext(request);
    if (!context.ok) return context.response;

    const body = await request.json().catch(() => null);
    const name = typeof body?.name === 'string' ? body.name.trim() : '';
    if (!name) {
        return NextResponse.json({ error: 'Key name is required' }, { status: 400 });
    }

    const rawKey = generateApiKey();
    const { error } = await context.client.supabase
        .from('developer_api_keys')
        .insert({
            developer_id: context.profile.id,
            name,
            key_prefix: rawKey.substring(0, 12),
            key_hash: await hashKey(rawKey),
            scopes: ['read', 'write'],
        });

    if (error) {
        return NextResponse.json({ error: 'Failed to create API key' }, { status: 502 });
    }

    // Creation is committed; a metadata read failure must not discard the
    // one-time credential or imply that retrying the mutation is safe.
    try {
        const keys = await loadKeys(context);
        return withDeveloperCookies(context, NextResponse.json({ rawKey, keys }));
    } catch {
        return withDeveloperCookies(context, NextResponse.json({ rawKey, keysRefreshFailed: true }));
    }
}
