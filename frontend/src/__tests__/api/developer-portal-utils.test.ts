import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { NextRequest } from 'next/server';

const mocks = vi.hoisted(() => ({
    createSupabaseRouteClient: vi.fn(),
}));

vi.mock('@/lib/supabase/route-client', () => ({
    createSupabaseRouteClient: mocks.createSupabaseRouteClient,
}));

import { getDeveloperPortalContext } from '@/app/api/developer/portal/_utils';

function makeRequest(url = 'https://regengine.co/api/developer/portal/dashboard') {
    return { url } as unknown as NextRequest;
}

describe('getDeveloperPortalContext', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('creates a developer profile for an authenticated first-time user', async () => {
        const maybeSingle = vi.fn()
            .mockResolvedValueOnce({ data: null, error: null })
            .mockResolvedValueOnce({
                data: {
                    id: 'dev_123',
                    email: 'founder@regengine.co',
                    display_name: 'Founder Test',
                    company_name: null,
                    created_at: '2026-08-15T00:00:00.000Z',
                },
                error: null,
            });
        const single = vi.fn().mockResolvedValue({
            data: {
                id: 'dev_123',
                email: 'founder@regengine.co',
                display_name: 'Founder Test',
                company_name: null,
                created_at: '2026-08-15T00:00:00.000Z',
            },
            error: null,
        });
        const eq = vi.fn(() => ({ maybeSingle }));
        const select = vi.fn(() => ({ eq }));
        const insertSelect = vi.fn(() => ({ single }));
        const insert = vi.fn(() => ({ select: insertSelect }));
        const from = vi.fn((table: string) => {
            if (table === 'developer_profiles') {
                return { select, insert };
            }
            throw new Error(`Unexpected table ${table}`);
        });

        mocks.createSupabaseRouteClient.mockReturnValue({
            supabase: {
                auth: {
                    getUser: vi.fn().mockResolvedValue({
                        data: {
                            user: {
                                id: 'user_123',
                                email: 'founder@regengine.co',
                                user_metadata: { full_name: 'Founder Test' },
                            },
                        },
                        error: null,
                    }),
                },
                from,
            },
            applyCookies: vi.fn((response: Response) => response),
        });

        const context = await getDeveloperPortalContext(makeRequest());

        expect('response' in context).toBe(false);
        if ('response' in context) {
            throw new Error('Expected developer context, received response');
        }

        expect(insert).toHaveBeenCalledWith({
            auth_user_id: 'user_123',
            email: 'founder@regengine.co',
            display_name: 'Founder Test',
            company_name: null,
        });
        expect(context.profile).toEqual({
            id: 'dev_123',
            email: 'founder@regengine.co',
            display_name: 'Founder Test',
            company_name: null,
            created_at: '2026-08-15T00:00:00.000Z',
        });
    });

    it('rejects unauthenticated callers before accessing developer data', async () => {
        const from = vi.fn();
        mocks.createSupabaseRouteClient.mockReturnValue({
            supabase: {
                auth: {
                    getUser: vi.fn().mockResolvedValue({
                        data: { user: null },
                        error: null,
                    }),
                },
                from,
            },
            applyCookies: vi.fn((response: Response) => response),
        });

        const context = await getDeveloperPortalContext(makeRequest());

        expect('response' in context).toBe(true);
        if (!('response' in context)) {
            throw new Error('Expected authentication response, received developer context');
        }
        expect(context.response.status).toBe(401);
        expect(from).not.toHaveBeenCalled();
    });

    it('fails closed when profile creation is rejected', async () => {
        const maybeSingle = vi.fn()
            .mockResolvedValueOnce({ data: null, error: null })
            .mockResolvedValueOnce({ data: null, error: null });
        const single = vi.fn().mockResolvedValue({
            data: null,
            error: new Error('row-level security policy denied insert'),
        });
        const eq = vi.fn(() => ({ maybeSingle }));
        const select = vi.fn(() => ({ eq }));
        const insert = vi.fn(() => ({ select: vi.fn(() => ({ single })) }));

        mocks.createSupabaseRouteClient.mockReturnValue({
            supabase: {
                auth: {
                    getUser: vi.fn().mockResolvedValue({
                        data: {
                            user: {
                                id: 'user_123',
                                email: 'founder@regengine.co',
                                user_metadata: {},
                            },
                        },
                        error: null,
                    }),
                },
                from: vi.fn(() => ({ select, insert })),
            },
            applyCookies: vi.fn((response: Response) => response),
        });

        const context = await getDeveloperPortalContext(makeRequest());

        expect('response' in context).toBe(true);
        if (!('response' in context)) {
            throw new Error('Expected failure response, received developer context');
        }
        expect(context.response.status).toBe(502);
    });
});
