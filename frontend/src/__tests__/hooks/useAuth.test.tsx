/**
 * React Hook Tests - useAuth
 *
 * Tests for the authentication hook:
 * - Login/logout functionality
 * - Token management (HTTP-only cookie based)
 * - User state
 * - Hydration handling
 * - localStorage persistence (non-sensitive data only)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { isSupabaseConfigured } from '@/lib/supabase/config';
import type { ReactNode } from 'react';

// Mock apiClient
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        setAccessToken: vi.fn(),
        setUser: vi.fn(),
        login: vi.fn(),
        setCurrentTenant: vi.fn(),
    },
}));

// Mock supabase client to avoid real auth calls
vi.mock('@/lib/supabase/config', () => ({
    isSupabaseConfigured: vi.fn(() => false),
    getSupabaseConfig: vi.fn(() => ({ url: '', anonKey: '' })),
}));

vi.mock('@/lib/supabase/client', () => ({
    createSupabaseBrowserClient: vi.fn(() => {
        throw new Error('Supabase not configured');
    }),
}));

// Mock localStorage
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

// Mock global fetch for /api/session calls
const mockFetch = vi.fn();

describe('useAuth Hook', () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
    );

    beforeEach(() => {
        vi.clearAllMocks();
        localStorageMock.clear();
        window.sessionStorage.clear();
        (isSupabaseConfigured as any).mockReturnValue(false);
        (createSupabaseBrowserClient as any).mockImplementation(() => {
            throw new Error('Supabase not configured');
        });

        // Default: /api/session GET returns no session, POST succeeds
        mockFetch.mockImplementation((url: string, options?: RequestInit) => {
            if (typeof url === 'string' && url.includes('/api/session')) {
                if (options?.method === 'POST' || options?.method === 'DELETE') {
                    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
                }
                // GET — no active session by default
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
    });

    describe('Initialization', () => {
        it('starts with no user when localStorage is empty', () => {
            const { result } = renderHook(() => useAuth(), { wrapper });

            expect(result.current.user).toBeNull();
            expect(result.current.accessToken).toBeNull();
        });

        it('hydrates authenticated email in memory without retaining it in storage', async () => {
            const mockUser = {
                id: '123',
                email: `${crypto.randomUUID()}@example.test`,
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            localStorageMock.setItem('regengine_user', JSON.stringify(mockUser));

            // Session endpoint says user is authenticated (cookie has token)
            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'POST' || options?.method === 'DELETE') {
                        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
                    }
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve({
                            authenticated: true,
                            has_api_key: false,
                            has_credentials: true,
                            tenant_id: 'tenant-123',
                            user: mockUser,
                        }),
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user).toEqual(mockUser);
            expect(apiClient.setUser).toHaveBeenLastCalledWith(mockUser);
            expect(JSON.parse(localStorageMock.getItem('regengine_user')!)).toEqual({ ...mockUser, email: '' });
            expect(localStorageMock.getItem('regengine_user')).not.toContain(mockUser.email);
            expect(window.sessionStorage.getItem('regengine_user')).toBeNull();
            // Access token is now a placeholder since actual token is in HTTP-only cookie
            expect(result.current.accessToken).toBe('cookie-managed');
        });

        it('sets isHydrated to true after initialization', async () => {
            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });
        });
    });

    describe('Login', () => {
        it('updates user and token on login', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(result.current.user).toEqual(mockUser);
            // Access token in state is the cookie-managed placeholder
            expect(result.current.accessToken).toBe('cookie-managed');
        });

        it('keeps login email in memory and out of browser storage', async () => {
            const mockUser = {
                id: '123',
                email: `${crypto.randomUUID()}@example.test`,
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(result.current.user).toEqual(mockUser);
            expect(apiClient.setUser).toHaveBeenLastCalledWith(mockUser);
            expect(JSON.parse(localStorageMock.getItem('regengine_user')!)).toEqual({ ...mockUser, email: '' });
            expect(localStorageMock.getItem('regengine_user')).not.toContain(mockUser.email);
            expect(window.sessionStorage.getItem('regengine_user')).toBeNull();
            // Tenant ID is still stored in localStorage (non-sensitive)
            expect(localStorageMock.getItem('regengine_tenant_id')).toBe('tenant-123');
        });

        it('stores credentials in HTTP-only cookies via /api/session on login', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            // Verify /api/session POST was called with the token
            const sessionPostCalls = mockFetch.mock.calls.filter(
                ([url, opts]) =>
                    typeof url === 'string' &&
                    url.includes('/api/session') &&
                    (opts as RequestInit | undefined)?.method === 'POST'
            );
            expect(sessionPostCalls.length).toBeGreaterThan(0);

            const lastPostBody = JSON.parse(sessionPostCalls[sessionPostCalls.length - 1][1].body);
            expect(lastPostBody.access_token).toBe('test-token');
            expect(lastPostBody.remember_me).toBe(true);
        });

        it('passes session-cookie preference to /api/session when remember is false', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123', { remember: false });
            });

            const sessionPostCalls = mockFetch.mock.calls.filter(
                ([url, opts]) =>
                    typeof url === 'string' &&
                    url.includes('/api/session') &&
                    (opts as RequestInit | undefined)?.method === 'POST'
            );

            const lastPostBody = JSON.parse(sessionPostCalls[sessionPostCalls.length - 1][1].body);
            expect(lastPostBody.remember_me).toBe(false);
        });

        it('does not load the Supabase browser SDK or replace the RegEngine JWT cookie with Supabase tokens', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => expect(result.current.isHydrated).toBe(true));

            await act(async () => {
                await result.current.login('regengine-jwt', mockUser, 'tenant-123');
            });

            const sessionPostBodies = mockFetch.mock.calls
                .filter(
                    ([url, opts]) =>
                        typeof url === 'string' &&
                        url.includes('/api/session') &&
                        (opts as RequestInit | undefined)?.method === 'POST'
                )
                .map(([, opts]) => JSON.parse((opts as RequestInit).body as string));

            expect(sessionPostBodies.some((body) => body.access_token === 'regengine-jwt')).toBe(true);
            expect(sessionPostBodies.some((body) => body.access_token === 'cookie-managed')).toBe(false);
            expect(createSupabaseBrowserClient).not.toHaveBeenCalled();
        });

        it('hydrates server-validated Supabase permissions into the app session without the browser SDK', async () => {
            const supabaseUser = {
                id: 'supabase-user',
                email: 'test@example.com',
                tenant_id: 'tenant-123',
                role_name: 'member',
                is_sysadmin: false,
                status: 'active',
                permissions: [' inflow:write ', '', 42, 'admin:*'],
            };

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'POST' || options?.method === 'DELETE') {
                        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
                    }
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve({
                            authenticated: true,
                            has_api_key: false,
                            has_credentials: true,
                            tenant_id: 'tenant-123',
                            user: supabaseUser,
                        }),
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.user?.id).toBe('supabase-user');
            });

            expect(result.current.user?.permissions).toEqual(['inflow:write', 'admin:*']);
            expect(result.current.accessToken).toBe('cookie-managed');
            expect(result.current.tenantId).toBe('tenant-123');
            expect(createSupabaseBrowserClient).not.toHaveBeenCalled();
        });

        it('hydrates auth assurance from the server session profile', async () => {
            const sessionUser = {
                id: 'opaque-user',
                email: 'owner@example.com',
                organization_id: 'tenant-456',
                role_name: 'owner',
                is_sysadmin: false,
                status: 'active',
                auth_method: 'webauthn' as const,
                permissions: ['admin:*'],
            };

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'POST' || options?.method === 'DELETE') {
                        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
                    }
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve({
                            authenticated: true,
                            has_api_key: false,
                            has_credentials: true,
                            tenant_id: 'tenant-456',
                            auth_method: 'webauthn',
                            user: sessionUser,
                        }),
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.authMethod).toBe('webauthn');
            });

            expect(result.current.isHighAssuranceSession).toBe(true);
            expect(result.current.user?.auth_method).toBe('webauthn');
            expect(result.current.tenantId).toBe('tenant-456');
        });

        it('hydrates Supabase fallback sessions from /api/session instead of local browser auth state', async () => {
            const storedUser = {
                id: 'stored-user',
                email: `${crypto.randomUUID()}@example.test`,
                is_sysadmin: false,
                status: 'active',
                role_name: 'owner',
                permissions: ['inflow.write', 'reports.read'],
            };
            const supabaseUser = {
                id: 'supabase-user',
                email: `${crypto.randomUUID()}@example.test`,
                tenant_id: 'tenant-123',
                role_name: 'member',
                is_sysadmin: false,
                status: 'active',
                permissions: ['inflow.write', 'reports.read'],
            };
            localStorageMock.setItem('regengine_user', JSON.stringify(storedUser));

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'POST' || options?.method === 'DELETE') {
                        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
                    }
                    return Promise.resolve({
                        ok: true,
                        json: () => Promise.resolve({
                            authenticated: true,
                            has_api_key: false,
                            has_credentials: true,
                            tenant_id: 'tenant-123',
                            user: supabaseUser,
                        }),
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.user?.id).toBe('supabase-user');
            });

            expect(result.current.user?.permissions).toEqual(['inflow.write', 'reports.read']);
            expect(localStorageMock.getItem('regengine_user')).toBe(JSON.stringify({ ...supabaseUser, email: '' }));
            expect(createSupabaseBrowserClient).not.toHaveBeenCalled();
        });

        it('calls apiClient.setAccessToken on login', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            // apiClient receives the placeholder, not the real token
            expect(apiClient.setAccessToken).toHaveBeenCalledWith('cookie-managed');
            expect(apiClient.setUser).toHaveBeenCalledWith(mockUser);
        });
    });

    describe('API key cookie', () => {
        it('publishes cookie-managed state only after the session cookie is stored', async () => {
            const { result } = renderHook(() => useAuth(), { wrapper });
            await waitFor(() => expect(result.current.isHydrated).toBe(true));

            await act(async () => {
                await result.current.setApiKey('rge_test_api_key'); // pragma: allowlist secret
            });

            expect(result.current.apiKey).toBe('cookie-managed');
            const sessionPostBodies = mockFetch.mock.calls
                .filter(([, opts]) => (opts as RequestInit | undefined)?.method === 'POST')
                .map(([, opts]) => JSON.parse((opts as RequestInit).body as string));
            expect(sessionPostBodies.some((body) => body.api_key === 'rge_test_api_key')).toBe(true); // pragma: allowlist secret
        });

        it('rejects a failed cookie write and keeps API-key state unset', async () => {
            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'POST') {
                        return Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}) });
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
            const { result } = renderHook(() => useAuth(), { wrapper });
            await waitFor(() => expect(result.current.isHydrated).toBe(true));

            await act(async () => {
                await expect(
                    result.current.setApiKey('rge_test_api_key'), // pragma: allowlist secret
                ).rejects.toThrow('API key could not be saved');
            });

            expect(result.current.apiKey).toBeNull();
        });
    });

    describe('Logout', () => {
        it('clears user and token on logout', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            // Login first
            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            // Then logout
            await act(async () => {
                await result.current.logout();
            });

            expect(result.current.user).toBeNull();
            expect(result.current.accessToken).toBeNull();
        });

        it('clears localStorage on logout', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            // Login first
            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            // Then logout
            await act(async () => {
                await result.current.logout();
            });

            expect(localStorageMock.getItem('regengine_user')).toBeNull();
            expect(localStorageMock.getItem('regengine_tenant_id')).toBeNull();
        });

        it('calls apiClient.setAccessToken(null) on logout', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            // Login first
            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            // Clear previous calls
            vi.clearAllMocks();

            // Then logout
            await act(async () => {
                await result.current.logout();
            });

            expect(apiClient.setAccessToken).toHaveBeenCalledWith(null);
            expect(apiClient.setUser).toHaveBeenCalledWith(null);
        });

        it('waits for cookie teardown before logout resolves without loading the Supabase browser SDK', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            type DeleteResponse = { ok: boolean; json: () => Promise<Record<string, never>> };
            let resolveDelete: ((value: DeleteResponse) => void) | undefined;

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'DELETE') {
                        return new Promise<DeleteResponse>((resolve) => {
                            resolveDelete = resolve;
                        });
                    }
                    if (options?.method === 'POST') {
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

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => expect(result.current.isHydrated).toBe(true));

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            let resolved = false;
            const logoutPromise = act(async () => {
                await result.current.logout();
                resolved = true;
            });

            await Promise.resolve();

            expect(resolved).toBe(false);
            expect(createSupabaseBrowserClient).not.toHaveBeenCalled();

            if (!resolveDelete) {
                throw new Error('Expected deferred logout request resolver to be set');
            }
            resolveDelete({ ok: true, json: () => Promise.resolve({}) });
            await logoutPromise;

            expect(createSupabaseBrowserClient).not.toHaveBeenCalled();
            expect(resolved).toBe(true);
        });

        it('does not instantiate Supabase on logout when browser Supabase config is absent', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            vi.clearAllMocks();
            (isSupabaseConfigured as any).mockReturnValue(false);

            await act(async () => {
                await result.current.logout();
            });

            expect(createSupabaseBrowserClient).not.toHaveBeenCalled();
            expect(apiClient.setAccessToken).toHaveBeenCalledWith(null);
        });
    });

    describe('Computed Properties', () => {
        it('isAuthenticated is true when user exists', async () => {
            const mockUser = {
                id: '123',
                email: 'test@example.com',
                name: 'Test User',
                is_sysadmin: false,
                tenant_id: 'tenant-123',
                role_id: 'role-1',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(result.current.isAuthenticated).toBe(true);
            expect(result.current.hasTenantSession).toBe(true);
        });

        it('isAuthenticated is false when user is null', () => {
            const { result } = renderHook(() => useAuth(), { wrapper });

            expect(result.current.isAuthenticated).toBe(false);
            expect(result.current.hasTenantSession).toBe(false);
            expect(result.current.hasAdminSession).toBe(false);
        });

        it('detects sysadmin users', async () => {
            const adminUser = {
                id: '456',
                email: 'admin@example.com',
                name: 'Admin User',
                is_sysadmin: true,
                tenant_id: 'tenant-456',
                role_id: 'role-admin',
                is_active: true,
                status: 'active',
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-27T00:00:00Z',
            };

            const { result } = renderHook(() => useAuth(), { wrapper });

            await act(async () => {
                await result.current.login('admin-token', adminUser, 'tenant-456');
            });

            expect(result.current.user?.is_sysadmin).toBe(true);
            expect(result.current.hasAdminSession).toBe(true);
        });

        it('does not grant privileged access from a retired key-only session field', async () => {
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
                            has_admin_key: true,
                            has_credentials: true,
                            tenant_id: null,
                            user: null,
                        }),
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.hasAdminSession).toBe(false);
            expect(result.current.hasTenantSession).toBe(false);
        });
    });

    describe('Stale session cleanup (hydration)', () => {
        const staleUser = {
            id: 'stale-user',
            email: `${crypto.randomUUID()}@example.test`,
            is_sysadmin: false,
            status: 'active',
            role_name: 'member',
        };

        it('clears the localStorage-hydrated user when the session reports unauthenticated', async () => {
            localStorageMock.setItem('regengine_user', JSON.stringify(staleUser));
            // Default beforeEach mock: GET /api/session → authenticated: false

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user).toBeNull();
            expect(result.current.isAuthenticated).toBe(false);
            expect(localStorageMock.getItem('regengine_user')).toBeNull();
            expect(apiClient.setUser).toHaveBeenLastCalledWith(null);
        });

        it('does not re-persist a session user echoed back from a stale re_user cookie', async () => {
            localStorageMock.setItem('regengine_user', JSON.stringify(staleUser));

            // re_access_token expired but the non-httpOnly re_user cookie
            // survived — the route echoes it back with authenticated: false.
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
                            user: staleUser,
                        }),
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user).toBeNull();
            expect(localStorageMock.getItem('regengine_user')).toBeNull();
        });

        it('keeps the hydrated user when the session check fails with a network error', async () => {
            localStorageMock.setItem('regengine_user', JSON.stringify(staleUser));

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session') &&
                    (!options?.method || options.method === 'GET')) {
                    return Promise.reject(new Error('network down'));
                }
                return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user?.id).toBe('stale-user');
            expect(result.current.user?.email).toBe(staleUser.email);
            expect(apiClient.setUser).toHaveBeenLastCalledWith(expect.objectContaining({ email: staleUser.email }));
            expect(localStorageMock.getItem('regengine_user')).toBe(JSON.stringify({ ...staleUser, email: '' }));
            expect(window.sessionStorage.getItem('regengine_user')).toBeNull();
        });

        it('keeps the hydrated user when the session check returns a non-2xx response', async () => {
            localStorageMock.setItem('regengine_user', JSON.stringify(staleUser));

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session') &&
                    (!options?.method || options.method === 'GET')) {
                    return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({}) });
                }
                return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user?.id).toBe('stale-user');
            expect(result.current.user?.email).toBe(staleUser.email);
            expect(apiClient.setUser).toHaveBeenLastCalledWith(expect.objectContaining({ email: staleUser.email }));
            expect(localStorageMock.getItem('regengine_user')).toBe(JSON.stringify({ ...staleUser, email: '' }));
            expect(window.sessionStorage.getItem('regengine_user')).toBeNull();
        });

        it('does not replace a completed login with the redacted cache after migration awaits', async () => {
            const loginUser = {
                id: crypto.randomUUID(),
                email: `${crypto.randomUUID()}@example.test`,
                is_sysadmin: false,
                status: 'active',
            };
            localStorageMock.setItem('regengine_access_token', crypto.randomUUID());
            const defaultFetch = mockFetch.getMockImplementation()!;
            let resolveMigration: ((value: { ok: boolean }) => void) | undefined;
            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (options?.method === 'POST' && !resolveMigration) {
                    return new Promise((resolve) => { resolveMigration = resolve; });
                }
                return defaultFetch(url, options);
            });
            const { result } = renderHook(() => useAuth(), { wrapper });
            await waitFor(() => expect(resolveMigration).toBeDefined());

            await act(async () => {
                await result.current.login(crypto.randomUUID(), loginUser);
                resolveMigration!({ ok: true });
            });
            await waitFor(() => expect(result.current.isHydrated).toBe(true));

            expect(result.current.user).toEqual(loginUser);
            expect(apiClient.setUser).toHaveBeenLastCalledWith(loginUser);
            expect(JSON.parse(localStorageMock.getItem('regengine_user')!)).toEqual({ ...loginUser, email: '' });
            expect(window.sessionStorage.getItem('regengine_user')).toBeNull();
        });

        it('does not wipe a login that completed while the hydrate session check was in flight', async () => {
            const mockUser = {
                id: 'fresh-user',
                email: 'fresh@example.com',
                is_sysadmin: false,
                status: 'active',
                role_name: 'member',
            };

            // Pre-seed the CSRF cookie so login()'s setSessionCookies skips
            // its bootstrap GET — the only GET is then the hydrate session
            // check, which the test holds open below.
            document.cookie = 're_csrf=test-token';

            type GetResponse = { ok: boolean; json: () => Promise<unknown> };
            let resolveGet: ((value: GetResponse) => void) | undefined;

            mockFetch.mockImplementation((url: string, options?: RequestInit) => {
                if (typeof url === 'string' && url.includes('/api/session')) {
                    if (options?.method === 'POST' || options?.method === 'DELETE') {
                        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
                    }
                    // Hold the hydrate GET until the test resolves it
                    return new Promise<GetResponse>((resolve) => {
                        resolveGet = resolve;
                    });
                }
                return Promise.reject(new Error(`Unmocked fetch: ${url}`));
            });

            const { result } = renderHook(() => useAuth(), { wrapper });

            // Magic-link style auto-login completes while GET is pending
            await act(async () => {
                await result.current.login('fresh-token', mockUser as any, 'tenant-123');
            });

            expect(result.current.user?.id).toBe('fresh-user');

            // Now the stale GET resolves with "unauthenticated" — it must not
            // clobber the session login() just established.
            if (!resolveGet) {
                throw new Error('Expected deferred session GET resolver to be set');
            }
            await act(async () => {
                resolveGet!({
                    ok: true,
                    json: () => Promise.resolve({
                        authenticated: false,
                        has_api_key: false,
                        has_credentials: false,
                        tenant_id: null,
                        user: null,
                    }),
                });
            });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user?.id).toBe('fresh-user');
            expect(localStorageMock.getItem('regengine_user')).toBe(JSON.stringify({ ...mockUser, email: '' }));
            expect(result.current.user?.email).toBe(mockUser.email);
            expect(apiClient.setUser).toHaveBeenLastCalledWith(expect.objectContaining({ email: mockUser.email }));

            document.cookie = 're_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
        });
    });

    describe('Error Handling', () => {
        it('handles corrupted localStorage data gracefully', async () => {
            localStorageMock.setItem('regengine_user', 'invalid-json');

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            // Should handle error and continue with null user
            expect(result.current.user).toBeNull();
        });

        it('handles missing localStorage gracefully', () => {
            // Should not throw errors if localStorage is unavailable
            const { result } = renderHook(() => useAuth(), { wrapper });

            expect(result.current.user).toBeNull();
        });
    });
});
