import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import VerifyClient from '@/app/auth/verify/VerifyClient';
import LoginPage from '@/app/login/page';

const mocks = vi.hoisted(() => ({
  routerPush: vi.fn(),
  routerRefresh: vi.fn(),
  searchParamGet: vi.fn(),
  startEmailChallenge: vi.fn(),
  saveOtpChallengeState: vi.fn(),
  performPasskeyLogin: vi.fn(),
  seedPasswordlessClientUser: vi.fn(),
  verifyEmailChallenge: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: mocks.routerPush,
    refresh: mocks.routerRefresh,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => ({
    get: mocks.searchParamGet,
  }),
}));

const authState = vi.hoisted(() => ({
  user: null as { id: string; email: string } | null,
  isAuthenticated: false,
  isHydrated: true,
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => authState,
}));

vi.mock('@/lib/passwordless-auth', () => ({
  isValidEmail: (value: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()),
  startEmailChallenge: mocks.startEmailChallenge,
  saveOtpChallengeState: mocks.saveOtpChallengeState,
  performPasskeyLogin: mocks.performPasskeyLogin,
  seedPasswordlessClientUser: mocks.seedPasswordlessClientUser,
  verifyEmailChallenge: mocks.verifyEmailChallenge,
  clearOtpChallengeState: vi.fn(),
  loadOtpChallengeState: vi.fn(() => null),
}));

function mockLocationAssign() {
  const originalLocation = window.location;
  const assign = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      ...originalLocation,
      assign,
    },
  });
  return assign;
}

describe('passwordless login', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = null;
    authState.isAuthenticated = false;
    authState.isHydrated = true;
    mocks.searchParamGet.mockReturnValue(null);
    mocks.startEmailChallenge.mockResolvedValue({
      detail: 'If this address is eligible, a sign-in code is on its way.',
      challenge_id: '11111111-1111-4111-8111-111111111111',
    });
    mocks.performPasskeyLogin.mockResolvedValue(undefined);
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  it('does not auto-forward on stale localStorage user without a cookie session (redirect loop regression)', () => {
    // A user object hydrated from localStorage can outlive the re_access_token
    // cookie. Auto-forwarding to ?next= in that state ping-pongs with the
    // server-side auth gate on the target page (login -> portal -> login ...).
    authState.user = { id: 'stale', email: 'stale@example.com' };
    authState.isAuthenticated = false;
    mocks.searchParamGet.mockImplementation((key: string) =>
      key === 'next' ? '/developer/portal' : null,
    );

    render(<LoginPage />);

    expect(mocks.routerPush).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
  });

  it('auto-forwards to the next path when the cookie session is authenticated', async () => {
    authState.user = { id: 'live', email: 'live@example.com' };
    authState.isAuthenticated = true;
    mocks.searchParamGet.mockImplementation((key: string) =>
      key === 'next' ? '/developer/portal' : null,
    );

    render(<LoginPage />);

    await waitFor(() => {
      expect(mocks.routerPush).toHaveBeenCalledWith('/developer/portal');
    });
  });

  // A `next` that is not a plain same-app path must never reach router.push:
  // an authenticated visitor following /login?next=<hostile> is forwarded
  // straight to it. '/<TAB>/evil.com' is the live bypass the old inline
  // validator accepted (browsers strip the TAB and read '//evil.com').
  const HOSTILE_NEXT: [string, string][] = [
    ['protocol-relative', '//evil.com'],
    ['TAB between slashes', '/\t/evil.com'],
    ['LF between slashes', '/\n/evil.com'],
    ['CR between slashes', '/\r/evil.com'],
    ['backslash host', '/\\evil.com'],
    ['dot-segment collapses to //', '/.//evil.com'],
    ['dot-dot-segment collapses to //', '/..//evil.com'],
    ['nested dot-dot collapses to //', '/x/..//evil.com'],
    ['encoded dot-dot collapses to //', '/%2e%2e//evil.com'],
    ['leading space', ' //evil.com'],
    ['absolute URL', 'https://evil.com'],
    ['javascript scheme', 'javascript:alert(1)'],
    ['the login page itself', '/login'],
    ['the verify page', '/auth/verify'],
  ];

  it.each(HOSTILE_NEXT)(
    'forwards an authenticated user to /dashboard, not the hostile next (%s)',
    async (_label, hostile) => {
      authState.user = { id: 'live', email: 'live@example.com' };
      authState.isAuthenticated = true;
      mocks.searchParamGet.mockImplementation((key: string) => (key === 'next' ? hostile : null));

      render(<LoginPage />);

      await waitFor(() => {
        expect(mocks.routerPush).toHaveBeenCalledWith('/dashboard');
      });
      expect(mocks.routerPush).not.toHaveBeenCalledWith(hostile);
      expect(mocks.routerPush).toHaveBeenCalledTimes(1);
    },
  );

  it.each([
    ['/developer/portal'],
    ['/developer/portal/keys'],
    ['/dashboard/settings?tab=api#keys'],
  ])('forwards an authenticated user to the validated next %s unchanged', async (valid) => {
    authState.user = { id: 'live', email: 'live@example.com' };
    authState.isAuthenticated = true;
    mocks.searchParamGet.mockImplementation((key: string) => (key === 'next' ? valid : null));

    render(<LoginPage />);

    await waitFor(() => {
      expect(mocks.routerPush).toHaveBeenCalledWith(valid);
    });
    expect(mocks.routerPush).toHaveBeenCalledTimes(1);
  });

  it('does not navigate an unauthenticated visitor, whatever next says', () => {
    mocks.searchParamGet.mockImplementation((key: string) =>
      key === 'next' ? '/\t/evil.com' : null,
    );

    render(<LoginPage />);

    expect(mocks.routerPush).not.toHaveBeenCalled();
  });

  it('sends a passkey sign-in to /dashboard when next is hostile', async () => {
    const assign = mockLocationAssign();
    mocks.searchParamGet.mockImplementation((key: string) =>
      key === 'next' ? '/\t/evil.com' : null,
    );
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /sign in with passkey/i }));
    await user.type(screen.getByLabelText(/passkey email/i), 'passkey@example.com');
    const passkeyButtons = screen.getAllByRole('button', { name: /sign in with passkey/i });
    await user.click(passkeyButtons[passkeyButtons.length - 1]);

    await waitFor(() => {
      expect(mocks.performPasskeyLogin).toHaveBeenCalledWith('passkey@example.com');
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
    expect(assign).not.toHaveBeenCalledWith('/\t/evil.com');
  });

  it('renders a single email entry point with passkey sign-in and no password field', () => {
    render(<LoginPage />);

    expect(screen.getByRole('heading', { name: /continue to regengine/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^continue/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in with passkey/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/^password$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /create an account/i })).not.toBeInTheDocument();
  });

  it('starts an OTP challenge and routes to the verification screen', async () => {
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'User@Example.com');
    await user.click(screen.getByRole('button', { name: /^continue/i }));

    await waitFor(() => {
      expect(mocks.startEmailChallenge).toHaveBeenCalledWith('user@example.com');
      expect(mocks.saveOtpChallengeState).toHaveBeenCalledWith({
        email: 'user@example.com',
        challengeId: '11111111-1111-4111-8111-111111111111',
        createdAt: expect.any(Number),
      });
      expect(mocks.routerPush).toHaveBeenCalledWith('/auth/verify');
    });
  });

  it('does not honor identity-revealing redirect fields in a challenge response', async () => {
    const assign = mockLocationAssign();
    mocks.startEmailChallenge.mockResolvedValueOnce({
      detail: 'If this address is eligible, a sign-in code is on its way.',
      challenge_id: '11111111-1111-4111-8111-111111111111',
      sso_redirect: true,
      organization_id: 'org-123',
    });
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.type(screen.getByLabelText(/email address/i), 'person@sso.example');
    await user.click(screen.getByRole('button', { name: /^continue/i }));

    await waitFor(() => {
      expect(assign).not.toHaveBeenCalled();
      expect(mocks.saveOtpChallengeState).toHaveBeenCalledWith({
        email: 'person@sso.example',
        challengeId: '11111111-1111-4111-8111-111111111111',
        createdAt: expect.any(Number),
      });
      expect(mocks.routerPush).toHaveBeenCalledWith('/auth/verify');
    });
  });

  it('prompts for email and starts passkey login', async () => {
    const assign = mockLocationAssign();
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByRole('button', { name: /sign in with passkey/i }));
    await user.type(screen.getByLabelText(/passkey email/i), 'passkey@example.com');
    const passkeyButtons = screen.getAllByRole('button', { name: /sign in with passkey/i });
    await user.click(passkeyButtons[passkeyButtons.length - 1]);

    await waitFor(() => {
      expect(mocks.performPasskeyLogin).toHaveBeenCalledWith('passkey@example.com');
      expect(mocks.seedPasswordlessClientUser).toHaveBeenCalledWith('passkey@example.com');
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
  });
});

