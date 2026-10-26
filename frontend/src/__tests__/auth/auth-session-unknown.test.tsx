/**
 * AuthProvider hydrate must keep the stored profile when the session check is
 * indeterminate (503 { authenticated: null, status: 'unknown' }) and clear it
 * only on a real unauthenticated result (authenticated === false).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import type { ReactNode } from 'react';

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        setAccessToken: vi.fn(),
        setUser: vi.fn(),
        setCurrentTenant: vi.fn(),
    },
}));

const wrapper = ({ children }: { children: ReactNode }) => (
    <AuthProvider>{children}</AuthProvider>
);

function storedProfile() {
    return {
        id: crypto.randomUUID(),
        email: 'owner@example.com',
        is_sysadmin: false,
        status: 'active',
        role_name: 'owner',
        tenant_id: crypto.randomUUID(),
        permissions: [] as string[],
    };
}

describe('AuthProvider hydrate on unknown vs unauthenticated session', () => {
    const originalFetch = global.fetch;

    beforeEach(() => {
        vi.clearAllMocks();
        localStorage.clear();
    });

    afterEach(() => {
        global.fetch = originalFetch;
        localStorage.clear();
    });

    it('keeps the stored profile when the session check is unknown (503)', async () => {
        const user = storedProfile();
        localStorage.setItem('regengine_user', JSON.stringify(user));
        localStorage.setItem('regengine_tenant_id', user.tenant_id);
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 503,
            json: () =>
                Promise.resolve({
                    authenticated: null,
                    status: 'unknown',
                    has_api_key: false,
                    has_credentials: null,
                    tenant_id: user.tenant_id,
                    auth_method: null,
                    user,
                }),
        }) as unknown as typeof fetch;

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
            expect(result.current.isHydrated).toBe(true);
        });

        expect(result.current.user).toMatchObject({ id: user.id, email: user.email });
        expect(result.current.tenantId).toBe(user.tenant_id);
        expect(localStorage.getItem('regengine_user')).toBe(JSON.stringify(user));
        expect(localStorage.getItem('regengine_tenant_id')).toBe(user.tenant_id);
    });

    it('clears the stored profile on a real unauthenticated result', async () => {
        const user = storedProfile();
        localStorage.setItem('regengine_user', JSON.stringify(user));
        localStorage.setItem('regengine_tenant_id', user.tenant_id);
        global.fetch = vi.fn().mockResolvedValue({
            ok: true,
            status: 200,
            json: () =>
                Promise.resolve({
                    authenticated: false,
                    has_api_key: false,
                    has_credentials: false,
                    tenant_id: null,
                    auth_method: null,
                    user: null,
                }),
        }) as unknown as typeof fetch;

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
            expect(result.current.isHydrated).toBe(true);
        });

        expect(result.current.user).toBeNull();
        expect(localStorage.getItem('regengine_user')).toBeNull();
    });

    it('treats a stored profile as authenticated while the session is unknown', async () => {
        const user = storedProfile();
        localStorage.setItem('regengine_user', JSON.stringify(user));
        localStorage.setItem('regengine_tenant_id', user.tenant_id);
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 503,
            json: () =>
                Promise.resolve({
                    authenticated: null,
                    status: 'unknown',
                    has_api_key: false,
                    has_credentials: null,
                    tenant_id: user.tenant_id,
                    auth_method: null,
                    user,
                }),
        }) as unknown as typeof fetch;

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
            expect(result.current.isHydrated).toBe(true);
        });

        // Last-known authenticated state is kept: dashboard layouts gate on
        // isAuthenticated, so unknown must never bounce to /login.
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.user).toMatchObject({ id: user.id, email: user.email });
    });

    it('stays unauthenticated when the session is unknown with no stored profile', async () => {
        global.fetch = vi.fn().mockResolvedValue({
            ok: false,
            status: 503,
            json: () =>
                Promise.resolve({
                    authenticated: null,
                    status: 'unknown',
                    has_api_key: false,
                    has_credentials: null,
                    tenant_id: null,
                    auth_method: null,
                    user: null,
                }),
        }) as unknown as typeof fetch;

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
            expect(result.current.isHydrated).toBe(true);
        });

        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
    });

    it('keeps the stored profile and stays authenticated when the session fetch throws', async () => {
        const user = storedProfile();
        localStorage.setItem('regengine_user', JSON.stringify(user));
        localStorage.setItem('regengine_tenant_id', user.tenant_id);
        global.fetch = vi
            .fn()
            .mockRejectedValue(new Error(`session fetch failed ${Date.now()}`)) as unknown as typeof fetch;

        const { result } = renderHook(() => useAuth(), { wrapper });

        await waitFor(() => {
            expect(result.current.isHydrated).toBe(true);
        });

        expect(result.current.user).toMatchObject({ id: user.id, email: user.email });
        expect(result.current.tenantId).toBe(user.tenant_id);
        expect(result.current.isAuthenticated).toBe(true);
        expect(localStorage.getItem('regengine_user')).toBe(JSON.stringify(user));
    });
});
