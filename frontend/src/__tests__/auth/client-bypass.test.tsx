import { describe, it, expect, vi, beforeEach } from 'vitest';
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

vi.mock('@/lib/supabase/config', () => ({
    isSupabaseConfigured: vi.fn(() => false),
    getSupabaseConfig: vi.fn(() => ({ url: '', anonKey: '' })),
}));

vi.mock('@/lib/supabase/client', () => ({
    createSupabaseBrowserClient: vi.fn(() => {
        throw new Error('Supabase not configured');
    }),
}));

const mockFetch = vi.fn();

const localStorageMock = (() => {
    let store: Record<string, string> = {};
    return {
        getItem: vi.fn((key: string) => store[key] || null),
        setItem: vi.fn((key: string, value: string) => { store[key] = value.toString(); }),
        removeItem: vi.fn((key: string) => { delete store[key]; }),
        clear: vi.fn(() => { store = {}; }),
    };
})();

Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
});

function unauthenticatedSession() {
    mockFetch.mockImplementation((url: string, options?: RequestInit) => {
        if (typeof url === 'string' && url.includes('/api/session')) {
            if (options?.method === 'POST' || options?.method === 'DELETE') {
                return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
            }
            return Promise.resolve({
                ok: true,
                json: () => Promise.resolve({
                    authenticated: false,
                    has_api_key: false,
                    has_credentials: false,
                    tenant_id: null,
                    user: null,
                }),
            });
        }
        return Promise.reject(new Error(`Unmocked fetch: ${url}`));
    });
    global.fetch = mockFetch;
}

describe('client-side auth bypass attempts (adversarial, must hold)', () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
    );

    beforeEach(() => {
        vi.clearAllMocks();
        localStorageMock.clear();
        window.sessionStorage.clear();
        unauthenticatedSession();
    });

    it('a forged localStorage sysadmin profile grants no session without cookies', async () => {
        window.sessionStorage.setItem('regengine_user', JSON.stringify({
            id: 'attacker',
            email: 'attacker@example.com',
            is_sysadmin: true,
            status: 'active',
            role_name: 'admin',
            permissions: ['review.read', 'review.decide'],
        }));
        localStorageMock.setItem('regengine_tenant_id', 'victim-tenant');

        const { result } = renderHook(() => useAuth(), { wrapper });
        await waitFor(() => expect(result.current.isHydrated).toBe(true));

        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.hasAdminSession).toBe(false);
        expect(result.current.hasTenantSession).toBe(false);
        expect(result.current.accessToken).toBeNull();
    });

    it('a forged member profile cannot flip isAuthenticated after expiry', async () => {
        window.sessionStorage.setItem('regengine_user', JSON.stringify({
            id: 'attacker',
            email: 'attacker@example.com',
            is_sysadmin: false,
            status: 'active',
            role_name: 'member',
            permissions: [],
        }));

        const { result } = renderHook(() => useAuth(), { wrapper });
        await waitFor(() => expect(result.current.isHydrated).toBe(true));

        expect(result.current.isAuthenticated).toBe(false);
        expect(result.current.user).toBeNull();
    });

    it('XSS-shaped email text seeded client-side stays inert data, not markup', async () => {
        const { seedPasswordlessClientUser } = await import('@/lib/passwordless-auth');
        seedPasswordlessClientUser('<img src=x onerror=alert(1)>@example.com');
        const raw = window.sessionStorage.getItem('regengine_user');
        expect(localStorageMock.getItem('regengine_user')).toBeNull();
        expect(raw).toContain('<img src=x onerror=alert(1)>');
        const parsed = JSON.parse(raw as string) as {
            email: string; is_sysadmin: boolean; permissions: string[];
        };
        expect(typeof parsed.email).toBe('string');
        expect(parsed.is_sysadmin).toBe(false);
        expect(parsed.permissions).toEqual([]);
    });
});
