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
                        has_admin_key: false,
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

        it('hydrates from localStorage on mount', async () => {
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
                            has_admin_key: false,
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

        it('persists user to localStorage on login', async () => {
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

            // User profile is still stored in localStorage (non-sensitive)
            expect(localStorageMock.getItem('regengine_user')).toBe(JSON.stringify(mockUser));
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
        });

        it('does not replace the RegEngine JWT cookie with Supabase tokens', async () => {
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

            const supabaseUser = {
                id: 'supabase-user',
                email: 'test@example.com',
                user_metadata: {
                    tenant_id: 'tenant-123',
                    role: 'member',
                    is_sysadmin: false,
                },
            };
            let authStateCallback:
                | ((event: string, session: { access_token: string; user: typeof supabaseUser }) => Promise<void>)
                | undefined;
            const supabaseAuth = {
                getUser: vi.fn().mockResolvedValue({ data: { user: null } }),
                getSession: vi.fn().mockResolvedValue({
                    data: {
                        session: {
                            access_token: 'supabase-session-token',
                            user: supabaseUser,
                        },
                    },
                }),
                onAuthStateChange: vi.fn((callback) => {
                    authStateCallback = callback;
                    return { data: { subscription: { unsubscribe: vi.fn() } } };
                }),
                signOut: vi.fn(),
            };
            (createSupabaseBrowserClient as any).mockReturnValue({ auth: supabaseAuth });

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => expect(result.current.isHydrated).toBe(true));

            await act(async () => {
                await result.current.login('regengine-jwt', mockUser, 'tenant-123');
            });

            await waitFor(() => expect(supabaseAuth.getSession).toHaveBeenCalled());

            await act(async () => {
                await authStateCallback?.('TOKEN_REFRESHED', {
                    access_token: 'supabase-refresh-token',
                    user: supabaseUser,
                });
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
            expect(sessionPostBodies.some((body) => body.access_token === 'supabase-session-token')).toBe(false);
            expect(sessionPostBodies.some((body) => body.access_token === 'supabase-refresh-token')).toBe(false);
            expect(sessionPostBodies.some((body) => body.access_token === 'cookie-managed')).toBe(false);
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
            act(() => {
                result.current.logout();
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
            act(() => {
                result.current.logout();
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
            act(() => {
                result.current.logout();
            });

            expect(apiClient.setAccessToken).toHaveBeenCalledWith(null);
            expect(apiClient.setUser).toHaveBeenCalledWith(null);
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
        });

        it('isAuthenticated is false when user is null', () => {
            const { result } = renderHook(() => useAuth(), { wrapper });

            expect(result.current.isAuthenticated).toBe(false);
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
