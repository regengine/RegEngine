/**
 * The developer portal gate is the real session (useAuth via DashboardLayout),
 * the same signal /login uses to decide whether to forward a visitor on. The
 * old layout asked Supabase getUser() instead, which never saw an email-code
 * session: /login forwarded an authenticated user to the portal, the portal
 * sent them straight back to /login, and the loop never ended.
 *
 * This file deliberately imports nothing from '@/lib/supabase'. The real
 * DashboardLayout is rendered; only its data hooks are mocked.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import DeveloperPortalLayout from '@/app/developer/portal/layout';

vi.mock('@/hooks/use-api', () => ({
    useSystemStatus: () => ({ data: { overall_status: 'healthy' }, isLoading: false, dataUpdatedAt: 0 }),
}));

vi.mock('next/navigation', () => ({
    usePathname: vi.fn(),
    useRouter: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

vi.mock('@/components/dashboard/breadcrumb', () => ({
    DashboardBreadcrumb: () => <nav aria-label="Breadcrumb" />,
}));

vi.mock('@/components/dashboard/error-boundary', () => ({
    DashboardErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

type AuthState = { isAuthenticated: boolean; isHydrated: boolean };

function setAuth({ isAuthenticated, isHydrated }: AuthState) {
    vi.mocked(useAuth).mockReturnValue({
        clearCredentials: vi.fn(),
        demoMode: false,
        isAuthenticated,
        isHydrated,
        logout: vi.fn(),
        user: isAuthenticated ? { id: 'u1', email: 'dev@example.com', is_sysadmin: false, status: 'active' } : null,
    } as unknown as ReturnType<typeof useAuth>);
}

function renderPortal() {
    return render(
        <DeveloperPortalLayout>
            <div>Portal content</div>
        </DeveloperPortalLayout>,
    );
}

describe('DeveloperPortalLayout', () => {
    const push = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        vi.mocked(useRouter).mockReturnValue({ push, replace: vi.fn() } as unknown as ReturnType<typeof useRouter>);
        vi.mocked(usePathname).mockReturnValue('/developer/portal');
        const store: Record<string, string> = {};
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => store[key] ?? null),
            setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
            removeItem: vi.fn((key: string) => { delete store[key]; }),
            clear: vi.fn(),
            length: 0,
            key: vi.fn(() => null),
        });
    });

    it('renders the portal for an authenticated session', () => {
        setAuth({ isAuthenticated: true, isHydrated: true });

        renderPortal();

        expect(screen.getByText('Portal content')).toBeInTheDocument();
        expect(push).not.toHaveBeenCalled();
    });

    it('sends a hydrated, unauthenticated visitor to /login with an encoded next and renders no children', () => {
        setAuth({ isAuthenticated: false, isHydrated: true });

        renderPortal();

        expect(push).toHaveBeenCalledTimes(1);
        expect(push).toHaveBeenCalledWith('/login?next=%2Fdeveloper%2Fportal');
        expect(screen.queryByText('Portal content')).not.toBeInTheDocument();
    });

    it('carries the sub-path in next for a signed-out visit to a portal sub-page', () => {
        vi.mocked(usePathname).mockReturnValue('/developer/portal/keys');
        setAuth({ isAuthenticated: false, isHydrated: true });

        renderPortal();

        expect(push).toHaveBeenCalledWith('/login?next=%2Fdeveloper%2Fportal%2Fkeys');
        expect(screen.queryByText('Portal content')).not.toBeInTheDocument();
    });

    it('waits for hydration: no redirect and no children before the session is known', () => {
        setAuth({ isAuthenticated: false, isHydrated: false });

        renderPortal();

        expect(push).not.toHaveBeenCalled();
        expect(screen.queryByText('Portal content')).not.toBeInTheDocument();
    });
});
