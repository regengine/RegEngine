import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
    createSupabaseServerClient: vi.fn(),
    redirect: vi.fn(),
}));

vi.mock('@/lib/supabase/server', () => ({
    createSupabaseServerClient: mocks.createSupabaseServerClient,
}));

vi.mock('next/navigation', () => ({
    redirect: mocks.redirect,
}));

vi.mock('@/components/developer/DeveloperPortalShell', () => ({
    DeveloperPortalShell: ({ children }: { children: React.ReactNode }) => children,
}));

import DeveloperPortalLayout from '@/app/developer/portal/layout';

describe('DeveloperPortalLayout', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('allows a user with a verified Supabase session', async () => {
        mocks.createSupabaseServerClient.mockResolvedValue({
            auth: {
                getUser: vi.fn().mockResolvedValue({ data: { user: { id: 'user-123' } } }),
            },
        });

        const child = React.createElement('div', null, 'Portal content');
        const result = await DeveloperPortalLayout({ children: child });

        expect(mocks.redirect).not.toHaveBeenCalled();
        expect(result.props.children).toBe(child);
    });

    it('redirects when no verified Supabase session exists', async () => {
        mocks.createSupabaseServerClient.mockResolvedValue({
            auth: {
                getUser: vi.fn().mockResolvedValue({ data: { user: null } }),
            },
        });

        await DeveloperPortalLayout({ children: React.createElement('div') });

        expect(mocks.redirect).toHaveBeenCalledWith('/login?next=/developer/portal');
    });
});
