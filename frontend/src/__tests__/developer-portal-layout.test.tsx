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
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import DeveloperPortalLayout from '@/app/developer/portal/layout';
import LoginPage from '@/app/login/page';

vi.mock('@/hooks/use-api', () => ({
    useSystemStatus: () => ({ data: { overall_status: 'healthy' }, isLoading: false, dataUpdatedAt: 0 }),
}));

vi.mock('next/navigation', () => ({
    usePathname: vi.fn(),
    useRouter: vi.fn(),
    useSearchParams: vi.fn(),
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

/**
 * Loop guard for ?next= (Phase 2). /login forwards an authenticated visitor to
 * `next`; the portal layout sends an unauthenticated one to /login?next=.
 * Both read the same useAuth() flag, so whatever the state, the pair settles:
 * one forward when signed in, no forward when signed out. Each test renders
 * /login and the portal against ONE shared router and ONE auth state, and
 * asserts every navigation either of them made.
 */
describe('login <-> developer portal loop guard', () => {
    const push = vi.fn();

    function setNext(next: string | null) {
        vi.mocked(useSearchParams).mockReturnValue({
            get: (key: string) => (key === 'next' ? next : null),
        } as unknown as ReturnType<typeof useSearchParams>);
    }

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

    it('signed in: /login?next=/developer/portal forwards once and the portal does not push back to /login', async () => {
        setAuth({ isAuthenticated: true, isHydrated: true });
        setNext('/developer/portal');

        const login = render(<LoginPage />);
        await waitFor(() => {
            expect(push).toHaveBeenCalledWith('/developer/portal');
        });
        login.unmount();

        renderPortal();

        expect(screen.getByText('Portal content')).toBeInTheDocument();
        // The whole round trip is the single forward: nothing went back to /login.
        expect(push.mock.calls).toEqual([['/developer/portal']]);
    });

    it('signed out: the portal sends the visitor to /login?next= and /login does not forward them back', () => {
        setAuth({ isAuthenticated: false, isHydrated: true });

        const portal = renderPortal();
        expect(push.mock.calls).toEqual([['/login?next=%2Fdeveloper%2Fportal']]);
        expect(screen.queryByText('Portal content')).not.toBeInTheDocument();
        portal.unmount();

        // The visitor lands on /login with that next. Still signed out, so
        // /login must stay put instead of forwarding to the portal again.
        setNext('/developer/portal');
        render(<LoginPage />);

        expect(push.mock.calls).toEqual([['/login?next=%2Fdeveloper%2Fportal']]);
        expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    });
});