describe('OTP verification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.verifyEmailChallenge.mockResolvedValue(undefined);
  });

  it('rejects malformed codes before calling the API', async () => {
    const user = userEvent.setup();
    render(
      <VerifyClient
        initialEmail="user@example.com"
        initialChallengeId="11111111-1111-4111-8111-111111111111"
      />,
    );

    await user.type(screen.getByLabelText(/verification code/i), '123');
    await user.click(screen.getByRole('button', { name: /verify and continue/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/6-digit code/i);
    expect(mocks.verifyEmailChallenge).not.toHaveBeenCalled();
  });

  it('verifies the OTP challenge and navigates to the dashboard', async () => {
    const assign = mockLocationAssign();
    const user = userEvent.setup();
    render(
      <VerifyClient
        initialEmail="user@example.com"
        initialChallengeId="11111111-1111-4111-8111-111111111111"
      />,
    );

    await user.type(screen.getByLabelText(/verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: /verify and continue/i }));

    await waitFor(() => {
      expect(mocks.verifyEmailChallenge).toHaveBeenCalledWith(
        '11111111-1111-4111-8111-111111111111',
        '123456',
      );
      expect(mocks.seedPasswordlessClientUser).toHaveBeenCalledWith('user@example.com');
      expect(assign).toHaveBeenCalledWith('/dashboard');
    });
  });

  it('shows inline errors for wrong or expired OTP codes', async () => {
    mocks.verifyEmailChallenge.mockRejectedValueOnce({ response: { status: 401 } });
    const user = userEvent.setup();
    render(
      <VerifyClient
        initialEmail="user@example.com"
        initialChallengeId="11111111-1111-4111-8111-111111111111"
      />,
    );

    await user.type(screen.getByLabelText(/verification code/i), '123456');
    await user.click(screen.getByRole('button', { name: /verify and continue/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/incorrect or expired/i);
  });
});
