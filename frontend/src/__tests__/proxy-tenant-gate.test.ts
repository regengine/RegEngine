/**
 * Tenant-suspension gate (Supabase auth path) in proxy.ts.
 *
 * Regression guard for the fail-OPEN bug: the tenant-status lookup ignored the
 * query `error`, so a failed read was indistinguishable from "status is fine"
 * and the suspension gate was skipped. These tests drive proxy() through the
 * Supabase strategy for GET /dashboard and assert:
 *   1. a FAILED tenants query fails CLOSED (redirect to
 *      /login?error=tenant_status_unavailable), not open;
 *   2. an explicit non-active status still blocks (?error=tenant_suspended);
 *   3. an active tenant is allowed through.
 *
 * Only @supabase/ssr is mocked. Strategy 1 (opaque session cookie) and
 * Strategy 2 (re_access_token JWT) are skipped simply by not setting those
 * cookies, so the request falls through to the Supabase path.
 */

import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { createServerClient } from '@supabase/ssr';

vi.mock('@supabase/ssr', () => ({
    createServerClient: vi.fn(),
}));

const ORIGINAL_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ORIGINAL_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// tenantResult is what `.from('tenants').select().eq().maybeSingle()` resolves to.
function mockSupabase(tenantResult: { data: unknown; error: unknown }) {
    const user = { id: 'user-1', user_metadata: { tenant_id: 'tenant-123' } };
    (createServerClient as unknown as ReturnType<typeof vi.fn>).mockReturnValue({
        auth: { getUser: async () => ({ data: { user }, error: null }) },
        from: () => ({
            select: () => ({
                eq: () => ({
                    maybeSingle: async () => tenantResult,
                }),
            }),
        }),
    });
}

async function runDashboardRequest() {
    // Import fresh each time so the module-level tenant-status cache does not
    // leak a value between cases (a cached status would skip the DB lookup).
    vi.resetModules();
    const { proxy } = await import('@/proxy');
    const req = new NextRequest(new URL('http://localhost/dashboard'));
    return proxy(req);
}

beforeEach(() => {
    // Must be set before the module under test reads it (via dynamic import).
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co';
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key';
});

afterEach(() => {
    vi.restoreAllMocks();
    process.env.NEXT_PUBLIC_SUPABASE_URL = ORIGINAL_URL;
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = ORIGINAL_KEY;
});

describe('proxy tenant-suspension gate (Supabase path)', () => {
    it('fails CLOSED when the tenant-status query errors', async () => {
        mockSupabase({ data: null, error: { message: 'permission denied' } });
        const res = await runDashboardRequest();
        expect(res.status).toBe(307);
        const loc = res.headers.get('location') ?? '';
        expect(loc).toContain('/login');
        expect(loc).toContain('error=tenant_status_unavailable');
    });

    it('blocks a non-active tenant status', async () => {
        mockSupabase({ data: { status: 'suspended' }, error: null });
        const res = await runDashboardRequest();
        expect(res.status).toBe(307);
        expect(res.headers.get('location') ?? '').toContain('error=tenant_suspended');
    });

    it('allows an active tenant through (no /login redirect)', async () => {
        mockSupabase({ data: { status: 'active' }, error: null });
        const res = await runDashboardRequest();
        expect(res.headers.get('location') ?? '').not.toContain('/login');
    });
});
