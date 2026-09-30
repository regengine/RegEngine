import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { StepUpModal } from '@/components/auth/StepUpModal';
import ApiKeysPage from '@/app/developer/portal/keys/page';
import DeveloperPortalDashboard from '@/app/developer/portal/page';
import UsagePage from '@/app/developer/portal/usage/page';

const mocks = vi.hoisted(() => ({
    fetchWithCsrf: vi.fn(),
    performPasskeyLogin: vi.fn(),
    // Stable identities: the pages key their load effects off the auth user, so a
    // fresh object per render would re-fire the effect forever.
    authValue: {
        user: { id: 'dev-1', email: 'dev@example.com' },
        isAuthenticated: true,
        isHydrated: true,
        logout: () => Promise.resolve(),
    },
}));

vi.mock('@/lib/passwordless-auth', () => ({
    isValidEmail: () => true,
    performPasskeyLogin: mocks.performPasskeyLogin,
    seedPasswordlessClientUser: vi.fn(),
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
        mocks.performPasskeyLogin.mockReset();
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

        expect(await screen.findByRole('alert')).toHaveTextContent(/key creation could not be confirmed/i);
    });


    it('blocks duplicate submissions, including Enter, until the request settles', async () => {
        const user = userEvent.setup();
        vi.mocked(global.fetch).mockResolvedValue(jsonResponse({ developerId: 'dev-1', keys: [] }));
        let resolve: ((response: Response) => void) | undefined;
        mocks.fetchWithCsrf.mockImplementation(() => new Promise<Response>(done => { resolve = done; }));
        render(<ApiKeysPage />);
        await user.click(await screen.findByRole('button', { name: /new key/i }));
        const input = screen.getByPlaceholderText(/local testing/i);
        await user.type(input, 'CI key');
        const generate = screen.getByRole('button', { name: /^generate$/i });
        act(() => {
            fireEvent.click(generate);
            fireEvent.click(generate);
            fireEvent.keyDown(input, { key: 'Enter' });
            fireEvent.keyDown(input, { key: 'Enter' });
        });
        expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(1);
        await act(async () => resolve?.(jsonResponse({ rawKey: 'synthetic-test-value', keys: [] })));
        expect(screen.getByText('synthetic-test-value')).toBeInTheDocument();
    });

    it('recovers uncertain creation with a read-only refresh and blocks retry until it succeeds', async () => {
        const user = userEvent.setup();
        vi.mocked(global.fetch)
            .mockResolvedValueOnce(jsonResponse({ developerId: 'dev-1', keys: [] }))
            .mockResolvedValueOnce(jsonResponse({}, false))
            .mockResolvedValueOnce(jsonResponse({ developerId: 'dev-1', keys: [] }));
        mocks.fetchWithCsrf.mockRejectedValue(new Error('Connection lost'));
        render(<ApiKeysPage />);
        await user.click(await screen.findByRole('button', { name: /new key/i }));
        await user.type(screen.getByPlaceholderText(/local testing/i), 'CI key');
        await user.click(screen.getByRole('button', { name: /^generate$/i }));
        expect(await screen.findByRole('alert')).toHaveTextContent(/could not be confirmed/i);
        expect(screen.getByRole('button', { name: /^generate$/i })).toBeDisabled();
        await user.click(screen.getByRole('button', { name: /refresh key list/i }));
        expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i);
        expect(screen.getByRole('button', { name: /^generate$/i })).toBeDisabled();
        await user.click(screen.getByRole('button', { name: /refresh key list/i }));
        await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
        expect(screen.getByRole('button', { name: /^generate$/i })).toBeEnabled();
        expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(1);
        expect(global.fetch).toHaveBeenCalledTimes(3);
    });

    it('preserves the revealed key and existing rows when the post-create metadata read fails', async () => {
        const user = userEvent.setup();
        vi.mocked(global.fetch).mockResolvedValue(jsonResponse({ developerId: 'dev-1', keys: [{
            id: 'old', name: 'Existing key', key_prefix: 'prefix', enabled: false, total_requests: 0,
            created_at: '', last_used_at: null, revoked_at: null,
        }] }));
        mocks.fetchWithCsrf.mockResolvedValue(jsonResponse({ rawKey: 'synthetic-test-value', keysRefreshFailed: true }));
        render(<ApiKeysPage />);
        await user.click(await screen.findByRole('button', { name: /new key/i }));
        await user.type(screen.getByPlaceholderText(/local testing/i), 'CI key');
        await user.click(screen.getByRole('button', { name: /^generate$/i }));
        expect(await screen.findByText('synthetic-test-value')).toBeInTheDocument();
        expect(screen.getByText('Existing key')).toBeInTheDocument();
        expect(screen.getByRole('alert')).toHaveTextContent(/your key was created/i);
        await user.click(screen.getByRole('button', { name: /refresh key list/i }));
        await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
        expect(screen.getByText('synthetic-test-value')).toBeInTheDocument();
        expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(1);
    });

    it.each(['canceled', 'failed'])('settles after step-up is %s without automatically retrying creation', async (outcome) => {
        const user = userEvent.setup();
        vi.mocked(global.fetch).mockResolvedValue(jsonResponse({ developerId: 'dev-1', keys: [] }));
        mocks.fetchWithCsrf.mockResolvedValue(jsonResponse({ detail: { code: 'requires_step_up' } }, false));
        mocks.performPasskeyLogin.mockRejectedValue(new Error('Passkey verification failed'));
        // Modal cancellation/failure cannot resume this mutation: only another
        // explicit Generate click starts a request. Modal internals are tested separately.
        const listener = vi.fn();
        window.addEventListener('regengine:requires-step-up', listener);
        try {
            render(<><ApiKeysPage /><StepUpModal /></>);
            await user.click(await screen.findByRole('button', { name: /new key/i }));
            await user.type(screen.getByPlaceholderText(/local testing/i), 'CI key');
            await user.click(screen.getByRole('button', { name: /^generate$/i }));
            expect(await screen.findByRole('dialog')).toBeInTheDocument();
            if (outcome === 'canceled') {
                await user.keyboard('{Escape}');
            } else {
                await user.click(screen.getByRole('button', { name: /authenticate with passkey/i }));
                expect(await screen.findByText('Passkey verification failed')).toBeInTheDocument();
                await user.keyboard('{Escape}');
            }
            expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
            expect(screen.getByRole('alert')).toHaveTextContent(/authenticate with your passkey/i);
            expect(listener).toHaveBeenCalledTimes(1);
            expect(screen.getByRole('button', { name: /^generate$/i })).toBeEnabled();
            expect(screen.getByPlaceholderText(/local testing/i)).toHaveValue('CI key');
            expect(mocks.fetchWithCsrf).toHaveBeenCalledTimes(1);
        } finally {
            window.removeEventListener('regengine:requires-step-up', listener);
        }
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
