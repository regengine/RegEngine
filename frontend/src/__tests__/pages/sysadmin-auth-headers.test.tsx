import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/admin',
}));

import SysAdminDashboard from '@/app/sysadmin/page';

const sysadminUser = {
    is_sysadmin: true,
};

function mockFetchForAdmin() {
    return vi.fn(async (url: string) => {
        if (String(url).endsWith('/v1/system/status')) {
            return {
                ok: true,
                json: async () => ({ overall_status: 'healthy', services: [] }),
            };
        }
        if (String(url).endsWith('/v1/system/metrics')) {
            return {
                ok: true,
                json: async () => ({ total_tenants: 1, total_documents: 2, active_jobs: 0 }),
            };
        }
        return { ok: false, json: async () => ({}) };
    });
}

describe('sysadmin page credential handling', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            user: sysadminUser,
            accessToken: 'cookie-managed',
            isHydrated: true,
        });
    });

    it('never sends an Authorization header; auth rides the HTTP-only cookie via the proxy', async () => {
        const fetchMock = mockFetchForAdmin();
        vi.stubGlobal('fetch', fetchMock);

        render(<SysAdminDashboard />);

        await waitFor(() => {
            expect(fetchMock).toHaveBeenCalled();
        });

        expect(fetchMock).toHaveBeenCalledTimes(2);
        for (const call of fetchMock.mock.calls) {
            const init = (call[1] ?? {}) as RequestInit & { headers?: Record<string, string> };
            expect(init.credentials).toBe('include');
            const headers = init.headers ?? {};
            const headerValues =
                headers instanceof Headers
                    ? [...headers.values()]
                    : Object.values(headers as Record<string, string>);
            expect(
                headerValues.some((value) => String(value).toLowerCase().includes('cookie-managed')),
                `fetch to ${String(call[0])} must not carry the cookie-managed placeholder`,
            ).toBe(false);
            expect('authorization' in headers && (headers as Record<string, string>).authorization).toBeFalsy();
            expect('Authorization' in headers && (headers as Record<string, string>).Authorization).toBeFalsy();
        }

        vi.unstubAllGlobals();
    });

    it('redirects non-sysadmin users to login without calling the backend', async () => {
        mockUseAuth.mockReturnValue({
            user: { is_sysadmin: false },
            accessToken: null,
            isHydrated: true,
        });
        const fetchMock = vi.fn();
        vi.stubGlobal('fetch', fetchMock);

        render(<SysAdminDashboard />);

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith('/login');
        });
        expect(fetchMock).not.toHaveBeenCalled();

        vi.unstubAllGlobals();
    });
});
