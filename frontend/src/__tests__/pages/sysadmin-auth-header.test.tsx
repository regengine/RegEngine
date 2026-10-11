import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

import SysAdminDashboard from '@/app/sysadmin/page';
import { useAuth } from '@/lib/auth-context';

vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

vi.mock('@/components/layout/page-container', () => ({
    PageContainer: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));

vi.mock('@/components/layout/page-header', () => ({
    PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

function authState(accessToken: string | null) {
    return {
        user: { id: 'u1', email: 'admin@example.com', is_sysadmin: true, status: 'active' },
        accessToken,
        isHydrated: true,
        isAuthenticated: true,
    };
}

function headerEntries(init?: RequestInit): Array<[string, string]> {
    if (!init?.headers) return [];
    if (init.headers instanceof Headers) return Array.from(init.headers.entries());
    if (Array.isArray(init.headers)) return init.headers as Array<[string, string]>;
    return Object.entries(init.headers as Record<string, string>);
}

describe('sysadmin dashboard auth headers', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
    });

    it('never sends the cookie-managed placeholder as an Authorization header', async () => {
        vi.mocked(useAuth).mockReturnValue(authState('cookie-managed') as never);
        const fetchMock = vi.fn().mockImplementation((url: string) =>
            Promise.resolve({
                ok: true,
                json: () => Promise.resolve(
                    url.includes('/metrics')
                        ? { total_tenants: 1, total_documents: 2, active_jobs: 0 }
                        : { overall_status: 'healthy', services: [] },
                ),
            }),
        );
        vi.stubGlobal('fetch', fetchMock);

        render(<SysAdminDashboard />);

        await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));

        for (const [, init] of fetchMock.mock.calls) {
            const auth = headerEntries(init as RequestInit)
                .find(([name]) => name.toLowerCase() === 'authorization');
            expect(auth).toBeUndefined();
        }

        vi.unstubAllGlobals();
    });
});
