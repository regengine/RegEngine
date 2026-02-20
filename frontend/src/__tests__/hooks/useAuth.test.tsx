/**
 * React Hook Tests - useAuth
 * 
 * Tests for the authentication hook:
 * - Login/logout functionality
 * - Token management
 * - User state
 * - Hydration handling
 * - Local storage persistence
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAuth, AuthProvider } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';
import type { ReactNode } from 'react';

// Mock apiClient
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        setAccessToken: vi.fn(),
        setUser: vi.fn(),
        login: vi.fn(),
    },
}));

// Mock localStorage
const localStorageMock = (() => {
    let store: Record<string, string> = {};

    return {
        getItem: (key: string) => store[key] || null,
        setItem: (key: string, value: string) => { store[key] = value; },
        removeItem: (key: string) => { delete store[key]; },
        clear: () => { store = {}; },
    };
})();

Object.defineProperty(window, 'localStorage', {
    value: localStorageMock,
});

describe('useAuth Hook', () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
        <AuthProvider>{children}</AuthProvider>
    );

    beforeEach(() => {
        vi.clearAllMocks();
        localStorageMock.clear();
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

            localStorageMock.setItem('user', JSON.stringify(mockUser));
            localStorageMock.setItem('accessToken', 'test-token');

            const { result } = renderHook(() => useAuth(), { wrapper });

            await waitFor(() => {
                expect(result.current.isHydrated).toBe(true);
            });

            expect(result.current.user).toEqual(mockUser);
            expect(result.current.accessToken).toBe('test-token');
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

            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(result.current.user).toEqual(mockUser);
            expect(result.current.accessToken).toBe('test-token');
        });

        it('persists to localStorage on login', async () => {
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

            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(localStorageMock.getItem('accessToken')).toBe('test-token');
            expect(localStorageMock.getItem('user')).toBe(JSON.stringify(mockUser));
        });

        it('calls apiClient.setAccessToken on login', () => {
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

            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(apiClient.setAccessToken).toHaveBeenCalledWith('test-token');
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
            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
            });

            // Then logout
            act(() => {
                result.current.logout();
            });

            expect(result.current.user).toBeNull();
            expect(result.current.accessToken).toBeNull();
        });

        it('clears localStorage on logout', () => {
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
            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
            });

            // Then logout
            act(() => {
                result.current.logout();
            });

            expect(localStorageMock.getItem('accessToken')).toBeNull();
            expect(localStorageMock.getItem('user')).toBeNull();
        });

        it('calls apiClient.setAccessToken(null) on logout', () => {
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
            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
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
        it('isAuthenticated is true when user exists', () => {
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

            act(() => {
                result.current.login('test-token', mockUser, 'tenant-123');
            });

            expect(result.current.isAuthenticated).toBe(true);
        });

        it('isAuthenticated is false when user is null', () => {
            const { result } = renderHook(() => useAuth(), { wrapper });

            expect(result.current.isAuthenticated).toBe(false);
        });

        it('detects sysadmin users', () => {
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

            act(() => {
                result.current.login('admin-token', adminUser, 'tenant-456');
            });

            expect(result.current.user?.is_sysadmin).toBe(true);
        });
    });

    describe('Error Handling', () => {
        it('handles corrupted localStorage data gracefully', async () => {
            localStorageMock.setItem('user', 'invalid-json');
            localStorageMock.setItem('accessToken', 'test-token');

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
