import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ApiKeysPage from '@/app/developer/portal/keys/page';
import DeveloperPortalDashboard from '@/app/developer/portal/page';
import UsagePage from '@/app/developer/portal/usage/page';

const mocks = vi.hoisted(() => ({
    fetchWithCsrf: vi.fn(),
    // Stable identities: the pages key their load effects off the auth user, so a
    // fresh object per render would re-fire the effect forever.
    authValue: {
        user: { id: 'dev-1', email: 'dev@example.com' },
        isAuthenticated: true,
        isHydrated: true,
        logout: () => Promise.resolve(),
    },
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: mocks.fetchWithCsrf,
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mocks.authValue,
}));

function jsonResponse(body: unknown, ok = true) {
    return { ok, status: ok ? 200 : 500, json: async () => body } as Response;
}

describe('developer portal click behavior', () => {
    beforeEach(() => {
        mocks.fetchWithCsrf.mockReset();
        vi.stubGlobal('fetch', vi.fn());
    });

    it('keeps the range toggle mounted while a usage range switch is in flight', async () => {
        const user = userEvent.setup();
        let resolveSecond: ((value: Response) => void) | undefined;

        vi.mocked(global.fetch)
            .mockResolvedValueOnce(jsonResponse({ usage: [] }))
            .mockImplementationOnce(() => new Promise<Response>(resolve => { resolveSecond = resolve; }));

        render(<UsagePage />);

        const rangeButton = await screen.findByRole('button', { name: '30d' });
        await user.click(rangeButton);

        // The page must not be replaced by a full-page spinner — the control the user
        // just clicked, and the heading, both stay on screen while data reloads.
        expect(screen.getByRole('button', { name: '30d' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { name: /api usage/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: '30d' })).toHaveAttribute('aria-pressed', 'true');

        resolveSecond?.(jsonResponse({ usage: [] }));
        await waitFor(() => expect(screen.getByRole('button', { name: '30d' })).toBeInTheDocument());
    });

    it('surfaces an error when key creation fails instead of silently doing nothing', async () => {
        const user = userEvent.setup();
        vi.mocked(global.fetch).mockResolvedValue(jsonResponse({ developerId: 'dev-1', keys: [] }));
        mocks.fetchWithCsrf.mockResolvedValue(jsonResponse({}, false));

        render(<ApiKeysPage />);

        await user.click(await screen.findByRole('button', { name: /new key/i }));
        await user.type(screen.getByPlaceholderText(/local testing/i), 'CI key');
        await user.click(screen.getByRole('button', { name: /generate/i }));

        expect(await screen.findByRole('alert')).toHaveTextContent(/key creation failed/i);
    });

    it('does not fire a second revoke while one is already in flight', async () => {
        const user = userEvent.setup();
        vi.mocked(global.fetch).mockResolvedValue(jsonResponse({
            developerId: 'dev-1',
            keys: [{
                id: 'key-1',
                name: 'Local testing',
                key_prefix: 'rge_test_ab',
                enabled: true,
                total_requests: 0,
                created_at: '2026-01-01T00:00:00Z',
                last_used_at: null,
                revoked_at: null,
            }],
        }));
        mocks.fetchWithCsrf.mockImplementation(() => new Promise(() => {}));

        render(<ApiKeysPage />);

        const revoke = await screen.findByRole('button', { name: /revoke local testing/i });
        await user.click(revoke);
        await waitFor(() => expect(revoke).toBeDisabled());
        await user.click(revoke);

        expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(1);
    });

    it('settles into a sign-in prompt instead of hanging when no auth user hydrates', async () => {
        // A stale re_access_token cookie passes the server layout's presence
        // check while the client auth context hydrates no user. The pages must
        // settle into an honest signed-out state — not spin forever, and not
        // render a fabricated zero-state dashboard.
        const savedUser = mocks.authValue.user;
        mocks.authValue.user = null as unknown as typeof savedUser;
        try {
            const dashboard = render(<DeveloperPortalDashboard />);
            expect(await screen.findByRole('heading', { name: /session has expired/i })).toBeInTheDocument();
            expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login?next=/developer/portal');
            expect(screen.queryByRole('heading', { name: /welcome back/i })).not.toBeInTheDocument();
            expect(global.fetch).not.toHaveBeenCalled();
            dashboard.unmount();

            render(<ApiKeysPage />);
            expect(await screen.findByRole('heading', { name: /session has expired/i })).toBeInTheDocument();
            expect(global.fetch).not.toHaveBeenCalled();
        } finally {
            mocks.authValue.user = savedUser;
        }
    });

    it('renders the already-completed onboarding step as text, not a "#" link', async () => {
        vi.mocked(global.fetch).mockResolvedValue(jsonResponse({
            profile: { id: 'dev-1', email: 'dev@example.com', display_name: 'Dev', company_name: null, created_at: '2026-01-01T00:00:00Z' },
            stats: { totalKeys: 0, activeKeys: 0, totalRequests: 0 },
        }));

        render(<DeveloperPortalDashboard />);

        expect(await screen.findByText('Create your account')).toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /create your account/i })).not.toBeInTheDocument();
        for (const link of screen.getAllByRole('link')) {
            expect(link.getAttribute('href')).not.toBe('#');
        }
    });
});
